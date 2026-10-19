"""Ingest what public bodies publish outside meetings into the corpus.

Sources are entries in data/publication_sources.json (the entry format is in
vendors/adapters/custom/publications_adapter_async.py). Every listed document
takes the path a meeting attachment takes -- download, sha256, archive the
original to R2, extract text -- through AsyncAnalyzer.extract_document_async
with the LLM off, so document_source records it under the body's banana. The
listing's title and date land on the same document_source rows.

State lives in the corpus: a URL whose current revision has text is not
fetched again (its listing title and date are still refreshed), and failures
go through document_ingest_failure with bounded retries. Restart at will.

    uv run scripts/ingest_publications.py onboard                 # plan rows for new bodies
    uv run scripts/ingest_publications.py onboard --apply
    uv run scripts/ingest_publications.py list schools-nyc        # what the listings show
    uv run scripts/ingest_publications.py ingest --slug schools-nyc --limit 50
"""

import argparse
import asyncio
import sys
import time
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from analysis.analyzer_async import AsyncAnalyzer
from config import get_logger
from corpus.store import EXTRACT_VERSION, get_corpus
from database.db_postgres import Database
from database.models import Jurisdiction
from exceptions import DocumentDownloadError, ExtractionError
from pipeline.utils import attachment_identity
from scripts._jurisdiction_naming import make_banana
from scripts.backfill_corpus_attachments import (
    COMPATIBLE_EXTRACT_VERSIONS,
    CORPUS_READY_SQL,
    FAILURE_STATE_SQL,
    READY_IDENTITIES_SQL,
    is_memory_pressure,
)
from scripts.ingest_minutes import failure_attempt_limit, failure_error_text, record_failure, record_ingest_result
from vendors.adapters.custom.publications_adapter_async import AsyncPublicationsAdapter, Publication, load_sources
from vendors.session_manager_async import AsyncSessionManager

logger = get_logger(__name__).bind(component="ingest_publications")

# Rows created here have no meeting feed; sync skips a vendor with no adapter.
NO_MEETINGS = "none"


# ---------------------------------------------------------------------------
# onboard: one jurisdictions row per body, with its owner
# ---------------------------------------------------------------------------

async def ensure_body(db, meta: Dict[str, Any], slug: str, apply: bool) -> Optional[str]:
    """The banana for a registry jurisdiction block, creating its row (and
    its parent's, when the parent is itself a block) on --apply."""
    parent = meta.get("parent")
    parent_banana = await ensure_body(db, parent, NO_MEETINGS, apply) if isinstance(parent, dict) else parent
    if parent_banana and not isinstance(parent, dict) and not await db.jurisdictions.get_city(parent_banana):
        print(f"MISSING PARENT {parent_banana} for {meta['name']}; not adding")
        return None

    banana = make_banana(meta["name"], meta["state"], meta.get("vernacular"))
    existing = await db.jurisdictions.get_city(banana)
    # A parent block names a body, not a feed: an existing row by that banana
    # is that body. An entry's own row must be this source's row.
    if existing and slug != NO_MEETINGS and (existing.vendor, existing.slug) != (NO_MEETINGS, slug):
        print(f"COLLISION {banana} is {existing.vendor}/{existing.slug}; give this entry \"banana\" instead")
        return None
    if existing:
        print(f"have {banana:<32} {meta['name']}")
    else:
        print(f"{'add ' if apply else 'plan'} {banana:<32} {meta['type']:<20} {meta['name']}"
              + (f"  (parent {parent_banana})" if parent_banana else ""))
        if apply:
            await db.jurisdictions.add_city(Jurisdiction(
                banana=banana, name=meta["name"], state=meta["state"], vendor=NO_MEETINGS,
                slug=slug, type=meta["type"], status="active"))
    if parent_banana and apply and await db.jurisdictions.set_parent(banana, parent_banana):
        print(f"     {banana} -> parent {parent_banana}")
    return banana


async def onboard(db, apply: bool) -> int:
    for slug, entry in load_sources().items():
        if entry.get("banana"):
            if not await db.jurisdictions.get_city(entry["banana"]):
                print(f"MISSING {entry['banana']} named by {slug}")
            continue
        if not entry.get("jurisdiction"):
            print(f"skip {slug}: neither banana nor jurisdiction block")
            continue
        await ensure_body(db, entry["jurisdiction"], slug, apply)
    return 0


async def resolve_banana(db, slug: str, entry: Dict[str, Any]) -> Optional[str]:
    if entry.get("banana"):
        return entry["banana"]
    async with db.pool.acquire() as conn:
        return await conn.fetchval(
            "SELECT banana FROM jurisdictions WHERE vendor = $1 AND slug = $2", NO_MEETINGS, slug)


# ---------------------------------------------------------------------------
# ingest
# ---------------------------------------------------------------------------

async def ingest_one(db, analyzer: AsyncAnalyzer, banana: str, publication: Publication, args,
                     counts: Dict[str, int]) -> None:
    url = publication.url
    identity = attachment_identity(url)
    started = time.monotonic()
    try:
        result = await analyzer.extract_document_async(url, banana=banana, retry_incomplete=True)
        content_sha256 = result.get("content_sha256")
        async with db.pool.acquire() as conn:
            ready = bool(content_sha256 and result.get("corpus_persisted") and await conn.fetchval(
                CORPUS_READY_SQL, content_sha256, COMPATIBLE_EXTRACT_VERSIONS))
        if not ready:
            counts["failed_persist"] += 1
            logger.warning("publication not durably persisted", banana=banana, url=identity[:110])
            return
        await record_ingest_result(db, result, identity, url, banana)
        counts["ingested"] += 1
        logger.info("publication ingested", banana=banana, url=identity[:110],
                    chars=len(result.get("text") or ""), from_corpus=bool(result.get("from_corpus")),
                    duration_ms=int((time.monotonic() - started) * 1000))
    except DocumentDownloadError as e:
        counts["failed_download"] += 1
        await record_failure(db, identity=identity, source_url=url, banana=banana, stage="download", error=e,
                             max_failures=failure_attempt_limit(e, args.max_failures),
                             retry_days=args.failure_retry_days)
        logger.warning("publication download failed", banana=banana, url=identity[:110],
                       error=failure_error_text(e, url)[:200])
    except ExtractionError as e:
        if is_memory_pressure(e):
            # The box was busy, not the document bad: spend none of its retries.
            counts["deferred_memory"] += 1
            logger.info("publication deferred: memory pressure", banana=banana, url=identity[:110])
            return
        counts["failed_extract"] += 1
        await record_failure(db, identity=identity, source_url=url, banana=banana, stage="extract", error=e,
                             max_failures=args.max_failures, retry_days=args.failure_retry_days)
        logger.warning("publication extraction failed", banana=banana, url=identity[:110],
                       error=failure_error_text(e, url)[:200])
    except Exception as e:
        counts["failed_other"] += 1
        logger.warning("publication ingest failed (will retry)", banana=banana, url=identity[:110],
                       error=failure_error_text(e, url)[:200])
    finally:
        # Archived bytes whose text failed are still this listing's document.
        await db.document_blobs.record_listing(identity, publication.title, publication.published_on)


async def pending(db, publications: List[Publication], counts: Dict[str, int],
                  retry_failures: bool) -> List[Publication]:
    """Publications without current text, minus failures not yet due. Ready
    ones get the listing's current title and date only."""
    by_identity = {attachment_identity(p.url): p for p in publications}
    identities = list(by_identity)
    async with db.pool.acquire() as conn:
        ready = {r["source_identity"] for r in await conn.fetch(
            READY_IDENTITIES_SQL, identities, COMPATIBLE_EXTRACT_VERSIONS)}
        failures = {r["source_identity"]: r for r in await conn.fetch(FAILURE_STATE_SQL, identities, EXTRACT_VERSION)}
    for identity in ready:
        p = by_identity[identity]
        counts["listing_refreshed"] += bool(await db.document_blobs.record_listing(identity, p.title, p.published_on))
    counts["already_ingested"] += len(ready)
    todo = []
    for identity, publication in by_identity.items():
        if identity in ready:
            continue
        failure = failures.get(identity)
        if failure and (failure["permanent"] or not (failure["retry_due"] or retry_failures)):
            counts["skipped_failed"] += 1
            continue
        todo.append(publication)
    return todo


async def ingest(db, args) -> int:
    sources = load_sources()
    slugs = args.slug.split(",") if args.slug else list(sources)
    if get_corpus() is None:
        print("ingest_publications: corpus unavailable; nothing processed")
        return 2
    analyzer = AsyncAnalyzer(enable_llm=False)
    counts: Dict[str, int] = defaultdict(int)
    try:
        for slug in slugs:
            banana = await resolve_banana(db, slug, sources[slug])
            if not banana:
                print(f"skip {slug}: no jurisdiction row (run onboard --apply)")
                continue
            adapter = AsyncPublicationsAdapter(slug)
            adapter.banana = banana
            publications = await adapter.fetch_publications(datetime(args.since_year, 1, 1))
            counts["listed"] += len(publications)
            todo = (await pending(db, publications, counts, args.retry_failures))[:args.limit]
            print(f"{slug} ({banana}): {len(publications)} listed, {len(todo)} to ingest")
            if args.dry_run:
                for p in todo[:20]:
                    print(f"  {p.published_on or '':<10} {p.title[:70]:<70} {p.url[:80]}")
                continue
            queue = iter(todo)

            async def worker(banana: str = banana):
                for publication in queue:
                    await ingest_one(db, analyzer, banana, publication, args, counts)

            await asyncio.gather(*(worker() for _ in range(args.concurrency)))
            print(f"  {dict(counts)}", flush=True)
    finally:
        await analyzer.close()
    logger.info("publications ingest complete", **counts)
    print(f"ingest_publications: {dict(counts)}")
    return 0


async def list_source(slug: str, since_year: int) -> int:
    adapter = AsyncPublicationsAdapter(slug)
    publications = await adapter.fetch_publications(datetime(since_year, 1, 1))
    for p in sorted(publications, key=lambda p: (p.published_on is None, p.published_on or datetime.min.date())):
        print(f"{str(p.published_on or ''):<10} {p.title[:80]:<80} {p.url}")
    print(f"{len(publications)} documents, {sum(1 for p in publications if p.published_on)} dated")
    return 0


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    steps = parser.add_subparsers(dest="step", required=True)
    step = steps.add_parser("onboard", help="create jurisdictions rows for registry bodies that lack one")
    step.add_argument("--apply", action="store_true")
    step = steps.add_parser("list", help="show what a source's listings hold; nothing is downloaded")
    step.add_argument("slug")
    step.add_argument("--since-year", type=int, default=2015)
    step = steps.add_parser("ingest", help="archive and extract every listed document not yet in the corpus")
    step.add_argument("--slug", default=None, help="comma-separated registry slugs; default all")
    step.add_argument("--since-year", type=int, default=2015, help="earliest year for {year} listing templates")
    step.add_argument("--limit", type=int, default=1000, help="max documents per source this run")
    step.add_argument("--concurrency", type=int, default=2)
    step.add_argument("--max-failures", type=int, default=3)
    step.add_argument("--failure-retry-days", type=int, default=7)
    step.add_argument("--retry-failures", action="store_true", help="retry ledger failures before their backoff")
    step.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    if args.step == "list":
        try:
            return await list_source(args.slug, args.since_year)
        finally:
            await AsyncSessionManager.close_all()
    db = await Database.create()
    try:
        if args.step == "onboard":
            return await onboard(db, args.apply)
        return await ingest(db, args)
    finally:
        await AsyncSessionManager.close_all()
        await db.close()


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
