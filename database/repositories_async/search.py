"""Async SearchRepository for search operations

Handles search operations using PostgreSQL features:
- Full-text search using PostgreSQL FTS
- Topic-based search using normalized tables
- Popular topics aggregation
"""

from typing import Dict, List, Optional
from collections import defaultdict

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

            if not rows:
                return []

            # Batch fetch ALL topics for ALL meetings (eliminates N+1)
            meeting_ids = [row["id"] for row in rows]
            topic_rows = await conn.fetch(
                "SELECT meeting_id, topic FROM meeting_topics WHERE meeting_id = ANY($1::text[])",
                meeting_ids,
            )

            # Group topics by meeting
            topics_by_meeting: Dict[str, List[str]] = defaultdict(list)
            for tr in topic_rows:
                topics_by_meeting[tr["meeting_id"]].append(tr["topic"])

            # Build meeting objects
            meetings = []
            for row in rows:
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
                        topics=topics_by_meeting.get(row["id"], []),
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

            if not rows:
                return []

            # Batch fetch ALL topics for ALL meetings (eliminates N+1)
            meeting_ids = [row["id"] for row in rows]
            topic_rows = await conn.fetch(
                "SELECT meeting_id, topic FROM meeting_topics WHERE meeting_id = ANY($1::text[])",
                meeting_ids,
            )

            # Group topics by meeting
            topics_by_meeting: Dict[str, List[str]] = defaultdict(list)
            for tr in topic_rows:
                topics_by_meeting[tr["meeting_id"]].append(tr["topic"])

            # Build meeting objects
            meetings = []
            for row in rows:
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
                    topics=topics_by_meeting.get(row["id"], []),
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

    async def get_trending_topics(
        self,
        period: str = "week",
        limit: int = 8,
        state: Optional[str] = None
    ) -> List[dict]:
        """Get trending topics with trend direction

        Compares current period to previous period to determine trend.

        Args:
            period: Time period - 'day', 'week', or 'month'
            limit: Maximum topics to return
            state: Optional state filter

        Returns:
            List of dicts with topic info and trend direction
        """
        from datetime import datetime, timedelta, timezone

        now = datetime.now(timezone.utc)

        # Define periods
        period_days = {"day": 1, "week": 7, "month": 30}
        days = period_days.get(period, 7)

        current_start = now - timedelta(days=days)
        previous_start = now - timedelta(days=days * 2)

        async with self.pool.acquire() as conn:
            # Get current period topic counts
            if state:
                current_counts = await conn.fetch("""
                    SELECT mt.topic, COUNT(DISTINCT m.id) as meeting_count,
                           COUNT(DISTINCT m.banana) as city_count
                    FROM meeting_topics mt
                    JOIN meetings m ON mt.meeting_id = m.id
                    JOIN cities c ON m.banana = c.banana
                    WHERE m.date >= $1
                      AND c.state = $2
                    GROUP BY mt.topic
                    ORDER BY meeting_count DESC
                    LIMIT $3
                """, current_start, state, limit)

                # Get previous period for trend comparison
                previous_counts = await conn.fetch("""
                    SELECT mt.topic, COUNT(DISTINCT m.id) as meeting_count
                    FROM meeting_topics mt
                    JOIN meetings m ON mt.meeting_id = m.id
                    JOIN cities c ON m.banana = c.banana
                    WHERE m.date >= $1 AND m.date < $2
                      AND c.state = $3
                    GROUP BY mt.topic
                """, previous_start, current_start, state)
            else:
                current_counts = await conn.fetch("""
                    SELECT mt.topic, COUNT(DISTINCT m.id) as meeting_count,
                           COUNT(DISTINCT m.banana) as city_count
                    FROM meeting_topics mt
                    JOIN meetings m ON mt.meeting_id = m.id
                    WHERE m.date >= $1
                    GROUP BY mt.topic
                    ORDER BY meeting_count DESC
                    LIMIT $2
                """, current_start, limit)

                previous_counts = await conn.fetch("""
                    SELECT mt.topic, COUNT(DISTINCT m.id) as meeting_count
                    FROM meeting_topics mt
                    JOIN meetings m ON mt.meeting_id = m.id
                    WHERE m.date >= $1 AND m.date < $2
                    GROUP BY mt.topic
                """, previous_start, current_start)

            # Build previous count map
            prev_map = {r["topic"]: r["meeting_count"] for r in previous_counts}

            from analysis.topics.normalizer import get_normalizer
            normalizer = get_normalizer()

            results = []
            for row in current_counts:
                topic = row["topic"]
                current = row["meeting_count"]
                previous = prev_map.get(topic, 0)

                # Calculate trend
                if previous == 0:
                    trend = "new" if current > 0 else "stable"
                elif current > previous:
                    trend = "up"
                elif current < previous:
                    trend = "down"
                else:
                    trend = "stable"

                results.append({
                    "topic": topic,
                    "display_name": normalizer.get_display_name(topic),
                    "meeting_count": current,
                    "city_count": row["city_count"],
                    "trend": trend,
                })

            return results
