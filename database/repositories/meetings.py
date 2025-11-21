"""
Meeting Repository - Meeting operations

Handles all meeting-related database operations including lookups,
storage, updates, and processing status management.

REPOSITORY PATTERN: All methods are atomic operations.
Transaction management is the CALLER'S responsibility.
Use `with transaction(conn):` context manager to group operations.
"""

import json
from typing import Optional, List, Dict, Any
from datetime import datetime

from config import get_logger
from database.repositories.base import BaseRepository
from database.models import Meeting
from exceptions import DatabaseConnectionError

logger = get_logger(__name__).bind(component="database")


class MeetingRepository(BaseRepository):
    """Repository for meeting operations"""

    def get_meeting(self, meeting_id: str) -> Optional[Meeting]:
        """Get a single meeting by ID"""
        if self.conn is None:
            raise DatabaseConnectionError("Database connection not established")
        row = self._fetch_one("SELECT * FROM meetings WHERE id = ?", (meeting_id,))
        return Meeting.from_db_row(row) if row else None

    def get_meetings(
        self,
        bananas: Optional[List[str]] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        has_summary: Optional[bool] = None,
        limit: int = 50,
    ) -> List[Meeting]:
        """
        Get meetings with flexible filtering.

        Args:
            bananas: Filter by list of bananas
            start_date: Filter by date >= start_date
            end_date: Filter by date <= end_date
            has_summary: Filter by whether summary exists
            limit: Maximum results
        """
        if self.conn is None:
            raise DatabaseConnectionError("Database connection not established")

        conditions = []
        params = []

        if bananas:
            placeholders = ",".join("?" * len(bananas))
            conditions.append(f"banana IN ({placeholders})")
            params.extend(bananas)

        if start_date:
            conditions.append("date >= ?")
            params.append(start_date.isoformat())

        if end_date:
            conditions.append("date <= ?")
            params.append(end_date.isoformat())

        if has_summary is not None:
            if has_summary:
                conditions.append("summary IS NOT NULL")
            else:
                conditions.append("summary IS NULL")

        where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""

        query = f"""
            SELECT * FROM meetings
            {where_clause}
            ORDER BY date DESC, created_at DESC
            LIMIT {limit}
        """

        rows = self._fetch_all(query, tuple(params))
        return [Meeting.from_db_row(row) for row in rows]

    def store_meeting(self, meeting: Meeting) -> Meeting:
        """Store or update a meeting

        NOTE: Does not commit - caller must manage transaction.

        Args:
            meeting: Meeting object to store
        """
        if self.conn is None:
            raise DatabaseConnectionError("Database connection not established")

        # Serialize JSON fields
        participation_json = (
            json.dumps(meeting.participation) if meeting.participation else None
        )
        topics_json = json.dumps(meeting.topics) if meeting.topics else None

        # Serialize packet_url if it's a list
        packet_url_value = meeting.packet_url
        if isinstance(packet_url_value, list):
            packet_url_value = json.dumps(packet_url_value)

        self._execute(
            """
            INSERT INTO meetings (id, banana, title, date, agenda_url, packet_url, summary, participation, status, topics,
             processing_status, processing_method, processing_time)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                title = excluded.title,
                date = excluded.date,
                agenda_url = excluded.agenda_url,
                packet_url = excluded.packet_url,
                participation = excluded.participation,
                status = excluded.status,
                -- PRESERVE existing summary/topics/processing data if new values are NULL
                summary = CASE
                    WHEN excluded.summary IS NOT NULL THEN excluded.summary
                    ELSE meetings.summary
                END,
                topics = CASE
                    WHEN excluded.topics IS NOT NULL THEN excluded.topics
                    ELSE meetings.topics
                END,
                processing_status = excluded.processing_status,
                processing_method = CASE
                    WHEN excluded.processing_method IS NOT NULL THEN excluded.processing_method
                    ELSE meetings.processing_method
                END,
                processing_time = CASE
                    WHEN excluded.processing_time IS NOT NULL THEN excluded.processing_time
                    ELSE meetings.processing_time
                END,
                updated_at = CURRENT_TIMESTAMP
        """,
            (
                meeting.id,
                meeting.banana,
                meeting.title,
                meeting.date.isoformat() if meeting.date else None,
                meeting.agenda_url,
                packet_url_value,
                meeting.summary,
                participation_json,
                meeting.status,
                topics_json,
                meeting.processing_status,
                meeting.processing_method,
                meeting.processing_time,
            ),
        )

        result = self.get_meeting(meeting.id)
        if result is None:
            raise DatabaseConnectionError(
                f"Failed to retrieve newly stored meeting: {meeting.id}"
            )
        return result


    def update_meeting_summary(
        self,
        meeting_id: str,
        summary: Optional[str],
        processing_method: str,
        processing_time: float,
        participation: Optional[Dict[str, Any]] = None,
        topics: Optional[List[str]] = None,
    ):
        """Update meeting with processed summary, topics, and optional participation info"""
        if self.conn is None:
            raise DatabaseConnectionError("Database connection not established")

        participation_json = json.dumps(participation) if participation else None
        topics_json = json.dumps(topics) if topics else None

        self._execute(
            """
            UPDATE meetings
            SET summary = ?,
                participation = ?,
                topics = ?,
                processing_status = 'completed',
                processing_method = ?,
                processing_time = ?,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
        """,
            (
                summary,
                participation_json,
                topics_json,
                processing_method,
                processing_time,
                meeting_id,
            ),
        )

        logger.info(
            f"Updated summary for meeting {meeting_id} using {processing_method}"
        )

    def get_unprocessed_meetings(self, limit: int = 50) -> List[Meeting]:
        """Get meetings that need summary processing"""
        if self.conn is None:
            raise DatabaseConnectionError("Database connection not established")

        rows = self._fetch_all(
            """
            SELECT * FROM meetings
            WHERE processing_status = 'pending'
            AND packet_url IS NOT NULL
            ORDER BY date DESC
            LIMIT ?
        """,
            (limit,),
        )

        return [Meeting.from_db_row(row) for row in rows]

    def get_meeting_by_packet_url(self, packet_url: str) -> Optional[Meeting]:
        """Get meeting by packet URL"""
        if self.conn is None:
            raise DatabaseConnectionError("Database connection not established")

        row = self._fetch_one(
            """
            SELECT * FROM meetings
            WHERE packet_url = ?
            LIMIT 1
        """,
            (packet_url,),
        )

        return Meeting.from_db_row(row) if row else None
