"""Async MeetingRepository for meeting operations

Handles CRUD operations for meetings:
- Store/update meetings with topic normalization
- Retrieve meetings by ID, city, or packet URL
- Update meeting summaries and processing metadata
- JSONB for participation data
"""

from typing import List, Optional

from database.repositories_async.base import BaseRepository
from database.repositories_async.helpers import build_meeting, fetch_topics_for_ids
from database.models import Meeting, ParticipationInfo
from config import get_logger

logger = get_logger(__name__).bind(component="meeting_repository")


class MeetingRepository(BaseRepository):
    """Repository for meeting operations

    Provides:
    - Store/update meetings with topic normalization
    - Retrieve meetings (by ID, city, packet URL)
    - Update summaries with processing metadata
    - Random meeting retrieval for testing
    """

    async def store_meeting(self, meeting: Meeting) -> None:
        """Store or update a meeting

        Uses UPSERT to handle both new meetings and updates.
        Normalizes topics to meeting_topics table.

        Args:
            meeting: Meeting object with all fields
        """
        async with self.transaction() as conn:
            # Upsert meeting row
            await conn.execute(
                """
                INSERT INTO meetings (
                    id, banana, title, date, agenda_url, packet_url,
                    summary, participation, status, processing_status,
                    processing_method, processing_time, committee_id
                )
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13)
                ON CONFLICT (id) DO UPDATE SET
                    title = EXCLUDED.title,
                    date = EXCLUDED.date,
                    agenda_url = EXCLUDED.agenda_url,
                    packet_url = EXCLUDED.packet_url,
                    summary = COALESCE(EXCLUDED.summary, meetings.summary),
                    participation = COALESCE(EXCLUDED.participation, meetings.participation),
                    status = EXCLUDED.status,
                    processing_status = COALESCE(EXCLUDED.processing_status, meetings.processing_status),
                    processing_method = COALESCE(EXCLUDED.processing_method, meetings.processing_method),
                    processing_time = COALESCE(EXCLUDED.processing_time, meetings.processing_time),
                    committee_id = COALESCE(EXCLUDED.committee_id, meetings.committee_id),
                    updated_at = CURRENT_TIMESTAMP
                """,
                meeting.id,
                meeting.banana,
                meeting.title,
                meeting.date,
                meeting.agenda_url,
                meeting.packet_url,
                meeting.summary,
                meeting.participation,
                meeting.status,
                meeting.processing_status or "pending",
                meeting.processing_method,
                meeting.processing_time,
                meeting.committee_id,
            )

            # Normalize topics to meeting_topics table (batch for efficiency)
            if meeting.topics:
                await conn.execute(
                    "DELETE FROM meeting_topics WHERE meeting_id = $1",
                    meeting.id,
                )
                topic_records = [(meeting.id, topic) for topic in meeting.topics]
                await conn.executemany(
                    "INSERT INTO meeting_topics (meeting_id, topic) VALUES ($1, $2) ON CONFLICT DO NOTHING",
                    topic_records,
                )

        logger.info("meeting stored", meeting_id=meeting.id, banana=meeting.banana)

    async def get_meeting(self, meeting_id: str) -> Optional[Meeting]:
        """Get a meeting by ID

        Args:
            meeting_id: Meeting identifier

        Returns:
            Meeting object with denormalized topics, or None
        """
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT
                    id, banana, title, date, agenda_url, packet_url,
                    summary, participation, status, processing_status,
                    processing_method, processing_time, committee_id,
                    created_at, updated_at
                FROM meetings
                WHERE id = $1
                """,
                meeting_id,
            )

            if not row:
                return None

            # Fetch normalized topics
            topics_map = await fetch_topics_for_ids(
                conn, "meeting_topics", "meeting_id", [meeting_id]
            )

            return build_meeting(row, topics_map.get(meeting_id, []))

    async def get_meetings_for_city(
        self,
        banana: str,
        limit: int = 50,
        offset: int = 0
    ) -> List[Meeting]:
        """Get meetings for a city, ordered by date descending

        Args:
            banana: City banana
            limit: Maximum number of meetings to return (default: 50)
            offset: Number of meetings to skip (default: 0)

        Returns:
            List of Meeting objects with topics
        """
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT
                    id, banana, title, date, agenda_url, packet_url,
                    summary, participation, status, processing_status,
                    processing_method, processing_time, committee_id
                FROM meetings
                WHERE banana = $1
                ORDER BY date DESC
                LIMIT $2 OFFSET $3
                """,
                banana,
                limit,
                offset,
            )

            if not rows:
                return []

            # Batch fetch all topics
            meeting_ids = [row["id"] for row in rows]
            topics_by_meeting = await fetch_topics_for_ids(
                conn, "meeting_topics", "meeting_id", meeting_ids
            )

            return [
                build_meeting(row, topics_by_meeting.get(row["id"], []))
                for row in rows
            ]

    async def get_meeting_by_packet_url(self, packet_url: str) -> Optional[Meeting]:
        """Get meeting by packet_url for cache optimization

        Used by processor.py to check if a packet has already been processed.

        Args:
            packet_url: The packet URL to look up

        Returns:
            Meeting object with denormalized topics, or None if not found
        """
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT
                    id, banana, title, date, agenda_url, packet_url,
                    summary, participation, status, processing_status,
                    processing_method, processing_time, committee_id,
                    created_at, updated_at
                FROM meetings
                WHERE packet_url = $1
                LIMIT 1
                """,
                packet_url,
            )

            if not row:
                return None

            # Fetch normalized topics
            topics_map = await fetch_topics_for_ids(
                conn, "meeting_topics", "meeting_id", [row["id"]]
            )

            return build_meeting(row, topics_map.get(row["id"], []))

    async def update_meeting_summary(
        self,
        meeting_id: str,
        summary: Optional[str],
        processing_method: str,
        processing_time: float,
        participation: Optional[ParticipationInfo] = None,
        topics: Optional[List[str]] = None,
    ) -> None:
        """Update meeting summary and processing metadata

        Args:
            meeting_id: Meeting identifier
            summary: Generated summary text (can be None for item-level processing)
            processing_method: Processing method used (e.g., "item_level", "monolithic")
            processing_time: Time taken in seconds
            participation: Optional participation data dict
            topics: Aggregated topics (normalized to meeting_topics table)
        """
        async with self.transaction() as conn:
            # Update meeting
            await conn.execute(
                """
                UPDATE meetings
                SET summary = $2,
                    processing_status = 'completed',
                    processing_method = $3,
                    processing_time = $4,
                    participation = $5,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = $1
                """,
                meeting_id,
                summary,
                processing_method,
                processing_time,
                participation,
            )

            # Normalize topics to meeting_topics table (batch for efficiency)
            if topics:
                await conn.execute(
                    "DELETE FROM meeting_topics WHERE meeting_id = $1",
                    meeting_id,
                )
                topic_records = [(meeting_id, topic) for topic in topics]
                await conn.executemany(
                    "INSERT INTO meeting_topics (meeting_id, topic) VALUES ($1, $2) ON CONFLICT DO NOTHING",
                    topic_records,
                )

        logger.info("updated meeting summary", meeting_id=meeting_id, topic_count=len(topics) if topics else 0)

    async def get_recent_meetings(self, limit: int = 50) -> List[Meeting]:
        """Get most recent meetings across all cities

        Args:
            limit: Maximum number of meetings to return

        Returns:
            List of Meeting objects sorted by date descending
        """
        async with self.pool.acquire() as conn:
            rows = await conn.fetch("""
                SELECT m.*
                FROM meetings m
                WHERE m.date IS NOT NULL
                ORDER BY m.date DESC
                LIMIT $1
            """, limit)

            if not rows:
                return []

            # Batch fetch all topics
            meeting_ids = [row["id"] for row in rows]
            topics_by_meeting = await fetch_topics_for_ids(
                conn, "meeting_topics", "meeting_id", meeting_ids
            )

            return [
                build_meeting(row, topics_by_meeting.get(row["id"], []))
                for row in rows
            ]

    async def get_random_meeting_with_items(self) -> Optional[Meeting]:
        """Get a random meeting that has items and a summary

        Used for testing/debugging.

        Returns:
            Meeting object, or None if no matching meetings
        """
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow("""
                SELECT m.*
                FROM meetings m
                WHERE m.summary IS NOT NULL
                AND EXISTS (SELECT 1 FROM items WHERE meeting_id = m.id)
                ORDER BY RANDOM()
                LIMIT 1
            """)

            if not row:
                return None

            # Fetch normalized topics
            topics_map = await fetch_topics_for_ids(
                conn, "meeting_topics", "meeting_id", [row["id"]]
            )

            return build_meeting(row, topics_map.get(row["id"], []))
