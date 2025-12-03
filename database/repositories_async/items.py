"""Async ItemRepository for agenda item operations

Handles CRUD operations for agenda items with PostgreSQL optimizations:
- Bulk insertions with ON CONFLICT handling
- Topic normalization (separate item_topics table)
- JSONB for attachments and sponsors
- Efficient matter-based lookups
"""

from collections import defaultdict
from typing import Dict, List, Optional

from database.repositories_async.base import BaseRepository
from database.repositories_async.helpers import build_agenda_item, fetch_topics_for_ids
from database.models import AgendaItem
from config import get_logger

logger = get_logger(__name__).bind(component="item_repository")


class ItemRepository(BaseRepository):
    """Repository for agenda item operations

    Provides:
    - Bulk item storage (with topic normalization)
    - Single item retrieval
    - Matter-based queries (get all items for a matter)
    - Bulk updates for canonical summaries
    - Topic-based filtering
    """

    async def store_agenda_items(self, meeting_id: str, items: List[AgendaItem]) -> int:
        """Store multiple agenda items (bulk insert with topic normalization)

        Optimized with executemany() for 2-3x speedup over individual inserts.
        Cannot use COPY due to ON CONFLICT requirement (UPSERT for re-syncs).

        Args:
            meeting_id: Meeting ID these items belong to
            items: List of AgendaItem objects

        Returns:
            Number of items stored
        """
        if not items:
            return 0

        async with self.transaction() as conn:
            # Batch upsert items using executemany()
            item_records = [
                (
                    item.id,
                    item.meeting_id,
                    item.title,
                    item.sequence,
                    item.attachments,
                    item.attachment_hash,
                    item.matter_id,
                    item.matter_file,
                    item.matter_type,
                    item.agenda_number,
                    item.sponsors,
                    item.summary,
                    item.topics,
                )
                for item in items
            ]

            await conn.executemany(
                """
                INSERT INTO items (
                    id, meeting_id, title, sequence, attachments,
                    attachment_hash, matter_id, matter_file, matter_type,
                    agenda_number, sponsors, summary, topics
                )
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13)
                ON CONFLICT (id) DO UPDATE SET
                    title = EXCLUDED.title,
                    sequence = EXCLUDED.sequence,
                    attachments = EXCLUDED.attachments,
                    attachment_hash = EXCLUDED.attachment_hash,
                    matter_id = EXCLUDED.matter_id,
                    matter_file = EXCLUDED.matter_file,
                    matter_type = EXCLUDED.matter_type,
                    agenda_number = EXCLUDED.agenda_number,
                    sponsors = EXCLUDED.sponsors,
                    summary = COALESCE(EXCLUDED.summary, items.summary),
                    topics = COALESCE(EXCLUDED.topics, items.topics)
                """,
                item_records,
            )

            # Batch normalize topics to item_topics table
            # First, collect all items with topics and delete their existing topics
            items_with_topics = [item for item in items if item.topics]
            if items_with_topics:
                # Batch delete existing topics
                item_ids_with_topics = [item.id for item in items_with_topics]
                await conn.execute(
                    "DELETE FROM item_topics WHERE item_id = ANY($1::text[])",
                    item_ids_with_topics,
                )

                # Batch insert new topics
                topic_records = [
                    (item.id, topic)
                    for item in items_with_topics
                    for topic in (item.topics or [])
                ]
                if topic_records:
                    await conn.executemany(
                        """
                        INSERT INTO item_topics (item_id, topic)
                        VALUES ($1, $2)
                        ON CONFLICT DO NOTHING
                        """,
                        topic_records,
                    )

        stored_count = len(items)
        logger.debug("stored agenda items", count=stored_count, meeting_id=meeting_id)
        return stored_count

    async def get_agenda_items(
        self, meeting_id: str, load_matters: bool = False
    ) -> List[AgendaItem]:
        """Get all agenda items for a meeting

        Args:
            meeting_id: Meeting identifier
            load_matters: If True, eagerly load Matter objects (not yet implemented)

        Returns:
            List of AgendaItem objects with denormalized topics
        """
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT
                    id, meeting_id, title, sequence, attachments,
                    attachment_hash, matter_id, matter_file, matter_type,
                    agenda_number, sponsors, summary, topics
                FROM items
                WHERE meeting_id = $1
                ORDER BY sequence
                """,
                meeting_id,
            )

            if not rows:
                return []

            # Batch fetch all topics
            item_ids = [row["id"] for row in rows]
            topics_by_item = await fetch_topics_for_ids(
                conn, "item_topics", "item_id", item_ids
            )

            return [
                build_agenda_item(row, topics_by_item.get(row["id"], []))
                for row in rows
            ]

    async def get_items_for_meetings(
        self, meeting_ids: List[str]
    ) -> Dict[str, List[AgendaItem]]:
        """Batch fetch items for multiple meetings - eliminates N+1

        Args:
            meeting_ids: List of meeting identifiers

        Returns:
            Dict mapping meeting_id to list of AgendaItem objects
        """
        if not meeting_ids:
            return {}

        async with self.pool.acquire() as conn:
            # Single query for ALL items across ALL meetings
            rows = await conn.fetch(
                """
                SELECT
                    id, meeting_id, title, sequence, attachments,
                    attachment_hash, matter_id, matter_file, matter_type,
                    agenda_number, sponsors, summary, topics
                FROM items
                WHERE meeting_id = ANY($1::text[])
                ORDER BY meeting_id, sequence
                """,
                meeting_ids,
            )

            if not rows:
                return {}

            # Batch fetch all topics
            item_ids = [row["id"] for row in rows]
            topics_by_item = await fetch_topics_for_ids(
                conn, "item_topics", "item_id", item_ids
            )

            # Build items grouped by meeting
            items_by_meeting: Dict[str, List[AgendaItem]] = defaultdict(list)
            for row in rows:
                item = build_agenda_item(row, topics_by_item.get(row["id"], []))
                items_by_meeting[row["meeting_id"]].append(item)

            return dict(items_by_meeting)

    async def get_agenda_item(self, item_id: str) -> Optional[AgendaItem]:
        """Get a single agenda item by ID

        Args:
            item_id: Item identifier

        Returns:
            AgendaItem object or None
        """
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT
                    id, meeting_id, title, sequence, attachments,
                    attachment_hash, matter_id, matter_file, matter_type,
                    agenda_number, sponsors, summary, topics
                FROM items
                WHERE id = $1
                """,
                item_id,
            )

            if not row:
                return None

            # Fetch normalized topics
            topics_map = await fetch_topics_for_ids(
                conn, "item_topics", "item_id", [item_id]
            )

            return build_agenda_item(row, topics_map.get(item_id, []))

    async def update_agenda_item(
        self,
        item_id: str,
        summary: Optional[str] = None,
        topics: Optional[List[str]] = None,
        **kwargs
    ) -> None:
        """Update agenda item fields

        Args:
            item_id: Item identifier
            summary: Item summary text (optional)
            topics: Item topics list (optional)
            **kwargs: Additional fields to update
        """
        # Merge positional args into kwargs
        if summary is not None:
            kwargs["summary"] = summary
        if topics is not None:
            kwargs["topics"] = topics

        if not kwargs:
            return

        # Build dynamic UPDATE query
        set_clauses = []
        values = []
        param_num = 1

        for key, value in kwargs.items():
            if key == "topics":
                # Handle topics separately (normalized table)
                continue
            set_clauses.append(f"{key} = ${param_num}")
            values.append(value)
            param_num += 1

        # Execute main update if we have fields
        if set_clauses:
            values.append(item_id)  # WHERE clause parameter
            query = f"""
                UPDATE items
                SET {', '.join(set_clauses)}
                WHERE id = ${param_num}
            """
            await self._execute(query, *values)

        # Handle topics normalization
        if "topics" in kwargs and kwargs["topics"]:
            topic_records = [(item_id, topic) for topic in kwargs["topics"]]
            async with self.transaction() as conn:
                await conn.execute(
                    "DELETE FROM item_topics WHERE item_id = $1",
                    item_id,
                )
                await conn.executemany(
                    """
                    INSERT INTO item_topics (item_id, topic)
                    VALUES ($1, $2)
                    ON CONFLICT DO NOTHING
                    """,
                    topic_records,
                )

        logger.debug("updated agenda item", item_id=item_id, fields=list(kwargs.keys()))

    async def get_all_items_for_matter(self, matter_id: str) -> List[AgendaItem]:
        """Get ALL agenda items across ALL meetings for a given matter

        Used by processor for matter-based processing.

        Args:
            matter_id: Composite matter ID (e.g., "nashvilleTN_7a8f3b2c1d9e4f5a")

        Returns:
            List of ALL AgendaItem objects for this matter across all meetings
        """
        if not matter_id:
            return []

        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT
                    id, meeting_id, title, sequence, attachments,
                    attachment_hash, matter_id, matter_file, matter_type,
                    agenda_number, sponsors, summary, topics
                FROM items
                WHERE matter_id = $1
                ORDER BY meeting_id, sequence
                """,
                matter_id,
            )

            if not rows:
                return []

            # Batch fetch all topics
            item_ids = [row["id"] for row in rows]
            topics_by_item = await fetch_topics_for_ids(
                conn, "item_topics", "item_id", item_ids
            )

            return [
                build_agenda_item(row, topics_by_item.get(row["id"], []))
                for row in rows
            ]

    async def bulk_update_item_summaries(
        self, item_ids: List[str], summary: str, topics: List[str]
    ) -> int:
        """Bulk update multiple agenda items with canonical summary and topics

        Used for matters-first processing where multiple items share a canonical summary.
        PostgreSQL-optimized using unnest() for efficient bulk updates.

        Args:
            item_ids: List of agenda item IDs to update
            summary: The canonical summary to apply to all items
            topics: List of normalized topics to apply to all items

        Returns:
            Number of items updated
        """
        if not item_ids:
            return 0

        async with self.transaction() as conn:
            # Bulk update items (single query)
            result = await conn.execute(
                """
                UPDATE items
                SET summary = $1, topics = $2
                WHERE id = ANY($3::text[])
                """,
                summary,
                topics,
                item_ids,
            )

            # Delete existing topics for all items
            await conn.execute(
                "DELETE FROM item_topics WHERE item_id = ANY($1::text[])",
                item_ids,
            )

            # Bulk insert topics (if provided)
            if topics:
                # Use executemany for bulk insert
                topic_params = [
                    (item_id, topic)
                    for item_id in item_ids
                    for topic in topics
                ]
                await conn.executemany(
                    """
                    INSERT INTO item_topics (item_id, topic)
                    VALUES ($1, $2)
                    ON CONFLICT DO NOTHING
                    """,
                    topic_params,
                )

        updated_count = self._parse_row_count(result)
        logger.debug("bulk updated items with canonical summary", count=updated_count)
        return updated_count

    async def get_items_by_topic(self, meeting_id: str, topic: str) -> List[AgendaItem]:
        """Get agenda items for a meeting filtered by topic

        Args:
            meeting_id: Meeting identifier
            topic: Topic to filter by

        Returns:
            List of AgendaItem objects matching topic
        """
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT DISTINCT i.*
                FROM items i
                JOIN item_topics it ON i.id = it.item_id
                WHERE i.meeting_id = $1 AND it.topic = $2
                ORDER BY i.sequence
                """,
                meeting_id,
                topic,
            )

            if not rows:
                return []

            # Batch fetch all topics
            item_ids = [row["id"] for row in rows]
            topics_by_item = await fetch_topics_for_ids(
                conn, "item_topics", "item_id", item_ids
            )

            return [
                build_agenda_item(row, topics_by_item.get(row["id"], []))
                for row in rows
            ]
