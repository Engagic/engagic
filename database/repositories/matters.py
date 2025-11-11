"""
Matter Repository - Matter operations

Handles all matter database operations including storage,
retrieval, and canonical summary management for matters-first architecture.
"""

import logging
import json
from typing import List, Optional

from database.repositories.base import BaseRepository
from database.models import Matter, DatabaseConnectionError

logger = logging.getLogger("engagic")


class MatterRepository(BaseRepository):
    """Repository for matter operations"""

    def store_matter(self, matter: Matter) -> bool:
        """
        Store or update a matter.

        CRITICAL: Preserves existing canonical_summary on conflict.
        Only updates structural fields (title, attachments, metadata).

        Args:
            matter: Matter object to store

        Returns:
            True if stored successfully
        """
        if self.conn is None:
            raise DatabaseConnectionError("Database connection not established")

        # Serialize JSON fields
        canonical_topics_json = (
            json.dumps(matter.canonical_topics) if matter.canonical_topics else None
        )
        attachments_json = (
            json.dumps(matter.attachments) if matter.attachments else None
        )
        metadata_json = json.dumps(matter.metadata) if matter.metadata else None

        self._execute(
            """
            INSERT INTO city_matters (id, banana, matter_file, matter_id, matter_type,
                                      title, canonical_summary, canonical_topics,
                                      attachments, metadata)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                title = excluded.title,
                attachments = excluded.attachments,
                metadata = excluded.metadata,
                updated_at = CURRENT_TIMESTAMP,
                -- PRESERVE existing canonical summary/topics if new values are NULL
                canonical_summary = CASE
                    WHEN excluded.canonical_summary IS NOT NULL THEN excluded.canonical_summary
                    ELSE city_matters.canonical_summary
                END,
                canonical_topics = CASE
                    WHEN excluded.canonical_topics IS NOT NULL THEN excluded.canonical_topics
                    ELSE city_matters.canonical_topics
                END
        """,
            (
                matter.id,
                matter.banana,
                matter.matter_file,
                matter.matter_id,
                matter.matter_type,
                matter.title,
                matter.canonical_summary,
                canonical_topics_json,
                attachments_json,
                metadata_json,
            ),
        )

        self._commit()
        logger.debug(f"Stored matter {matter.id}")
        return True

    def get_matter(self, matter_id: str) -> Optional[Matter]:
        """
        Get a matter by its composite ID.

        Args:
            matter_id: Composite matter ID (banana_matter_key)

        Returns:
            Matter object or None if not found
        """
        if self.conn is None:
            raise DatabaseConnectionError("Database connection not established")

        row = self._fetch_one(
            """
            SELECT * FROM city_matters
            WHERE id = ?
        """,
            (matter_id,),
        )

        return Matter.from_db_row(row) if row else None

    def get_matters_by_city(self, banana: str, include_processed: bool = True) -> List[Matter]:
        """
        Get all matters for a city.

        Args:
            banana: City identifier
            include_processed: If False, only return matters without canonical_summary

        Returns:
            List of Matter objects
        """
        if self.conn is None:
            raise DatabaseConnectionError("Database connection not established")

        query = """
            SELECT * FROM city_matters
            WHERE banana = ?
        """

        if not include_processed:
            query += " AND canonical_summary IS NULL"

        query += " ORDER BY created_at DESC"

        rows = self._fetch_all(query, (banana,))
        return [Matter.from_db_row(row) for row in rows]

    def get_matter_by_keys(
        self, banana: str, matter_file: Optional[str] = None, matter_id: Optional[str] = None
    ) -> Optional[Matter]:
        """
        Get a matter by matter_file or matter_id.

        Args:
            banana: City identifier
            matter_file: Official matter file (25-1234, BL2025-1098)
            matter_id: Backend matter ID (UUID, numeric)

        Returns:
            Matter object or None if not found
        """
        if self.conn is None:
            raise DatabaseConnectionError("Database connection not established")

        if not matter_file and not matter_id:
            return None

        # Prefer matter_file over matter_id
        if matter_file:
            row = self._fetch_one(
                """
                SELECT * FROM city_matters
                WHERE banana = ? AND matter_file = ?
            """,
                (banana, matter_file),
            )
        else:
            row = self._fetch_one(
                """
                SELECT * FROM city_matters
                WHERE banana = ? AND matter_id = ?
            """,
                (banana, matter_id),
            )

        return Matter.from_db_row(row) if row else None

    def update_matter_summary(
        self, matter_id: str, canonical_summary: str, canonical_topics: List[str], attachment_hash: str
    ) -> None:
        """
        Update matter with canonical summary, topics, and attachment hash.

        Args:
            matter_id: Composite matter ID
            canonical_summary: Deduplicated summary
            canonical_topics: Extracted topics
            attachment_hash: SHA256 hash of attachments
        """
        if self.conn is None:
            raise DatabaseConnectionError("Database connection not established")

        topics_json = json.dumps(canonical_topics) if canonical_topics else None

        self._execute(
            """
            UPDATE city_matters
            SET canonical_summary = ?,
                canonical_topics = ?,
                metadata = json_set(COALESCE(metadata, '{}'), '$.attachment_hash', ?),
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
        """,
            (canonical_summary, topics_json, attachment_hash, matter_id),
        )

        self._commit()
        logger.debug(f"Updated matter {matter_id} with canonical summary")
