"""
Search Repository - Search and discovery operations

Handles search, topic-based queries, cache lookups, and database statistics.
"""

import logging
import json
from typing import Optional, List, Dict, Any

from database.repositories.base import BaseRepository
from database.models import Meeting, AgendaItem
from exceptions import DatabaseConnectionError

logger = logging.getLogger("engagic")


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
            self._commit()

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

        self._commit()

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

    def get_dashboard_overview(self, start_date: Optional[str] = None, end_date: Optional[str] = None) -> Dict[str, Any]:
        """Get comprehensive dashboard overview metrics"""
        if self.conn is None:
            raise DatabaseConnectionError("Database connection not established")

        # Build date filter
        date_filter = ""
        date_params = []
        if start_date and end_date:
            date_filter = " AND m.date BETWEEN ? AND ?"
            date_params = [start_date, end_date]

        # Total cities and states
        cities_row = self._fetch_one("SELECT COUNT(*) as count, COUNT(DISTINCT state) as states FROM cities WHERE status = 'active'")
        total_cities = cities_row["count"] if cities_row else 0
        total_states = cities_row["states"] if cities_row else 0

        # Total meetings and items
        meetings_row = self._fetch_one(f"SELECT COUNT(*) as count FROM meetings m WHERE 1=1{date_filter}", tuple(date_params))
        total_meetings = meetings_row["count"] if meetings_row else 0

        items_row = self._fetch_one(f"SELECT COUNT(*) as count FROM items i JOIN meetings m ON i.meeting_id = m.id WHERE 1=1{date_filter}", tuple(date_params))
        total_items = items_row["count"] if items_row else 0

        # Matters count
        matters_row = self._fetch_one("SELECT COUNT(*) as count FROM city_matters")
        total_matters = matters_row["count"] if matters_row else 0

        # Cross-state matters (matters appearing in multiple states)
        cross_state_row = self._fetch_one("""
            SELECT COUNT(*) as count
            FROM (
                SELECT cm.matter_id
                FROM city_matters cm
                JOIN cities c ON cm.city_banana = c.city_banana
                GROUP BY cm.matter_id
                HAVING COUNT(DISTINCT c.state) > 1
            ) AS cross_state_matters
        """)
        cross_state_matters = cross_state_row["count"] if cross_state_row else 0

        # Topic diversity (unique topics count)
        topics_row = self._fetch_one("""
            SELECT COUNT(DISTINCT value) as count
            FROM meetings m, json_each(m.topics)
            WHERE m.topics IS NOT NULL
        """)
        unique_topics = topics_row["count"] if topics_row else 0

        # Processing queue health
        queue_row = self._fetch_one("SELECT COUNT(*) as count FROM queue WHERE status = 'pending'")
        queue_depth = queue_row["count"] if queue_row else 0

        # Success rate
        processed_row = self._fetch_one("SELECT COUNT(*) as count FROM queue WHERE status IN ('completed', 'failed')")
        total_processed = processed_row["count"] if processed_row else 0
        completed_row = self._fetch_one("SELECT COUNT(*) as count FROM queue WHERE status = 'completed'")
        total_completed = completed_row["count"] if completed_row else 0
        success_rate = (total_completed / total_processed * 100) if total_processed > 0 else 0

        # Growth trends (last 7/30/90 days comparisons)
        growth_7 = self._calculate_growth_trend(7)
        growth_30 = self._calculate_growth_trend(30)
        growth_90 = self._calculate_growth_trend(90)

        return {
            "totals": {
                "cities": total_cities,
                "states": total_states,
                "meetings": total_meetings,
                "items": total_items,
                "matters": total_matters,
                "cross_state_matters": cross_state_matters,
                "unique_topics": unique_topics,
            },
            "processing": {
                "queue_depth": queue_depth,
                "success_rate": round(success_rate, 1),
                "total_processed": total_processed,
                "total_completed": total_completed,
            },
            "growth": {
                "meetings_7d": growth_7,
                "meetings_30d": growth_30,
                "meetings_90d": growth_90,
            }
        }

    def _calculate_growth_trend(self, days: int) -> Dict[str, Any]:
        """Calculate growth trend for specified number of days"""
        if self.conn is None:
            raise DatabaseConnectionError("Database connection not established")

        # Meetings in the period
        period_row = self._fetch_one("""
            SELECT COUNT(*) as count
            FROM meetings
            WHERE date >= date('now', ?)
        """, (f'-{days} days',))
        period_count = period_row["count"] if period_row else 0

        # Meetings in previous period
        prev_row = self._fetch_one("""
            SELECT COUNT(*) as count
            FROM meetings
            WHERE date >= date('now', ?) AND date < date('now', ?)
        """, (f'-{days * 2} days', f'-{days} days'))
        prev_count = prev_row["count"] if prev_row else 0

        # Calculate percentage change
        if prev_count > 0:
            change_pct = ((period_count - prev_count) / prev_count) * 100
        else:
            change_pct = 100 if period_count > 0 else 0

        return {
            "current": period_count,
            "previous": prev_count,
            "change_percent": round(change_pct, 1),
        }

    def get_geographic_stats(self) -> Dict[str, Any]:
        """Get state-level geographic statistics"""
        if self.conn is None:
            raise DatabaseConnectionError("Database connection not established")

        # Meetings per state
        state_meetings = self._fetch_all("""
            SELECT c.state, COUNT(DISTINCT m.id) as meeting_count, COUNT(DISTINCT c.city_banana) as city_count
            FROM cities c
            LEFT JOIN meetings m ON c.city_banana = m.banana
            WHERE c.status = 'active'
            GROUP BY c.state
            ORDER BY meeting_count DESC
        """)

        # Vendor distribution
        vendor_dist = self._fetch_all("""
            SELECT vendor, COUNT(*) as count
            FROM cities
            WHERE status = 'active' AND vendor IS NOT NULL
            GROUP BY vendor
            ORDER BY count DESC
        """)

        # Coverage score per state (cities with meetings / total cities)
        state_coverage = []
        for state in state_meetings:
            cities_with_meetings = self._fetch_one("""
                SELECT COUNT(DISTINCT c.city_banana) as count
                FROM cities c
                JOIN meetings m ON c.city_banana = m.banana
                WHERE c.state = ? AND c.status = 'active'
            """, (state["state"],))

            coverage_pct = (cities_with_meetings["count"] / state["city_count"] * 100) if state["city_count"] > 0 else 0

            state_coverage.append({
                "state": state["state"],
                "meeting_count": state["meeting_count"],
                "city_count": state["city_count"],
                "cities_with_meetings": cities_with_meetings["count"],
                "coverage_percent": round(coverage_pct, 1),
            })

        return {
            "states": [dict(row) for row in state_meetings],
            "vendors": [dict(row) for row in vendor_dist],
            "coverage": state_coverage,
        }

    def get_topic_trends(self, start_date: Optional[str] = None, end_date: Optional[str] = None) -> Dict[str, Any]:
        """Get topic frequency and trend analysis"""
        if self.conn is None:
            raise DatabaseConnectionError("Database connection not established")

        # Build date filter
        date_filter = ""
        date_params = []
        if start_date and end_date:
            date_filter = " AND m.date BETWEEN ? AND ?"
            date_params = [start_date, end_date]

        # Overall topic frequency
        topic_freq = self._fetch_all(f"""
            SELECT value as topic, COUNT(*) as count
            FROM meetings m, json_each(m.topics)
            WHERE m.topics IS NOT NULL{date_filter}
            GROUP BY value
            ORDER BY count DESC
        """, tuple(date_params))

        # Trending topics (last 30 days vs previous 30 days)
        trending = self._fetch_all("""
            SELECT
                recent.topic,
                recent.count as recent_count,
                COALESCE(prev.count, 0) as previous_count,
                CASE
                    WHEN COALESCE(prev.count, 0) > 0 THEN
                        ROUND(((recent.count - COALESCE(prev.count, 0)) * 100.0 / COALESCE(prev.count, 1)), 1)
                    ELSE 100.0
                END as change_percent
            FROM (
                SELECT value as topic, COUNT(*) as count
                FROM meetings m, json_each(m.topics)
                WHERE m.topics IS NOT NULL
                AND m.date >= date('now', '-30 days')
                GROUP BY value
            ) recent
            LEFT JOIN (
                SELECT value as topic, COUNT(*) as count
                FROM meetings m, json_each(m.topics)
                WHERE m.topics IS NOT NULL
                AND m.date >= date('now', '-60 days')
                AND m.date < date('now', '-30 days')
                GROUP BY value
            ) prev ON recent.topic = prev.topic
            ORDER BY change_percent DESC
            LIMIT 10
        """)

        # Topic co-occurrence (which topics appear together)
        cooccurrence = self._fetch_all("""
            SELECT
                t1.value as topic1,
                t2.value as topic2,
                COUNT(*) as count
            FROM meetings m
            JOIN json_each(m.topics) t1
            JOIN json_each(m.topics) t2 ON t1.value < t2.value
            WHERE m.topics IS NOT NULL
            GROUP BY t1.value, t2.value
            HAVING COUNT(*) >= 5
            ORDER BY count DESC
            LIMIT 50
        """)

        return {
            "frequency": [dict(row) for row in topic_freq],
            "trending": [dict(row) for row in trending],
            "cooccurrence": [dict(row) for row in cooccurrence],
        }

    def get_matter_trends(self, start_date: Optional[str] = None, end_date: Optional[str] = None) -> Dict[str, Any]:
        """Get legislative matter tracking trends"""
        if self.conn is None:
            raise DatabaseConnectionError("Database connection not established")

        # Most tracked matters
        top_matters = self._fetch_all("""
            SELECT
                cm.matter_id,
                cm.title,
                cm.file_number,
                COUNT(DISTINCT ma.meeting_id) as appearance_count,
                COUNT(DISTINCT c.state) as state_count,
                cm.first_seen,
                cm.last_seen
            FROM city_matters cm
            JOIN matter_appearances ma ON cm.matter_id = ma.matter_id
            JOIN cities c ON cm.city_banana = c.city_banana
            GROUP BY cm.matter_id
            ORDER BY appearance_count DESC
            LIMIT 20
        """)

        # Cross-state matters
        cross_state = self._fetch_all("""
            SELECT
                cm.matter_id,
                cm.title,
                COUNT(DISTINCT c.state) as state_count,
                COUNT(DISTINCT cm.city_banana) as city_count,
                COUNT(DISTINCT ma.meeting_id) as meeting_count
            FROM city_matters cm
            JOIN cities c ON cm.city_banana = c.city_banana
            JOIN matter_appearances ma ON cm.matter_id = ma.matter_id
            GROUP BY cm.matter_id
            HAVING COUNT(DISTINCT c.state) > 1
            ORDER BY state_count DESC, city_count DESC
            LIMIT 20
        """)

        # Recent activity (matters with recent appearances)
        recent_activity = self._fetch_all("""
            SELECT
                cm.matter_id,
                cm.title,
                cm.last_seen,
                COUNT(DISTINCT ma.meeting_id) as total_appearances
            FROM city_matters cm
            JOIN matter_appearances ma ON cm.matter_id = ma.matter_id
            WHERE cm.last_seen >= date('now', '-30 days')
            GROUP BY cm.matter_id
            ORDER BY cm.last_seen DESC
            LIMIT 20
        """)

        # Matter velocity (appearances per month)
        velocity = []
        for matter in top_matters:
            first_seen = matter["first_seen"]
            last_seen = matter["last_seen"]

            # Calculate months between first and last appearance
            duration_row = self._fetch_one("""
                SELECT CAST((julianday(?) - julianday(?)) / 30.0 AS REAL) as months
            """, (last_seen, first_seen))

            months = max(duration_row["months"], 1) if duration_row else 1
            velocity_val = matter["appearance_count"] / months

            velocity.append({
                "matter_id": matter["matter_id"],
                "title": matter["title"],
                "appearances": matter["appearance_count"],
                "velocity": round(velocity_val, 2),
            })

        return {
            "top_matters": [dict(row) for row in top_matters],
            "cross_state": [dict(row) for row in cross_state],
            "recent_activity": [dict(row) for row in recent_activity],
            "velocity": sorted(velocity, key=lambda x: x["velocity"], reverse=True)[:20],
        }

    def get_processing_health(self, start_date: Optional[str] = None, end_date: Optional[str] = None) -> Dict[str, Any]:
        """Get processing system health metrics"""
        if self.conn is None:
            raise DatabaseConnectionError("Database connection not established")

        # Queue depth over time (last 30 days)
        queue_timeline = self._fetch_all("""
            SELECT
                DATE(created_at) as date,
                SUM(CASE WHEN status = 'pending' THEN 1 ELSE 0 END) as pending,
                SUM(CASE WHEN status = 'completed' THEN 1 ELSE 0 END) as completed,
                SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END) as failed
            FROM queue
            WHERE created_at >= date('now', '-30 days')
            GROUP BY DATE(created_at)
            ORDER BY date ASC
        """)

        # Success rates by vendor
        vendor_success = self._fetch_all("""
            SELECT
                c.vendor,
                COUNT(*) as total,
                SUM(CASE WHEN q.status = 'completed' THEN 1 ELSE 0 END) as completed,
                ROUND(SUM(CASE WHEN q.status = 'completed' THEN 1 ELSE 0 END) * 100.0 / COUNT(*), 1) as success_rate
            FROM queue q
            JOIN meetings m ON q.meeting_id = m.id
            JOIN cities c ON m.banana = c.city_banana
            WHERE q.status IN ('completed', 'failed')
            GROUP BY c.vendor
            HAVING COUNT(*) >= 10
            ORDER BY success_rate DESC
        """)

        # Processing speed (average time)
        speed_stats = self._fetch_one("""
            SELECT
                AVG(processing_time) as avg_time,
                MIN(processing_time) as min_time,
                MAX(processing_time) as max_time
            FROM cache
            WHERE processing_time IS NOT NULL
        """)

        # Cache statistics
        cache_stats = self._fetch_one("""
            SELECT
                COUNT(*) as total_cached,
                SUM(cache_hit_count) as total_hits,
                AVG(cache_hit_count) as avg_hits_per_entry
            FROM cache
        """)

        return {
            "queue_timeline": [dict(row) for row in queue_timeline],
            "vendor_success": [dict(row) for row in vendor_success],
            "processing_speed": {
                "average_seconds": round(speed_stats["avg_time"], 2) if speed_stats and speed_stats["avg_time"] else 0,
                "min_seconds": round(speed_stats["min_time"], 2) if speed_stats and speed_stats["min_time"] else 0,
                "max_seconds": round(speed_stats["max_time"], 2) if speed_stats and speed_stats["max_time"] else 0,
            },
            "cache": {
                "total_entries": cache_stats["total_cached"] if cache_stats else 0,
                "total_hits": cache_stats["total_hits"] if cache_stats else 0,
                "avg_hits_per_entry": round(cache_stats["avg_hits_per_entry"], 2) if cache_stats and cache_stats["avg_hits_per_entry"] else 0,
            }
        }

    def extract_funding_data(self) -> Dict[str, Any]:
        """Extract and analyze funding information from meeting summaries"""
        if self.conn is None:
            raise DatabaseConnectionError("Database connection not established")

        # Find meetings with potential funding mentions
        # Look for dollar signs, "budget", "contract", "grant", etc.
        funding_meetings = self._fetch_all("""
            SELECT
                m.id,
                m.banana,
                m.title,
                m.date,
                m.summary,
                m.packet_url
            FROM meetings m
            WHERE m.summary IS NOT NULL
            AND (
                m.summary LIKE '%$%'
                OR LOWER(m.summary) LIKE '%budget%'
                OR LOWER(m.summary) LIKE '%contract%'
                OR LOWER(m.summary) LIKE '%grant%'
                OR LOWER(m.summary) LIKE '%million%'
                OR LOWER(m.summary) LIKE '%billion%'
                OR LOWER(m.summary) LIKE '%funding%'
            )
            ORDER BY m.date DESC
            LIMIT 100
        """)

        # Aggregate by city
        city_funding = self._fetch_all("""
            SELECT
                m.banana,
                c.city_name,
                c.state,
                COUNT(*) as budget_meeting_count
            FROM meetings m
            JOIN cities c ON m.banana = c.city_banana
            WHERE m.summary IS NOT NULL
            AND (
                m.summary LIKE '%$%'
                OR LOWER(m.summary) LIKE '%budget%'
                OR LOWER(m.summary) LIKE '%contract%'
            )
            GROUP BY m.banana
            ORDER BY budget_meeting_count DESC
            LIMIT 20
        """)

        # Aggregate by state
        state_funding = self._fetch_all("""
            SELECT
                c.state,
                COUNT(*) as budget_meeting_count
            FROM meetings m
            JOIN cities c ON m.banana = c.city_banana
            WHERE m.summary IS NOT NULL
            AND (
                m.summary LIKE '%$%'
                OR LOWER(m.summary) LIKE '%budget%'
            )
            GROUP BY c.state
            ORDER BY budget_meeting_count DESC
        """)

        return {
            "total_funding_meetings": len(funding_meetings),
            "top_meetings": [dict(row) for row in funding_meetings[:20]],
            "by_city": [dict(row) for row in city_funding],
            "by_state": [dict(row) for row in state_funding],
        }
