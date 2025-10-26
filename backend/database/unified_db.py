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
    slug: str         # cityofpaloalto (vendor-specific)
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
            banana=row_dict['banana'],
            name=row_dict['name'],
            state=row_dict['state'],
            vendor=row_dict['vendor'],
            slug=row_dict['slug'],
            county=row_dict.get('county'),
            status=row_dict.get('status', 'active'),
            created_at=datetime.fromisoformat(row_dict['created_at']) if row_dict.get('created_at') else None,
            updated_at=datetime.fromisoformat(row_dict['updated_at']) if row_dict.get('updated_at') else None
        )


@dataclass
class Meeting:
    """Meeting entity with optional summary"""
    id: str                  # Unique meeting ID
    banana: str              # Foreign key to City
    title: str
    date: Optional[datetime]
    packet_url: Optional[str | List[str]]  # Single URL or list for multiple PDFs (main + supplemental)
    summary: Optional[str] = None
    status: Optional[str] = None  # cancelled, postponed, revised, rescheduled, or None for normal
    processing_status: str = "pending"  # pending, processing, completed, failed
    processing_method: Optional[str] = None  # tier1_pypdf2_gemini, multiple_pdfs_N_combined
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

        # Deserialize packet_url if it's a JSON list
        packet_url = row_dict.get('packet_url')
        if packet_url and packet_url.startswith('['):
            try:
                packet_url = json.loads(packet_url)
            except json.JSONDecodeError:
                logger.warning(f"Failed to deserialize packet_url JSON: {packet_url}")
                pass  # Keep as string if JSON parsing fails

        return cls(
            id=row_dict['id'],
            banana=row_dict['banana'],
            title=row_dict['title'],
            date=datetime.fromisoformat(row_dict['date']) if row_dict.get('date') else None,
            packet_url=packet_url,
            summary=row_dict.get('summary'),
            status=row_dict.get('status'),
            processing_status=row_dict.get('processing_status', 'pending'),
            processing_method=row_dict.get('processing_method'),
            processing_time=row_dict.get('processing_time'),
            created_at=datetime.fromisoformat(row_dict['created_at']) if row_dict.get('created_at') else None,
            updated_at=datetime.fromisoformat(row_dict['updated_at']) if row_dict.get('updated_at') else None
        )


@dataclass
class AgendaItem:
    """Agenda item entity - individual items within a meeting"""
    id: str                     # Vendor-specific item ID
    meeting_id: str             # Foreign key to Meeting
    title: str
    sequence: int               # Order in agenda
    attachments: List[Any]      # Attachment metadata as JSON (flexible: URLs, dicts with name/url/type, page ranges, etc.)
    summary: Optional[str] = None
    topics: Optional[List[str]] = None  # Extracted topics
    created_at: Optional[datetime] = None

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization"""
        data = asdict(self)
        if self.created_at:
            data['created_at'] = self.created_at.isoformat()
        return data

    @classmethod
    def from_db_row(cls, row: sqlite3.Row) -> 'AgendaItem':
        """Create AgendaItem from database row"""
        row_dict = dict(row)

        # Deserialize JSON fields
        attachments = row_dict.get('attachments')
        if attachments:
            try:
                attachments = json.loads(attachments)
            except json.JSONDecodeError:
                logger.warning(f"Failed to deserialize attachments JSON: {attachments}")
                attachments = []
        else:
            attachments = []

        topics = row_dict.get('topics')
        if topics:
            try:
                topics = json.loads(topics)
            except json.JSONDecodeError:
                logger.warning(f"Failed to deserialize topics JSON: {topics}")
                topics = None
        else:
            topics = None

        return cls(
            id=row_dict['id'],
            meeting_id=row_dict['meeting_id'],
            title=row_dict['title'],
            sequence=row_dict['sequence'],
            attachments=attachments,
            summary=row_dict.get('summary'),
            topics=topics,
            created_at=datetime.fromisoformat(row_dict['created_at']) if row_dict.get('created_at') else None
        )


class UnifiedDatabase:
    """
    Single database interface for all Engagic data.
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
            banana TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            state TEXT NOT NULL,
            vendor TEXT NOT NULL,
            slug TEXT NOT NULL,
            county TEXT,
            status TEXT DEFAULT 'active',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(name, state)
        );

        -- City zipcodes: Many-to-many relationship
        CREATE TABLE IF NOT EXISTS zipcodes (
            banana TEXT NOT NULL,
            zipcode TEXT NOT NULL,
            is_primary BOOLEAN DEFAULT FALSE,
            FOREIGN KEY (banana) REFERENCES cities(banana) ON DELETE CASCADE,
            PRIMARY KEY (banana, zipcode)
        );

        -- Meetings table: Meeting data with optional summaries
        CREATE TABLE IF NOT EXISTS meetings (
            id TEXT PRIMARY KEY,
            banana TEXT NOT NULL,
            title TEXT NOT NULL,
            date TIMESTAMP,
            packet_url TEXT,
            summary TEXT,
            status TEXT,
            processing_status TEXT DEFAULT 'pending',
            processing_method TEXT,
            processing_time REAL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (banana) REFERENCES cities(banana) ON DELETE CASCADE
        );

        -- Agenda items: Individual items within meetings
        CREATE TABLE IF NOT EXISTS items (
            id TEXT PRIMARY KEY,
            meeting_id TEXT NOT NULL,
            title TEXT NOT NULL,
            sequence INTEGER NOT NULL,
            attachments TEXT,
            summary TEXT,
            topics TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (meeting_id) REFERENCES meetings(id) ON DELETE CASCADE
        );

        -- Processing cache: Track PDF processing for cost optimization
        CREATE TABLE IF NOT EXISTS cache (
            packet_url TEXT PRIMARY KEY,
            content_hash TEXT,
            processing_method TEXT,
            processing_time REAL,
            cache_hit_count INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            last_accessed TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        -- Processing queue: Decoupled PDF processing queue (Phase 4)
        CREATE TABLE IF NOT EXISTS queue (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            packet_url TEXT NOT NULL UNIQUE,
            meeting_id TEXT,
            banana TEXT,
            status TEXT DEFAULT 'pending' CHECK (status IN ('pending', 'processing', 'completed', 'failed')),
            priority INTEGER DEFAULT 0,
            retry_count INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            started_at TIMESTAMP,
            completed_at TIMESTAMP,
            error_message TEXT,
            processing_metadata TEXT,
            FOREIGN KEY (banana) REFERENCES cities(banana) ON DELETE CASCADE,
            FOREIGN KEY (meeting_id) REFERENCES meetings(id) ON DELETE CASCADE
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
            banana TEXT NOT NULL,
            added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (tenant_id) REFERENCES tenants(id) ON DELETE CASCADE,
            FOREIGN KEY (banana) REFERENCES cities(banana) ON DELETE CASCADE,
            PRIMARY KEY (tenant_id, banana)
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
            banana TEXT NOT NULL,
            first_mentioned_meeting_id TEXT,
            first_seen TIMESTAMP,
            last_seen TIMESTAMP,
            status TEXT DEFAULT 'active',
            metadata TEXT,
            FOREIGN KEY (tenant_id) REFERENCES tenants(id) ON DELETE CASCADE,
            FOREIGN KEY (banana) REFERENCES cities(banana) ON DELETE CASCADE
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
        CREATE INDEX IF NOT EXISTS idx_zipcodes_zipcode ON zipcodes(zipcode);
        CREATE INDEX IF NOT EXISTS idx_meetings_banana ON meetings(banana);
        CREATE INDEX IF NOT EXISTS idx_meetings_date ON meetings(date);
        CREATE INDEX IF NOT EXISTS idx_meetings_status ON meetings(processing_status);
        CREATE INDEX IF NOT EXISTS idx_cache_hash ON cache(content_hash);
        CREATE INDEX IF NOT EXISTS idx_queue_status ON queue(status);
        CREATE INDEX IF NOT EXISTS idx_queue_priority ON queue(priority DESC);
        CREATE INDEX IF NOT EXISTS idx_queue_city ON queue(banana);
        CREATE INDEX IF NOT EXISTS idx_tenant_coverage_city ON tenant_coverage(banana);
        CREATE INDEX IF NOT EXISTS idx_tracked_items_tenant ON tracked_items(tenant_id);
        CREATE INDEX IF NOT EXISTS idx_tracked_items_city ON tracked_items(banana);
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
        slug: Optional[str] = None,
        zipcode: Optional[str] = None
    ) -> Optional[City]:
        """
        Unified city lookup - replaces 4+ separate methods.

        Uses most specific parameter provided:
        - banana: Direct primary key lookup (fastest)
        - slug: Lookup by vendor-specific identifier
        - zipcode: Lookup via zipcodes join
        - name + state: Normalized name matching

        Examples:
            get_city(banana="paloaltoCA")
            get_city(name="Palo Alto", state="CA")
            get_city(slug="cityofpaloalto")
            get_city(zipcode="94301")
        """
        if self.conn is None:
            raise DatabaseConnectionError("Database connection not established")
        cursor = self.conn.cursor()

        if banana:
            # Direct primary key lookup
            cursor.execute("SELECT * FROM cities WHERE banana = ?", (banana,))
        elif slug:
            # Lookup by vendor slug
            cursor.execute("SELECT * FROM cities WHERE slug = ?", (slug,))
        elif zipcode:
            # Lookup via zipcode join
            cursor.execute("""
                SELECT c.* FROM cities c
                JOIN zipcodes cz ON c.banana = cz.banana
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

    def get_city_meeting_stats(self, bananas: List[str]) -> Dict[str, Dict[str, int]]:
        """Get meeting statistics for multiple cities at once"""
        if not bananas:
            return {}

        assert self.conn is not None, "Database connection not established"
        placeholders = ','.join('?' * len(bananas))
        cursor = self.conn.cursor()
        cursor.execute(f"""
            SELECT
                banana,
                COUNT(*) as total_meetings,
                SUM(CASE WHEN summary IS NOT NULL THEN 1 ELSE 0 END) as summarized_meetings
            FROM meetings
            WHERE banana IN ({placeholders})
            GROUP BY banana
        """, bananas)

        return {
            row['banana']: {
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
        slug: str,
        county: Optional[str] = None,
        zipcodes: Optional[List[str]] = None
    ) -> City:
        """Add a new city to the database"""
        assert self.conn is not None, "Database connection not established"
        cursor = self.conn.cursor()

        cursor.execute("""
            INSERT OR REPLACE INTO cities
            (banana, name, state, vendor, slug, county)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (banana, name, state, vendor, slug, county))

        # Add zipcodes if provided
        if zipcodes:
            for i, zipcode in enumerate(zipcodes):
                is_primary = (i == 0)
                cursor.execute("""
                    INSERT OR IGNORE INTO zipcodes
                    (banana, zipcode, is_primary)
                    VALUES (?, ?, ?)
                """, (banana, zipcode, is_primary))

        self.conn.commit()
        logger.info(f"Added city: {banana} ({name}, {state})")

        result = self.get_city(banana=banana)
        if result is None:
            raise DatabaseConnectionError(f"Failed to retrieve newly added city: {banana}")
        return result

    def get_city_zipcodes(self, banana: str) -> List[str]:
        """Get all zipcodes for a city"""
        if self.conn is None:
            raise DatabaseConnectionError("Database connection not established")
        cursor = self.conn.cursor()
        cursor.execute("""
            SELECT zipcode FROM zipcodes
            WHERE banana = ?
            ORDER BY is_primary DESC, zipcode
        """, (banana,))

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
        bananas: Optional[List[str]] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        has_summary: Optional[bool] = None,
        limit: int = 50
    ) -> List[Meeting]:
        """
        Get meetings with flexible filtering.

        Args:
            bananas: Filter by list of bananas
            start_date: Filter by date >= start_date
            end_date: Filter by date <= end_date
            has_summary: Filter by whether summary exists
            limit: Maximum results
        """
        assert self.conn is not None, "Database connection not established"
        conditions = []
        params = []

        if bananas:
            placeholders = ','.join('?' * len(bananas))
            conditions.append(f"banana IN ({placeholders})")
            params.extend(bananas)

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
            (id, banana, title, date, packet_url, summary, status,
             processing_status, processing_method, processing_time)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            meeting.id,
            meeting.banana,
            meeting.title,
            meeting.date.isoformat() if meeting.date else None,
            meeting.packet_url,
            meeting.summary,
            meeting.status,
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

    def get_city_meeting_frequency(self, banana: str, days: int = 30) -> int:
        """Get count of meetings for a city in the last N days"""
        assert self.conn is not None, "Database connection not established"
        cursor = self.conn.cursor()
        cursor.execute("""
            SELECT COUNT(*) as count
            FROM meetings
            WHERE banana = ?
            AND date >= datetime('now', '-' || ? || ' days')
        """, (banana, days))

        result = cursor.fetchone()
        return result['count'] if result else 0

    def get_city_last_sync(self, banana: str) -> Optional[datetime]:
        """Get the last sync time for a city (most recent meeting created_at)"""
        assert self.conn is not None, "Database connection not established"
        cursor = self.conn.cursor()
        cursor.execute("""
            SELECT MAX(created_at) as last_sync
            FROM meetings
            WHERE banana = ?
        """, (banana,))

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

    # ========== Agenda Item Operations ==========

    def store_agenda_items(self, meeting_id: str, items: List[AgendaItem]) -> int:
        """
        Store agenda items for a meeting.

        Args:
            meeting_id: The meeting ID these items belong to
            items: List of AgendaItem objects

        Returns:
            Number of items stored
        """
        assert self.conn is not None, "Database connection not established"
        cursor = self.conn.cursor()

        stored_count = 0

        for item in items:
            # Serialize JSON fields
            attachments_json = json.dumps(item.attachments) if item.attachments else None
            topics_json = json.dumps(item.topics) if item.topics else None

            cursor.execute("""
                INSERT OR REPLACE INTO items
                (id, meeting_id, title, sequence, attachments, summary, topics)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                item.id,
                meeting_id,
                item.title,
                item.sequence,
                attachments_json,
                item.summary,
                topics_json
            ))
            stored_count += 1

        self.conn.commit()
        logger.debug(f"Stored {stored_count} agenda items for meeting {meeting_id}")
        return stored_count

    def get_agenda_items(self, meeting_id: str) -> List[AgendaItem]:
        """
        Get all agenda items for a meeting, ordered by sequence.

        Args:
            meeting_id: The meeting ID

        Returns:
            List of AgendaItem objects
        """
        assert self.conn is not None, "Database connection not established"
        cursor = self.conn.cursor()

        cursor.execute("""
            SELECT * FROM items
            WHERE meeting_id = ?
            ORDER BY sequence ASC
        """, (meeting_id,))

        rows = cursor.fetchall()
        return [AgendaItem.from_db_row(row) for row in rows]

    def update_agenda_item(self, item_id: str, summary: str, topics: List[str]) -> None:
        """
        Update an agenda item with processed summary and topics.

        Args:
            item_id: The agenda item ID
            summary: The processed summary
            topics: List of extracted topics
        """
        assert self.conn is not None, "Database connection not established"
        cursor = self.conn.cursor()

        topics_json = json.dumps(topics) if topics else None

        cursor.execute("""
            UPDATE items
            SET summary = ?,
                topics = ?
            WHERE id = ?
        """, (summary, topics_json, item_id))

        self.conn.commit()
        logger.debug(f"Updated agenda item {item_id} with summary and topics")

    # ========== Processing Cache Operations ==========

    def get_cached_summary(self, packet_url: str | List[str]) -> Optional[Meeting]:
        """Get meeting by packet URL if it has been processed"""
        if self.conn is None:
            raise DatabaseConnectionError("Database connection not established")
        cursor = self.conn.cursor()

        # Serialize URL if it's a list
        lookup_url = json.dumps(packet_url) if isinstance(packet_url, list) else packet_url

        cursor.execute("""
            SELECT * FROM meetings
            WHERE packet_url = ? AND summary IS NOT NULL
            LIMIT 1
        """, (lookup_url,))

        row = cursor.fetchone()
        if row:
            # Update cache hit count
            cursor.execute("""
                UPDATE cache
                SET cache_hit_count = cache_hit_count + 1,
                    last_accessed = CURRENT_TIMESTAMP
                WHERE packet_url = ?
            """, (lookup_url,))
            self.conn.commit()

            return Meeting.from_db_row(row)

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
            INSERT OR REPLACE INTO cache
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

    # === Processing Queue Methods (Phase 4) ===

    def enqueue_for_processing(self, packet_url: str, meeting_id: str, banana: str,
                               priority: int = 0, metadata: Optional[Dict[str, Any]] = None) -> int:
        """Add a packet URL to the processing queue with priority"""
        if self.conn is None:
            raise DatabaseConnectionError("Database connection not established")

        cursor = self.conn.cursor()
        metadata_json = json.dumps(metadata) if metadata else None

        try:
            cursor.execute(
                """
                INSERT INTO queue
                (packet_url, meeting_id, banana, priority, processing_metadata)
                VALUES (?, ?, ?, ?, ?)
                """,
                (packet_url, meeting_id, banana, priority, metadata_json)
            )
            self.conn.commit()
            queue_id = cursor.lastrowid
            if queue_id is None:
                raise DatabaseConnectionError("Failed to get queue ID after insert")
            logger.info(f"Enqueued {packet_url} for processing with priority {priority}")
            return queue_id
        except sqlite3.IntegrityError as e:
            if "UNIQUE constraint failed" in str(e):
                logger.debug(f"Packet {packet_url} already in queue")
                return -1
            raise

    def get_next_for_processing(self, banana: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """Get next item from processing queue based on priority and status"""
        if self.conn is None:
            raise DatabaseConnectionError("Database connection not established")

        cursor = self.conn.cursor()

        if banana:
            cursor.execute(
                """
                SELECT * FROM queue
                WHERE status = 'pending' AND banana = ?
                ORDER BY priority DESC, created_at ASC
                LIMIT 1
                """,
                (banana,)
            )
        else:
            cursor.execute(
                """
                SELECT * FROM queue
                WHERE status = 'pending'
                ORDER BY priority DESC, created_at ASC
                LIMIT 1
                """
            )

        row = cursor.fetchone()
        if row:
            # Mark as processing
            cursor.execute(
                """
                UPDATE queue
                SET status = 'processing', started_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (row['id'],)
            )
            self.conn.commit()

            result = dict(row)
            if result.get('processing_metadata'):
                result['processing_metadata'] = json.loads(result['processing_metadata'])
            return result
        return None

    def mark_processing_complete(self, queue_id: int) -> None:
        """Mark a queue item as completed"""
        if self.conn is None:
            raise DatabaseConnectionError("Database connection not established")

        cursor = self.conn.cursor()
        cursor.execute(
            """
            UPDATE queue
            SET status = 'completed', completed_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (queue_id,)
        )
        self.conn.commit()
        logger.info(f"Marked queue item {queue_id} as completed")

    def mark_processing_failed(self, queue_id: int, error_message: str, increment_retry: bool = True) -> None:
        """Mark a queue item as failed with error message"""
        if self.conn is None:
            raise DatabaseConnectionError("Database connection not established")

        cursor = self.conn.cursor()

        if increment_retry:
            cursor.execute(
                """
                UPDATE queue
                SET status = 'failed',
                    error_message = ?,
                    retry_count = retry_count + 1,
                    completed_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (error_message, queue_id)
            )
        else:
            cursor.execute(
                """
                UPDATE queue
                SET status = 'failed',
                    error_message = ?,
                    completed_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (error_message, queue_id)
            )
        self.conn.commit()
        logger.warning(f"Marked queue item {queue_id} as failed: {error_message}")

    def reset_failed_items(self, max_retries: int = 3) -> int:
        """Reset failed items back to pending if under retry limit"""
        if self.conn is None:
            raise DatabaseConnectionError("Database connection not established")

        cursor = self.conn.cursor()
        cursor.execute(
            """
            UPDATE queue
            SET status = 'pending', error_message = NULL
            WHERE status = 'failed' AND retry_count < ?
            """,
            (max_retries,)
        )
        reset_count = cursor.rowcount
        self.conn.commit()
        logger.info(f"Reset {reset_count} failed items back to pending")
        return reset_count

    def get_queue_stats(self) -> Dict[str, Any]:
        """Get processing queue statistics"""
        if self.conn is None:
            raise DatabaseConnectionError("Database connection not established")

        cursor = self.conn.cursor()
        stats = {}

        # Count by status
        cursor.execute(
            """
            SELECT status, COUNT(*) as count
            FROM queue
            GROUP BY status
            """
        )
        for row in cursor.fetchall():
            stats[f"{row['status']}_count"] = row['count']

        # Failed with high retry count
        cursor.execute(
            """
            SELECT COUNT(*) as count
            FROM queue
            WHERE status = 'failed' AND retry_count >= 3
            """
        )
        result = cursor.fetchone()
        stats['permanently_failed'] = result['count'] if result else 0

        # Average processing time
        cursor.execute(
            """
            SELECT AVG(julianday(completed_at) - julianday(started_at)) * 86400 as avg_seconds
            FROM queue
            WHERE status = 'completed' AND completed_at IS NOT NULL AND started_at IS NOT NULL
            """
        )
        result = cursor.fetchone()
        avg_time = result['avg_seconds'] if result else None
        stats['avg_processing_seconds'] = avg_time if avg_time else 0

        return stats

    def bulk_enqueue_unprocessed_meetings(self, limit: Optional[int] = None) -> int:
        """Bulk enqueue all unprocessed meetings with packet URLs"""
        if self.conn is None:
            raise DatabaseConnectionError("Database connection not established")

        cursor = self.conn.cursor()

        # Find all meetings with packet URLs but no summaries
        query = """
            SELECT m.packet_url, m.id, m.banana, m.date
            FROM meetings m
            LEFT JOIN queue pq ON m.packet_url = pq.packet_url
            WHERE m.packet_url IS NOT NULL
            AND m.summary IS NULL
            AND pq.id IS NULL
            ORDER BY m.date DESC
        """

        if limit:
            query += f" LIMIT {limit}"

        cursor.execute(query)
        meetings = cursor.fetchall()

        enqueued = 0
        for meeting in meetings:
            # Calculate priority based on meeting date recency
            if meeting['date']:
                try:
                    meeting_date = datetime.fromisoformat(meeting['date']) if isinstance(meeting['date'], str) else meeting['date']
                    days_old = (datetime.now() - meeting_date).days
                except Exception:
                    days_old = 999
            else:
                days_old = 999

            priority = max(0, 100 - days_old)  # Recent meetings get higher priority

            try:
                cursor.execute(
                    """
                    INSERT INTO queue
                    (packet_url, meeting_id, banana, priority)
                    VALUES (?, ?, ?, ?)
                    """,
                    (meeting['packet_url'], meeting['id'], meeting['banana'], priority)
                )
                enqueued += 1
            except sqlite3.IntegrityError:
                logger.debug(f"Skipping already queued packet: {meeting['packet_url']}")

        self.conn.commit()
        logger.info(f"Bulk enqueued {enqueued} meetings for processing")
        return enqueued

    def close(self):
        """Close database connection"""
        if self.conn:
            self.conn.close()
            logger.info("Database connection closed")
