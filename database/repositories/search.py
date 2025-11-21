"""
Search Repository - Search and discovery operations

Handles search, topic-based queries, cache lookups, and database statistics.

REPOSITORY PATTERN: All methods are atomic operations.
Transaction management is the CALLER'S responsibility.
Use `with transaction(conn):` context manager to group operations.
"""

import json
from typing import Optional, List, Dict, Any

from database.repositories.base import BaseRepository
from database.models import Meeting, AgendaItem
from exceptions import DatabaseConnectionError

from config import get_logger

logger = get_logger(__name__).bind(component="database")



class SearchRepository(BaseRepository):
    """Repository for search, cache, and discovery operations"""

    def get_random_meeting_with_items(self) -> Optional[Dict[str, Any]]:
        """Get a random meeting that has multiple items with summaries"""
        if self.conn is None:
            raise DatabaseConnectionError("Database connection not established")

        row = self._fetch_one("""
            SELECT
                m.id,
                m.banana,
                m.title,
                m.date,
                m.packet_url,
                m.summary,
                COUNT(i.id) as item_count,
                AVG(LENGTH(i.summary)) as avg_summary_length
            FROM meetings m
            JOIN items i ON m.id = i.meeting_id
            WHERE i.summary IS NOT NULL
                AND LENGTH(i.summary) > 100
            GROUP BY m.id
            HAVING COUNT(i.id) >= 3
            ORDER BY RANDOM()
            LIMIT 1
        """)

        if not row:
            return None

        meeting_id = row["id"]

        # Fetch items for this meeting
        items_rows = self._fetch_all("""
            SELECT id, meeting_id, title, sequence, attachments, summary, topics, created_at
            FROM items
            WHERE meeting_id = ?
            ORDER BY sequence
        """, (meeting_id,))

        items = [AgendaItem.from_db_row(item_row).to_dict() for item_row in items_rows]

        return {
            "id": row["id"],
            "banana": row["banana"],
            "title": row["title"],
            "date": row["date"],
            "packet_url": row["packet_url"],
            "summary": row["summary"],
            "items": items,
            "item_count": row["item_count"],
            "avg_summary_length": round(row["avg_summary_length"]) if row["avg_summary_length"] else 0
        }

    def search_meetings_by_topic(
        self, topic: str, city_banana: Optional[str] = None, limit: int = 50
    ) -> List[Meeting]:
        """Search meetings by topic (uses normalized topic name)"""
        if self.conn is None:
            raise DatabaseConnectionError("Database connection not established")

        # Build query conditions
        conditions = []
        params = []

        # Topic match using JSON
        conditions.append("EXISTS (SELECT 1 FROM json_each(meetings.topics) WHERE value = ?)")
        params.append(topic)

        # City filter
        if city_banana:
            conditions.append("meetings.banana = ?")
            params.append(city_banana)

        # Only return meetings with topics
        conditions.append("meetings.topics IS NOT NULL")

        where_clause = " AND ".join(conditions)
        query = f"""
            SELECT * FROM meetings
            WHERE {where_clause}
            ORDER BY date DESC
            LIMIT ?
        """
        params.append(limit)

        rows = self._fetch_all(query, tuple(params))
        return [Meeting.from_db_row(row) for row in rows]

    def get_items_by_topic(self, meeting_id: str, topic: str) -> List[AgendaItem]:
        """Get agenda items from a meeting that match a specific topic"""
        if self.conn is None:
            raise DatabaseConnectionError("Database connection not established")

        rows = self._fetch_all("""
            SELECT * FROM items
            WHERE meeting_id = ?
            AND EXISTS (SELECT 1 FROM json_each(items.topics) WHERE value = ?)
            ORDER BY sequence ASC
        """, (meeting_id, topic))

        return [AgendaItem.from_db_row(row) for row in rows]

    def get_popular_topics(self, limit: int = 20) -> List[Dict[str, Any]]:
        """Get most common topics across all meetings"""
        if self.conn is None:
            raise DatabaseConnectionError("Database connection not established")

        rows = self._fetch_all("""
            SELECT value as topic, COUNT(*) as count
            FROM meetings, json_each(meetings.topics)
            WHERE meetings.topics IS NOT NULL
            GROUP BY value
            ORDER BY count DESC
            LIMIT ?
        """, (limit,))

        return [{"topic": row["topic"], "count": row["count"]} for row in rows]

    def get_cached_summary(self, packet_url: str | List[str]) -> Optional[Meeting]:
        """Get meeting by packet URL if it has been processed"""
        if self.conn is None:
            raise DatabaseConnectionError("Database connection not established")

        # Serialize URL if it's a list
        lookup_url = (
            json.dumps(packet_url) if isinstance(packet_url, list) else packet_url
        )

        row = self._fetch_one(
            """
            SELECT * FROM meetings
            WHERE packet_url = ? AND summary IS NOT NULL
            LIMIT 1
        """,
            (lookup_url,),
        )

        if row:
            # Update cache hit count
            self._execute(
                """
                UPDATE cache
                SET cache_hit_count = cache_hit_count + 1,
                    last_accessed = CURRENT_TIMESTAMP
                WHERE packet_url = ?
            """,
                (lookup_url,),
            )

            return Meeting.from_db_row(row)

        return None

    def store_processing_result(
        self, packet_url: str, processing_method: str, processing_time: float
    ):
        """Store processing result in cache"""
        if self.conn is None:
            raise DatabaseConnectionError("Database connection not established")

        lookup_url = (
            json.dumps(packet_url) if isinstance(packet_url, list) else packet_url
        )

        self._execute(
            """
            INSERT INTO cache (packet_url, processing_method, processing_time, cache_hit_count)
            VALUES (?, ?, ?, 0)
            ON CONFLICT(packet_url) DO UPDATE SET
                processing_method = excluded.processing_method,
                processing_time = excluded.processing_time,
                -- PRESERVE cache_hit_count, created_at (don't reset counters!)
                last_accessed = CURRENT_TIMESTAMP
        """,
            (lookup_url, processing_method, processing_time),
        )

    def get_stats(self) -> Dict[str, Any]:
        """Get database statistics"""
        if self.conn is None:
            raise DatabaseConnectionError("Database connection not established")

        active_cities_row = self._fetch_one(
            "SELECT COUNT(*) as count FROM cities WHERE status = 'active'"
        )
        active_cities = active_cities_row["count"] if active_cities_row else 0

        total_meetings_row = self._fetch_one("SELECT COUNT(*) as count FROM meetings")
        total_meetings = total_meetings_row["count"] if total_meetings_row else 0

        summarized_meetings_row = self._fetch_one(
            "SELECT COUNT(*) as count FROM meetings WHERE summary IS NOT NULL"
        )
        summarized_meetings = summarized_meetings_row["count"] if summarized_meetings_row else 0

        pending_meetings_row = self._fetch_one(
            "SELECT COUNT(*) as count FROM meetings WHERE processing_status = 'pending'"
        )
        pending_meetings = pending_meetings_row["count"] if pending_meetings_row else 0

        return {
            "active_cities": active_cities,
            "total_meetings": total_meetings,
            "summarized_meetings": summarized_meetings,
            "pending_meetings": pending_meetings,
            "summary_rate": f"{summarized_meetings / total_meetings * 100:.1f}%"
            if total_meetings > 0
            else "0%",
        }
