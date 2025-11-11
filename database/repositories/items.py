"""
Agenda Item Repository - Item operations

Handles all agenda item database operations including storage,
retrieval, and updates for item-level summaries.
"""

import logging
import json
from typing import List

from database.repositories.base import BaseRepository
from database.models import AgendaItem
from exceptions import DatabaseConnectionError

logger = logging.getLogger("engagic")


class ItemRepository(BaseRepository):
    """Repository for agenda item operations"""

    def store_agenda_items(self, meeting_id: str, items: List[AgendaItem]) -> int:
        """
        Store agenda items for a meeting.

        CRITICAL: Preserves existing summaries/topics on conflict.
        Only updates structural fields (title, sequence, attachments).

        Args:
            meeting_id: The meeting ID these items belong to
            items: List of AgendaItem objects

        Returns:
            Number of items stored
        """
        if self.conn is None:
            raise DatabaseConnectionError("Database connection not established")

        stored_count = 0

        for item in items:
            # Serialize JSON fields
            attachments_json = (
                json.dumps(item.attachments) if item.attachments else None
            )
            topics_json = json.dumps(item.topics) if item.topics else None
            sponsors_json = json.dumps(item.sponsors) if item.sponsors else None

            self._execute(
                """
                INSERT INTO items (id, meeting_id, title, sequence, attachments,
                                   matter_id, matter_file, matter_type, agenda_number,
                                   sponsors, summary, topics)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    title = excluded.title,
                    sequence = excluded.sequence,
                    attachments = excluded.attachments,
                    matter_id = excluded.matter_id,
                    matter_file = excluded.matter_file,
                    matter_type = excluded.matter_type,
                    agenda_number = excluded.agenda_number,
                    sponsors = excluded.sponsors,
                    -- PRESERVE existing summary/topics if new values are NULL
                    summary = CASE
                        WHEN excluded.summary IS NOT NULL THEN excluded.summary
                        ELSE items.summary
                    END,
                    topics = CASE
                        WHEN excluded.topics IS NOT NULL THEN excluded.topics
                        ELSE items.topics
                    END
            """,
                (
                    item.id,
                    meeting_id,
                    item.title,
                    item.sequence,
                    attachments_json,
                    item.matter_id,
                    item.matter_file,
                    item.matter_type,
                    item.agenda_number,
                    sponsors_json,
                    item.summary,
                    topics_json,
                ),
            )
            stored_count += 1

        self._commit()
        logger.debug(f"Stored {stored_count} agenda items for meeting {meeting_id}")
        return stored_count

    def get_agenda_items(self, meeting_id: str) -> List[AgendaItem]:
        """
        Get all agenda items for a meeting, ordered by sequence.

        Args:
            meeting_id: The meeting ID

        Returns:
            List of AgendaItem objects
        """
        if self.conn is None:
            raise DatabaseConnectionError("Database connection not established")

        rows = self._fetch_all(
            """
            SELECT * FROM items
            WHERE meeting_id = ?
            ORDER BY sequence ASC
        """,
            (meeting_id,),
        )

        return [AgendaItem.from_db_row(row) for row in rows]

    def update_agenda_item(self, item_id: str, summary: str, topics: List[str]) -> None:
        """
        Update an agenda item with processed summary and topics.

        Args:
            item_id: The agenda item ID
            summary: The processed summary
            topics: List of extracted topics
        """
        if self.conn is None:
            raise DatabaseConnectionError("Database connection not established")

        topics_json = json.dumps(topics) if topics else None

        self._execute(
            """
            UPDATE items
            SET summary = ?,
                topics = ?
            WHERE id = ?
        """,
            (summary, topics_json, item_id),
        )

        self._commit()
        logger.debug(f"Updated agenda item {item_id} with summary and topics")
