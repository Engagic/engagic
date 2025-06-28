import sqlite3
import json
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
                    vendor TEXT,
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

            # Legacy table - will be migrated to cities table
            conn.execute("""
                CREATE TABLE IF NOT EXISTS zipcode_entries (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    zipcode TEXT UNIQUE NOT NULL,
                    city_name TEXT NOT NULL,
                    city_slug TEXT NOT NULL,
                    vendor TEXT,
                    state TEXT,
                    county TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    last_accessed TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # New city-centric table
            conn.execute("""
                CREATE TABLE IF NOT EXISTS cities (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    city_name TEXT NOT NULL,
                    state TEXT NOT NULL,
                    city_slug TEXT NOT NULL UNIQUE,
                    vendor TEXT,
                    county TEXT,
                    primary_zipcode TEXT,
                    zipcodes TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    last_accessed TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(city_name, state)
                )
            """)

            # Handle migrations
            self._migrate_add_vendor_column(conn)
            self._migrate_to_city_centric_schema(conn)

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
            conn.execute("CREATE INDEX IF NOT EXISTS idx_vendor ON meetings(vendor)")
            
            # Legacy indices
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_zipcode ON zipcode_entries(zipcode)"
            )
            
            # New city table indices
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_cities_city_slug ON cities(city_slug)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_cities_city_state ON cities(city_name, state)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_cities_primary_zipcode ON cities(primary_zipcode)"
            )

            conn.commit()

    def _migrate_add_vendor_column(self, conn):
        """Add vendor column to existing tables if it doesn't exist"""
        try:
            # Check if vendor column exists in meetings table
            cursor = conn.execute("PRAGMA table_info(meetings)")
            columns = [row[1] for row in cursor.fetchall()]

            if "vendor" not in columns:
                print("Adding vendor column to meetings table...")
                conn.execute("ALTER TABLE meetings ADD COLUMN vendor TEXT")
                print("Migration complete: vendor column added to meetings")
                
            # Check if vendor column exists in zipcode_entries table
            cursor = conn.execute("PRAGMA table_info(zipcode_entries)")
            zipcode_columns = [row[1] for row in cursor.fetchall()]
            
            if "vendor" not in zipcode_columns:
                print("Adding vendor column to zipcode_entries table...")
                conn.execute("ALTER TABLE zipcode_entries ADD COLUMN vendor TEXT")
                print("Migration complete: vendor column added to zipcode_entries")
        except Exception as e:
            print(f"Migration warning: {e}")

    def _migrate_to_city_centric_schema(self, conn):
        """Migrate zipcode_entries to cities table"""
        try:
            # Check if migration is needed
            try:
                cursor = conn.execute("SELECT COUNT(*) as count FROM cities")
                cities_count = cursor.fetchone()[0]
                
                cursor = conn.execute("SELECT COUNT(*) as count FROM zipcode_entries")
                zipcode_count = cursor.fetchone()[0]
            except (sqlite3.OperationalError, TypeError):
                # Tables may not exist yet
                return
            
            if cities_count > 0 or zipcode_count == 0:
                # Migration already done or no data to migrate
                return
                
            print(f"Migrating {zipcode_count} zipcode entries to city-centric schema...")
            
            # Group zipcode entries by (city_name, state) and aggregate zipcodes
            cursor = conn.execute("""
                SELECT 
                    city_name,
                    state,
                    city_slug,
                    vendor,
                    county,
                    GROUP_CONCAT(zipcode) as zipcodes_str,
                    MIN(zipcode) as primary_zipcode,
                    MIN(created_at) as earliest_created,
                    MAX(last_accessed) as latest_accessed
                FROM zipcode_entries 
                GROUP BY city_name, state, city_slug, vendor, county
                ORDER BY city_name, state
            """)
            
            migrated_count = 0
            for row in cursor.fetchall():
                # Convert comma-separated zipcodes to JSON array
                zipcode_list = row["zipcodes_str"].split(",") if row["zipcodes_str"] else []
                zipcodes_json = json.dumps(zipcode_list)
                
                # Insert into cities table
                try:
                    conn.execute("""
                        INSERT OR IGNORE INTO cities 
                        (city_name, state, city_slug, vendor, county, primary_zipcode, zipcodes, created_at, last_accessed)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        row["city_name"],
                        row["state"],
                        row["city_slug"],
                        row["vendor"],
                        row["county"],
                        row["primary_zipcode"],
                        zipcodes_json,
                        row["earliest_created"],
                        row["latest_accessed"]
                    ))
                    migrated_count += 1
                except sqlite3.IntegrityError as e:
                    print(f"Skipping duplicate city entry: {row['city_name']}, {row['state']} - {e}")
            
            print(f"Migration complete: {migrated_count} cities created from {zipcode_count} zipcode entries")
            
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
        self,
        meeting_data: Dict[str, Any],
        summary: str,
        processing_time: float,
        vendor: str,
    ) -> Optional[int]:
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
        self, query: str, city_slug: Optional[str] = None, limit: int = 50
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

    def get_meetings_by_vendor(
        self, vendor: str, limit: int = 50
    ) -> List[Dict[str, Any]]:
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
            cursor = conn.execute(
                "SELECT vendor FROM meetings WHERE packet_url = ?", (packet_url,)
            )
            row = cursor.fetchone()
            return row["vendor"] if row else None

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

    def get_city_by_zipcode(self, zipcode: str) -> Optional[Dict[str, Any]]:
        """Get city entry by zipcode using new cities table"""
        with self.get_connection() as conn:
            # Search in cities table using JSON zipcode array
            cursor = conn.execute("""
                SELECT id, city_name, state, city_slug, vendor, county, primary_zipcode, zipcodes, created_at, last_accessed
                FROM cities 
                WHERE primary_zipcode = ? OR json_extract(zipcodes, '$') LIKE '%' || ? || '%'
            """, (zipcode, zipcode))
            
            city_row = cursor.fetchone()
            if not city_row:
                return None
            
            # Update last_accessed
            conn.execute(
                "UPDATE cities SET last_accessed = ? WHERE id = ?",
                (datetime.now(timezone.utc).isoformat(), city_row["id"])
            )
            
            # Get associated meetings
            cursor = conn.execute("""
                SELECT meeting_date, meeting_name, packet_url 
                FROM meetings WHERE city_slug = ? 
                ORDER BY meeting_date DESC
            """, (city_row["city_slug"],))
            
            meetings = [
                {
                    "title": row["meeting_name"],
                    "start": row["meeting_date"],
                    "packet_url": row["packet_url"],
                }
                for row in cursor.fetchall()
            ]
            
            return {
                "zipcode": zipcode,  # The searched zipcode
                "city": city_row["city_name"],
                "city_slug": city_row["city_slug"],
                "vendor": city_row["vendor"],
                "state": city_row["state"],
                "county": city_row["county"],
                "primary_zipcode": city_row["primary_zipcode"],
                "all_zipcodes": json.loads(city_row["zipcodes"]) if city_row["zipcodes"] else [],
                "meetings": meetings,
            }

    def get_city_by_name(self, city_name: str, state: str = None) -> Optional[Dict[str, Any]]:
        """Get city entry by name and optional state"""
        with self.get_connection() as conn:
            if state:
                # Exact match with state
                cursor = conn.execute("""
                    SELECT id, city_name, state, city_slug, vendor, county, primary_zipcode, zipcodes, created_at, last_accessed
                    FROM cities 
                    WHERE city_name = ? AND state = ?
                """, (city_name, state))
            else:
                # Try case-insensitive match first
                cursor = conn.execute("""
                    SELECT id, city_name, state, city_slug, vendor, county, primary_zipcode, zipcodes, created_at, last_accessed
                    FROM cities 
                    WHERE LOWER(city_name) = LOWER(?)
                """, (city_name,))
            
            city_row = cursor.fetchone()
            if not city_row:
                return None
            
            # Update last_accessed
            conn.execute(
                "UPDATE cities SET last_accessed = ? WHERE id = ?",
                (datetime.now(timezone.utc).isoformat(), city_row["id"])
            )
            
            # Get associated meetings
            cursor = conn.execute("""
                SELECT meeting_date, meeting_name, packet_url 
                FROM meetings WHERE city_slug = ? 
                ORDER BY meeting_date DESC
            """, (city_row["city_slug"],))
            
            meetings = [
                {
                    "title": row["meeting_name"],
                    "start": row["meeting_date"],
                    "packet_url": row["packet_url"],
                }
                for row in cursor.fetchall()
            ]
            
            return {
                "city": city_row["city_name"],
                "city_slug": city_row["city_slug"],
                "vendor": city_row["vendor"],
                "state": city_row["state"],
                "county": city_row["county"],
                "primary_zipcode": city_row["primary_zipcode"],
                "all_zipcodes": json.loads(city_row["zipcodes"]) if city_row["zipcodes"] else [],
                "meetings": meetings,
            }

    def get_city_by_slug(self, city_slug: str) -> Optional[Dict[str, Any]]:
        """Get city entry by city slug"""
        with self.get_connection() as conn:
            cursor = conn.execute("""
                SELECT id, city_name, state, city_slug, vendor, county, primary_zipcode, zipcodes, created_at, last_accessed
                FROM cities 
                WHERE city_slug = ?
            """, (city_slug,))
            
            city_row = cursor.fetchone()
            if not city_row:
                return None
            
            # Update last_accessed
            conn.execute(
                "UPDATE cities SET last_accessed = ? WHERE id = ?",
                (datetime.now(timezone.utc).isoformat(), city_row["id"])
            )
            
            # Get associated meetings
            cursor = conn.execute("""
                SELECT meeting_date, meeting_name, packet_url 
                FROM meetings WHERE city_slug = ? 
                ORDER BY meeting_date DESC
            """, (city_row["city_slug"],))
            
            meetings = [
                {
                    "title": row["meeting_name"],
                    "start": row["meeting_date"],
                    "packet_url": row["packet_url"],
                }
                for row in cursor.fetchall()
            ]
            
            return {
                "city": city_row["city_name"],
                "city_slug": city_row["city_slug"],
                "vendor": city_row["vendor"],
                "state": city_row["state"],
                "county": city_row["county"],
                "primary_zipcode": city_row["primary_zipcode"],
                "all_zipcodes": json.loads(city_row["zipcodes"]) if city_row["zipcodes"] else [],
                "meetings": meetings,
            }

    def store_city_entry(self, entry_data: Dict[str, Any]) -> int:
        """Store city entry with automatic zipcode aggregation"""
        with self.get_connection() as conn:
            # Check if city already exists to merge zipcodes
            existing_city = None
            try:
                cursor = conn.execute("""
                    SELECT zipcodes, primary_zipcode FROM cities 
                    WHERE city_name = ? AND state = ?
                """, (entry_data["city"], entry_data.get("state")))
                row = cursor.fetchone()
                if row:
                    existing_city = row
            except sqlite3.OperationalError:
                pass
            
            # Handle zipcode aggregation
            zipcode = entry_data.get("zipcode") or entry_data.get("primary_zipcode")
            existing_zipcodes = entry_data.get("all_zipcodes", [])
            
            # Merge with existing zipcodes if city exists
            if existing_city and existing_city["zipcodes"]:
                try:
                    old_zipcodes = json.loads(existing_city["zipcodes"])
                    existing_zipcodes.extend(old_zipcodes)
                except (json.JSONDecodeError, TypeError):
                    pass
            
            # Add current zipcode if not in list
            if zipcode and zipcode not in existing_zipcodes:
                existing_zipcodes.append(zipcode)
            
            # Remove duplicates and sort
            existing_zipcodes = sorted(list(set(existing_zipcodes)))
            zipcodes_json = json.dumps(existing_zipcodes)
            
            # Use existing primary zipcode if available, otherwise use current
            primary_zipcode = (existing_city and existing_city["primary_zipcode"]) or zipcode
            
            # Store or update city entry
            cursor = conn.execute("""
                INSERT OR REPLACE INTO cities 
                (city_name, state, city_slug, vendor, county, primary_zipcode, zipcodes, created_at, last_accessed)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                entry_data["city"],
                entry_data.get("state"),
                entry_data["city_slug"],
                entry_data.get("vendor"),
                entry_data.get("county"),
                primary_zipcode,
                zipcodes_json,
                datetime.now(timezone.utc).isoformat(),
                datetime.now(timezone.utc).isoformat(),
            ))
            
            # Store meetings (if any)
            for meeting in entry_data.get("meetings", []):
                try:
                    conn.execute("""
                        INSERT OR IGNORE INTO meetings 
                        (city_slug, city_name, meeting_name, packet_url, meeting_date, created_at, last_accessed)
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                    """, (
                        entry_data["city_slug"],
                        entry_data["city"],
                        meeting.get("title"),
                        meeting.get("packet_url"),
                        meeting.get("start"),
                        datetime.now(timezone.utc).isoformat(),
                        datetime.now(timezone.utc).isoformat(),
                    ))
                except sqlite3.IntegrityError:
                    # Meeting already exists, skip
                    pass
            
            return cursor.lastrowid

    def get_all_cities(self) -> List[Dict[str, Any]]:
        """Get all city entries"""
        with self.get_connection() as conn:
            cursor = conn.execute("""
                SELECT city_name, state, city_slug, vendor, county, primary_zipcode, zipcodes 
                FROM cities ORDER BY city_name, state
            """)
            
            result = []
            for row in cursor.fetchall():
                city_data = dict(row)
                # Parse zipcodes JSON
                city_data["all_zipcodes"] = json.loads(row["zipcodes"]) if row["zipcodes"] else []
                result.append(city_data)
            
            return result



    def store_meeting_data(
        self, meeting_data: Dict[str, Any], vendor: str
    ) -> Optional[int]:
        """Store meeting data in database"""
        with self.get_connection() as conn:
            cursor = conn.execute(
                """INSERT OR IGNORE INTO meetings 
                   (vendor, city_slug, city_name, meeting_name, packet_url, meeting_date, created_at, last_accessed)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    vendor,
                    meeting_data["city_slug"],
                    meeting_data.get("meeting_name"),
                    meeting_data.get("packet_url"),
                    meeting_data.get("meeting_date"),
                    datetime.now(timezone.utc).isoformat(),
                    datetime.now(timezone.utc).isoformat(),
                ),
            )
            return cursor.lastrowid


def get_city_info(city_slug: str) -> Dict[str, Optional[str]]:
    """Get city name and zipcode from city slug using cities table"""
    db = MeetingDatabase()
    city_data = db.get_city_by_slug(city_slug)
    
    if city_data:
        return {
            "zipcode": city_data["primary_zipcode"], 
            "city_name": city_data["city"]
        }
    
    # Fallback for unknown cities
    return {"zipcode": None, "city_name": city_slug.replace("cityof", "").title()}