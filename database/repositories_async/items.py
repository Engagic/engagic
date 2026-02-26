"""Async ItemRepository for agenda item operations."""

from collections import defaultdict
from typing import Dict, List, Optional

from asyncpg import Connection

from database.repositories_async.base import BaseRepository
from database.repositories_async.helpers import (
    build_agenda_item,
    fetch_topics_for_ids,
    replace_entity_topics,
    replace_entity_topics_batch,
)
from database.models import AgendaItem
from config import get_logger

logger = get_logger(__name__).bind(component="item_repository")


class ItemRepository(BaseRepository):
    """Repository for agenda item operations."""

    def _dedupe_items_by_matter(self, items: List[AgendaItem]) -> List[AgendaItem]:
        """Deduplicate items by matter_id within the same meeting.

        When multiple items reference the same matter (e.g., Legistar returning
        duplicate agenda entries), keep only the one with the most data.

        Scoring: prefer items with agenda_number, summary, attachments, topics.
        """
        if not items:
            return items

        # Group items by matter_id (None matter_id items are kept as-is)
        by_matter: Dict[Optional[str], List[AgendaItem]] = defaultdict(list)
        no_matter_items = []

        for item in items:
            if item.matter_id:
                by_matter[item.matter_id].append(item)
            else:
                no_matter_items.append(item)

        # For each matter, keep the item with the most data
        deduped = []
        duplicates_removed = 0

        for matter_id, matter_items in by_matter.items():
            if len(matter_items) == 1:
                deduped.append(matter_items[0])
            else:
                # Score each item by data completeness
                def score_item(item: AgendaItem) -> int:
                    score = 0
                    if item.agenda_number:
                        score += 10
                    if item.summary:
                        score += 5
                    if item.attachments:
                        score += len(item.attachments)
                    if item.topics:
                        score += len(item.topics)
                    if item.sponsors:
                        score += 2
                    return score

                best_item = max(matter_items, key=score_item)
                deduped.append(best_item)
                duplicates_removed += len(matter_items) - 1

        if duplicates_removed > 0:
            logger.info(
                "deduplicated items by matter_id",
                duplicates_removed=duplicates_removed,
                original_count=len(items),
                deduped_count=len(deduped) + len(no_matter_items),
            )

        return deduped + no_matter_items

    def dedupe_items_by_matter(self, items: List[AgendaItem]) -> List[AgendaItem]:
        """Public wrapper for item deduplication. Call before store_agenda_items."""
        return self._dedupe_items_by_matter(items)

    async def store_agenda_items(
        self, meeting_id: str, items: List[AgendaItem], conn: Optional[Connection] = None
    ) -> int:
        """Store multiple agenda items. Items should already be deduped via dedupe_items_by_matter()."""
        if not items:
            return 0

        async with self._ensure_conn(conn) as c:
            # Batch upsert items using executemany()
            item_records = [
                (
                    item.id,
                    item.meeting_id,
                    item.title,
                    item.sequence,
                    item.attachments,
                    item.attachment_hash,
                    item.body_text,
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

            await c.executemany(
                """
                INSERT INTO items (
                    id, meeting_id, title, sequence, attachments,
                    attachment_hash, body_text, matter_id, matter_file, matter_type,
                    agenda_number, sponsors, summary, topics
                )
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14)
                ON CONFLICT (id) DO UPDATE SET
                    title = EXCLUDED.title,
                    sequence = EXCLUDED.sequence,
                    attachments = EXCLUDED.attachments,
                    attachment_hash = EXCLUDED.attachment_hash,
                    body_text = COALESCE(EXCLUDED.body_text, items.body_text),
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
            items_with_topics = {
                item.id: item.topics
                for item in items
                if item.topics
            }
            if items_with_topics:
                await replace_entity_topics_batch(
                    c, "item_topics", "item_id", items_with_topics
                )

        logger.debug("stored agenda items", count=len(items), meeting_id=meeting_id)
        return len(items)

    async def get_agenda_items(
        self, meeting_id: str, load_matters: bool = False
    ) -> List[AgendaItem]:
        """Get all agenda items for a meeting."""
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT
                    id, meeting_id, title, sequence, attachments,
                    attachment_hash, body_text, matter_id, matter_file, matter_type,
                    agenda_number, sponsors, summary, topics, quality_score, rating_count
                FROM items
                WHERE meeting_id = $1
                ORDER BY sequence
                """,
                meeting_id,
            )

            if not rows:
                return []

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
        """Batch fetch items for multiple meetings - eliminates N+1."""
        if not meeting_ids:
            return {}

        async with self.pool.acquire() as conn:
            # Single query for ALL items across ALL meetings
            rows = await conn.fetch(
                """
                SELECT
                    id, meeting_id, title, sequence, attachments,
                    attachment_hash, body_text, matter_id, matter_file, matter_type,
                    agenda_number, sponsors, summary, topics, quality_score, rating_count
                FROM items
                WHERE meeting_id = ANY($1::text[])
                ORDER BY meeting_id, sequence
                """,
                meeting_ids,
            )

            if not rows:
                return {}

            item_ids = [row["id"] for row in rows]
            topics_by_item = await fetch_topics_for_ids(
                conn, "item_topics", "item_id", item_ids
            )

            items_by_meeting: Dict[str, List[AgendaItem]] = defaultdict(list)
            for row in rows:
                item = build_agenda_item(row, topics_by_item.get(row["id"], []))
                items_by_meeting[row["meeting_id"]].append(item)

            return dict(items_by_meeting)

    async def get_has_summarized_items(
        self, meeting_ids: List[str]
    ) -> Dict[str, bool]:
        """Check which meetings have items with summaries - lightweight for listings.

        Returns dict mapping meeting_id -> True if has summarized items.
        Much faster than get_items_for_meetings when you only need to know
        if items exist, not their content.
        """
        if not meeting_ids:
            return {}

        async with self.pool.acquire() as conn:
            # Single aggregate query - no item content loaded
            rows = await conn.fetch(
                """
                SELECT meeting_id, bool_or(summary IS NOT NULL) as has_summary
                FROM items
                WHERE meeting_id = ANY($1::text[])
                GROUP BY meeting_id
                """,
                meeting_ids,
            )

            return {row["meeting_id"]: row["has_summary"] for row in rows}

    async def get_agenda_item(self, item_id: str) -> Optional[AgendaItem]:
        """Get a single agenda item by ID."""
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT
                    id, meeting_id, title, sequence, attachments,
                    attachment_hash, body_text, matter_id, matter_file, matter_type,
                    agenda_number, sponsors, summary, topics, quality_score, rating_count
                FROM items
                WHERE id = $1
                """,
                item_id,
            )

            if not row:
                return None

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
        """Update agenda item fields.

        Uses single transaction for both item update and topics update
        to prevent race conditions where item updates but topics fail.
        """
        if summary is not None:
            kwargs["summary"] = summary
        if topics is not None:
            kwargs["topics"] = topics

        if not kwargs:
            return

        set_clauses = []
        values = []
        param_num = 1

        for key, value in kwargs.items():
            if key == "topics":
                continue  # topics handled via normalized table
            set_clauses.append(f"{key} = ${param_num}")
            values.append(value)
            param_num += 1

        # Single transaction for both item update and topics update
        async with self.transaction() as conn:
            if set_clauses:
                values.append(item_id)  # WHERE clause parameter
                query = f"""
                    UPDATE items
                    SET {', '.join(set_clauses)}
                    WHERE id = ${param_num}
                """
                await conn.execute(query, *values)

            if "topics" in kwargs and kwargs["topics"]:
                await replace_entity_topics(
                    conn, "item_topics", "item_id", item_id, kwargs["topics"]
                )

        logger.debug("updated agenda item", item_id=item_id, fields=list(kwargs.keys()))

    async def get_all_items_for_matter(self, matter_id: str) -> List[AgendaItem]:
        """Get all agenda items across all meetings for a given matter."""
        if not matter_id:
            return []

        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT
                    id, meeting_id, title, sequence, attachments,
                    attachment_hash, body_text, matter_id, matter_file, matter_type,
                    agenda_number, sponsors, summary, topics, quality_score, rating_count
                FROM items
                WHERE matter_id = $1
                ORDER BY meeting_id, sequence
                """,
                matter_id,
            )

            if not rows:
                return []

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
        """Bulk update multiple agenda items with canonical summary and topics."""
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

            if topics:
                entity_topics = {item_id: topics for item_id in item_ids}
                await replace_entity_topics_batch(
                    conn, "item_topics", "item_id", entity_topics
                )

        updated_count = self._parse_row_count(result)
        logger.debug("bulk updated items with canonical summary", count=updated_count)
        return updated_count

    async def get_items_by_topic(self, meeting_id: str, topic: str) -> List[AgendaItem]:
        """Get agenda items for a meeting filtered by topic."""
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

            item_ids = [row["id"] for row in rows]
            topics_by_item = await fetch_topics_for_ids(
                conn, "item_topics", "item_id", item_ids
            )

            return [
                build_agenda_item(row, topics_by_item.get(row["id"], []))
                for row in rows
            ]

    async def search_by_keyword(
        self,
        banana: str,
        keyword: str,
        since_date,
        exclude_cancelled: bool = True
    ) -> List[Dict]:
        """
        Search items by keyword in summary, with meeting context.

        Used by userland matching engine.
        Returns raw dicts with both item and meeting fields for flexibility.

        Args:
            banana: City banana identifier
            keyword: Keyword to search (case-insensitive LIKE match)
            since_date: Only include items from meetings after this date
            exclude_cancelled: Filter out cancelled/postponed meetings

        Returns:
            List of dicts with item and meeting fields
        """
        status_filter = "AND (m.status IS NULL OR m.status NOT IN ('cancelled', 'postponed'))" if exclude_cancelled else ""

        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                f"""
                SELECT i.id, i.meeting_id, i.title, i.summary,
                       i.agenda_number, i.matter_file, i.sequence,
                       m.title as meeting_title, m.date, m.banana,
                       m.agenda_url, m.status,
                       c.name as city_name, c.state
                FROM items i
                JOIN meetings m ON i.meeting_id = m.id
                JOIN cities c ON m.banana = c.banana
                WHERE m.banana = $1
                  AND m.date >= $2
                  {status_filter}
                  AND i.summary LIKE $3
                ORDER BY m.date DESC
                """,
                banana,
                since_date,
                f"%{keyword}%",
            )

            return [dict(row) for row in rows]

    async def search_upcoming_by_keyword(
        self,
        banana: str,
        keyword: str,
        start_date,
        end_date
    ) -> List[Dict]:
        """
        Search items by keyword in upcoming meetings (date range).

        Used by weekly digest for forward-looking keyword matches.

        Args:
            banana: City banana identifier
            keyword: Keyword to search (case-insensitive LIKE match)
            start_date: Start of date range
            end_date: End of date range

        Returns:
            List of dicts with item and meeting fields
        """
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT i.id as item_id, i.meeting_id, i.title as item_title,
                       i.summary, i.agenda_number, i.matter_file, i.sequence,
                       m.title as meeting_title, m.date, m.banana,
                       m.agenda_url, m.status
                FROM items i
                JOIN meetings m ON i.meeting_id = m.id
                WHERE m.banana = $1
                  AND m.date >= $2
                  AND m.date <= $3
                  AND (m.status IS NULL OR m.status NOT IN ('cancelled', 'postponed'))
                  AND i.summary LIKE $4
                ORDER BY m.date ASC
                """,
                banana,
                start_date,
                end_date,
                f"%{keyword}%",
            )

            return [dict(row) for row in rows]
