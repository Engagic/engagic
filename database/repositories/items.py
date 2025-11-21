"""
Agenda Item Repository - Item operations

Handles all agenda item database operations including storage,
retrieval, and updates for item-level summaries.
"""

import json
from typing import List

from config import get_logger
from database.repositories.base import BaseRepository
from database.models import AgendaItem
from exceptions import DatabaseConnectionError

logger = get_logger(__name__).bind(component="database")


class ItemRepository(BaseRepository):
    """Repository for agenda item operations"""

    def store_agenda_items(self, meeting_id: str, items: List[AgendaItem], defer_commit: bool = False) -> int:
        """
        Store agenda items for a meeting.

        CRITICAL: Preserves existing summaries/topics on conflict.
        Only updates structural fields (title, sequence, attachments).

        Args:
            meeting_id: The meeting ID these items belong to
            items: List of AgendaItem objects
            defer_commit: If True, skip commit (caller handles transaction)

        Returns:
            Number of items stored
        """
        if self.conn is None:
            raise DatabaseConnectionError("Database connection not established")

        from database.id_generation import validate_matter_id

        stored_count = 0

        for item in items:
            # Defensive: validate matter_id format before storing
            if item.matter_id:
                if not validate_matter_id(item.matter_id):
                    logger.error(
                        f"[Items] CRITICAL: Refusing to store item {item.id} with invalid matter_id format: '{item.matter_id}'"
                    )
                    continue  # Skip this item, don't store broken data

            # Serialize JSON fields
            attachments_json = (
                json.dumps(item.attachments) if item.attachments else None
            )
            topics_json = json.dumps(item.topics) if item.topics else None
            sponsors_json = json.dumps(item.sponsors) if item.sponsors else None

            try:
                self._execute(
                    """
                    INSERT INTO items (id, meeting_id, title, sequence, attachments, attachment_hash,
                                       matter_id, matter_file, matter_type, agenda_number,
                                       sponsors, summary, topics)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(id) DO UPDATE SET
                        title = excluded.title,
                        sequence = excluded.sequence,
                        attachments = excluded.attachments,
                        attachment_hash = excluded.attachment_hash,
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
                        item.attachment_hash,
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
            except Exception as e:
                # Catch FK constraint violations and log clearly
                error_msg = str(e)
                if "FOREIGN KEY constraint failed" in error_msg:
                    logger.error(
                        f"[Items] FK CONSTRAINT FAILED for item {item.id}: matter_id '{item.matter_id}' "
                        f"does not exist in city_matters table. Matter tracking broken for this item."
                    )
                else:
                    logger.error(f"[Items] Failed to store item {item.id}: {e}")
                # Propagate error to trigger transaction rollback
                raise

        if not defer_commit:
            self._commit()
        logger.debug(f"Stored {stored_count} agenda items for meeting {meeting_id}")
        return stored_count

    def get_agenda_items(self, meeting_id: str, load_matters: bool = False) -> List[AgendaItem]:
        """
        Get all agenda items for a meeting, ordered by sequence.

        Args:
            meeting_id: The meeting ID
            load_matters: If True, eagerly load Matter objects for items (default: False)

        Returns:
            List of AgendaItem objects (with matter field populated if load_matters=True)
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

        items = [AgendaItem.from_db_row(row) for row in rows]

        # Eager load matters if requested
        if load_matters:
            # Get all unique matter_ids from items
            matter_ids = {item.matter_id for item in items if item.matter_id}

            if matter_ids:
                # Fetch all matters in a single query
                placeholders = ",".join("?" * len(matter_ids))
                matter_rows = self._fetch_all(
                    f"SELECT * FROM city_matters WHERE id IN ({placeholders})",
                    tuple(matter_ids),
                )

                # Build matter lookup map
                from database.models import Matter
                matters_map = {Matter.from_db_row(row).id: Matter.from_db_row(row) for row in matter_rows}

                # Populate matter field on items
                for item in items:
                    if item.matter_id and item.matter_id in matters_map:
                        item.matter = matters_map[item.matter_id]

        return items

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

    def bulk_update_item_summaries(
        self, item_ids: List[str], summary: str, topics: List[str], defer_commit: bool = False
    ) -> int:
        """
        Bulk update multiple agenda items with the same summary and topics.

        Used for matters-first processing where multiple items share a canonical summary.

        Args:
            item_ids: List of agenda item IDs to update
            summary: The canonical summary to apply
            topics: List of normalized topics
            defer_commit: If True, skip commit (caller handles transaction)

        Returns:
            Number of items updated
        """
        if self.conn is None:
            raise DatabaseConnectionError("Database connection not established")

        if not item_ids:
            return 0

        topics_json = json.dumps(topics) if topics else None
        updated_count = 0

        for item_id in item_ids:
            self._execute(
                """
                UPDATE items
                SET summary = ?, topics = ?
                WHERE id = ?
                """,
                (summary, topics_json, item_id),
            )
            updated_count += 1

        if not defer_commit:
            self._commit()

        logger.debug(f"Bulk updated {updated_count} items with canonical summary")
        return updated_count
