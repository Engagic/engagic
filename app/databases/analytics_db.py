import json
import logging
from typing import List, Dict, Any
from datetime import datetime
from .base_db import BaseDatabase

logger = logging.getLogger("engagic")


class AnalyticsDatabase(BaseDatabase):
    """Database for usage metrics, search logs, and demand tracking"""

    def _init_database(self):
        """Initialize the analytics database schema"""
        schema = """
        -- Usage metrics table - track user behavior (minimal, privacy-focused)
        CREATE TABLE IF NOT EXISTS usage_metrics (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            city_banana TEXT,  -- Reference to city (no FK since it's in different DB)
            zipcode TEXT,
            search_query TEXT,
            search_type TEXT,
            topic_flags TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        -- City requests table - track user demand for missing cities
        CREATE TABLE IF NOT EXISTS city_requests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            city_name TEXT NOT NULL,
            state TEXT NOT NULL,
            zipcode TEXT,
            search_query TEXT NOT NULL,
            search_type TEXT NOT NULL,
            user_ip TEXT,
            request_count INTEGER DEFAULT 1,
            first_requested TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            last_requested TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            status TEXT DEFAULT 'requested',
            priority_score INTEGER DEFAULT 0,
            UNIQUE(city_name, state)
        );

        -- Search analytics - aggregated search patterns (daily)
        CREATE TABLE IF NOT EXISTS search_analytics (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT NOT NULL,  -- YYYY-MM-DD format
            total_searches INTEGER DEFAULT 0,
            zipcode_searches INTEGER DEFAULT 0,
            city_searches INTEGER DEFAULT 0,
            ambiguous_searches INTEGER DEFAULT 0,
            successful_searches INTEGER DEFAULT 0,
            top_cities TEXT,  -- JSON array of top searched cities
            top_zipcodes TEXT,  -- JSON array of top searched zipcodes
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(date)
        );

        -- Create indices for performance
        CREATE INDEX IF NOT EXISTS idx_usage_city_banana ON usage_metrics(city_banana);
        CREATE INDEX IF NOT EXISTS idx_usage_zipcode ON usage_metrics(zipcode);
        CREATE INDEX IF NOT EXISTS idx_usage_created_at ON usage_metrics(created_at);
        CREATE INDEX IF NOT EXISTS idx_city_requests_name_state ON city_requests(city_name, state);
        CREATE INDEX IF NOT EXISTS idx_city_requests_count ON city_requests(request_count);
        CREATE INDEX IF NOT EXISTS idx_city_requests_priority ON city_requests(priority_score);
        CREATE INDEX IF NOT EXISTS idx_search_analytics_date ON search_analytics(date);
        """
        self.execute_script(schema)

    def log_search(
        self,
        search_query: str,
        search_type: str,
        city_banana: str = None,
        zipcode: str = None,
        topic_flags: List[str] = None,
    ):
        """Log search activity (minimal data collection)"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO usage_metrics 
                (city_banana, zipcode, search_query, search_type, topic_flags)
                VALUES (?, ?, ?, ?, ?)
            """,
                (
                    city_banana,
                    zipcode,
                    search_query,
                    search_type,
                    json.dumps(topic_flags) if topic_flags else None,
                ),
            )
            conn.commit()

    def log_city_request(
        self,
        city_name: str,
        state: str,
        search_query: str,
        search_type: str,
        zipcode: str = None,
        user_ip: str = None,
    ) -> int:
        """Log a request for a missing city - track demand"""
        with self.get_connection() as conn:
            cursor = conn.cursor()

            # Normalize city and state
            city_normalized = city_name.strip().title()
            state_normalized = state.strip().upper()

            # Check if we already have this request
            cursor.execute(
                """
                SELECT id, request_count FROM city_requests 
                WHERE city_name = ? AND state = ?
            """,
                (city_normalized, state_normalized),
            )

            existing = cursor.fetchone()

            if existing:
                # Increment request count
                new_count = existing["request_count"] + 1
                cursor.execute(
                    """
                    UPDATE city_requests 
                    SET request_count = ?, last_requested = CURRENT_TIMESTAMP,
                        priority_score = ? * 10 + COALESCE(?, 0)
                    WHERE id = ?
                """,
                    (
                        new_count,
                        new_count,
                        zipcode and len(zipcode) or 0,
                        existing["id"],
                    ),
                )

                logger.info(
                    f"Updated city request: {city_normalized}, {state_normalized} (count: {new_count})"
                )
                conn.commit()
                return existing["id"]
            else:
                # New request
                priority_score = 10 + (len(zipcode) if zipcode else 0)
                cursor.execute(
                    """
                    INSERT INTO city_requests 
                    (city_name, state, zipcode, search_query, search_type, user_ip, priority_score)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                    (
                        city_normalized,
                        state_normalized,
                        zipcode,
                        search_query,
                        search_type,
                        user_ip,
                        priority_score,
                    ),
                )

                request_id = cursor.lastrowid
                conn.commit()
                logger.info(
                    f"New city request logged: {city_normalized}, {state_normalized} (ID: {request_id})"
                )
                return request_id

    def get_top_city_requests(self, limit: int = 20) -> List[Dict[str, Any]]:
        """Get most requested cities for admin review"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT city_name, state, zipcode, request_count, priority_score,
                       first_requested, last_requested, status
                FROM city_requests 
                ORDER BY priority_score DESC, request_count DESC, last_requested DESC
                LIMIT ?
            """,
                (limit,),
            )

            return [dict(row) for row in cursor.fetchall()]

    def get_city_request_stats(self) -> Dict[str, Any]:
        """Get stats on city requests"""
        with self.get_connection() as conn:
            cursor = conn.cursor()

            # Total requests
            cursor.execute("SELECT COUNT(*) as count FROM city_requests")
            total_requests = cursor.fetchone()["count"]

            # Total demand (sum of request counts)
            cursor.execute(
                "SELECT SUM(request_count) as total_demand FROM city_requests"
            )
            total_demand = cursor.fetchone()["total_demand"] or 0

            # Recent requests (last 7 days)
            cursor.execute(
                "SELECT COUNT(*) as count FROM city_requests WHERE last_requested > datetime('now', '-7 days')"
            )
            recent_requests = cursor.fetchone()["count"]

            # Top states
            cursor.execute("""
                SELECT state, COUNT(*) as city_count, SUM(request_count) as total_requests
                FROM city_requests 
                GROUP BY state 
                ORDER BY total_requests DESC 
                LIMIT 5
            """)
            top_states = [dict(row) for row in cursor.fetchall()]

            return {
                "total_unique_cities_requested": total_requests,
                "total_demand": total_demand,
                "recent_activity": recent_requests,
                "top_states": top_states,
            }

    def update_daily_analytics(self, date: str = None) -> Dict[str, Any]:
        """Update daily search analytics for a given date (default: today)"""
        if not date:
            date = datetime.now().strftime("%Y-%m-%d")

        with self.get_connection() as conn:
            cursor = conn.cursor()

            # Get search counts for the date
            cursor.execute(
                """
                SELECT 
                    COUNT(*) as total_searches,
                    SUM(CASE WHEN search_type = 'zipcode' THEN 1 ELSE 0 END) as zipcode_searches,
                    SUM(CASE WHEN search_type LIKE 'city%' THEN 1 ELSE 0 END) as city_searches,
                    SUM(CASE WHEN search_type = 'city_name_ambiguous' THEN 1 ELSE 0 END) as ambiguous_searches
                FROM usage_metrics 
                WHERE DATE(created_at) = ?
            """,
                (date,),
            )

            stats = cursor.fetchone()

            # Get top cities and zipcodes
            cursor.execute(
                """
                SELECT city_banana, COUNT(*) as count
                FROM usage_metrics 
                WHERE DATE(created_at) = ? AND city_banana IS NOT NULL
                GROUP BY city_banana 
                ORDER BY count DESC 
                LIMIT 10
            """,
                (date,),
            )
            top_cities = [
                {"city_banana": row[0], "count": row[1]} for row in cursor.fetchall()
            ]

            cursor.execute(
                """
                SELECT zipcode, COUNT(*) as count
                FROM usage_metrics 
                WHERE DATE(created_at) = ? AND zipcode IS NOT NULL
                GROUP BY zipcode 
                ORDER BY count DESC 
                LIMIT 10
            """,
                (date,),
            )
            top_zipcodes = [
                {"zipcode": row[0], "count": row[1]} for row in cursor.fetchall()
            ]

            # Insert or update analytics
            cursor.execute(
                """
                INSERT OR REPLACE INTO search_analytics 
                (date, total_searches, zipcode_searches, city_searches, ambiguous_searches, 
                 top_cities, top_zipcodes)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    date,
                    stats["total_searches"],
                    stats["zipcode_searches"],
                    stats["city_searches"],
                    stats["ambiguous_searches"],
                    json.dumps(top_cities),
                    json.dumps(top_zipcodes),
                ),
            )

            conn.commit()

            return {
                "date": date,
                "total_searches": stats["total_searches"],
                "zipcode_searches": stats["zipcode_searches"],
                "city_searches": stats["city_searches"],
                "ambiguous_searches": stats["ambiguous_searches"],
                "top_cities": top_cities,
                "top_zipcodes": top_zipcodes,
            }

    def get_analytics_summary(self, days: int = 7) -> Dict[str, Any]:
        """Get analytics summary for the last N days"""
        with self.get_connection() as conn:
            cursor = conn.cursor()

            # Get aggregated stats
            cursor.execute(
                """
                SELECT 
                    SUM(total_searches) as total_searches,
                    SUM(zipcode_searches) as zipcode_searches,
                    SUM(city_searches) as city_searches,
                    SUM(ambiguous_searches) as ambiguous_searches,
                    COUNT(*) as days_with_data
                FROM search_analytics 
                WHERE date > date('now', '-{} days')
            """.format(days)
            )

            summary = dict(cursor.fetchone())

            # Get recent daily breakdown
            cursor.execute(
                """
                SELECT date, total_searches, zipcode_searches, city_searches
                FROM search_analytics 
                WHERE date > date('now', '-{} days')
                ORDER BY date DESC
            """.format(days)
            )

            daily_breakdown = [dict(row) for row in cursor.fetchall()]

            return {
                "period_days": days,
                "summary": summary,
                "daily_breakdown": daily_breakdown,
            }

    def cleanup_old_analytics(self, days_old: int = 365) -> int:
        """Clean up old analytics data"""
        logger.info(f"Cleaning up analytics older than {days_old} days")
        with self.get_connection() as conn:
            cursor = conn.cursor()

            # Clean usage metrics
            cursor.execute(
                """
                DELETE FROM usage_metrics 
                WHERE created_at < datetime('now', '-{} days')
            """.format(days_old)
            )
            usage_deleted = cursor.rowcount

            # Clean search analytics (keep daily summaries longer)
            cursor.execute(
                """
                DELETE FROM search_analytics 
                WHERE date < date('now', '-{} days')
            """.format(days_old * 2)
            )  # Keep analytics twice as long
            analytics_deleted = cursor.rowcount

            conn.commit()
            total_deleted = usage_deleted + analytics_deleted
            logger.info(f"Cleaned up {total_deleted} old analytics entries")
            return total_deleted
