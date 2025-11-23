"""Async ItemRepository for agenda item operations

Handles CRUD operations for agenda items with PostgreSQL optimizations:
- Bulk insertions with ON CONFLICT handling
- Topic normalization (separate item_topics table)
- JSONB for attachments and sponsors
- Efficient matter-based lookups
"""

import json
from typing import List, Optional

from database.repositories_async.base import BaseRepository
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

        Args:
            meeting_id: Meeting ID these items belong to
            items: List of AgendaItem objects

        Returns:
            Number of items stored
        """
        if not items:
            return 0

        stored_count = 0

        async with self.transaction() as conn:
            for item in items:
                # Upsert item row
                await conn.execute(
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
                        summary = EXCLUDED.summary,
                        topics = EXCLUDED.topics
                    """,
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
                stored_count += 1

                # Normalize topics to item_topics table
                if item.topics:
                    await conn.execute(
                        "DELETE FROM item_topics WHERE item_id = $1",
                        item.id,
                    )
                    for topic in item.topics:
                        await conn.execute(
                            """
                            INSERT INTO item_topics (item_id, topic)
                            VALUES ($1, $2)
                            ON CONFLICT DO NOTHING
                            """,
                            item.id,
                            topic,
                        )

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

            # Batch fetch all topics for all items (fix N+1 query)
            item_ids = [row["id"] for row in rows]
            topic_rows = await conn.fetch(
                "SELECT item_id, topic FROM item_topics WHERE item_id = ANY($1::text[])",
                item_ids,
            )

            # Build topic map: item_id -> [topics]
            topics_by_item = {}
            for topic_row in topic_rows:
                item_id = topic_row["item_id"]
                if item_id not in topics_by_item:
                    topics_by_item[item_id] = []
                topics_by_item[item_id].append(topic_row["topic"])

            items = []
            for row in rows:
                topics = topics_by_item.get(row["id"], [])

                attachments = row["attachments"] or []
                sponsors = row["sponsors"] or []

                items.append(
                    AgendaItem(
                        id=row["id"],
                        meeting_id=row["meeting_id"],
                        title=row["title"],
                        sequence=row["sequence"],
                        attachments=attachments or [],
                        attachment_hash=row["attachment_hash"],
                        matter_id=row["matter_id"],
                        matter_file=row["matter_file"],
                        matter_type=row["matter_type"],
                        agenda_number=row["agenda_number"],
                        sponsors=sponsors,
                        summary=row["summary"],
                        topics=topics,  # Single source: normalized item_topics table
                    )
                )

            return items

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
            topic_rows = await conn.fetch(
                "SELECT topic FROM item_topics WHERE item_id = $1",
                row["id"],
            )
            topics = [r["topic"] for r in topic_rows]

            attachments = row["attachments"] or []
            sponsors = row["sponsors"] or []

            return AgendaItem(
                id=row["id"],
                meeting_id=row["meeting_id"],
                title=row["title"],
                sequence=row["sequence"],
                attachments=attachments or [],
                attachment_hash=row["attachment_hash"],
                matter_id=row["matter_id"],
                matter_file=row["matter_file"],
                matter_type=row["matter_type"],
                agenda_number=row["agenda_number"],
                sponsors=sponsors,
                summary=row["summary"],
                topics=topics,  # Single source: normalized item_topics table
            )

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
            async with self.transaction() as conn:
                await conn.execute(
                    "DELETE FROM item_topics WHERE item_id = $1",
                    item_id,
                )
                for topic in kwargs["topics"]:
                    await conn.execute(
                        """
                        INSERT INTO item_topics (item_id, topic)
                        VALUES ($1, $2)
                        ON CONFLICT DO NOTHING
                        """,
                        item_id,
                        topic,
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

            items = []
            for row in rows:
                # Fetch normalized topics
                topic_rows = await conn.fetch(
                    "SELECT topic FROM item_topics WHERE item_id = $1",
                    row["id"],
                )
                topics = [r["topic"] for r in topic_rows]

                attachments = row["attachments"] or []
                sponsors = row["sponsors"] or []

                items.append(
                    AgendaItem(
                        id=row["id"],
                        meeting_id=row["meeting_id"],
                        title=row["title"],
                        sequence=row["sequence"],
                        attachments=attachments or [],
                        attachment_hash=row["attachment_hash"],
                        matter_id=row["matter_id"],
                        matter_file=row["matter_file"],
                        matter_type=row["matter_type"],
                        agenda_number=row["agenda_number"],
                        sponsors=sponsors,
                        summary=row["summary"],
                        topics=topics,  # Single source: normalized item_topics table
                    )
                )

            return items

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

        # Parse result tag to get count (e.g., "UPDATE 5" -> 5)
        updated_count = int(result.split()[-1]) if result else 0
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

            items = []
            for row in rows:
                # Parse JSONB fields
                attachments = row["attachments"] or []
                sponsors = row["sponsors"] or []

                # Get normalized topics
                topic_rows = await conn.fetch(
                    "SELECT topic FROM item_topics WHERE item_id = $1",
                    row["id"],
                )
                topics = [t["topic"] for t in topic_rows]

                items.append(
                    AgendaItem(
                        id=row["id"],
                        meeting_id=row["meeting_id"],
                        title=row["title"],
                        sequence=row["sequence"],
                        attachments=attachments or [],
                        summary=row["summary"],
                        topics=topics,
                        matter_id=row["matter_id"],
                        matter_file=row["matter_file"],
                        matter_type=row["matter_type"],
                        agenda_number=row["agenda_number"],
                        sponsors=sponsors,
                        attachment_hash=row["attachment_hash"],
                    )
                )

            return items
