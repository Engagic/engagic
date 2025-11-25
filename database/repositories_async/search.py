"""Async SearchRepository for search operations

Handles search operations using PostgreSQL features:
- Full-text search using PostgreSQL FTS
- Topic-based search using normalized tables
- Popular topics aggregation
"""

from typing import List, Optional

from database.repositories_async.base import BaseRepository
from database.models import Meeting, ParticipationInfo
from config import get_logger

logger = get_logger(__name__).bind(component="search_repository")


class SearchRepository(BaseRepository):
    """Repository for search operations

    Provides:
    - Full-text search on meetings (PostgreSQL FTS)
    - Topic-based meeting search
    - Popular topics aggregation
    """

    async def search_meetings_fulltext(
        self,
        query: str,
        banana: Optional[str] = None,
        limit: int = 50
    ) -> List[Meeting]:
        """Full-text search on meetings using PostgreSQL FTS

        Uses to_tsvector and ts_rank for relevance scoring.

        Args:
            query: Search query (plain text, automatically converted to tsquery)
            banana: Optional city filter
            limit: Maximum results (default: 50)

        Returns:
            List of matching meetings ordered by relevance
        """
        async with self.pool.acquire() as conn:
            if banana:
                rows = await conn.fetch(
                    """
                    SELECT
                        id, banana, title, date, agenda_url, packet_url,
                        summary, participation, status, processing_status,
                        processing_method, processing_time,
                        ts_rank(to_tsvector('english', COALESCE(title, '') || ' ' || COALESCE(summary, '')), plainto_tsquery('english', $1)) AS rank
                    FROM meetings
                    WHERE banana = $2
                      AND to_tsvector('english', COALESCE(title, '') || ' ' || COALESCE(summary, '')) @@ plainto_tsquery('english', $1)
                    ORDER BY rank DESC, date DESC
                    LIMIT $3
                    """,
                    query,
                    banana,
                    limit,
                )
            else:
                rows = await conn.fetch(
                    """
                    SELECT
                        id, banana, title, date, agenda_url, packet_url,
                        summary, participation, status, processing_status,
                        processing_method, processing_time,
                        ts_rank(to_tsvector('english', COALESCE(title, '') || ' ' || COALESCE(summary, '')), plainto_tsquery('english', $1)) AS rank
                    FROM meetings
                    WHERE to_tsvector('english', COALESCE(title, '') || ' ' || COALESCE(summary, '')) @@ plainto_tsquery('english', $1)
                    ORDER BY rank DESC, date DESC
                    LIMIT $2
                    """,
                    query,
                    limit,
                )

            meetings = []
            for row in rows:
                # Fetch normalized topics
                topic_rows = await conn.fetch(
                    "SELECT topic FROM meeting_topics WHERE meeting_id = $1",
                    row["id"],
                )
                topics = [r["topic"] for r in topic_rows]

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

    async def search_meetings_by_topic(
        self,
        topic: str,
        banana: Optional[str] = None,
        limit: int = 50
    ) -> List[Meeting]:
        """Search meetings by topic, optionally filtered by city

        Uses normalized meeting_topics table for efficient filtering.

        Args:
            topic: Topic name (exact match)
            banana: Optional city filter
            limit: Maximum results (default: 50)

        Returns:
            List of meetings ordered by date (most recent first)
        """
        async with self.pool.acquire() as conn:
            if banana:
                rows = await conn.fetch("""
                    SELECT DISTINCT m.*
                    FROM meetings m
                    JOIN meeting_topics mt ON m.id = mt.meeting_id
                    WHERE mt.topic = $1 AND m.banana = $2
                    ORDER BY m.date DESC
                    LIMIT $3
                """, topic, banana, limit)
            else:
                rows = await conn.fetch("""
                    SELECT DISTINCT m.*
                    FROM meetings m
                    JOIN meeting_topics mt ON m.id = mt.meeting_id
                    WHERE mt.topic = $1
                    ORDER BY m.date DESC
                    LIMIT $2
                """, topic, limit)

            meetings = []
            for row in rows:
                # Deserialize JSONB participation to typed model
                participation = ParticipationInfo(**row["participation"]) if row["participation"] else None

                # Get normalized topics
                topic_rows = await conn.fetch(
                    "SELECT topic FROM meeting_topics WHERE meeting_id = $1",
                    row["id"]
                )
                topics = [t["topic"] for t in topic_rows]

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

    async def get_popular_topics(self, limit: int = 20) -> List[dict]:
        """Get most popular topics across all meetings

        Args:
            limit: Maximum topics to return (default: 20)

        Returns:
            List of dicts with 'topic' and 'count' keys, ordered by count DESC
        """
        rows = await self._fetch("""
            SELECT topic, COUNT(*) as count
            FROM meeting_topics
            GROUP BY topic
            ORDER BY count DESC
            LIMIT $1
        """, limit)

        return [{"topic": row["topic"], "count": row["count"]} for row in rows]
