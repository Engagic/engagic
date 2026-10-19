"""Async DocketRepository: commission dockets and their filings.

A docket and its filings are written together in one transaction, the way a
meeting and its items are. Upserts are keyed by the minted ids, so relisting a
case updates what changed (a new filing, a retitled one, a moved sequence) and
never duplicates.
"""

from typing import List, Optional

from asyncpg import Connection

from config import get_logger
from database.models import Docket, DocketFiling
from database.repositories_async.base import BaseRepository

logger = get_logger(__name__).bind(component="docket_repository")


class DocketRepository(BaseRepository):
    async def store_docket(self, docket: Docket, filings: List[DocketFiling],
                           conn: Optional[Connection] = None) -> None:
        if conn is None:
            async with self.transaction() as tx:
                await self._store(tx, docket, filings)
        else:
            await self._store(conn, docket, filings)

    async def _store(self, conn: Connection, docket: Docket, filings: List[DocketFiling]) -> None:
        await conn.execute(
            """
            INSERT INTO dockets (id, banana, system, case_key, docket_number, title, url,
                                 first_filed_on, last_filed_on, filing_count)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
            ON CONFLICT (id) DO UPDATE SET
                docket_number = COALESCE(EXCLUDED.docket_number, dockets.docket_number),
                title = COALESCE(EXCLUDED.title, dockets.title),
                url = EXCLUDED.url,
                first_filed_on = EXCLUDED.first_filed_on,
                last_filed_on = EXCLUDED.last_filed_on,
                filing_count = EXCLUDED.filing_count,
                updated_at = CURRENT_TIMESTAMP
            WHERE (dockets.docket_number, dockets.title, dockets.url, dockets.first_filed_on,
                   dockets.last_filed_on, dockets.filing_count)
                  IS DISTINCT FROM
                  (COALESCE(EXCLUDED.docket_number, dockets.docket_number),
                   COALESCE(EXCLUDED.title, dockets.title), EXCLUDED.url, EXCLUDED.first_filed_on,
                   EXCLUDED.last_filed_on, EXCLUDED.filing_count)
            """,
            docket.id, docket.banana, docket.system, docket.case_key, docket.docket_number,
            docket.title, docket.url, docket.first_filed_on, docket.last_filed_on, docket.filing_count,
        )
        if not filings:
            return
        await conn.executemany(
            """
            INSERT INTO docket_filings (id, docket_id, vendor_filing_id, sequence, title, filing_type,
                                        description, filer, filed_on, attachments, attachment_hash)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
            ON CONFLICT (id) DO UPDATE SET
                sequence = EXCLUDED.sequence,
                title = EXCLUDED.title,
                filing_type = EXCLUDED.filing_type,
                description = EXCLUDED.description,
                filer = EXCLUDED.filer,
                filed_on = EXCLUDED.filed_on,
                attachments = EXCLUDED.attachments,
                attachment_hash = EXCLUDED.attachment_hash,
                updated_at = CURRENT_TIMESTAMP
            WHERE docket_filings.attachment_hash IS DISTINCT FROM EXCLUDED.attachment_hash
               OR docket_filings.sequence IS DISTINCT FROM EXCLUDED.sequence
               OR docket_filings.title IS DISTINCT FROM EXCLUDED.title
               OR docket_filings.filed_on IS DISTINCT FROM EXCLUDED.filed_on
            """,
            [(f.id, f.docket_id, f.vendor_filing_id, f.sequence, f.title, f.filing_type, f.description,
              # The pool's JSONB codec encodes; a json.dumps here would store a string.
              f.filer, f.filed_on, [a.model_dump(exclude_none=True) for a in f.attachments or []],
              f.attachment_hash) for f in filings],
        )
