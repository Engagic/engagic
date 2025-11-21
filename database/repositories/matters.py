"""
Matter Repository - Matter operations

Handles all matter database operations including storage,
retrieval, and canonical summary management for matters-first architecture.
"""

import json
from typing import List, Optional

from config import get_logger
from database.repositories.base import BaseRepository
from database.models import Matter
from exceptions import DatabaseConnectionError
from database.id_generation import generate_matter_id, validate_matter_id

logger = get_logger(__name__).bind(component="database")


class MatterRepository(BaseRepository):
    """Repository for matter operations"""

    def store_matter(self, matter: Matter, defer_commit: bool = False) -> bool:
        """
        Store or update a matter.

        CRITICAL: Preserves existing canonical_summary on conflict.
        Only updates structural fields (title, attachments, metadata).

        Args:
            matter: Matter object to store
            defer_commit: If True, skip commit (caller handles transaction)

        Returns:
            True if stored successfully
        """
        if self.conn is None:
            raise DatabaseConnectionError("Database connection not established")

        # Validate matter ID format (must be hashed: {banana}_{16-hex})
        if not validate_matter_id(matter.id):
            raise ValueError(
                f"Invalid matter ID format: {matter.id}. "
                f"Must use generate_matter_id() to create properly hashed IDs."
            )

        # Verify city exists before insert (prevent FK constraint failures)
        city_check = self._fetch_one("SELECT banana FROM cities WHERE banana = ?", (matter.banana,))
        if not city_check:
            raise ValueError(
                f"City '{matter.banana}' does not exist in cities table. "
                f"Cannot create matter for non-existent city."
            )

        # Serialize JSON fields
        canonical_topics_json = (
            json.dumps(matter.canonical_topics) if matter.canonical_topics else None
        )
        attachments_json = (
            json.dumps(matter.attachments) if matter.attachments else None
        )
        metadata_json = json.dumps(matter.metadata) if matter.metadata else None
        sponsors_json = json.dumps(matter.sponsors) if matter.sponsors else None

        # Debug: Log the banana value to diagnose FK failures
        logger.debug(f"[Matters] Inserting matter {matter.id} with banana='{matter.banana}'")

        # Sanity check: Verify city exists before insert (diagnose FK failures)
        city_check = self._fetch_one("SELECT banana FROM cities WHERE banana = ?", (matter.banana,))
        if not city_check:
            logger.error(f"[Matters] FATAL: City '{matter.banana}' does NOT exist in cities table! FK will fail.")
        else:
            logger.debug(f"[Matters] City '{matter.banana}' verified in cities table")

        self._execute(
            """
            INSERT INTO city_matters (id, banana, matter_file, matter_id, matter_type,
                                      title, canonical_summary, canonical_topics,
                                      attachments, metadata, sponsors, first_seen,
                                      last_seen, appearance_count)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                title = excluded.title,
                attachments = excluded.attachments,
                metadata = excluded.metadata,
                sponsors = excluded.sponsors,
                last_seen = excluded.last_seen,
                appearance_count = excluded.appearance_count,
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
                sponsors_json,
                matter.first_seen,
                matter.last_seen,
                matter.appearance_count,
            ),
        )

        if not defer_commit:
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
        DEPRECATED: Get a matter by matter_file or matter_id using deterministic ID generation.

        This method is deprecated as of 2025-11-12. Items now store composite matter_id
        directly, so you should use get_matter(item.matter_id) instead.

        This method remains for backward compatibility but generates composite ID
        from raw identifiers, which is slower than direct lookup.

        Args:
            banana: City identifier
            matter_file: Official matter file (25-1234, BL2025-1098)
            matter_id: Backend matter ID (UUID, numeric) - RAW, not composite

        Returns:
            Matter object or None if not found

        Deprecation:
            Use get_matter(composite_id) directly instead. Items already have
            composite matter_id stored, no need to regenerate.
        """
        import warnings
        warnings.warn(
            "get_matter_by_keys() is deprecated. Use get_matter(item.matter_id) directly.",
            DeprecationWarning,
            stacklevel=2
        )

        if self.conn is None:
            raise DatabaseConnectionError("Database connection not established")

        if not matter_file and not matter_id:
            return None

        # Generate deterministic ID and lookup by composite ID
        try:
            composite_id = generate_matter_id(banana, matter_file, matter_id)
            return self.get_matter(composite_id)
        except ValueError as e:
            logger.error(f"Failed to generate matter ID: {e}")
            return None

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

    def search_matters(
        self,
        search_term: str,
        banana: Optional[str] = None,
        state: Optional[str] = None,
        case_sensitive: bool = False
    ) -> List[Matter]:
        """
        Search for text in canonical matter summaries.

        Args:
            search_term: String to search for
            banana: Optional city filter
            state: Optional state filter (2-letter code)
            case_sensitive: Whether search should be case-sensitive

        Returns:
            List of Matter objects ordered by last_seen DESC
        """
        if self.conn is None:
            raise DatabaseConnectionError("Database connection not established")

        like_pattern = f'%{search_term}%'
        filters = []
        params = [like_pattern]

        if banana:
            filters.append("m.banana = ?")
            params.append(banana)

        if state:
            filters.append("c.state = ?")
            params.append(state.upper())

        filter_clause = ""
        if filters:
            filter_clause = " AND " + " AND ".join(filters)

        query = f'''
            SELECT m.*
            FROM city_matters m
            JOIN cities c ON m.banana = c.banana
            WHERE m.canonical_summary IS NOT NULL
              AND m.canonical_summary LIKE ?
              AND m.appearance_count >= 1
              {filter_clause}
            ORDER BY m.last_seen DESC
        '''

        rows = self._fetch_all(query, tuple(params))
        return [Matter.from_db_row(row) for row in rows]

    def check_appearance_exists(self, matter_id: str, meeting_id: str) -> bool:
        """
        Check if a matter already has an appearance record for a specific meeting.

        Args:
            matter_id: Composite matter ID
            meeting_id: Meeting identifier

        Returns:
            True if appearance record exists, False otherwise
        """
        if self.conn is None:
            raise DatabaseConnectionError("Database connection not established")

        count = self._fetch_one(
            """
            SELECT COUNT(*) FROM matter_appearances
            WHERE matter_id = ? AND meeting_id = ?
            """,
            (matter_id, meeting_id),
        )

        return count[0] > 0 if count else False

    def update_matter_tracking(
        self,
        matter_id: str,
        meeting_date: str,
        attachments: Optional[list],
        attachment_hash: str,
        increment_appearance_count: bool = False,
        defer_commit: bool = False
    ) -> None:
        """
        Update matter tracking fields (last_seen, appearance_count, attachments).

        Args:
            matter_id: Composite matter ID
            meeting_date: Date when matter appeared
            attachments: List of attachment dicts
            attachment_hash: SHA256 hash of attachments
            increment_appearance_count: Whether to increment appearance count
            defer_commit: If True, skip commit (caller handles transaction)
        """
        if self.conn is None:
            raise DatabaseConnectionError("Database connection not established")

        attachments_json = json.dumps(attachments) if attachments else None

        # Build dynamic SQL for appearance count
        increment_sql = "appearance_count + 1" if increment_appearance_count else "appearance_count"

        self._execute(
            f"""
            UPDATE city_matters
            SET last_seen = ?,
                appearance_count = {increment_sql},
                attachments = ?,
                metadata = json_set(COALESCE(metadata, '{{}}'), '$.attachment_hash', ?),
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (meeting_date, attachments_json, attachment_hash, matter_id),
        )

        if not defer_commit:
            self._commit()
        logger.debug(f"Updated matter tracking for {matter_id}")

    def create_appearance(
        self,
        matter_id: str,
        meeting_id: str,
        item_id: str,
        appeared_at: str,
        committee: Optional[str] = None,
        sequence: Optional[int] = None,
        defer_commit: bool = False
    ) -> None:
        """
        Create a matter appearance record (INSERT OR IGNORE for idempotency).

        Args:
            matter_id: Composite matter ID
            meeting_id: Meeting identifier
            item_id: Agenda item identifier
            appeared_at: Date when matter appeared
            committee: Optional committee name
            sequence: Optional item sequence number
            defer_commit: If True, skip commit (caller handles transaction)
        """
        if self.conn is None:
            raise DatabaseConnectionError("Database connection not established")

        self._execute(
            """
            INSERT OR IGNORE INTO matter_appearances (
                matter_id, meeting_id, item_id, appeared_at,
                committee, sequence
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (matter_id, meeting_id, item_id, appeared_at, committee, sequence),
        )

        if not defer_commit:
            self._commit()
        logger.debug(f"Created appearance for matter {matter_id} in meeting {meeting_id}")
