"""Archive state commissions' docket systems: structure to Postgres, originals to R2.

Walks each system's case keys (newest first), lists a case through
vendors/adapters/custom/dockets_adapter_async.py, and writes it the way a
meeting sync writes a meeting: the docket and its filings in one transaction
(dockets, docket_filings; ids minted in database/id_generation.py, filing
attachments in the items shape), then every document archived the way the
meeting archive backfills do: streamed to R2 by the adapter's acquirer,
content-addressed, no text extraction. Each document's document_source rows
also carry its filing's title and date. Systems and their ranges are
data/docket_systems.json.

State: originals live in the corpus (a URL already archived is a database
lookup, not a download). Cases whose documents were all archived or are gone
(403/404/410) are appended to data/dockets/<system>.jsonl and skipped on the
next run; a case with a transient failure is not, so it is listed again.
Restart at will. A bot wall stops that system; the disk floor stops the run.

Several systems run in one process, each paced per host by the rate limiter.

    uv run scripts/ingest_dockets.py kypsc --onboard             # create the body row
    uv run scripts/ingest_dockets.py nydps --start 75000 --end 1 --dry-run
    uv run scripts/ingest_dockets.py nydps txpuc orpuc wautc kypsc
"""

import argparse
import asyncio
import json
import shutil
import sys
import time
from collections import defaultdict
from datetime import date
from pathlib import Path
from typing import Dict, Set

import aiohttp

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import config, get_logger
from corpus.store import get_corpus
from database.db_postgres import Database
from exceptions import VendorHTTPError
from pipeline.document_acquisition import ArchiveDocumentUnavailable
from database.id_generation import generate_docket_filing_id, generate_docket_id
from database.models import AttachmentInfo, Docket, DocketFiling
from pipeline.utils import attachment_identity, hash_attachments_fast
from scripts.ingest_publications import ensure_body
from vendors.adapters.custom.dockets_adapter_async import (
    BotWallError,
    RawDocket,
    RawFiling,
    load_systems,
    system_adapter,
)
from vendors.session_manager_async import AsyncSessionManager

logger = get_logger(__name__).bind(component="ingest_dockets")

DISK_FLOOR_BYTES = 4_000 * 1024 * 1024


def attachment_type(name: str, url: str) -> str:
    ext = (name if "." in name else url.split("?", 1)[0]).rsplit(".", 1)[-1].lower()
    return {"pdf": "pdf", "doc": "doc", "docx": "doc", "rtf": "doc", "xls": "spreadsheet",
            "xlsx": "spreadsheet", "csv": "spreadsheet"}.get(ext, "unknown")


def to_models(banana: str, system: str, raw: RawDocket) -> tuple[Docket, list[DocketFiling]]:
    docket_id = generate_docket_id(banana, system, raw.case_key)
    ordered = sorted(raw.filings, key=lambda f: (f.filed_on is None, f.filed_on or date.min, f.vendor_filing_id))
    filings = []
    for sequence, f in enumerate(ordered, 1):
        attachments = [AttachmentInfo(name=d.name or "document", url=d.url, type=attachment_type(d.name, d.url))
                       for d in f.documents]
        filings.append(DocketFiling(
            id=generate_docket_filing_id(docket_id, f.vendor_filing_id), docket_id=docket_id,
            vendor_filing_id=f.vendor_filing_id, sequence=sequence, title=f.title, filing_type=f.filing_type,
            description=f.description, filer=f.filer, filed_on=f.filed_on, attachments=attachments,
            attachment_hash=hash_attachments_fast(attachments) or None))
    dates = [f.filed_on for f in ordered if f.filed_on]
    docket = Docket(id=docket_id, banana=banana, system=system, case_key=raw.case_key, url=raw.url,
                    docket_number=raw.docket_number, title=raw.title, first_filed_on=min(dates, default=None),
                    last_filed_on=max(dates, default=None), filing_count=len(filings))
    return docket, filings


def checkpoint_path(system: str) -> Path:
    # v2: cases recorded before dockets/docket_filings existed must be walked again.
    path = Path(config.DB_DIR) / "dockets" / f"{system}.v2.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def done_cases(path: Path) -> Set[int]:
    done = set()
    if path.exists():
        with path.open() as f:
            for line in f:
                try:
                    done.add(json.loads(line)["seq"])
                except (json.JSONDecodeError, KeyError):
                    continue  # a torn tail from a killed run
    return done


class SystemRun:
    def __init__(self, db, system: str, args, stop: Dict[str, str]):
        self.db, self.system, self.args, self.stop = db, system, args, stop
        self.adapter = system_adapter(system)
        self.counts: Dict[str, int] = defaultdict(int)
        self.halted = ""

    async def banana(self) -> str:
        body = self.adapter.body
        banana = body if isinstance(body, str) else await ensure_body(self.db, body, self.system,
                                                                     apply=self.args.onboard)
        if banana and not self.args.onboard and not await self.db.jurisdictions.get_city(banana):
            print(f"{self.system}: {banana} has no row yet; run with --onboard first")
            return ""
        return banana or ""

    async def archive_one(self, banana: str, filing: RawFiling, url: str) -> bool:
        """True when the document is settled: archived, already held, or gone."""
        try:
            receipt = await self.adapter._document_acquirer.archive(url, banana=banana)
            self.counts["reused" if receipt.get("reused") else "archived"] += 1
            self.counts["bytes"] += 0 if receipt.get("reused") else int(receipt.get("bytes") or 0)
            settled = True
        except ArchiveDocumentUnavailable:
            self.counts["unavailable"] += 1
            settled = True
        except Exception as e:
            self.counts["failed"] += 1
            logger.warning("docket document archive failed", system=self.system, url=url[:120],
                           error=f"{type(e).__name__}: {e}"[:200])
            return False
        await self.db.document_blobs.record_listing(attachment_identity(url), filing.title, filing.filed_on)
        return settled

    async def one_case(self, banana: str, seq: int, out) -> None:
        try:
            raw = await self.adapter.list_case(seq)
        except BotWallError as e:
            self.halted = f"bot wall at case {seq} ({e})"
            return
        except (VendorHTTPError, asyncio.TimeoutError, aiohttp.ClientError) as e:
            # _get checks status; a body that stalls or drops mid-read surfaces here instead. The case
            # stays out of the checkpoint, so the next run lists it again.
            self.counts["case_list_failed"] += 1
            logger.warning("case listing failed", system=self.system, seq=seq,
                           error=f"{type(e).__name__}: {e}"[:200])
            return
        documents = [(f, d.url) for f in raw.filings for d in f.documents] if raw else []
        if raw:
            self.counts["cases"] += 1
            self.counts["filings"] += len(raw.filings)
            self.counts["listed"] += len(documents)
        if self.args.dry_run:
            if raw:
                print(f"{self.system} case {seq}: {raw.docket_number} {(raw.title or '')[:70]!r}; "
                      f"{len(raw.filings)} filings, {len(documents)} documents; e.g. {raw.filings[0].title[:80]}")
            return
        if raw:
            docket, filings = to_models(banana, self.system, raw)
            await self.db.dockets.store_docket(docket, filings)
        queue = iter(documents)
        results = []

        async def worker():
            for filing, url in queue:
                results.append(await self.archive_one(banana, filing, url))

        await asyncio.gather(*(worker() for _ in range(self.args.concurrency)))
        if all(results):
            out.write(json.dumps({"seq": seq, "filings": len(raw.filings) if raw else 0,
                                  "docs": len(documents)}) + "\n")
            out.flush()

    async def run(self) -> None:
        banana = await self.banana()
        if self.args.onboard or not banana:
            return
        self.adapter.banana = banana
        start, end = (self.args.start, self.args.end) if self.args.start is not None \
            else self.adapter.conf["range"]
        numbers = self.adapter.case_numbers(start, end)
        path = checkpoint_path(self.system)
        done = done_cases(path)
        cases = iter(seq for seq in numbers if seq not in done)
        last_report = time.monotonic()

        async def case_worker(out) -> None:
            nonlocal last_report
            for seq in cases:
                if self.stop or self.halted:
                    return
                if shutil.disk_usage("/").free < DISK_FLOOR_BYTES:
                    self.stop["reason"] = "disk floor reached"
                    return
                await self.one_case(banana, seq, out)
                if time.monotonic() - last_report > 300:
                    last_report = time.monotonic()
                    logger.info("dockets progress", system=self.system, at_case=seq, **self.counts)

        with path.open("a") as out:
            # Most cases are empty or tiny, so listing, not downloading, sets the pace.
            await asyncio.gather(*(case_worker(out) for _ in range(self.args.case_workers)))
        if self.halted:
            print(f"{self.system}: stopped: {self.halted}")
        logger.info("dockets system finished", system=self.system, halted=self.halted or None, **self.counts)
        print(f"{self.system}: {dict(self.counts)}", flush=True)


async def run(args) -> int:
    db = await Database.create()
    try:
        if not args.onboard and get_corpus() is None:
            print("ingest_dockets: corpus unavailable; nothing processed")
            return 2
        stop: Dict[str, str] = {}
        runs = [SystemRun(db, system, args, stop) for system in args.systems]
        await asyncio.gather(*(r.run() for r in runs))
        if stop:
            print(f"ingest_dockets: stopped: {stop['reason']}")
            return 3
        return 0
    finally:
        await db.close()
        await AsyncSessionManager.close_all()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("systems", nargs="+", choices=sorted(load_systems()))
    parser.add_argument("--onboard", action="store_true", help="create the commissions' jurisdictions rows and exit")
    parser.add_argument("--start", type=int, default=None, help="first case number (one system only)")
    parser.add_argument("--end", type=int, default=None)
    parser.add_argument("--concurrency", type=int, default=2, help="document downloads per case")
    parser.add_argument("--case-workers", type=int, default=3, help="cases handled at once per system")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    if args.start is not None and (len(args.systems) > 1 or args.end is None):
        parser.error("--start/--end take one system and both bounds")
    return asyncio.run(run(args))


if __name__ == "__main__":
    sys.exit(main())
