"""Extract corpus text for items whose originals are archived but never texted.

The deep backfills archive originals only. A reader that needs text for a
specific set of items (an evaluation panel, a linkage pass) names them here,
and each archived original is extracted from R2 through the analyzer's own
extraction and persist path. The origin host is never contacted.

State lives in the corpus: an identity with current-version text is skipped,
so a rerun picks up only what failed.

Usage:
    uv run python scripts/extract_archived_text.py --items ids.txt --concurrency 2
"""

import argparse
import asyncio
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from analysis.analyzer_async import AsyncAnalyzer
from config import get_logger
from corpus.store import COMPATIBLE_EXTRACT_VERSIONS, get_corpus
from database.db_postgres import Database
from exceptions import ExtractionError
from pipeline.utils import attachment_identity

logger = get_logger(__name__).bind(component="extract_archived_text")

ATTACHMENT_IDENTITIES_SQL = """
    SELECT DISTINCT a ->> 'url' AS url
    FROM items i CROSS JOIN LATERAL jsonb_array_elements(i.attachments) a
    WHERE i.id = ANY($1) AND jsonb_typeof(i.attachments) = 'array' AND coalesce(a ->> 'url', '') <> ''
"""

# Newest revision per identity, as acquisition resolves it.
PENDING_SQL = """
    SELECT DISTINCT ON (s.source_identity) s.source_identity, b.text_key, b.extract_version
    FROM document_source s JOIN document_blob b USING (content_sha256)
    WHERE s.source_identity = ANY($1) AND b.original_key IS NOT NULL
    ORDER BY s.source_identity, s.last_validated_at DESC NULLS LAST, s.first_seen DESC
"""


async def pending_identities(db: Database, item_ids: list[str]) -> list[str]:
    async with db.pool.acquire() as conn:
        urls = [r["url"] for r in await conn.fetch(ATTACHMENT_IDENTITIES_SQL, item_ids)]
        identities = sorted({attachment_identity(u) for u in urls})
        rows = await conn.fetch(PENDING_SQL, identities)
    return [r["source_identity"] for r in rows
            if not r["text_key"] or r["extract_version"] not in COMPATIBLE_EXTRACT_VERSIONS]


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--items", required=True, help="file of item ids, one per line")
    parser.add_argument("--concurrency", type=int, default=2)
    parser.add_argument("--no-ocr", action="store_true",
                        help="text layer only; scanned pages stay ocr_pending for the OCR-owning path")
    args = parser.parse_args()
    item_ids = [line.strip() for line in Path(args.items).read_text().splitlines() if line.strip()]

    db = await Database.create()
    analyzer = None
    try:
        if get_corpus() is None:
            print("extract_archived_text: corpus unavailable")
            return 2
        todo = await pending_identities(db, item_ids)
        print(f"{len(item_ids)} items, {len(todo)} archived originals without text", flush=True)
        analyzer = AsyncAnalyzer(enable_llm=False)
        counts: Counter = Counter()
        queue = iter(todo)

        async def worker() -> None:
            for identity in queue:
                try:
                    result = await analyzer.extract_archived_async(identity, ocr_enabled=not args.no_ocr)
                    counts["texted" if result.get("corpus_persisted") else "not_persisted"] += 1
                except ExtractionError as e:
                    counts["extraction_error"] += 1
                    logger.warning("archived extraction failed", url=identity[:120], error=str(e)[:200])
                done = sum(counts.values())
                if done % 50 == 0:
                    print(f"{done}/{len(todo)} {dict(counts)}", flush=True)

        await asyncio.gather(*(worker() for _ in range(args.concurrency)))
        print(f"extract_archived_text: {dict(counts)}")
        return 0
    finally:
        if analyzer is not None:
            await analyzer.close()
        await db.close()


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
