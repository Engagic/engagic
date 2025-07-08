import sqlite3
import json
import logging
from datetime import datetime, timezone
from typing import Dict, Optional, List, Any, Tuple
from contextlib import contextmanager
import hashlib
from uszipcode import SearchEngine

logger = logging.getLogger("engagic")


class MeetingDatabase:
    def __init__(self, db_path: str = "/root/engagic/app/meetings.db"):
        self.db_path = db_path
        self.zipcode_search = SearchEngine()
        logger.info(f"Initializing database at {db_path}")
        self._init_database()

    def _init_database(self):
        """Initialize database with clean schema"""
        with sqlite3.connect(self.db_path) as conn:
            # Cities table - master city registry
            conn.execute("""
                CREATE TABLE IF NOT EXISTS cities (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    city_name TEXT NOT NULL,
                    state TEXT NOT NULL,
                    city_slug TEXT NOT NULL UNIQUE,
                    vendor TEXT,
                    county TEXT,
                    status TEXT DEFAULT 'active',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(city_name, state, vendor)
                )
            """)

            # Zipcodes table - zipcode to city mapping
            conn.execute("""
                CREATE TABLE IF NOT EXISTS zipcodes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    zipcode TEXT NOT NULL,
                    city_id INTEGER NOT NULL,
                    is_primary BOOLEAN DEFAULT FALSE,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (city_id) REFERENCES cities(id),
                    UNIQUE(zipcode, city_id)
                )
            """)

            # Meetings table - meeting data cache
            conn.execute("""
                CREATE TABLE IF NOT EXISTS meetings (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    city_id INTEGER NOT NULL,
                    meeting_id TEXT,
                    meeting_name TEXT,
                    meeting_date DATETIME,
                    packet_url TEXT NOT NULL,
                    raw_packet_size INTEGER,
                    processed_summary TEXT,
                    processing_time_seconds REAL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    last_accessed TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (city_id) REFERENCES cities(id),
                    UNIQUE(packet_url)
                )
            """)

            # Usage metrics table - track user behavior (minimal, privacy-focused)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS usage_metrics (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    city_id INTEGER,
                    zipcode TEXT,
                    search_query TEXT,
                    search_type TEXT,
                    topic_flags TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (city_id) REFERENCES cities(id)
                )
            """)

            # Processing cache table - LLM processing cache
            conn.execute("""
                CREATE TABLE IF NOT EXISTS processing_cache (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    packet_url TEXT NOT NULL UNIQUE,
                    content_hash TEXT,
                    raw_text_size INTEGER,
                    cleaned_text_size INTEGER,
                    summary_size INTEGER,
                    processing_duration_seconds REAL,
                    cache_hit_count INTEGER DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    last_accessed TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # Create indices for performance
            conn.execute("CREATE INDEX IF NOT EXISTS idx_cities_slug ON cities(city_slug)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_cities_name_state ON cities(city_name, state)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_zipcodes_zipcode ON zipcodes(zipcode)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_zipcodes_city_id ON zipcodes(city_id)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_meetings_city_id ON meetings(city_id)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_meetings_packet_url ON meetings(packet_url)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_meetings_date ON meetings(meeting_date)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_usage_city_id ON usage_metrics(city_id)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_usage_zipcode ON usage_metrics(zipcode)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_cache_url ON processing_cache(packet_url)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_cache_hash ON processing_cache(content_hash)")

    @contextmanager
    def get_connection(self):
        """Context manager for database connections"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
        finally:
            conn.close()

    def add_city(self, city_name: str, state: str, city_slug: str, vendor: str, 
                 county: str = None, zipcodes: List[str] = None) -> int:
        """Add a new city with optional zipcodes"""
        logger.info(f"Adding city: {city_name}, {state} with vendor {vendor}")
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            # Insert city
            cursor.execute("""
                INSERT INTO cities (city_name, state, city_slug, vendor, county)
                VALUES (?, ?, ?, ?, ?)
            """, (city_name, state, city_slug, vendor, county))
            
            city_id = cursor.lastrowid
            
            # Add zipcodes if provided
            if zipcodes:
                for i, zipcode in enumerate(zipcodes):
                    is_primary = i == 0  # First zipcode is primary
                    cursor.execute("""
                        INSERT OR IGNORE INTO zipcodes (zipcode, city_id, is_primary)
                        VALUES (?, ?, ?)
                    """, (zipcode, city_id, is_primary))
            
            conn.commit()
            logger.info(f"Successfully added city {city_name} with ID {city_id}")
            return city_id

    def get_city_by_zipcode(self, zipcode: str) -> Optional[Dict[str, Any]]:
        """Get city information by zipcode"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT c.*, z.zipcode, z.is_primary
                FROM cities c
                JOIN zipcodes z ON c.id = z.city_id
                WHERE z.zipcode = ?
            """, (zipcode,))
            
            row = cursor.fetchone()
            if row:
                return dict(row)
            return None

    def get_city_by_name(self, city_name: str, state: str) -> Optional[Dict[str, Any]]:
        """Get city information by name and state (case-insensitive with space normalization)"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            # Normalize inputs: case-insensitive and handle spaces
            city_normalized = city_name.strip().replace(' ', '').lower()
            state_normalized = state.strip().upper()
            
            cursor.execute("""
                SELECT c.*, 
                       GROUP_CONCAT(z.zipcode) as zipcodes,
                       (SELECT z2.zipcode FROM zipcodes z2 WHERE z2.city_id = c.id AND z2.is_primary = 1) as primary_zipcode
                FROM cities c
                LEFT JOIN zipcodes z ON c.id = z.city_id
                WHERE LOWER(REPLACE(c.city_name, ' ', '')) = ? AND UPPER(c.state) = ?
                GROUP BY c.id
            """, (city_normalized, state_normalized))
            
            row = cursor.fetchone()
            if row:
                result = dict(row)
                if result['zipcodes']:
                    result['zipcodes'] = result['zipcodes'].split(',')
                return result
            return None

    def get_city_by_slug(self, city_slug: str) -> Optional[Dict[str, Any]]:
        """Get city information by slug"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT c.*, 
                       GROUP_CONCAT(z.zipcode) as zipcodes,
                       (SELECT z2.zipcode FROM zipcodes z2 WHERE z2.city_id = c.id AND z2.is_primary = 1) as primary_zipcode
                FROM cities c
                LEFT JOIN zipcodes z ON c.id = z.city_id
                WHERE c.city_slug = ?
                GROUP BY c.id
            """, (city_slug,))
            
            row = cursor.fetchone()
            if row:
                result = dict(row)
                if result['zipcodes']:
                    result['zipcodes'] = result['zipcodes'].split(',')
                return result
            return None

    def store_meeting_data(self, meeting_data: Dict[str, Any], vendor: str = None) -> int:
        """Store meeting data linked to city"""
        city_slug = meeting_data.get('city_slug')
        logger.debug(f"Storing meeting data for {city_slug}: {meeting_data.get('meeting_name', 'Unknown')}")
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            # Get city_id from city_slug
            city_slug = meeting_data.get('city_slug')
            if not city_slug:
                raise ValueError("city_slug required in meeting_data")
                
            cursor.execute("SELECT id FROM cities WHERE city_slug = ?", (city_slug,))
            city_row = cursor.fetchone()
            if not city_row:
                raise ValueError(f"City not found for slug: {city_slug}")
                
            city_id = city_row['id']
            
            # Insert meeting
            cursor.execute("""
                INSERT OR REPLACE INTO meetings 
                (city_id, meeting_id, meeting_name, meeting_date, packet_url, last_accessed)
                VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            """, (
                city_id,
                meeting_data.get('meeting_id'),
                meeting_data.get('meeting_name'),
                meeting_data.get('meeting_date'),
                meeting_data.get('packet_url')
            ))
            
            conn.commit()
            return cursor.lastrowid

    def store_meeting_summary(self, meeting_data: Dict[str, Any], summary: str, 
                            processing_time: float, vendor: str = None) -> int:
        """Store processed meeting summary"""
        city_slug = meeting_data.get('city_slug')
        logger.info(f"Storing meeting summary for {city_slug}: {len(summary)} chars, {processing_time:.2f}s")
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            # Get city_id from city_slug
            city_slug = meeting_data.get('city_slug')
            if not city_slug:
                raise ValueError("city_slug required in meeting_data")
                
            cursor.execute("SELECT id FROM cities WHERE city_slug = ?", (city_slug,))
            city_row = cursor.fetchone()
            if not city_row:
                raise ValueError(f"City not found for slug: {city_slug}")
                
            city_id = city_row['id']
            
            # Insert/update meeting with summary
            cursor.execute("""
                INSERT OR REPLACE INTO meetings 
                (city_id, meeting_id, meeting_name, meeting_date, packet_url, 
                 processed_summary, processing_time_seconds, last_accessed)
                VALUES (?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            """, (
                city_id,
                meeting_data.get('meeting_id'),
                meeting_data.get('meeting_name'),
                meeting_data.get('meeting_date'),
                meeting_data.get('packet_url'),
                summary,
                processing_time
            ))
            
            conn.commit()
            return cursor.lastrowid

    def get_meetings_by_city(self, city_slug: str, limit: int = 50) -> List[Dict[str, Any]]:
        """Get meetings for a city by slug"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT m.*, c.city_name, c.state, c.vendor
                FROM meetings m
                JOIN cities c ON m.city_id = c.id
                WHERE c.city_slug = ?
                ORDER BY m.meeting_date DESC, m.last_accessed DESC
                LIMIT ?
            """, (city_slug, limit))
            
            return [dict(row) for row in cursor.fetchall()]

    def get_cached_summary(self, packet_url: str) -> Optional[Dict[str, Any]]:
        """Get cached meeting summary by packet URL"""
        logger.debug(f"Checking cache for packet: {packet_url}")
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT m.*, c.city_name, c.state, c.vendor, c.city_slug
                FROM meetings m
                JOIN cities c ON m.city_id = c.id
                WHERE m.packet_url = ? AND m.processed_summary IS NOT NULL
            """, (packet_url,))
            
            row = cursor.fetchone()
            if row:
                # Update last accessed
                cursor.execute("""
                    UPDATE meetings SET last_accessed = CURRENT_TIMESTAMP 
                    WHERE packet_url = ?
                """, (packet_url,))
                conn.commit()
                logger.debug(f"Cache hit for packet: {packet_url}")
                return dict(row)
            logger.debug(f"Cache miss for packet: {packet_url}")
            return None

    def get_recent_meetings(self, limit: int = 20) -> List[Dict[str, Any]]:
        """Get most recently accessed meetings across all cities"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT m.*, c.city_name, c.state, c.vendor, c.city_slug
                FROM meetings m
                JOIN cities c ON m.city_id = c.id
                ORDER BY m.last_accessed DESC
                LIMIT ?
            """, (limit,))
            
            return [dict(row) for row in cursor.fetchall()]

    def log_search(self, search_query: str, search_type: str, city_id: int = None, 
                  zipcode: str = None, topic_flags: List[str] = None):
        """Log search activity (minimal data collection)"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO usage_metrics 
                (city_id, zipcode, search_query, search_type, topic_flags)
                VALUES (?, ?, ?, ?, ?)
            """, (
                city_id,
                zipcode,
                search_query,
                search_type,
                json.dumps(topic_flags) if topic_flags else None
            ))
            conn.commit()

    def get_cache_stats(self) -> Dict[str, Any]:
        """Get cache statistics"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            # Cities count
            cursor.execute("SELECT COUNT(*) as count FROM cities")
            cities_count = cursor.fetchone()['count']
            
            # Meetings count
            cursor.execute("SELECT COUNT(*) as count FROM meetings")
            meetings_count = cursor.fetchone()['count']
            
            # Processed meetings count
            cursor.execute("SELECT COUNT(*) as count FROM meetings WHERE processed_summary IS NOT NULL")
            processed_count = cursor.fetchone()['count']
            
            # Recent activity
            cursor.execute("SELECT COUNT(*) as count FROM meetings WHERE last_accessed > datetime('now', '-7 days')")
            recent_activity = cursor.fetchone()['count']
            
            return {
                'cities_count': cities_count,
                'meetings_count': meetings_count,
                'processed_count': processed_count,
                'recent_activity': recent_activity
            }

    def cleanup_old_entries(self, days_old: int = 90) -> int:
        """Clean up old cache entries"""
        logger.info(f"Cleaning up cache entries older than {days_old} days")
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                DELETE FROM meetings 
                WHERE last_accessed < datetime('now', '-{} days')
            """.format(days_old))
            deleted_count = cursor.rowcount
            conn.commit()
            logger.info(f"Cleaned up {deleted_count} old cache entries")
            return deleted_count

    def get_all_cities(self) -> List[Dict[str, Any]]:
        """Get all cities with their zipcode information"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT c.*, 
                       GROUP_CONCAT(z.zipcode) as zipcodes,
                       (SELECT z2.zipcode FROM zipcodes z2 WHERE z2.city_id = c.id AND z2.is_primary = 1) as primary_zipcode
                FROM cities c
                LEFT JOIN zipcodes z ON c.id = z.city_id
                GROUP BY c.id
                ORDER BY c.city_name, c.state
            """)
            
            results = []
            for row in cursor.fetchall():
                result = dict(row)
                if result['zipcodes']:
                    result['zipcodes'] = result['zipcodes'].split(',')
                results.append(result)
            return results


def get_city_info(city_slug: str) -> Dict[str, Any]:
    """Utility function to get city info by slug"""
    db = MeetingDatabase()
    city_info = db.get_city_by_slug(city_slug)
    return city_info or {}