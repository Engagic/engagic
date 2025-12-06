"""Async MatterRepository for matter operations."""

from datetime import datetime
from typing import Dict, List, Optional

from database.repositories_async.base import BaseRepository
from database.repositories_async.helpers import build_matter, fetch_topics_for_ids, replace_entity_topics
from database.models import Matter, AttachmentInfo
from config import get_logger

logger = get_logger(__name__).bind(component="matter_repository")


class MatterRepository(BaseRepository):
    """Repository for matter operations."""

    async def store_matter(self, matter: Matter) -> None:
        """Store or update a matter with topic normalization."""
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

            if matter.canonical_topics:
                await replace_entity_topics(
                    conn, "matter_topics", "matter_id", matter.id, matter.canonical_topics
                )

        logger.debug("stored matter", matter_id=matter.id, banana=matter.banana)

    async def get_matter(self, matter_id: str) -> Optional[Matter]:
        """Get a matter by ID."""
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT
                    id, banana, matter_id, matter_file, matter_type,
                    title, sponsors, canonical_summary, canonical_topics,
                    attachments, metadata, first_seen, last_seen,
                    appearance_count, status, created_at, updated_at,
                    final_vote_date, quality_score, rating_count
                FROM city_matters
                WHERE id = $1
                """,
                matter_id,
            )

            if not row:
                return None

            topics_map = await fetch_topics_for_ids(
                conn, "matter_topics", "matter_id", [matter_id]
            )
            topics = topics_map.get(matter_id, [])

            return build_matter(row, topics or None)

    async def get_matters_batch(self, matter_ids: List[str]) -> Dict[str, Matter]:
        """Batch fetch multiple matters by ID - eliminates N+1."""
        if not matter_ids:
            return {}

        unique_ids = list(set(matter_ids))

        async with self.pool.acquire() as conn:
            # Single query for all matters
            rows = await conn.fetch(
                """
                SELECT
                    id, banana, matter_id, matter_file, matter_type,
                    title, sponsors, canonical_summary, canonical_topics,
                    attachments, metadata, first_seen, last_seen,
                    appearance_count, status, created_at, updated_at,
                    final_vote_date, quality_score, rating_count
                FROM city_matters
                WHERE id = ANY($1::text[])
                """,
                unique_ids,
            )

            if not rows:
                return {}

            topics_by_matter = await fetch_topics_for_ids(
                conn, "matter_topics", "matter_id", unique_ids
            )

            return {
                row["id"]: build_matter(
                    row, topics_by_matter.get(row["id"]) or None
                )
                for row in rows
            }

    async def update_matter_summary(
        self,
        matter_id: str,
        canonical_summary: str,
        canonical_topics: List[str],
        attachment_hash: str
    ) -> None:
        """Update matter with canonical summary, topics, and attachment hash."""
        async with self.transaction() as conn:
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

            if canonical_topics:
                await replace_entity_topics(
                    conn, "matter_topics", "matter_id", matter_id, canonical_topics
                )

        logger.debug("updated matter with canonical summary", matter_id=matter_id)

    async def update_matter_tracking(
        self,
        matter_id: str,
        meeting_date: Optional[datetime],
        attachments: Optional[List[AttachmentInfo]],
        attachment_hash: str,
        increment_appearance_count: bool = False
    ) -> Optional[int]:
        """Update matter tracking fields with atomic increment to prevent race conditions."""
        async with self.transaction() as conn:
            if increment_appearance_count:
                new_count = await conn.fetchval(
                    """
                    UPDATE city_matters
                    SET last_seen = $2,
                        attachments = $3::jsonb,
                        metadata = COALESCE(metadata, '{}'::jsonb) || jsonb_build_object('attachment_hash', $4::text),
                        updated_at = CURRENT_TIMESTAMP,
                        appearance_count = appearance_count + 1
                    WHERE id = $1
                    RETURNING appearance_count
                    """,
                    matter_id,
                    meeting_date,
                    attachments,
                    attachment_hash,
                )
                logger.debug("updated matter tracking", matter_id=matter_id, new_count=new_count)
                return new_count
            else:
                await conn.execute(
                    """
                    UPDATE city_matters
                    SET last_seen = $2,
                        attachments = $3::jsonb,
                        metadata = COALESCE(metadata, '{}'::jsonb) || jsonb_build_object('attachment_hash', $4::text),
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = $1
                    """,
                    matter_id,
                    meeting_date,
                    attachments,
                    attachment_hash,
                )
                logger.debug("updated matter tracking", matter_id=matter_id, increment=False)
                return None

    async def has_appearance(self, matter_id: str, meeting_id: str) -> bool:
        """Check if a matter already has an appearance record for a specific meeting."""
        async with self.pool.acquire() as conn:
            exists = await conn.fetchval(
                """
                SELECT EXISTS(
                    SELECT 1 FROM matter_appearances
                    WHERE matter_id = $1 AND meeting_id = $2
                )
                """,
                matter_id,
                meeting_id,
            )
            return exists

    async def create_appearance(
        self,
        matter_id: str,
        meeting_id: str,
        item_id: str,
        appeared_at: Optional[datetime],
        committee: Optional[str] = None,
        committee_id: Optional[str] = None,
        sequence: Optional[int] = None
    ) -> None:
        """Create a matter appearance record."""
        async with self.transaction() as conn:
            await conn.execute(
                """
                INSERT INTO matter_appearances (
                    matter_id, meeting_id, item_id, appeared_at, committee, committee_id, sequence
                )
                VALUES ($1, $2, $3, $4, $5, $6, $7)
                ON CONFLICT (matter_id, meeting_id, item_id) DO NOTHING
                """,
                matter_id,
                meeting_id,
                item_id,
                appeared_at,
                committee,
                committee_id,
                sequence,
            )

        logger.debug("created matter appearance", matter_id=matter_id, meeting_id=meeting_id)

    async def search_matters_fulltext(
        self,
        query: str,
        banana: str,
        limit: int = 50
    ) -> List[Matter]:
        """Full-text search on matters using PostgreSQL FTS."""
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT
                    id, banana, matter_id, matter_file, matter_type,
                    title, sponsors, canonical_summary, canonical_topics,
                    attachments, metadata, first_seen, last_seen,
                    appearance_count, status, final_vote_date, quality_score, rating_count,
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

            matter_ids = [row["id"] for row in rows]
            topics_by_matter = await fetch_topics_for_ids(
                conn, "matter_topics", "matter_id", matter_ids
            )

            return [
                build_matter(row, topics_by_matter.get(row["id"]) or None)
                for row in rows
            ]

    async def update_appearance_outcome(
        self,
        matter_id: str,
        meeting_id: str,
        item_id: str,
        vote_outcome: str,
        vote_tally: dict
    ) -> None:
        """Update matter appearance with vote outcome and tally."""
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
        """Update matter disposition status when reaching a terminal state."""
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
        """Get matter with full vote history across all meetings."""
        async with self.pool.acquire() as conn:
            matter = await self.get_matter(matter_id)
            if not matter:
                return None

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
