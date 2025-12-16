"""Async SearchRepository for search operations

Handles search operations using PostgreSQL features:
- Full-text search using PostgreSQL FTS
- Topic-based search using normalized tables
- Popular topics aggregation
"""

from typing import List, Optional

from database.repositories_async.base import BaseRepository
from database.repositories_async.helpers import build_meeting, fetch_topics_for_ids
from database.models import Meeting
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
        # Uses search_vector stored column (requires migration 012_fts_optimization)
        async with self.pool.acquire() as conn:
            if banana:
                rows = await conn.fetch(
                    """
                    SELECT
                        id, banana, title, date, agenda_url, agenda_sources, packet_url,
                        summary, participation, status, processing_status,
                        processing_method, processing_time,
                        ts_rank(search_vector, plainto_tsquery('english', $1)) AS rank
                    FROM meetings
                    WHERE banana = $2
                      AND search_vector @@ plainto_tsquery('english', $1)
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
                        id, banana, title, date, agenda_url, agenda_sources, packet_url,
                        summary, participation, status, processing_status,
                        processing_method, processing_time,
                        ts_rank(search_vector, plainto_tsquery('english', $1)) AS rank
                    FROM meetings
                    WHERE search_vector @@ plainto_tsquery('english', $1)
                    ORDER BY rank DESC, date DESC
                    LIMIT $2
                    """,
                    query,
                    limit,
                )

            if not rows:
                return []

            # Batch fetch topics
            meeting_ids = [row["id"] for row in rows]
            topics_by_meeting = await fetch_topics_for_ids(
                conn, "meeting_topics", "meeting_id", meeting_ids
            )

            # Build meeting objects
            return [
                build_meeting(row, topics_by_meeting.get(row["id"], []))
                for row in rows
            ]

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

            # Batch fetch topics
            meeting_ids = [row["id"] for row in rows]
            topics_by_meeting = await fetch_topics_for_ids(
                conn, "meeting_topics", "meeting_id", meeting_ids
            )

            # Build meeting objects
            return [
                build_meeting(row, topics_by_meeting.get(row["id"], []))
                for row in rows
            ]

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

    async def search_items_fulltext(
        self,
        query: str,
        banana: str,
        limit: int = 50
    ) -> List[dict]:
        """Full-text search on items using PostgreSQL FTS

        Searches item summary, title, and matter_file. Returns item-level
        results with meeting context for rich search results.

        Args:
            query: Search query (plain text, automatically converted to tsquery)
            banana: City filter (required for scoped search)
            limit: Maximum results (default: 50)

        Returns:
            List of dicts with item + meeting context for frontend display
        """
        # Uses search_vector stored column (requires migration 012_fts_optimization)
        async with self.pool.acquire() as conn:
            # Search items by summary, title, and matter_file
            # Join with meetings to get meeting context
            rows = await conn.fetch(
                """
                SELECT
                    i.id as item_id,
                    i.title as item_title,
                    i.sequence as item_sequence,
                    i.agenda_number,
                    i.summary,
                    i.topics as item_topics,
                    i.matter_id,
                    i.matter_file,
                    i.matter_type,
                    i.attachments as item_attachments,
                    m.id as meeting_id,
                    m.title as meeting_title,
                    m.date as meeting_date,
                    m.agenda_url,
                    m.agenda_sources,
                    ts_rank(i.search_vector, plainto_tsquery('english', $1)) AS rank,
                    ts_headline(
                        'english',
                        COALESCE(i.summary, i.title, ''),
                        plainto_tsquery('english', $1),
                        'MaxWords=60, MinWords=30, StartSel=<mark>, StopSel=</mark>, HighlightAll=false'
                    ) AS context_headline
                FROM items i
                JOIN meetings m ON i.meeting_id = m.id
                WHERE m.banana = $2
                  AND (
                      i.search_vector @@ plainto_tsquery('english', $1)
                      OR i.matter_file ILIKE '%' || $1 || '%'
                  )
                ORDER BY rank DESC, m.date DESC, i.sequence ASC
                LIMIT $3
                """,
                query,
                banana,
                limit,
            )

            if not rows:
                return []

            # Transform to frontend-friendly dicts
            results = []
            for row in rows:
                results.append({
                    "type": "item",
                    "item_id": row["item_id"],
                    "item_title": row["item_title"],
                    "item_sequence": row["item_sequence"],
                    "agenda_number": row["agenda_number"],
                    "summary": row["summary"],
                    "topics": row["item_topics"] or [],
                    "matter_id": row["matter_id"],
                    "matter_file": row["matter_file"],
                    "matter_type": row["matter_type"],
                    "attachments": row["item_attachments"] or [],
                    "meeting_id": row["meeting_id"],
                    "meeting_title": row["meeting_title"],
                    "meeting_date": row["meeting_date"].isoformat() if row["meeting_date"] else None,
                    "agenda_url": row["agenda_url"],
                    "agenda_sources": row["agenda_sources"],
                    "context_headline": row["context_headline"],
                })

            return results
