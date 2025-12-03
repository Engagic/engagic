"""Async MeetingRepository for meeting operations

Handles CRUD operations for meetings:
- Store/update meetings with topic normalization
- Retrieve meetings by ID, city, or packet URL
- Update meeting summaries and processing metadata
- JSONB for participation data
"""

from typing import List, Optional

from database.repositories_async.base import BaseRepository
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
                    processing_method, processing_time
                )
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12)
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
                    processing_method, processing_time, created_at, updated_at
                FROM meetings
                WHERE id = $1
                """,
                meeting_id,
            )

            if not row:
                return None

            # Fetch normalized topics
            topic_rows = await conn.fetch(
                """
                SELECT topic
                FROM meeting_topics
                WHERE meeting_id = $1
                """,
                meeting_id,
            )
            topics = [r["topic"] for r in topic_rows]

            # Deserialize JSONB participation to typed model
            participation = ParticipationInfo(**row["participation"]) if row["participation"] else None

            return Meeting(
                id=row["id"],
                banana=row["banana"],
                title=row["title"],
                date=row["date"],
                agenda_url=row["agenda_url"],
                packet_url=row["packet_url"],
                summary=row["summary"],
                participation=participation,
                status=row["status"],
                processing_status=row["processing_status"],
                processing_method=row["processing_method"],
                processing_time=row["processing_time"],
                topics=topics,
            )

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
                    processing_method, processing_time
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

            # Batch fetch all topics for all meetings (fix N+1 query)
            meeting_ids = [row["id"] for row in rows]
            topic_rows = await conn.fetch(
                "SELECT meeting_id, topic FROM meeting_topics WHERE meeting_id = ANY($1::text[])",
                meeting_ids,
            )

            # Build topic map: meeting_id -> [topics]
            topics_by_meeting = {}
            for topic_row in topic_rows:
                meeting_id = topic_row["meeting_id"]
                if meeting_id not in topics_by_meeting:
                    topics_by_meeting[meeting_id] = []
                topics_by_meeting[meeting_id].append(topic_row["topic"])

            meetings = []
            for row in rows:
                topics = topics_by_meeting.get(row["id"], [])

                # Deserialize JSONB participation to typed model
                participation = ParticipationInfo(**row["participation"]) if row["participation"] else None

                meetings.append(
                    Meeting(
                        id=row["id"],
                        banana=row["banana"],
                        title=row["title"],
                        date=row["date"],
                        agenda_url=row["agenda_url"],
                        packet_url=row["packet_url"],
                        summary=row["summary"],
                        participation=participation,
                        status=row["status"],
                        processing_status=row["processing_status"],
                        processing_method=row["processing_method"],
                        processing_time=row["processing_time"],
                        topics=topics,
                    )
                )

            return meetings

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
                    processing_method, processing_time, created_at, updated_at
                FROM meetings
                WHERE packet_url = $1
                LIMIT 1
                """,
                packet_url,
            )

            if not row:
                return None

            # Fetch normalized topics
            topic_rows = await conn.fetch(
                """
                SELECT topic
                FROM meeting_topics
                WHERE meeting_id = $1
                """,
                row["id"],
            )
            topics = [r["topic"] for r in topic_rows]

            # Deserialize JSONB participation to typed model
            participation = ParticipationInfo(**row["participation"]) if row["participation"] else None

            return Meeting(
                id=row["id"],
                banana=row["banana"],
                title=row["title"],
                date=row["date"],
                agenda_url=row["agenda_url"],
                packet_url=row["packet_url"],
                summary=row["summary"],
                participation=participation,
                status=row["status"],
                processing_status=row["processing_status"],
                processing_method=row["processing_method"],
                processing_time=row["processing_time"],
                topics=topics,
            )

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

            # Batch fetch all topics for all meetings (avoid N+1 query)
            meeting_ids = [row["id"] for row in rows]
            topic_rows = await conn.fetch(
                "SELECT meeting_id, topic FROM meeting_topics WHERE meeting_id = ANY($1::text[])",
                meeting_ids,
            )

            # Build topic map: meeting_id -> [topics]
            topics_by_meeting: dict[str, list[str]] = {}
            for topic_row in topic_rows:
                meeting_id = topic_row["meeting_id"]
                if meeting_id not in topics_by_meeting:
                    topics_by_meeting[meeting_id] = []
                topics_by_meeting[meeting_id].append(topic_row["topic"])

            meetings = []
            for row in rows:
                topics = topics_by_meeting.get(row["id"], [])
                # Deserialize JSONB participation to typed model
                participation = ParticipationInfo(**row["participation"]) if row["participation"] else None

                meetings.append(Meeting(
                    id=row["id"],
                    banana=row["banana"],
                    title=row["title"],
                    date=row["date"],
                    agenda_url=row["agenda_url"],
                    packet_url=row["packet_url"],
                    summary=row["summary"],
                    participation=participation,
                    status=row["status"],
                    processing_status=row["processing_status"],
                    processing_method=row["processing_method"],
                    processing_time=row["processing_time"],
                    topics=topics,
                ))

            return meetings

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

            # Deserialize JSONB participation to typed model
            participation = ParticipationInfo(**row["participation"]) if row["participation"] else None

            # Get normalized topics
            topic_rows = await conn.fetch(
                "SELECT topic FROM meeting_topics WHERE meeting_id = $1",
                row["id"]
            )
            topics = [t["topic"] for t in topic_rows]

            return Meeting(
                id=row["id"],
                banana=row["banana"],
                title=row["title"],
                date=row["date"],
                agenda_url=row["agenda_url"],
                packet_url=row["packet_url"],
                summary=row["summary"],
                participation=participation,
                status=row["status"],
                processing_status=row["processing_status"],
                processing_method=row["processing_method"],
                processing_time=row["processing_time"],
                topics=topics,
            )
