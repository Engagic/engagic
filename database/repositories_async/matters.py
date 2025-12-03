"""Async MatterRepository for matter operations

Handles CRUD operations for matters (recurring legislative items):
- Store/update matters with canonical summaries
- Topic normalization (separate matter_topics table)
- JSONB for attachments, sponsors, metadata
- Timeline tracking (first_seen, last_seen, appearance_count)
"""

from collections import defaultdict
from datetime import datetime
from typing import Dict, List, Optional

from database.repositories_async.base import BaseRepository
from database.models import Matter, AttachmentInfo, MatterMetadata
from config import get_logger

logger = get_logger(__name__).bind(component="matter_repository")


class MatterRepository(BaseRepository):
    """Repository for matter operations."""

    async def _replace_topics(self, conn, matter_id: str, topics: Optional[List[str]]) -> None:
        """Replace all topics for a matter (destructive operation).

        Deletes existing topics then inserts new ones. Use when topics are
        recomputed and the new list should fully replace the old one.

        Args:
            conn: Database connection within transaction
            matter_id: The matter's composite ID
            topics: New topics to set (None or empty = no change)
        """
        if not topics:
            return
        await conn.execute("DELETE FROM matter_topics WHERE matter_id = $1", matter_id)
        topic_records = [(matter_id, topic) for topic in topics]
        await conn.executemany(
            "INSERT INTO matter_topics (matter_id, topic) VALUES ($1, $2) ON CONFLICT DO NOTHING",
            topic_records,
        )

    async def store_matter(self, matter: Matter) -> None:
        """Store or update a matter

        Uses UPSERT to handle both new matters and updates.
        Normalizes topics to matter_topics table.

        Args:
            matter: Matter object with canonical summary and topics
        """
        async with self.transaction() as conn:
            # Upsert matter row
            await conn.execute(
                """
                INSERT INTO city_matters (
                    id, banana, matter_id, matter_file, matter_type,
                    title, sponsors, canonical_summary, canonical_topics,
                    attachments, metadata, first_seen, last_seen,
                    appearance_count, status
                )
                VALUES ($1, $2, $3::text, $4::text, $5::text, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15)
                ON CONFLICT (id) DO UPDATE SET
                    matter_file = EXCLUDED.matter_file,
                    matter_type = EXCLUDED.matter_type,
                    title = EXCLUDED.title,
                    sponsors = EXCLUDED.sponsors,
                    canonical_summary = COALESCE(EXCLUDED.canonical_summary, city_matters.canonical_summary),
                    canonical_topics = COALESCE(EXCLUDED.canonical_topics, city_matters.canonical_topics),
                    attachments = EXCLUDED.attachments,
                    metadata = EXCLUDED.metadata,
                    last_seen = EXCLUDED.last_seen,
                    appearance_count = EXCLUDED.appearance_count,
                    status = EXCLUDED.status,
                    updated_at = CURRENT_TIMESTAMP
                """,
                matter.id,
                matter.banana,
                matter.matter_id,
                matter.matter_file,
                matter.matter_type,
                matter.title,
                matter.sponsors,
                matter.canonical_summary,
                matter.canonical_topics,
                matter.attachments,
                matter.metadata,
                matter.first_seen,
                matter.last_seen,
                matter.appearance_count or 1,
                matter.status or "active",
            )

            await self._replace_topics(conn, matter.id, matter.canonical_topics)

        logger.debug("stored matter", matter_id=matter.id, banana=matter.banana)

    async def get_matter(self, matter_id: str) -> Optional[Matter]:
        """Get a matter by ID

        Args:
            matter_id: Matter identifier (composite hash including city_banana)

        Returns:
            Matter object with denormalized topics, or None
        """
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT
                    id, banana, matter_id, matter_file, matter_type,
                    title, sponsors, canonical_summary, canonical_topics,
                    attachments, metadata, first_seen, last_seen,
                    appearance_count, status, created_at, updated_at
                FROM city_matters
                WHERE id = $1
                """,
                matter_id,
            )

            if not row:
                return None

            # Fetch normalized topics
            topic_rows = await conn.fetch(
                "SELECT topic FROM matter_topics WHERE matter_id = $1",
                matter_id,
            )
            topics = [r["topic"] for r in topic_rows]

            # Deserialize JSONB fields to typed models
            attachments = [AttachmentInfo(**a) for a in (row["attachments"] or [])]
            metadata = MatterMetadata(**row["metadata"]) if row["metadata"] else None

            return Matter(
                id=row["id"],
                banana=row["banana"],
                matter_id=row["matter_id"],
                matter_file=row["matter_file"],
                matter_type=row["matter_type"],
                title=row["title"],
                sponsors=row["sponsors"],
                canonical_summary=row["canonical_summary"],
                canonical_topics=topics or row["canonical_topics"],
                attachments=attachments,
                metadata=metadata,
                first_seen=row["first_seen"],
                last_seen=row["last_seen"],
                appearance_count=row["appearance_count"],
                status=row["status"],
            )

    async def get_matters_batch(self, matter_ids: List[str]) -> Dict[str, Matter]:
        """Batch fetch multiple matters by ID - eliminates N+1

        Args:
            matter_ids: List of matter identifiers

        Returns:
            Dict mapping matter_id to Matter object
        """
        if not matter_ids:
            return {}

        # Deduplicate IDs
        unique_ids = list(set(matter_ids))

        async with self.pool.acquire() as conn:
            # Single query for all matters
            rows = await conn.fetch(
                """
                SELECT
                    id, banana, matter_id, matter_file, matter_type,
                    title, sponsors, canonical_summary, canonical_topics,
                    attachments, metadata, first_seen, last_seen,
                    appearance_count, status, created_at, updated_at
                FROM city_matters
                WHERE id = ANY($1::text[])
                """,
                unique_ids,
            )

            if not rows:
                return {}

            # Single query for ALL matter topics
            topic_rows = await conn.fetch(
                "SELECT matter_id, topic FROM matter_topics WHERE matter_id = ANY($1::text[])",
                unique_ids,
            )

            # Group topics by matter
            topics_by_matter: Dict[str, List[str]] = defaultdict(list)
            for tr in topic_rows:
                topics_by_matter[tr["matter_id"]].append(tr["topic"])

            # Build matters dict
            matters: Dict[str, Matter] = {}
            for row in rows:
                attachments = [AttachmentInfo(**a) for a in (row["attachments"] or [])]
                metadata = MatterMetadata(**row["metadata"]) if row["metadata"] else None
                topics = topics_by_matter.get(row["id"], []) or row["canonical_topics"]

                matters[row["id"]] = Matter(
                    id=row["id"],
                    banana=row["banana"],
                    matter_id=row["matter_id"],
                    matter_file=row["matter_file"],
                    matter_type=row["matter_type"],
                    title=row["title"],
                    sponsors=row["sponsors"],
                    canonical_summary=row["canonical_summary"],
                    canonical_topics=topics,
                    attachments=attachments,
                    metadata=metadata,
                    first_seen=row["first_seen"],
                    last_seen=row["last_seen"],
                    appearance_count=row["appearance_count"],
                    status=row["status"],
                )

            return matters

    async def update_matter_summary(
        self,
        matter_id: str,
        canonical_summary: str,
        canonical_topics: List[str],
        attachment_hash: str
    ) -> None:
        """Update matter with canonical summary, topics, and attachment hash

        Used when matter attachments change and summary needs recomputation.

        Args:
            matter_id: Composite matter ID
            canonical_summary: Deduplicated summary text
            canonical_topics: Extracted topics
            attachment_hash: SHA256 hash of attachments for change detection
        """
        async with self.transaction() as conn:
            # Update matter row with new summary and attachment hash
            await conn.execute(
                """
                UPDATE city_matters
                SET canonical_summary = $2,
                    metadata = COALESCE(metadata, '{}'::jsonb) || jsonb_build_object('attachment_hash', $3),
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = $1
                """,
                matter_id,
                canonical_summary,
                attachment_hash,
            )

            await self._replace_topics(conn, matter_id, canonical_topics)

        logger.debug("updated matter with canonical summary", matter_id=matter_id)

    async def update_matter_tracking(
        self,
        matter_id: str,
        meeting_date: Optional[datetime],
        attachments: Optional[List[AttachmentInfo]],
        attachment_hash: str,
        increment_appearance_count: bool = False
    ) -> None:
        """Update matter tracking fields (last_seen, appearance_count, attachments)

        Args:
            matter_id: Composite matter ID
            meeting_date: Datetime when matter appeared
            attachments: List of attachment dicts
            attachment_hash: SHA256 hash of attachments
            increment_appearance_count: Whether to increment appearance count
        """
        async with self.transaction() as conn:
            appearance_clause = ", appearance_count = appearance_count + 1" if increment_appearance_count else ""
            await conn.execute(
                f"""
                UPDATE city_matters
                SET last_seen = $2,
                    attachments = $3::jsonb,
                    metadata = COALESCE(metadata, '{{}}'::jsonb) || jsonb_build_object('attachment_hash', $4::text),
                    updated_at = CURRENT_TIMESTAMP{appearance_clause}
                WHERE id = $1
                """,
                matter_id,
                meeting_date,
                attachments,
                attachment_hash,
            )

        logger.debug("updated matter tracking", matter_id=matter_id, increment=increment_appearance_count)

    async def has_appearance(self, matter_id: str, meeting_id: str) -> bool:
        """Check if a matter already has an appearance record for a specific meeting

        Args:
            matter_id: Composite matter ID
            meeting_id: Meeting identifier

        Returns:
            True if appearance record exists, False otherwise
        """
        async with self.pool.acquire() as conn:
            count = await conn.fetchval(
                """
                SELECT COUNT(*) FROM matter_appearances
                WHERE matter_id = $1 AND meeting_id = $2
                """,
                matter_id,
                meeting_id,
            )
            return count > 0

    async def create_appearance(
        self,
        matter_id: str,
        meeting_id: str,
        item_id: str,
        appeared_at: Optional[datetime],
        committee: Optional[str] = None,
        sequence: Optional[int] = None
    ) -> None:
        """Create a matter appearance record

        Args:
            matter_id: Composite matter ID
            meeting_id: Meeting identifier
            item_id: Item identifier
            appeared_at: Datetime when matter appeared
            committee: Committee name (extracted from meeting title)
            sequence: Item sequence in meeting
        """
        async with self.transaction() as conn:
            await conn.execute(
                """
                INSERT INTO matter_appearances (
                    matter_id, meeting_id, item_id, appeared_at, committee, sequence
                )
                VALUES ($1, $2, $3, $4, $5, $6)
                ON CONFLICT (matter_id, meeting_id, item_id) DO NOTHING
                """,
                matter_id,
                meeting_id,
                item_id,
                appeared_at,
                committee,
                sequence,
            )

        logger.debug("created matter appearance", matter_id=matter_id, meeting_id=meeting_id)

    async def search_matters_fulltext(
        self,
        query: str,
        banana: str,
        limit: int = 50
    ) -> List[Matter]:
        """Full-text search on matters using PostgreSQL FTS

        Searches title, canonical_summary, and matter_file fields.

        Args:
            query: Search query (plain text, automatically converted to tsquery)
            banana: City filter (required for scoped search)
            limit: Maximum results (default: 50)

        Returns:
            List of matching matters ordered by relevance then last_seen
        """
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT
                    id, banana, matter_id, matter_file, matter_type,
                    title, sponsors, canonical_summary, canonical_topics,
                    attachments, metadata, first_seen, last_seen,
                    appearance_count, status,
                    ts_rank(
                        to_tsvector('english', COALESCE(title, '') || ' ' || COALESCE(canonical_summary, '')),
                        plainto_tsquery('english', $1)
                    ) AS rank
                FROM city_matters
                WHERE banana = $2
                  AND (
                      to_tsvector('english', COALESCE(title, '') || ' ' || COALESCE(canonical_summary, ''))
                          @@ plainto_tsquery('english', $1)
                      OR matter_file ILIKE '%' || $1 || '%'
                  )
                ORDER BY rank DESC, last_seen DESC
                LIMIT $3
                """,
                query,
                banana,
                limit,
            )

            if not rows:
                return []

            # Batch fetch ALL topics for ALL matters (eliminates N+1)
            matter_ids = [row["id"] for row in rows]
            topic_rows = await conn.fetch(
                "SELECT matter_id, topic FROM matter_topics WHERE matter_id = ANY($1::text[])",
                matter_ids,
            )

            # Group topics by matter
            topics_by_matter: Dict[str, List[str]] = defaultdict(list)
            for tr in topic_rows:
                topics_by_matter[tr["matter_id"]].append(tr["topic"])

            # Build matter objects
            matters = []
            for row in rows:
                attachments = [AttachmentInfo(**a) for a in (row["attachments"] or [])]
                metadata = MatterMetadata(**row["metadata"]) if row["metadata"] else None
                topics = topics_by_matter.get(row["id"], []) or row["canonical_topics"]

                matters.append(
                    Matter(
                        id=row["id"],
                        banana=row["banana"],
                        matter_id=row["matter_id"],
                        matter_file=row["matter_file"],
                        matter_type=row["matter_type"],
                        title=row["title"],
                        sponsors=row["sponsors"],
                        canonical_summary=row["canonical_summary"],
                        canonical_topics=topics,
                        attachments=attachments,
                        metadata=metadata,
                        first_seen=row["first_seen"],
                        last_seen=row["last_seen"],
                        appearance_count=row["appearance_count"],
                        status=row["status"],
                    )
                )

            return matters

    async def update_appearance_outcome(
        self,
        matter_id: str,
        meeting_id: str,
        item_id: str,
        vote_outcome: str,
        vote_tally: dict
    ) -> None:
        """Update matter appearance with vote outcome and tally

        Called after processing votes for an item. Records the
        per-meeting outcome (passed/failed/etc) and vote counts.

        Args:
            matter_id: Composite matter ID
            meeting_id: Meeting identifier
            item_id: Item identifier
            vote_outcome: Result: passed, failed, tabled, referred, amended, no_vote
            vote_tally: Vote counts dict: {yes: N, no: N, abstain: N, absent: N}
        """
        async with self.transaction() as conn:
            await conn.execute(
                """
                UPDATE matter_appearances
                SET vote_outcome = $1, vote_tally = $2
                WHERE matter_id = $3 AND meeting_id = $4 AND item_id = $5
                """,
                vote_outcome,
                vote_tally,
                matter_id,
                meeting_id,
                item_id,
            )

        logger.debug(
            "updated appearance outcome",
            matter_id=matter_id,
            meeting_id=meeting_id,
            outcome=vote_outcome
        )

    async def update_status(
        self,
        matter_id: str,
        status: str,
        final_vote_date: Optional[datetime] = None
    ) -> None:
        """Update matter disposition status

        Called when a matter reaches a terminal state (passed, failed, etc).
        Sets the status and records when the final vote occurred.

        Args:
            matter_id: Composite matter ID
            status: Disposition: passed, failed, tabled, withdrawn, etc.
            final_vote_date: Date of final vote (optional)
        """
        async with self.transaction() as conn:
            await conn.execute(
                """
                UPDATE city_matters
                SET status = $1,
                    final_vote_date = COALESCE($2, final_vote_date),
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = $3
                """,
                status,
                final_vote_date,
                matter_id,
            )

        logger.info(
            "updated matter status",
            matter_id=matter_id,
            status=status,
            final_vote_date=final_vote_date
        )

    async def get_matter_with_votes(self, matter_id: str) -> Optional[dict]:
        """Get matter with full vote history across all meetings

        Returns matter data enriched with vote timeline showing
        each appearance, outcome, and tally.

        Args:
            matter_id: Composite matter ID

        Returns:
            Dict with matter data and vote_history array, or None
        """
        async with self.pool.acquire() as conn:
            # Get matter
            matter = await self.get_matter(matter_id)
            if not matter:
                return None

            # Get vote history from appearances
            appearances = await conn.fetch(
                """
                SELECT
                    ma.meeting_id,
                    ma.appeared_at,
                    ma.committee,
                    ma.vote_outcome,
                    ma.vote_tally,
                    m.title as meeting_title
                FROM matter_appearances ma
                JOIN meetings m ON m.id = ma.meeting_id
                WHERE ma.matter_id = $1
                ORDER BY ma.appeared_at DESC
                """,
                matter_id,
            )

            vote_history = [
                {
                    "meeting_id": row["meeting_id"],
                    "meeting_title": row["meeting_title"],
                    "date": row["appeared_at"].isoformat() if row["appeared_at"] else None,
                    "committee": row["committee"],
                    "outcome": row["vote_outcome"],
                    "tally": row["vote_tally"],
                }
                for row in appearances
            ]

            return {
                "matter": matter,
                "vote_history": vote_history,
            }

    async def get_matter_vote_outcomes(self, matter_id: str) -> List[dict]:
        """Get vote outcomes for a matter across all meetings where votes were recorded."""
        rows = await self._fetch(
            """
            SELECT
                ma.meeting_id,
                ma.vote_outcome,
                ma.vote_tally,
                ma.appeared_at,
                m.title as meeting_title
            FROM matter_appearances ma
            JOIN meetings m ON m.id = ma.meeting_id
            WHERE ma.matter_id = $1 AND ma.vote_outcome IS NOT NULL
            ORDER BY ma.appeared_at DESC
            """,
            matter_id
        )

        return [
            {
                "meeting_id": row["meeting_id"],
                "meeting_title": row["meeting_title"],
                "date": row["appeared_at"].isoformat() if row["appeared_at"] else None,
                "outcome": row["vote_outcome"],
                "tally": row["vote_tally"],
            }
            for row in rows
        ]
