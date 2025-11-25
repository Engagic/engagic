"""Async MatterRepository for matter operations

Handles CRUD operations for matters (recurring legislative items):
- Store/update matters with canonical summaries
- Topic normalization (separate matter_topics table)
- JSONB for attachments, sponsors, metadata
- Timeline tracking (first_seen, last_seen, appearance_count)
"""

from typing import Dict, List, Optional
from collections import defaultdict
from datetime import datetime

from database.repositories_async.base import BaseRepository
from database.models import Matter, AttachmentInfo, MatterMetadata
from config import get_logger

logger = get_logger(__name__).bind(component="matter_repository")


class MatterRepository(BaseRepository):
    """Repository for matter operations

    Provides:
    - Store/update matters with canonical summaries
    - Retrieve matters by ID
    - Update summaries with topic normalization
    - Attachment hash tracking for change detection
    """

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

            # Normalize topics to matter_topics table
            if matter.canonical_topics:
                await conn.execute(
                    "DELETE FROM matter_topics WHERE matter_id = $1",
                    matter.id,
                )
                for topic in matter.canonical_topics:
                    await conn.execute(
                        """
                        INSERT INTO matter_topics (matter_id, topic)
                        VALUES ($1, $2)
                        ON CONFLICT DO NOTHING
                        """,
                        matter.id,
                        topic,
                    )

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

            # Update topics normalization
            if canonical_topics:
                # Delete existing topics
                await conn.execute(
                    "DELETE FROM matter_topics WHERE matter_id = $1",
                    matter_id,
                )
                # Insert new topics
                for topic in canonical_topics:
                    await conn.execute(
                        """
                        INSERT INTO matter_topics (matter_id, topic)
                        VALUES ($1, $2)
                        ON CONFLICT DO NOTHING
                        """,
                        matter_id,
                        topic,
                    )

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
            # Build dynamic SQL for appearance count
            if increment_appearance_count:
                await conn.execute(
                    """
                    UPDATE city_matters
                    SET last_seen = $2,
                        attachments = $3::jsonb,
                        metadata = COALESCE(metadata, '{}'::jsonb) || jsonb_build_object('attachment_hash', $4::text),
                        appearance_count = appearance_count + 1,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = $1
                    """,
                    matter_id,
                    meeting_date,
                    attachments,
                    attachment_hash,
                )
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

        logger.debug("updated matter tracking", matter_id=matter_id, increment=increment_appearance_count)

    async def check_appearance_exists(self, matter_id: str, meeting_id: str) -> bool:
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
