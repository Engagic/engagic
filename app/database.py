import sqlite3
from datetime import datetime, timezone
from typing import Dict, Optional, List, Any
from contextlib import contextmanager


class MeetingDatabase:
    def __init__(self, db_path: str = "/root/engagic/app/meetings.db"):
        self.db_path = db_path
        self._init_database()

    def _init_database(self):
        """Initialize database with schema"""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS meetings (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    vendor TEXT NOT NULL DEFAULT 'primegov',
                    zipcode TEXT,
                    city_name TEXT,
                    city_slug TEXT NOT NULL,
                    meeting_date DATE,
                    meeting_name TEXT,
                    packet_url TEXT UNIQUE NOT NULL,
                    processed_summary TEXT,
                    processing_time_seconds REAL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    last_accessed TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            conn.execute("""
                CREATE TABLE IF NOT EXISTS zipcode_entries (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    zipcode TEXT UNIQUE NOT NULL,
                    city_name TEXT NOT NULL,
                    city_slug TEXT NOT NULL,
                    state TEXT,
                    county TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    last_accessed TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # Handle migration for existing tables
            self._migrate_add_vendor_column(conn)

            # Create indices for performance
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_packet_url ON meetings(packet_url)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_city_slug ON meetings(city_slug)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_meeting_date ON meetings(meeting_date)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_last_accessed ON meetings(last_accessed)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_vendor ON meetings(vendor)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_zipcode ON zipcode_entries(zipcode)"
            )

            conn.commit()

    def _migrate_add_vendor_column(self, conn):
        """Add vendor column to existing tables if it doesn't exist"""
        try:
            # Check if vendor column exists
            cursor = conn.execute("PRAGMA table_info(meetings)")
            columns = [row[1] for row in cursor.fetchall()]
            
            if 'vendor' not in columns:
                print("Adding vendor column to existing database...")
                conn.execute("ALTER TABLE meetings ADD COLUMN vendor TEXT DEFAULT 'primegov'")
                # Update existing records to have vendor set
                conn.execute("UPDATE meetings SET vendor = 'primegov' WHERE vendor IS NULL")
                print("Migration complete: vendor column added")
        except Exception as e:
            print(f"Migration warning: {e}")

    @contextmanager
    def get_connection(self):
        """Context manager for database connections"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row  # Enable dict-like access
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def get_cached_summary(self, packet_url: str) -> Optional[Dict[str, Any]]:
        """Check if we have a cached summary for this packet URL"""
        with self.get_connection() as conn:
            cursor = conn.execute(
                """SELECT id, vendor, zipcode, city_name, city_slug, meeting_date, meeting_name, 
                          packet_url, processed_summary, processing_time_seconds, 
                          created_at, last_accessed 
                   FROM meetings WHERE packet_url = ?""",
                (packet_url,),
            )
            row = cursor.fetchone()

            if row:
                # Update last_accessed timestamp
                conn.execute(
                    "UPDATE meetings SET last_accessed = ? WHERE id = ?",
                    (datetime.now(timezone.utc).isoformat(), row["id"]),
                )
                return dict(row)

            return None

    def store_meeting_summary(
        self, meeting_data: Dict[str, Any], summary: str, processing_time: float, vendor: str
    ) -> int:
        """Store a new meeting summary in the database"""
        with self.get_connection() as conn:
            cursor = conn.execute(
                """INSERT INTO meetings 
                   (vendor, zipcode, city_name, city_slug, meeting_date, meeting_name, 
                    packet_url, processed_summary, processing_time_seconds, 
                    created_at, last_accessed)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    vendor,
                    meeting_data.get("zipcode"),
                    meeting_data.get("city_name"),
                    meeting_data.get("city_slug"),
                    meeting_data.get("meeting_date"),
                    meeting_data.get("meeting_name"),
                    meeting_data["packet_url"],
                    summary,
                    processing_time,
                    datetime.now(timezone.utc).isoformat(),
                    datetime.now(timezone.utc).isoformat(),
                ),
            )
            return cursor.lastrowid

    def get_meetings_by_city(
        self, city_slug: str, limit: int = 50
    ) -> List[Dict[str, Any]]:
        """Get meetings for a specific city, ordered by meeting date desc"""
        with self.get_connection() as conn:
            cursor = conn.execute(
                """SELECT id, vendor, zipcode, city_name, city_slug, meeting_date, meeting_name, 
                          packet_url, processed_summary, processing_time_seconds, 
                          created_at, last_accessed 
                   FROM meetings 
                   WHERE city_slug = ? 
                   ORDER BY meeting_date DESC 
                   LIMIT ?""",
                (city_slug, limit),
            )
            return [dict(row) for row in cursor.fetchall()]

    def get_recent_meetings(self, limit: int = 20) -> List[Dict[str, Any]]:
        """Get most recently accessed meetings across all cities"""
        with self.get_connection() as conn:
            cursor = conn.execute(
                """SELECT id, vendor, zipcode, city_name, city_slug, meeting_date, meeting_name, 
                          packet_url, processed_summary, processing_time_seconds, 
                          created_at, last_accessed 
                   FROM meetings 
                   ORDER BY last_accessed DESC 
                   LIMIT ?""",
                (limit,),
            )
            return [dict(row) for row in cursor.fetchall()]

    def search_meetings(
        self, query: str, city_slug: str = None, limit: int = 50
    ) -> List[Dict[str, Any]]:
        """Search meetings by summary content or meeting name"""
        query_pattern = f"%{query}%"

        with self.get_connection() as conn:
            if city_slug:
                cursor = conn.execute(
                    """SELECT id, vendor, zipcode, city_name, city_slug, meeting_date, meeting_name, 
                              packet_url, processed_summary, processing_time_seconds, 
                              created_at, last_accessed 
                       FROM meetings 
                       WHERE city_slug = ? 
                       AND (meeting_name LIKE ? OR processed_summary LIKE ?)
                       ORDER BY meeting_date DESC 
                       LIMIT ?""",
                    (city_slug, query_pattern, query_pattern, limit),
                )
            else:
                cursor = conn.execute(
                    """SELECT id, vendor, zipcode, city_name, city_slug, meeting_date, meeting_name, 
                              packet_url, processed_summary, processing_time_seconds, 
                              created_at, last_accessed 
                       FROM meetings 
                       WHERE meeting_name LIKE ? OR processed_summary LIKE ?
                       ORDER BY meeting_date DESC 
                       LIMIT ?""",
                    (query_pattern, query_pattern, limit),
                )

            return [dict(row) for row in cursor.fetchall()]

    def get_meetings_by_vendor(self, vendor: str, limit: int = 50) -> List[Dict[str, Any]]:
        """Get meetings from specific vendor"""
        with self.get_connection() as conn:
            cursor = conn.execute(
                """SELECT id, vendor, zipcode, city_name, city_slug, meeting_date, meeting_name, 
                          packet_url, processed_summary, processing_time_seconds, 
                          created_at, last_accessed 
                   FROM meetings 
                   WHERE vendor = ? 
                   ORDER BY meeting_date DESC 
                   LIMIT ?""",
                (vendor, limit),
            )
            return [dict(row) for row in cursor.fetchall()]

    def get_adapter_for_meeting(self, packet_url: str) -> Optional[str]:
        """Return which adapter to use for re-processing this meeting"""
        with self.get_connection() as conn:
            cursor = conn.execute('SELECT vendor FROM meetings WHERE packet_url = ?', (packet_url,))
            row = cursor.fetchone()
            return row['vendor'] if row else None

    def get_cache_stats(self) -> Dict[str, Any]:
        """Get statistics about the cache"""
        with self.get_connection() as conn:
            stats = {}

            # Total meetings cached
            cursor = conn.execute("SELECT COUNT(*) as total FROM meetings")
            stats["total_meetings"] = cursor.fetchone()["total"]

            # Meetings by city
            cursor = conn.execute(
                """SELECT city_slug, COUNT(*) as count 
                   FROM meetings 
                   GROUP BY city_slug 
                   ORDER BY count DESC"""
            )
            stats["meetings_by_city"] = [dict(row) for row in cursor.fetchall()]

            # Meetings by vendor
            cursor = conn.execute(
                """SELECT vendor, COUNT(*) as count 
                   FROM meetings 
                   GROUP BY vendor 
                   ORDER BY count DESC"""
            )
            stats["meetings_by_vendor"] = [dict(row) for row in cursor.fetchall()]

            # Average processing time
            cursor = conn.execute(
                "SELECT AVG(processing_time_seconds) as avg_time FROM meetings WHERE processing_time_seconds IS NOT NULL"
            )
            avg_time = cursor.fetchone()["avg_time"]
            stats["avg_processing_time"] = round(avg_time, 2) if avg_time else None

            # Cache hit potential (estimate based on recent activity)
            cursor = conn.execute(
                """SELECT COUNT(*) as recent_access 
                   FROM meetings 
                   WHERE last_accessed > datetime('now', '-7 days')"""
            )
            stats["recent_activity"] = cursor.fetchone()["recent_access"]

            return stats

    def cleanup_old_entries(self, days_old: int = 90) -> int:
        """Remove entries older than specified days that haven't been accessed recently"""
        with self.get_connection() as conn:
            cursor = conn.execute(
                """DELETE FROM meetings 
                   WHERE created_at < datetime('now', '-{} days') 
                   AND last_accessed < datetime('now', '-30 days')""".format(days_old)
            )
            return cursor.rowcount

    def get_zipcode_entry(self, zipcode: str) -> Optional[Dict[str, Any]]:
        """Get zipcode entry with associated meetings"""
        with self.get_connection() as conn:
            # Get zipcode entry
            cursor = conn.execute(
                """SELECT zipcode, city_name, city_slug, state, county, created_at, last_accessed 
                   FROM zipcode_entries WHERE zipcode = ?""",
                (zipcode,),
            )
            zipcode_row = cursor.fetchone()
            
            if not zipcode_row:
                return None
            
            # Update last_accessed
            conn.execute(
                "UPDATE zipcode_entries SET last_accessed = ? WHERE zipcode = ?",
                (datetime.now(timezone.utc).isoformat(), zipcode),
            )
            
            # Get associated meetings
            cursor = conn.execute(
                """SELECT meeting_date, meeting_name, packet_url 
                   FROM meetings WHERE city_slug = ? 
                   ORDER BY meeting_date DESC""",
                (zipcode_row["city_slug"],),
            )
            meetings = [{"title": row["meeting_name"], "start": row["meeting_date"], "packet_url": row["packet_url"]} 
                       for row in cursor.fetchall()]
            
            return {
                "zipcode": zipcode_row["zipcode"],
                "city": zipcode_row["city_name"],
                "city_slug": zipcode_row["city_slug"],
                "state": zipcode_row["state"],
                "county": zipcode_row["county"],
                "meetings": meetings
            }

    def store_zipcode_entry(self, entry_data: Dict[str, Any]) -> int:
        """Store zipcode entry and associated meetings"""
        with self.get_connection() as conn:
            # Store zipcode entry
            cursor = conn.execute(
                """INSERT OR REPLACE INTO zipcode_entries 
                   (zipcode, city_name, city_slug, state, county, created_at, last_accessed)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    entry_data["zipcode"],
                    entry_data["city"],
                    entry_data["city_slug"],
                    entry_data.get("state"),
                    entry_data.get("county"),
                    datetime.now(timezone.utc).isoformat(),
                    datetime.now(timezone.utc).isoformat(),
                ),
            )
            
            # Store meetings (if any)
            for meeting in entry_data.get("meetings", []):
                try:
                    conn.execute(
                        """INSERT OR IGNORE INTO meetings 
                           (city_slug, city_name, meeting_name, packet_url, meeting_date, created_at, last_accessed)
                           VALUES (?, ?, ?, ?, ?, ?, ?)""",
                        (
                            entry_data["city_slug"],
                            entry_data["city"],
                            meeting.get("title"),
                            meeting.get("packet_url"),
                            meeting.get("start"),
                            datetime.now(timezone.utc).isoformat(),
                            datetime.now(timezone.utc).isoformat(),
                        ),
                    )
                except sqlite3.IntegrityError:
                    # Meeting already exists, skip
                    pass
            
            return cursor.lastrowid


# City to zipcode mapping - can be expanded as needed
CITY_ZIPCODE_MAPPING = {
    "cityofpaloalto": {"zipcode": "94301", "city_name": "Palo Alto"},
    "menlopark": {"zipcode": "94025", "city_name": "Menlo Park"},
    "mountainview": {"zipcode": "94041", "city_name": "Mountain View"},
    "sunnyvale": {"zipcode": "94086", "city_name": "Sunnyvale"},
    "cupertino": {"zipcode": "95014", "city_name": "Cupertino"},
    "losaltos": {"zipcode": "94022", "city_name": "Los Altos"},
    "redwoodcity": {"zipcode": "94063", "city_name": "Redwood City"},
}


def get_city_info(city_slug: str) -> Dict[str, str]:
    """Get city name and zipcode from city slug"""
    return CITY_ZIPCODE_MAPPING.get(
        city_slug,
        {"zipcode": None, "city_name": city_slug.replace("cityof", "").title()},
    )


# Adapter factory pattern for vendor-specific processing
ADAPTERS = {
    'primegov': 'PrimeGovAdapter',
    'granicus': 'GranicusAdapter',
    'civicplus': 'CivicPlusAdapter',
}

def get_adapter_class(vendor: str) -> str:
    """Return adapter class name for given vendor"""
    return ADAPTERS.get(vendor, 'PrimeGovAdapter')  # Default to primegov
