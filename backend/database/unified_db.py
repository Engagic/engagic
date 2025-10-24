"""
Unified Database for Engagic - Phase 1 Refactor

Consolidates locations.db, meetings.db, and analytics.db into a single database
with clean, minimal interface.

Key improvements:
- Single get_city() method with optional parameters (no more 4+ lookup methods)
- Simplified meeting storage with normalized dates
- Multi-tenancy tables ready for Phase 5
- Clear separation of concerns
"""

import logging
import sqlite3
import json
from typing import Optional, List, Dict, Any
from datetime import datetime
from dataclasses import dataclass, asdict
from pathlib import Path

logger = logging.getLogger("engagic")


class DatabaseConnectionError(Exception):
    """Raised when database connection is not established"""
    pass


@dataclass
class City:
    """City entity - single source of truth"""
    banana: str              # Primary key: paloaltoCA (derived)
    name: str                # Palo Alto
    state: str               # CA
    vendor: str              # primegov, legistar, granicus, etc.
    vendor_slug: str         # cityofpaloalto (vendor-specific)
    county: Optional[str] = None
    status: str = "active"
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization"""
        data = asdict(self)
        if self.created_at:
            data['created_at'] = self.created_at.isoformat()
        if self.updated_at:
            data['updated_at'] = self.updated_at.isoformat()
        return data

    @classmethod
    def from_db_row(cls, row: sqlite3.Row) -> 'City':
        """Create City from database row"""
        row_dict = dict(row)
        return cls(
            banana=row_dict['city_banana'],
            name=row_dict['name'],
            state=row_dict['state'],
            vendor=row_dict['vendor'],
            vendor_slug=row_dict['vendor_slug'],
            county=row_dict.get('county'),
            status=row_dict.get('status', 'active'),
            created_at=datetime.fromisoformat(row_dict['created_at']) if row_dict.get('created_at') else None,
            updated_at=datetime.fromisoformat(row_dict['updated_at']) if row_dict.get('updated_at') else None
        )


@dataclass
class Meeting:
    """Meeting entity with optional summary"""
    id: str                  # Unique meeting ID
    city_banana: str         # Foreign key to City
    title: str
    date: Optional[datetime]
    packet_url: Optional[str]  # Can be JSON list for multiple PDFs
    summary: Optional[str] = None
    processing_status: str = "pending"  # pending, processing, completed, failed
    processing_method: Optional[str] = None  # tier1_fast, tier3_gemini_pdf
    processing_time: Optional[float] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization"""
        data = asdict(self)
        if self.date:
            data['date'] = self.date.isoformat()
        if self.created_at:
            data['created_at'] = self.created_at.isoformat()
        if self.updated_at:
            data['updated_at'] = self.updated_at.isoformat()
        return data

    @classmethod
    def from_db_row(cls, row: sqlite3.Row) -> 'Meeting':
        """Create Meeting from database row"""
        row_dict = dict(row)
        return cls(
            id=row_dict['id'],
            city_banana=row_dict['city_banana'],
            title=row_dict['title'],
            date=datetime.fromisoformat(row_dict['date']) if row_dict.get('date') else None,
            packet_url=row_dict.get('packet_url'),
            summary=row_dict.get('summary'),
            processing_status=row_dict.get('processing_status', 'pending'),
            processing_method=row_dict.get('processing_method'),
            processing_time=row_dict.get('processing_time'),
            created_at=datetime.fromisoformat(row_dict['created_at']) if row_dict.get('created_at') else None,
            updated_at=datetime.fromisoformat(row_dict['updated_at']) if row_dict.get('updated_at') else None
        )


class UnifiedDatabase:
    """
    Single database interface for all Engagic data.

    Replaces the old 3-database architecture with a unified approach.
    Key design: Prefer specific lookups over generic queries.
    """

    def __init__(self, db_path: str):
        """Initialize unified database connection"""
        self.db_path = db_path
        self.conn = None
        self._connect()
        self._init_schema()
        logger.info(f"Initialized unified database at {db_path}")

    def _connect(self):
        """Create database connection with optimizations"""
        # Ensure directory exists
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)

        self.conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row

        # Performance optimizations
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA synchronous=NORMAL")
        self.conn.execute("PRAGMA cache_size=10000")
        self.conn.execute("PRAGMA foreign_keys=ON")

    def _init_schema(self):
        """Initialize unified database schema"""
        if self.conn is None:
            raise DatabaseConnectionError("Database connection not established")

        schema = """
        -- Cities table: Core city registry
        CREATE TABLE IF NOT EXISTS cities (
            city_banana TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            state TEXT NOT NULL,
            vendor TEXT NOT NULL,
            vendor_slug TEXT NOT NULL,
            county TEXT,
            status TEXT DEFAULT 'active',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(name, state)
        );

        -- City zipcodes: Many-to-many relationship
        CREATE TABLE IF NOT EXISTS city_zipcodes (
            city_banana TEXT NOT NULL,
            zipcode TEXT NOT NULL,
            is_primary BOOLEAN DEFAULT FALSE,
            FOREIGN KEY (city_banana) REFERENCES cities(city_banana) ON DELETE CASCADE,
            PRIMARY KEY (city_banana, zipcode)
        );

        -- Meetings table: Meeting data with optional summaries
        CREATE TABLE IF NOT EXISTS meetings (
            id TEXT PRIMARY KEY,
            city_banana TEXT NOT NULL,
            title TEXT NOT NULL,
            date TIMESTAMP,
            packet_url TEXT,
            summary TEXT,
            processing_status TEXT DEFAULT 'pending',
            processing_method TEXT,
            processing_time REAL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (city_banana) REFERENCES cities(city_banana) ON DELETE CASCADE
        );

        -- Processing cache: Track PDF processing for cost optimization
        CREATE TABLE IF NOT EXISTS processing_cache (
            packet_url TEXT PRIMARY KEY,
            content_hash TEXT,
            processing_method TEXT,
            processing_time REAL,
            cache_hit_count INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            last_accessed TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        -- Tenants table: B2B customers (Phase 5)
        CREATE TABLE IF NOT EXISTS tenants (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            api_key TEXT UNIQUE NOT NULL,
            webhook_url TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        -- Tenant coverage: Which cities each tenant tracks
        CREATE TABLE IF NOT EXISTS tenant_coverage (
            tenant_id TEXT NOT NULL,
            city_banana TEXT NOT NULL,
            added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (tenant_id) REFERENCES tenants(id) ON DELETE CASCADE,
            FOREIGN KEY (city_banana) REFERENCES cities(city_banana) ON DELETE CASCADE,
            PRIMARY KEY (tenant_id, city_banana)
        );

        -- Tenant keywords: Topics tenants care about
        CREATE TABLE IF NOT EXISTS tenant_keywords (
            tenant_id TEXT NOT NULL,
            keyword TEXT NOT NULL,
            added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (tenant_id) REFERENCES tenants(id) ON DELETE CASCADE,
            PRIMARY KEY (tenant_id, keyword)
        );

        -- Tracked items: Ordinances, proposals, etc. (Phase 6)
        CREATE TABLE IF NOT EXISTS tracked_items (
            id TEXT PRIMARY KEY,
            tenant_id TEXT NOT NULL,
            item_type TEXT NOT NULL,
            title TEXT NOT NULL,
            description TEXT,
            city_banana TEXT NOT NULL,
            first_mentioned_meeting_id TEXT,
            first_seen TIMESTAMP,
            last_seen TIMESTAMP,
            status TEXT DEFAULT 'active',
            metadata TEXT,
            FOREIGN KEY (tenant_id) REFERENCES tenants(id) ON DELETE CASCADE,
            FOREIGN KEY (city_banana) REFERENCES cities(city_banana) ON DELETE CASCADE
        );

        -- Tracked item meetings: Link tracked items to meetings
        CREATE TABLE IF NOT EXISTS tracked_item_meetings (
            tracked_item_id TEXT NOT NULL,
            meeting_id TEXT NOT NULL,
            mentioned_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            excerpt TEXT,
            FOREIGN KEY (tracked_item_id) REFERENCES tracked_items(id) ON DELETE CASCADE,
            FOREIGN KEY (meeting_id) REFERENCES meetings(id) ON DELETE CASCADE,
            PRIMARY KEY (tracked_item_id, meeting_id)
        );

        -- Performance indices
        CREATE INDEX IF NOT EXISTS idx_cities_vendor ON cities(vendor);
        CREATE INDEX IF NOT EXISTS idx_cities_state ON cities(state);
        CREATE INDEX IF NOT EXISTS idx_cities_status ON cities(status);
        CREATE INDEX IF NOT EXISTS idx_city_zipcodes_zipcode ON city_zipcodes(zipcode);
        CREATE INDEX IF NOT EXISTS idx_meetings_city ON meetings(city_banana);
        CREATE INDEX IF NOT EXISTS idx_meetings_date ON meetings(date);
        CREATE INDEX IF NOT EXISTS idx_meetings_status ON meetings(processing_status);
        CREATE INDEX IF NOT EXISTS idx_processing_cache_hash ON processing_cache(content_hash);
        CREATE INDEX IF NOT EXISTS idx_tenant_coverage_city ON tenant_coverage(city_banana);
        CREATE INDEX IF NOT EXISTS idx_tracked_items_tenant ON tracked_items(tenant_id);
        CREATE INDEX IF NOT EXISTS idx_tracked_items_city ON tracked_items(city_banana);
        CREATE INDEX IF NOT EXISTS idx_tracked_items_status ON tracked_items(status);
        """

        self.conn.executescript(schema)
        self.conn.commit()

    # ========== City Operations ==========

    def get_city(
        self,
        banana: Optional[str] = None,
        name: Optional[str] = None,
        state: Optional[str] = None,
        vendor_slug: Optional[str] = None,
        zipcode: Optional[str] = None
    ) -> Optional[City]:
        """
        Unified city lookup - replaces 4+ separate methods.

        Uses most specific parameter provided:
        - banana: Direct primary key lookup (fastest)
        - vendor_slug: Lookup by vendor-specific identifier
        - zipcode: Lookup via city_zipcodes join
        - name + state: Normalized name matching

        Examples:
            get_city(banana="paloaltoCA")
            get_city(name="Palo Alto", state="CA")
            get_city(vendor_slug="cityofpaloalto")
            get_city(zipcode="94301")
        """
        if self.conn is None:
            raise DatabaseConnectionError("Database connection not established")
        cursor = self.conn.cursor()

        if banana:
            # Direct primary key lookup
            cursor.execute("SELECT * FROM cities WHERE city_banana = ?", (banana,))
        elif vendor_slug:
            # Lookup by vendor slug
            cursor.execute("SELECT * FROM cities WHERE vendor_slug = ?", (vendor_slug,))
        elif zipcode:
            # Lookup via zipcode join
            cursor.execute("""
                SELECT c.* FROM cities c
                JOIN city_zipcodes cz ON c.city_banana = cz.city_banana
                WHERE cz.zipcode = ?
                LIMIT 1
            """, (zipcode,))
        elif name and state:
            # Normalized name matching (case-insensitive, space-normalized)
            normalized_name = name.lower().replace(' ', '')
            cursor.execute("""
                SELECT * FROM cities
                WHERE LOWER(REPLACE(name, ' ', '')) = ?
                AND UPPER(state) = ?
            """, (normalized_name, state.upper()))
        else:
            raise ValueError("Must provide at least one search parameter")

        row = cursor.fetchone()
        return City.from_db_row(row) if row else None

    def get_cities(
        self,
        state: Optional[str] = None,
        vendor: Optional[str] = None,
        name: Optional[str] = None,
        status: str = "active",
        limit: Optional[int] = None
    ) -> List[City]:
        """
        Batch city lookup with filters.

        Args:
            state: Filter by state (e.g., "CA")
            vendor: Filter by vendor (e.g., "primegov")
            name: Filter by exact name match (for ambiguous city search)
            status: Filter by status (default: "active")
            limit: Maximum results to return
        """
        assert self.conn is not None, "Database connection not established"
        conditions = ["status = ?"]
        params = [status]

        if state:
            conditions.append("UPPER(state) = ?")
            params.append(state.upper())

        if vendor:
            conditions.append("vendor = ?")
            params.append(vendor)

        if name:
            conditions.append("LOWER(name) = ?")
            params.append(name.lower())

        query = f"""
            SELECT * FROM cities
            WHERE {' AND '.join(conditions)}
            ORDER BY name
        """

        if limit:
            query += f" LIMIT {limit}"

        cursor = self.conn.cursor()
        cursor.execute(query, params)

        return [City.from_db_row(row) for row in cursor.fetchall()]

    def get_city_meeting_stats(self, city_bananas: List[str]) -> Dict[str, Dict[str, int]]:
        """Get meeting statistics for multiple cities at once"""
        if not city_bananas:
            return {}

        assert self.conn is not None, "Database connection not established"
        placeholders = ','.join('?' * len(city_bananas))
        cursor = self.conn.cursor()
        cursor.execute(f"""
            SELECT
                city_banana,
                COUNT(*) as total_meetings,
                SUM(CASE WHEN summary IS NOT NULL THEN 1 ELSE 0 END) as summarized_meetings
            FROM meetings
            WHERE city_banana IN ({placeholders})
            GROUP BY city_banana
        """, city_bananas)

        return {
            row['city_banana']: {
                'total_meetings': row['total_meetings'],
                'summarized_meetings': row['summarized_meetings']
            }
            for row in cursor.fetchall()
        }

    def add_city(
        self,
        banana: str,
        name: str,
        state: str,
        vendor: str,
        vendor_slug: str,
        county: Optional[str] = None,
        zipcodes: Optional[List[str]] = None
    ) -> City:
        """Add a new city to the database"""
        assert self.conn is not None, "Database connection not established"
        cursor = self.conn.cursor()

        cursor.execute("""
            INSERT OR REPLACE INTO cities
            (city_banana, name, state, vendor, vendor_slug, county)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (banana, name, state, vendor, vendor_slug, county))

        # Add zipcodes if provided
        if zipcodes:
            for i, zipcode in enumerate(zipcodes):
                is_primary = (i == 0)
                cursor.execute("""
                    INSERT OR IGNORE INTO city_zipcodes
                    (city_banana, zipcode, is_primary)
                    VALUES (?, ?, ?)
                """, (banana, zipcode, is_primary))

        self.conn.commit()
        logger.info(f"Added city: {banana} ({name}, {state})")

        result = self.get_city(banana=banana)
        if result is None:
            raise DatabaseConnectionError(f"Failed to retrieve newly added city: {banana}")
        return result

    def get_city_zipcodes(self, city_banana: str) -> List[str]:
        """Get all zipcodes for a city"""
        if self.conn is None:
            raise DatabaseConnectionError("Database connection not established")
        cursor = self.conn.cursor()
        cursor.execute("""
            SELECT zipcode FROM city_zipcodes
            WHERE city_banana = ?
            ORDER BY is_primary DESC, zipcode
        """, (city_banana,))

        return [row['zipcode'] for row in cursor.fetchall()]

    # ========== Meeting Operations ==========

    def get_meeting(self, meeting_id: str) -> Optional[Meeting]:
        """Get a single meeting by ID"""
        assert self.conn is not None, "Database connection not established"
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM meetings WHERE id = ?", (meeting_id,))

        row = cursor.fetchone()
        return Meeting.from_db_row(row) if row else None

    def get_meetings(
        self,
        city_bananas: Optional[List[str]] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        has_summary: Optional[bool] = None,
        limit: int = 50
    ) -> List[Meeting]:
        """
        Get meetings with flexible filtering.

        Args:
            city_bananas: Filter by list of city_bananas
            start_date: Filter by date >= start_date
            end_date: Filter by date <= end_date
            has_summary: Filter by whether summary exists
            limit: Maximum results
        """
        assert self.conn is not None, "Database connection not established"
        conditions = []
        params = []

        if city_bananas:
            placeholders = ','.join('?' * len(city_bananas))
            conditions.append(f"city_banana IN ({placeholders})")
            params.extend(city_bananas)

        if start_date:
            conditions.append("date >= ?")
            params.append(start_date.isoformat())

        if end_date:
            conditions.append("date <= ?")
            params.append(end_date.isoformat())

        if has_summary is not None:
            if has_summary:
                conditions.append("summary IS NOT NULL")
            else:
                conditions.append("summary IS NULL")

        where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""

        query = f"""
            SELECT * FROM meetings
            {where_clause}
            ORDER BY date DESC, created_at DESC
            LIMIT {limit}
        """

        cursor = self.conn.cursor()
        cursor.execute(query, params)

        return [Meeting.from_db_row(row) for row in cursor.fetchall()]

    def store_meeting(self, meeting: Meeting) -> Meeting:
        """Store or update a meeting"""
        assert self.conn is not None, "Database connection not established"
        cursor = self.conn.cursor()

        cursor.execute("""
            INSERT OR REPLACE INTO meetings
            (id, city_banana, title, date, packet_url, summary,
             processing_status, processing_method, processing_time)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            meeting.id,
            meeting.city_banana,
            meeting.title,
            meeting.date.isoformat() if meeting.date else None,
            meeting.packet_url,
            meeting.summary,
            meeting.processing_status,
            meeting.processing_method,
            meeting.processing_time
        ))

        self.conn.commit()
        result = self.get_meeting(meeting.id)
        assert result is not None, f"Failed to retrieve newly stored meeting: {meeting.id}"
        return result

    def update_meeting_summary(
        self,
        meeting_id: str,
        summary: str,
        processing_method: str,
        processing_time: float
    ):
        """Update meeting with processed summary"""
        assert self.conn is not None, "Database connection not established"
        cursor = self.conn.cursor()

        cursor.execute("""
            UPDATE meetings
            SET summary = ?,
                processing_status = 'completed',
                processing_method = ?,
                processing_time = ?,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
        """, (summary, processing_method, processing_time, meeting_id))

        self.conn.commit()
        logger.info(f"Updated summary for meeting {meeting_id} using {processing_method}")

    def get_unprocessed_meetings(self, limit: int = 50) -> List[Meeting]:
        """Get meetings that need summary processing"""
        assert self.conn is not None, "Database connection not established"
        cursor = self.conn.cursor()
        cursor.execute("""
            SELECT * FROM meetings
            WHERE processing_status = 'pending'
            AND packet_url IS NOT NULL
            ORDER BY date DESC
            LIMIT ?
        """, (limit,))

        return [Meeting.from_db_row(row) for row in cursor.fetchall()]

    def get_city_meeting_frequency(self, city_banana: str, days: int = 30) -> int:
        """Get count of meetings for a city in the last N days"""
        assert self.conn is not None, "Database connection not established"
        cursor = self.conn.cursor()
        cursor.execute("""
            SELECT COUNT(*) as count
            FROM meetings
            WHERE city_banana = ?
            AND date >= datetime('now', '-' || ? || ' days')
        """, (city_banana, days))

        result = cursor.fetchone()
        return result['count'] if result else 0

    def get_city_last_sync(self, city_banana: str) -> Optional[datetime]:
        """Get the last sync time for a city (most recent meeting created_at)"""
        assert self.conn is not None, "Database connection not established"
        cursor = self.conn.cursor()
        cursor.execute("""
            SELECT MAX(created_at) as last_sync
            FROM meetings
            WHERE city_banana = ?
        """, (city_banana,))

        result = cursor.fetchone()
        if result and result['last_sync']:
            return datetime.fromisoformat(result['last_sync'])
        return None

    def get_meeting_by_packet_url(self, packet_url: str) -> Optional[Meeting]:
        """Get meeting by packet URL"""
        assert self.conn is not None, "Database connection not established"
        cursor = self.conn.cursor()
        cursor.execute("""
            SELECT * FROM meetings
            WHERE packet_url = ?
            LIMIT 1
        """, (packet_url,))

        row = cursor.fetchone()
        return Meeting.from_db_row(row) if row else None

    # ========== Processing Cache Operations ==========

    def get_cached_summary(self, packet_url: str) -> Optional[Dict[str, Any]]:
        """Check if packet URL has been processed before"""
        assert self.conn is not None, "Database connection not established"
        cursor = self.conn.cursor()

        # Serialize URL if it's a list
        lookup_url = json.dumps(packet_url) if isinstance(packet_url, list) else packet_url

        cursor.execute("""
            SELECT * FROM processing_cache
            WHERE packet_url = ?
        """, (lookup_url,))

        row = cursor.fetchone()
        if row:
            # Update hit count
            cursor.execute("""
                UPDATE processing_cache
                SET cache_hit_count = cache_hit_count + 1,
                    last_accessed = CURRENT_TIMESTAMP
                WHERE packet_url = ?
            """, (lookup_url,))
            self.conn.commit()

            return dict(row)

        return None

    def store_processing_result(
        self,
        packet_url: str,
        processing_method: str,
        processing_time: float
    ):
        """Store processing result in cache"""
        assert self.conn is not None, "Database connection not established"
        cursor = self.conn.cursor()

        lookup_url = json.dumps(packet_url) if isinstance(packet_url, list) else packet_url

        cursor.execute("""
            INSERT OR REPLACE INTO processing_cache
            (packet_url, processing_method, processing_time, cache_hit_count)
            VALUES (?, ?, ?, 0)
        """, (lookup_url, processing_method, processing_time))

        self.conn.commit()

    # ========== Stats & Utilities ==========

    def get_stats(self) -> Dict[str, Any]:
        """Get database statistics"""
        assert self.conn is not None, "Database connection not established"
        cursor = self.conn.cursor()

        cursor.execute("SELECT COUNT(*) as count FROM cities WHERE status = 'active'")
        active_cities = cursor.fetchone()['count']

        cursor.execute("SELECT COUNT(*) as count FROM meetings")
        total_meetings = cursor.fetchone()['count']

        cursor.execute("SELECT COUNT(*) as count FROM meetings WHERE summary IS NOT NULL")
        summarized_meetings = cursor.fetchone()['count']

        cursor.execute("SELECT COUNT(*) as count FROM meetings WHERE processing_status = 'pending'")
        pending_meetings = cursor.fetchone()['count']

        return {
            "active_cities": active_cities,
            "total_meetings": total_meetings,
            "summarized_meetings": summarized_meetings,
            "pending_meetings": pending_meetings,
            "summary_rate": f"{summarized_meetings / total_meetings * 100:.1f}%" if total_meetings > 0 else "0%"
        }

    def close(self):
        """Close database connection"""
        if self.conn:
            self.conn.close()
            logger.info("Database connection closed")
