"""Async MatterRepository for matter operations

Handles CRUD operations for matters (recurring legislative items):
- Store/update matters with canonical summaries
- Topic normalization (separate matter_topics table)
- JSONB for attachments, sponsors, metadata
- Timeline tracking (first_seen, last_seen, appearance_count)
"""

import json
from typing import List, Optional

from database.repositories_async.base import BaseRepository
from database.models import Matter
from config import get_logger

logger = get_logger(__name__).bind(component="matter_repository")


class MatterRepository(BaseRepository):
    """Repository for matter operations

    Provides:
    - Store/update matters with canonical summaries
    - Retrieve matters by ID
    - Update summaries with topic normalization
    - Attachment hash tracking for change detection

    Confidence: 9/10 (standard CRUD with matter-specific deduplication logic)
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
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15)
                ON CONFLICT (id) DO UPDATE SET
                    matter_file = EXCLUDED.matter_file,
                    matter_type = EXCLUDED.matter_type,
                    title = EXCLUDED.title,
                    sponsors = EXCLUDED.sponsors,
                    canonical_summary = EXCLUDED.canonical_summary,
                    canonical_topics = EXCLUDED.canonical_topics,
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
                json.dumps(matter.sponsors) if matter.sponsors else None,
                matter.canonical_summary,
                json.dumps(matter.canonical_topics) if matter.canonical_topics else None,
                json.dumps(matter.attachments) if matter.attachments else None,
                json.dumps(matter.metadata) if matter.metadata else None,
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

            # Deserialize JSONB fields (defensive handling)
            canonical_topics_jsonb = row["canonical_topics"]
            if isinstance(canonical_topics_jsonb, str):
                canonical_topics_jsonb = json.loads(canonical_topics_jsonb)

            return Matter(
                id=row["id"],
                banana=row["banana"],
                matter_id=row["matter_id"],
                matter_file=row["matter_file"],
                matter_type=row["matter_type"],
                title=row["title"],
                sponsors=row["sponsors"],
                canonical_summary=row["canonical_summary"],
                canonical_topics=topics or canonical_topics_jsonb,  # Prefer normalized
                attachments=row["attachments"],
                metadata=row["metadata"],
                first_seen=row["first_seen"],
                last_seen=row["last_seen"],
                appearance_count=row["appearance_count"],
                status=row["status"],
            )

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
