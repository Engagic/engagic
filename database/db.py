"""
Unified Database for Engagic - Repository Pattern

Consolidates locations.db, meetings.db, and analytics.db into a single database
with clean repository-based architecture.

This facade provides the same API as before but delegates to focused repositories:
- CityRepository: City and zipcode operations
- MeetingRepository: Meeting storage and retrieval
- ItemRepository: Agenda item operations
- MatterRepository: Matter operations (matters-first architecture)
- QueueRepository: Processing queue management
- SearchRepository: Search, topics, cache, and stats
"""

import json
import logging
import sqlite3
from typing import Optional, List, Dict, Any
from datetime import datetime
from pathlib import Path

from database.models import City, Meeting, AgendaItem, Matter
from exceptions import DatabaseConnectionError
from database.repositories.cities import CityRepository
from database.repositories.meetings import MeetingRepository
from database.repositories.items import ItemRepository
from database.repositories.matters import MatterRepository
from database.repositories.queue import QueueRepository
from database.repositories.search import SearchRepository
from pipeline.utils import hash_attachments

logger = logging.getLogger("engagic")


class UnifiedDatabase:
    """
    Single database interface for all Engagic data.
    Delegates to focused repositories for cleaner separation of concerns.

    Threading Model:
    - Each instance creates its own SQLite connection
    - WAL mode enables multiple writers with separate connections
    - DO NOT share instances across threads - create one per thread
    """

    conn: sqlite3.Connection

    def __init__(self, db_path: str):
        """Initialize unified database connection and repositories

        Note: Each instance is thread-local. Multi-threaded applications
        should create one UnifiedDatabase instance per thread.
        """
        self.db_path = db_path
        self._connect()
        self._init_schema()

        # Initialize repositories with shared connection
        self.cities = CityRepository(self.conn)
        self.meetings = MeetingRepository(self.conn)
        self.items = ItemRepository(self.conn)
        self.matters = MatterRepository(self.conn)
        self.queue = QueueRepository(self.conn)
        self.search = SearchRepository(self.conn)

        logger.info(f"Initialized unified database at {db_path}")

    def _connect(self):
        """Create database connection with optimizations

        Note: check_same_thread=False allows passing connection to repositories,
        but instances should NOT be shared across threads. Each thread should
        create its own UnifiedDatabase instance for proper isolation.
        """
        # Ensure directory exists
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)

        self.conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row

        # Performance optimizations
        # WAL mode enables multiple writers (each with own connection)
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
            agenda_url TEXT,
            packet_url TEXT,
            summary TEXT,
            participation TEXT,
            status TEXT,
            topics TEXT,
            processing_status TEXT DEFAULT 'pending',
            processing_method TEXT,
            processing_time REAL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (banana) REFERENCES cities(banana) ON DELETE CASCADE
        );

        -- City Matters: Canonical representation of legislative items
        -- Matters-First Architecture: Each matter has ONE canonical summary
        -- that is reused across all appearances (deduplication)
        CREATE TABLE IF NOT EXISTS city_matters (
            id TEXT PRIMARY KEY,
            banana TEXT NOT NULL,
            matter_id TEXT,
            matter_file TEXT,
            matter_type TEXT,
            title TEXT NOT NULL,
            sponsors TEXT,
            canonical_summary TEXT,
            canonical_topics TEXT,
            attachments TEXT,
            metadata TEXT,
            first_seen TIMESTAMP,
            last_seen TIMESTAMP,
            appearance_count INTEGER DEFAULT 1,
            status TEXT DEFAULT 'active',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (banana) REFERENCES cities(banana) ON DELETE CASCADE
        );

        -- Matter Appearances: Timeline tracking for matters across meetings
        -- Junction table linking matters to meetings via agenda items
        CREATE TABLE IF NOT EXISTS matter_appearances (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            matter_id TEXT NOT NULL,
            meeting_id TEXT NOT NULL,
            item_id TEXT NOT NULL,
            appeared_at TIMESTAMP NOT NULL,
            committee TEXT,
            action TEXT,
            vote_tally TEXT,
            sequence INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (matter_id) REFERENCES city_matters(id) ON DELETE CASCADE,
            FOREIGN KEY (meeting_id) REFERENCES meetings(id) ON DELETE CASCADE,
            FOREIGN KEY (item_id) REFERENCES items(id) ON DELETE CASCADE,
            UNIQUE(matter_id, meeting_id, item_id)
        );

        -- Agenda items: Individual items within meetings
        -- matter_id stores COMPOSITE HASHED ID matching city_matters.id
        CREATE TABLE IF NOT EXISTS items (
            id TEXT PRIMARY KEY,
            meeting_id TEXT NOT NULL,
            title TEXT NOT NULL,
            sequence INTEGER NOT NULL,
            attachments TEXT,
            attachment_hash TEXT,
            matter_id TEXT,
            matter_file TEXT,
            matter_type TEXT,
            agenda_number TEXT,
            sponsors TEXT,
            summary TEXT,
            topics TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (meeting_id) REFERENCES meetings(id) ON DELETE CASCADE,
            FOREIGN KEY (matter_id) REFERENCES city_matters(id) ON DELETE SET NULL
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

        -- Processing queue: Decoupled processing queue (agenda-first, item-level)
        CREATE TABLE IF NOT EXISTS queue (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source_url TEXT NOT NULL UNIQUE,
            meeting_id TEXT,
            banana TEXT,
            job_type TEXT,
            payload TEXT,
            status TEXT DEFAULT 'pending' CHECK (status IN ('pending', 'processing', 'completed', 'failed', 'dead_letter')),
            priority INTEGER DEFAULT 0,
            retry_count INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            started_at TIMESTAMP,
            completed_at TIMESTAMP,
            failed_at TIMESTAMP,
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

        -- User profiles: End-user accounts (Phase 2)
        CREATE TABLE IF NOT EXISTS user_profiles (
            id TEXT PRIMARY KEY,
            email TEXT UNIQUE NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        -- User topic subscriptions: Topics users want alerts for (Phase 2)
        CREATE TABLE IF NOT EXISTS user_topic_subscriptions (
            user_id TEXT NOT NULL,
            banana TEXT NOT NULL,
            topic TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES user_profiles(id) ON DELETE CASCADE,
            FOREIGN KEY (banana) REFERENCES cities(banana) ON DELETE CASCADE,
            PRIMARY KEY (user_id, banana, topic)
        );

        -- Performance indices
        CREATE INDEX IF NOT EXISTS idx_cities_vendor ON cities(vendor);
        CREATE INDEX IF NOT EXISTS idx_cities_state ON cities(state);
        CREATE INDEX IF NOT EXISTS idx_cities_status ON cities(status);
        CREATE INDEX IF NOT EXISTS idx_zipcodes_zipcode ON zipcodes(zipcode);
        CREATE INDEX IF NOT EXISTS idx_meetings_banana ON meetings(banana);
        CREATE INDEX IF NOT EXISTS idx_meetings_date ON meetings(date);
        CREATE INDEX IF NOT EXISTS idx_meetings_status ON meetings(processing_status);
        CREATE INDEX IF NOT EXISTS idx_items_matter_file ON items(matter_file) WHERE matter_file IS NOT NULL;
        CREATE INDEX IF NOT EXISTS idx_items_matter_id ON items(matter_id) WHERE matter_id IS NOT NULL;
        CREATE INDEX IF NOT EXISTS idx_items_meeting_id ON items(meeting_id);
        CREATE INDEX IF NOT EXISTS idx_city_matters_banana ON city_matters(banana);
        CREATE INDEX IF NOT EXISTS idx_city_matters_matter_file ON city_matters(matter_file);
        CREATE INDEX IF NOT EXISTS idx_city_matters_first_seen ON city_matters(first_seen);
        CREATE INDEX IF NOT EXISTS idx_city_matters_status ON city_matters(status);
        CREATE INDEX IF NOT EXISTS idx_matter_appearances_matter ON matter_appearances(matter_id);
        CREATE INDEX IF NOT EXISTS idx_matter_appearances_meeting ON matter_appearances(meeting_id);
        CREATE INDEX IF NOT EXISTS idx_matter_appearances_item ON matter_appearances(item_id);
        CREATE INDEX IF NOT EXISTS idx_matter_appearances_date ON matter_appearances(appeared_at);
        CREATE INDEX IF NOT EXISTS idx_cache_hash ON cache(content_hash);
        CREATE INDEX IF NOT EXISTS idx_queue_status ON queue(status);
        CREATE INDEX IF NOT EXISTS idx_queue_priority ON queue(priority DESC);
        CREATE INDEX IF NOT EXISTS idx_queue_city ON queue(banana);
        CREATE INDEX IF NOT EXISTS idx_tenant_coverage_city ON tenant_coverage(banana);
        CREATE INDEX IF NOT EXISTS idx_tracked_items_tenant ON tracked_items(tenant_id);
        CREATE INDEX IF NOT EXISTS idx_tracked_items_city ON tracked_items(banana);
        CREATE INDEX IF NOT EXISTS idx_tracked_items_status ON tracked_items(status);
        CREATE INDEX IF NOT EXISTS idx_user_profiles_email ON user_profiles(email);
        CREATE INDEX IF NOT EXISTS idx_user_subscriptions_user ON user_topic_subscriptions(user_id);
        CREATE INDEX IF NOT EXISTS idx_user_subscriptions_city ON user_topic_subscriptions(banana);
        CREATE INDEX IF NOT EXISTS idx_user_subscriptions_topic ON user_topic_subscriptions(topic);
        """

        self.conn.executescript(schema)
        self.conn.commit()

    # ========== City Operations (delegate to CityRepository) ==========

    def get_city(
        self,
        banana: Optional[str] = None,
        name: Optional[str] = None,
        state: Optional[str] = None,
        slug: Optional[str] = None,
        zipcode: Optional[str] = None,
    ) -> Optional[City]:
        """Unified city lookup - delegates to CityRepository"""
        return self.cities.get_city(banana, name, state, slug, zipcode)

    def get_cities(
        self,
        state: Optional[str] = None,
        vendor: Optional[str] = None,
        name: Optional[str] = None,
        status: str = "active",
        limit: Optional[int] = None,
    ) -> List[City]:
        """Batch city lookup - delegates to CityRepository"""
        return self.cities.get_cities(state, vendor, name, status, limit)

    def get_city_meeting_stats(self, bananas: List[str]) -> Dict[str, Dict[str, int]]:
        """Get meeting statistics for multiple cities - delegates to CityRepository"""
        return self.cities.get_city_meeting_stats(bananas)

    def add_city(
        self,
        banana: str,
        name: str,
        state: str,
        vendor: str,
        slug: str,
        county: Optional[str] = None,
        zipcodes: Optional[List[str]] = None,
    ) -> City:
        """Add a new city - delegates to CityRepository"""
        return self.cities.add_city(banana, name, state, vendor, slug, county, zipcodes)

    def get_city_zipcodes(self, banana: str) -> List[str]:
        """Get all zipcodes for a city - delegates to CityRepository"""
        return self.cities.get_city_zipcodes(banana)

    def get_city_meeting_frequency(self, banana: str, days: int = 30) -> int:
        """Get meeting count for city in last N days - delegates to CityRepository"""
        return self.cities.get_city_meeting_frequency(banana, days)

    def get_city_last_sync(self, banana: str) -> Optional[datetime]:
        """Get last sync time for city - delegates to CityRepository"""
        return self.cities.get_city_last_sync(banana)

    # ========== Meeting Operations (delegate to MeetingRepository) ==========

    def get_meeting(self, meeting_id: str) -> Optional[Meeting]:
        """Get a single meeting by ID - delegates to MeetingRepository"""
        return self.meetings.get_meeting(meeting_id)

    def get_meetings(
        self,
        bananas: Optional[List[str]] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        has_summary: Optional[bool] = None,
        limit: int = 50,
    ) -> List[Meeting]:
        """Get meetings with filters - delegates to MeetingRepository"""
        return self.meetings.get_meetings(bananas, start_date, end_date, has_summary, limit)

    def store_meeting(self, meeting: Meeting) -> Meeting:
        """Store or update a meeting - delegates to MeetingRepository"""
        return self.meetings.store_meeting(meeting)

    def store_meeting_from_sync(
        self, meeting_dict: Dict[str, Any], city: City
    ) -> tuple[Optional[Meeting], Dict[str, int]]:
        """
        Transform vendor meeting dict → validate → store → enqueue for processing

        This method orchestrates across multiple repositories:
        1. Parses dates from vendor format
        2. Creates Meeting and AgendaItem objects
        3. Validates meeting data
        4. Stores meeting and items in database
        5. Enqueues for LLM processing

        Args:
            meeting_dict: Raw meeting dict from vendor adapter
            city: City object for this meeting

        Returns:
            Stored Meeting object (or None if validation failed)
        """
        from vendors.validator import MeetingValidator
        from vendors.utils.item_filters import should_skip_procedural_item

        # Initialize stats tracking
        stats = {
            'items_stored': 0,
            'items_skipped_procedural': 0,
            'matters_tracked': 0,
            'matters_duplicate': 0,
        }

        try:
            # Parse date from adapter format
            meeting_date = None
            if meeting_dict.get("start"):
                date_str = meeting_dict["start"]
                # Try multiple date formats
                for fmt in [
                    None,  # ISO format via fromisoformat
                    "%m/%d/%y",  # NovusAgenda: "11/05/25"
                    "%Y-%m-%d",  # Standard: "2025-11-05"
                    "%m/%d/%Y",  # US format: "11/05/2025"
                ]:
                    try:
                        if fmt is None:
                            # Try ISO format
                            meeting_date = datetime.fromisoformat(
                                date_str.replace("Z", "+00:00")
                            )
                        else:
                            meeting_date = datetime.strptime(date_str, fmt)
                        break  # Successfully parsed
                    except Exception:
                        continue

            # Validate meeting_id (fail fast if adapter didn't provide one)
            meeting_id = meeting_dict.get("meeting_id")
            if not meeting_id or not meeting_id.strip():
                logger.error(
                    f"[{city.banana}] CRITICAL: Adapter returned blank meeting_id for "
                    f"'{meeting_dict.get('title', 'Unknown')}' on {meeting_dict.get('date', 'Unknown')}. "
                    f"Adapter should use _generate_meeting_id() fallback."
                )
                return (None, stats)

            # Create Meeting object
            meeting_obj = Meeting(
                id=meeting_id,
                banana=city.banana,
                title=meeting_dict.get("title", ""),
                date=meeting_date,
                agenda_url=meeting_dict.get("agenda_url"),
                packet_url=meeting_dict.get("packet_url"),
                summary=None,
                participation=meeting_dict.get("participation"),
                status=meeting_dict.get("meeting_status"),
                processing_status="pending",
            )

            # Preserve existing summary if already processed (don't overwrite on re-sync)
            existing_meeting = self.get_meeting(meeting_obj.id)
            if existing_meeting and existing_meeting.summary:
                meeting_obj.summary = existing_meeting.summary
                meeting_obj.processing_status = existing_meeting.processing_status
                meeting_obj.processing_method = existing_meeting.processing_method
                meeting_obj.processing_time = existing_meeting.processing_time
                meeting_obj.topics = existing_meeting.topics
                logger.debug(f"Preserved existing summary for {meeting_obj.title}")

            # Validate meeting before storing
            if not MeetingValidator.validate_and_store(
                {
                    "packet_url": meeting_obj.packet_url,
                    "title": meeting_obj.title,
                },
                city.banana,
                city.name,
                city.vendor,
                city.slug,
            ):
                logger.warning(f"[Items] Skipping corrupted meeting: {meeting_obj.title}")
                return None, stats

            # Store meeting (upsert)
            stored_meeting = self.store_meeting(meeting_obj)

            # Store agenda items if present (preserve existing summaries on re-sync)
            agenda_items = []  # Initialize outside if block for later reference
            if meeting_dict.get("items"):
                items = meeting_dict["items"]
                procedural_items = []

                # Build map of existing items to preserve summaries
                existing_items = self.get_agenda_items(stored_meeting.id)
                existing_items_map = {item.id: item for item in existing_items}

                for item_data in items:
                    item_id = f"{stored_meeting.id}_{item_data['item_id']}"
                    item_title = item_data.get("title", "")
                    item_type = item_data.get("matter_type", "")

                    # Check if procedural (skip for processing but log)
                    is_procedural = should_skip_procedural_item(item_title, item_type)
                    if is_procedural:
                        procedural_items.append(item_title[:50])
                        stats['items_skipped_procedural'] += 1
                        # Still store it, just mark it as skip
                        logger.info(f"[Items] Procedural (skipped): {item_title[:60]}")

                    # Generate composite matter_id for FK relationship
                    # Items.matter_id MUST match city_matters.id (composite hashed ID)
                    # Skip matter tracking for procedural items (they don't need timeline tracking)
                    composite_matter_id = None
                    raw_matter_id = item_data.get("matter_id")
                    raw_matter_file = item_data.get("matter_file")

                    # Check BOTH title-based AND matter_type-based procedural filters
                    # to prevent FK constraint failures from matter tracking skip
                    if not is_procedural and (raw_matter_id or raw_matter_file):
                        from database.id_generation import generate_matter_id
                        from vendors.utils.item_filters import should_skip_matter

                        # Additional check: skip if matter_type is procedural
                        # (e.g., "Minutes (Min)", "Information Item (Inf)")
                        if should_skip_matter(item_type):
                            logger.debug(
                                f"[Items] Skipping matter tracking for procedural type: {item_title[:40]} ({item_type})"
                            )
                            composite_matter_id = None
                        else:
                            try:
                                composite_matter_id = generate_matter_id(
                                    banana=city.banana,
                                    matter_file=raw_matter_file,
                                    matter_id=raw_matter_id
                                )
                            except ValueError as e:
                                # Fail-fast: Item claims to have a matter but generation failed
                                # This indicates data quality issues that should be fixed at adapter level
                                logger.error(
                                    f"[Items] FATAL: Invalid matter data for {item_title[:40]}: {e}"
                                )
                                raise ValueError(
                                    f"Item '{item_title}' has invalid matter data (matter_id={raw_matter_id}, "
                                    f"matter_file={raw_matter_file}): {e}"
                                ) from e

                    # Compute attachment hash for change detection
                    item_attachments = item_data.get("attachments", [])
                    item_attachment_hash = hash_attachments(item_attachments) if item_attachments else None

                    agenda_item = AgendaItem(
                        id=item_id,
                        meeting_id=stored_meeting.id,
                        title=item_title,
                        sequence=item_data.get("sequence", 0),
                        attachments=item_attachments,
                        attachment_hash=item_attachment_hash,
                        matter_id=composite_matter_id,  # Store COMPOSITE ID for FK
                        matter_file=raw_matter_file,     # Store public identifier
                        matter_type=item_data.get("matter_type"),
                        agenda_number=item_data.get("agenda_number"),
                        sponsors=item_data.get("sponsors"),
                        summary=None,
                        topics=None,
                    )

                    # Preserve existing summary if already processed
                    if item_id in existing_items_map:
                        existing_item = existing_items_map[item_id]
                        if existing_item.summary:
                            agenda_item.summary = existing_item.summary
                        if existing_item.topics:
                            agenda_item.topics = existing_item.topics

                    # Log item with matter tracking
                    if agenda_item.matter_file or composite_matter_id:
                        logger.info(
                            f"[Items] {item_title[:50]} | Matter: {agenda_item.matter_file} ({composite_matter_id[:24]}...)"
                            if composite_matter_id else
                            f"[Items] {item_title[:50]} | Matter: {agenda_item.matter_file}"
                        )
                    else:
                        logger.info(f"[Items] {item_title[:50]}")

                    agenda_items.append(agenda_item)

                if agenda_items:
                    # ATOMIC TRANSACTION: Track matters + store items + create appearances
                    # All-or-nothing: if any step fails, rollback entire meeting ingest
                    # Note: Using defer_commit=True with final commit for implicit transaction control
                    try:
                        # Track matters FIRST in city_matters table (creates FK targets)
                        # CRITICAL: Must happen before store_agenda_items to avoid FK constraint failures
                        matters_stats = self._track_matters(stored_meeting, items, agenda_items, defer_commit=True)
                        stats['matters_tracked'] = matters_stats.get('tracked', 0)
                        stats['matters_duplicate'] = matters_stats.get('duplicate', 0)

                        # THEN store items (FK targets exist now)
                        count = self.store_agenda_items(stored_meeting.id, agenda_items, defer_commit=True)
                        stats['items_stored'] = count
                        items_with_summaries = sum(1 for item in agenda_items if item.summary)

                        # Commit transaction atomically
                        self.conn.commit()

                        logger.info(
                            f"[Items] Stored {count} items ({stats['items_skipped_procedural']} procedural, "
                            f"{items_with_summaries} with preserved summaries)"
                        )

                    except Exception as e:
                        self.conn.rollback()
                        logger.error(f"[Items] Transaction rolled back due to error: {e}")
                        raise


            # Check if already processed before enqueuing (to avoid wasting credits)
            # AGENDA-FIRST: Check item-level summaries (golden path) first
            #
            # TODO: Future enhancement - PDF content hash detection
            # Calculate hash of packet_url content and compare against cache.content_hash
            # to detect meaningful changes. Would require fetching PDF during sync (slower)
            # but enables smart re-processing only when content actually changes.
            # Trade-off: Sync latency vs credit efficiency for updated agendas.
            has_items = bool(meeting_dict.get("items"))
            agenda_url = meeting_dict.get("agenda_url")
            packet_url = meeting_dict.get("packet_url")

            skip_enqueue = False
            skip_reason = None

            # Priority 1: Check for item-level summaries (GOLDEN PATH)
            # Only skip if ALL items have summaries - processor handles partial completion granularly
            if has_items and 'agenda_items' in locals():
                items_with_summaries = [item for item in agenda_items if item.summary]
                # Skip only if 100% complete (processor will filter procedural/public comments)
                if items_with_summaries and len(items_with_summaries) == len(agenda_items):
                    skip_enqueue = True
                    skip_reason = f"all {len(agenda_items)} items already have summaries"

            # Priority 2: Check for monolithic summary (fallback path)
            if not skip_enqueue and stored_meeting.summary:
                skip_enqueue = True
                skip_reason = "meeting already has summary (monolithic)"

            if skip_enqueue:
                logger.debug(
                    f"Skipping enqueue for {stored_meeting.title} - {skip_reason}"
                )
            elif has_items or packet_url:
                # Calculate priority based on meeting date proximity
                if meeting_date:
                    days_from_now = (meeting_date - datetime.now()).days
                    days_distance = abs(days_from_now)
                else:
                    days_distance = 999

                priority = max(0, 150 - days_distance)

                # MATTERS-FIRST: Deduplicate summarization work across meetings
                # If matter exists with unchanged attachments, reuse canonical summary
                if has_items and 'agenda_items' in locals():
                    matters_enqueued = self._enqueue_matters_first(
                        city.banana, stored_meeting, agenda_items, priority
                    )

                    if matters_enqueued > 0:
                        logger.debug(
                            f"Enqueued {matters_enqueued} matters for {stored_meeting.title} (priority {priority})"
                        )
                    else:
                        logger.debug(f"All matters already processed for {stored_meeting.title}")

                # MONOLITH FALLBACK: No items at all, process entire packet
                elif packet_url:
                    self.enqueue_meeting_job(
                        meeting_id=stored_meeting.id,
                        source_url=packet_url,
                        banana=city.banana,
                        priority=priority,
                    )
                    logger.debug(
                        f"Enqueued monolithic-packet processing for {stored_meeting.title} (priority {priority})"
                    )
                else:
                    # No items and no packet - nothing to process
                    logger.warning(
                        f"[DB] Meeting {stored_meeting.id} has no items or packet URL - skipping queue"
                    )
            else:
                logger.debug(
                    f"Meeting {stored_meeting.title} has no agenda/packet/items - stored for display only"
                )

            # Validate matter tracking (detect orphaned items)
            if agenda_items:
                self.validate_matter_tracking(stored_meeting.id)

            return stored_meeting, stats

        except Exception as e:
            logger.error(
                f"Error storing meeting {meeting_dict.get('packet_url', 'unknown')}: {e}"
            )
            return None, stats

    def _track_matters(
        self, meeting: Meeting, items_data: List[Dict], agenda_items: List[AgendaItem], defer_commit: bool = False
    ) -> Dict[str, int]:
        """
        Track legislative matters across meetings (Matters-First Architecture).

        For each agenda item with a matter_file:
        1. Create/update Matter object with attachments
        2. Store in city_matters table via MatterRepository
        3. Create matter_appearance record (timeline tracking)

        Args:
            meeting: Stored Meeting object
            items_data: Raw item data from adapter (with sponsors, matter_type)
            agenda_items: Stored AgendaItem objects
            defer_commit: If True, skip commit (caller handles transaction)

        Returns:
            Dict with 'tracked' and 'duplicate' counts
        """
        from vendors.utils.item_filters import should_skip_matter

        stats = {'tracked': 0, 'duplicate': 0, 'skipped_procedural': 0}

        if not items_data or not agenda_items:
            return stats

        # Build map from item_id to raw data for sponsor/type lookup
        items_map = {item["item_id"]: item for item in items_data}

        for agenda_item in agenda_items:
            # agenda_item.matter_id is ALREADY composite hash (set during item creation)
            # Skip items without matter tracking
            if not agenda_item.matter_id:
                continue

            # Defensive validation
            from database.id_generation import validate_matter_id
            if not validate_matter_id(agenda_item.matter_id):
                logger.error(
                    f"[Matters] Invalid matter_id format in item {agenda_item.id}: '{agenda_item.matter_id}'"
                )
                continue

            matter_composite_id = agenda_item.matter_id  # Already composite

            # Get raw vendor data (for storing in city_matters table)
            item_id_short = agenda_item.id.rsplit("_", 1)[1]  # Remove meeting_id prefix (rsplit handles underscores in meeting_id)
            raw_item = items_map.get(item_id_short, {})
            sponsors = raw_item.get("sponsors", [])
            matter_type = raw_item.get("matter_type")
            raw_vendor_matter_id = raw_item.get("matter_id")  # RAW vendor ID (UUID, numeric, etc.)

            # Skip procedural matter types (minutes, info items, calendars)
            if matter_type and should_skip_matter(matter_type):
                stats['skipped_procedural'] += 1
                logger.debug(f"[Matters] Skipping procedural: {agenda_item.matter_file or raw_vendor_matter_id} ({matter_type})")
                continue

            try:
                # Check if matter exists
                existing_matter = self.get_matter(matter_composite_id)

                # Compute attachment hash for deduplication
                # Uses fast URL-only mode by default
                # For better change detection (at cost of latency), use:
                # attachment_hash = hash_attachments(agenda_item.attachments, include_metadata=True)
                attachment_hash = hash_attachments(agenda_item.attachments)

                if existing_matter:
                    # Check if this meeting_id is already counted for this matter
                    appearance_exists = self.conn.execute(
                        """
                        SELECT COUNT(*) FROM matter_appearances
                        WHERE matter_id = ? AND meeting_id = ?
                        """,
                        (matter_composite_id, meeting.id)
                    ).fetchone()[0] > 0

                    # Only increment appearance_count if this is a NEW meeting
                    increment_sql = "appearance_count + 1" if not appearance_exists else "appearance_count"

                    # Update last_seen and appearance_count (only if new meeting)
                    self.conn.execute(
                        f"""
                        UPDATE city_matters
                        SET last_seen = ?,
                            appearance_count = {increment_sql},
                            attachments = ?,
                            metadata = json_set(COALESCE(metadata, '{{}}'), '$.attachment_hash', ?),
                            updated_at = CURRENT_TIMESTAMP
                        WHERE id = ?
                    """,
                        (
                            meeting.date,
                            json.dumps(agenda_item.attachments) if agenda_item.attachments else None,
                            attachment_hash,
                            matter_composite_id,
                        ),
                    )
                    stats['duplicate'] += 1
                    logger.info(f"[Matters] {'New appearance' if not appearance_exists else 'Reprocess'}: {agenda_item.matter_file or raw_vendor_matter_id} ({matter_type})")
                else:
                    # Create new Matter object
                    # Store RAW vendor identifiers for reference, composite as primary key
                    matter_obj = Matter(
                        id=matter_composite_id,              # Composite hash (PRIMARY KEY)
                        banana=meeting.banana,
                        matter_id=raw_vendor_matter_id,      # RAW vendor ID (for reference)
                        matter_file=agenda_item.matter_file,  # Public identifier (for display)
                        matter_type=matter_type,
                        title=agenda_item.title,
                        sponsors=sponsors,
                        canonical_summary=None,  # Will be filled by processor
                        canonical_topics=None,
                        attachments=agenda_item.attachments,
                        metadata={'attachment_hash': attachment_hash},
                        first_seen=meeting.date,
                        last_seen=meeting.date,
                        appearance_count=1,
                    )

                    # Store via Matter repository (single-phase INSERT with all fields)
                    try:
                        self.store_matter(matter_obj, defer_commit=defer_commit)
                    except Exception as e:
                        logger.error(f"[Matters] FAILED to store matter {agenda_item.matter_file or raw_vendor_matter_id}: {e}")
                        raise

                    stats['tracked'] += 1
                    logger.info(f"[Matters] New: {agenda_item.matter_file or raw_vendor_matter_id} ({matter_type}) - {len(sponsors)} sponsors")

                # Create matter_appearance record
                committee = meeting.title.split("-")[0].strip() if meeting.title else None

                self.conn.execute(
                    """
                    INSERT OR IGNORE INTO matter_appearances (
                        matter_id, meeting_id, item_id, appeared_at,
                        committee, sequence
                    ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                    (
                        matter_composite_id,
                        meeting.id,
                        agenda_item.id,
                        meeting.date,
                        committee,
                        agenda_item.sequence,
                    ),
                )

                if not defer_commit:
                    self.conn.commit()

            except Exception as e:
                logger.error(f"[Matters] Error tracking matter {matter_composite_id}: {e}")
                raise  # Propagate to outer transaction handler for rollback

        return stats

    def _enqueue_matters_first(
        self,
        banana: str,
        meeting: Meeting,
        agenda_items: List[AgendaItem],
        priority: int,
    ) -> int:
        """
        Matters-first enqueue logic: Deduplicate summarization work.

        Groups items by matter_id (composite hash), checks if matter already processed
        with unchanged attachments. If unchanged, copies canonical summary. If new/changed, enqueues.

        Args:
            banana: City identifier
            meeting: Meeting object
            agenda_items: List of agenda items with matter tracking
            priority: Queue priority

        Returns:
            Number of matters enqueued (0 if all reused from canonical)
        """
        from vendors.utils.item_filters import should_skip_matter
        from database.id_generation import validate_matter_id

        # Group items by matter_id (already composite hash from item creation)
        matters_map: Dict[str, List[AgendaItem]] = {}
        items_without_matters = []

        for item in agenda_items:
            if item.matter_id:
                # item.matter_id is already composite hash - just use it directly
                if item.matter_id not in matters_map:
                    matters_map[item.matter_id] = []
                matters_map[item.matter_id].append(item)
            else:
                items_without_matters.append(item)

        enqueued_count = 0

        # Process each matter
        for matter_id, matter_items in matters_map.items():
            # matter_id is already composite hash, validate it
            if not validate_matter_id(matter_id):
                logger.error(f"[Matters] Invalid matter_id format in items: {matter_id}")
                continue

            # Filter out procedural matter types
            first_item = matter_items[0]
            matter_type = first_item.matter_type
            if matter_type and should_skip_matter(matter_type):
                logger.debug(
                    f"[Matters] Skipping procedural matter: {first_item.matter_file or matter_id} ({matter_type})"
                )
                continue

            # Query ALL items across ALL meetings for this matter (by composite ID)
            all_items_for_matter = self._get_all_items_for_matter(matter_id)

            if not all_items_for_matter:
                logger.warning(f"[Matters] No items found for matter {first_item.matter_file or matter_id}")
                continue

            # Check if matter already processed
            existing_matter = self.get_matter(matter_id)

            if existing_matter and existing_matter.canonical_summary:
                # Matter exists - check if attachments changed
                # Use first item's attachments as representative (should be same across items)
                current_hash = hash_attachments(all_items_for_matter[0].attachments)

                stored_hash = existing_matter.metadata.get("attachment_hash") if existing_matter.metadata else None

                # Also check if any items are missing summaries (e.g., user deleted for reprocessing)
                items_missing_summary = [item for item in all_items_for_matter if not item.summary]

                if stored_hash == current_hash and not items_missing_summary:
                    # Unchanged AND all items have summaries - copy canonical summary to ALL items
                    self._apply_canonical_summary(all_items_for_matter, existing_matter)
                    logger.debug(
                        f"[Matters] Reusing canonical summary for {first_item.matter_file or matter_id} "
                        f"({len(all_items_for_matter)} items across all meetings)"
                    )
                    continue  # Skip enqueue
                elif items_missing_summary:
                    logger.info(
                        f"[Matters] Re-enqueueing {first_item.matter_file or matter_id}: "
                        f"{len(items_missing_summary)} items missing summaries (manual deletion detected)"
                    )

            # New or changed - enqueue matter for processing
            # Include ALL item IDs across ALL meetings
            queue_id = self.enqueue_matter_job(
                matter_id=matter_id,
                meeting_id=meeting.id,
                item_ids=[item.id for item in all_items_for_matter],
                banana=banana,
                priority=priority,
            )
            # Only count if actually enqueued (not -1 for already pending/processing)
            if queue_id != -1:
                enqueued_count += 1
                logger.info(
                    f"[Matters] Enqueued {first_item.matter_file or matter_id} with {len(all_items_for_matter)} items "
                    f"across {len(set(item.meeting_id for item in all_items_for_matter))} meetings"
                )

        # Items without matters - enqueue as item-level batch (fallback)
        if items_without_matters:
            queue_id = self.enqueue_meeting_job(
                meeting_id=meeting.id,
                source_url=f"items://{meeting.id}",
                banana=banana,
                priority=priority,
            )
            # Only count if actually enqueued (not -1 for already pending/processing)
            if queue_id != -1:
                enqueued_count += 1

        return enqueued_count

    def _get_matter(self, matter_id: str) -> Optional[Dict[str, Any]]:
        """Get matter by ID for deduplication checks"""
        if self.conn is None:
            raise DatabaseConnectionError("Database connection not established")

        cursor = self.conn.execute(
            "SELECT * FROM city_matters WHERE id = ?", (matter_id,)
        )
        row = cursor.fetchone()
        if row:
            return dict(row)
        return None

    def _get_all_items_for_matter(self, matter_id: str) -> List[AgendaItem]:
        """Get ALL agenda items across ALL meetings for a given matter.

        Uses composite matter_id (FK to city_matters) for simple, fast lookup.

        Args:
            matter_id: Composite matter ID (e.g., "nashvilleTN_7a8f3b2c1d9e4f5a")

        Returns:
            List of ALL AgendaItem objects for this matter across all meetings
        """
        if self.conn is None:
            raise DatabaseConnectionError("Database connection not established")

        if not matter_id:
            return []

        # Simple FK lookup - matter_id is already composite hash
        cursor = self.conn.execute(
            """
            SELECT i.* FROM items i
            WHERE i.matter_id = ?
            ORDER BY i.meeting_id, i.sequence
            """,
            (matter_id,)
        )
        rows = cursor.fetchall()

        # Convert to AgendaItem objects
        items = []
        for row in rows:
            items.append(AgendaItem(
                id=row["id"],
                meeting_id=row["meeting_id"],
                title=row["title"],
                sequence=row["sequence"],
                attachments=json.loads(row["attachments"]) if row["attachments"] else [],
                summary=row["summary"],
                topics=json.loads(row["topics"]) if row["topics"] else None,
                matter_id=row["matter_id"],
                matter_file=row["matter_file"],
                matter_type=row["matter_type"],
                agenda_number=row["agenda_number"],
                sponsors=json.loads(row["sponsors"]) if row["sponsors"] else None,
            ))

        return items

    def _apply_canonical_summary(
        self, items: List[AgendaItem], matter: Matter
    ):
        """Apply canonical summary from matter to all items"""
        if self.conn is None:
            raise DatabaseConnectionError("Database connection not established")

        canonical_summary = matter.canonical_summary
        canonical_topics_json = json.dumps(matter.canonical_topics) if matter.canonical_topics else None

        for item in items:
            self.conn.execute(
                """
                UPDATE items
                SET summary = ?, topics = ?
                WHERE id = ?
                """,
                (canonical_summary, canonical_topics_json, item.id),
            )

        self.conn.commit()

    def update_meeting_summary(
        self,
        meeting_id: str,
        summary: Optional[str],
        processing_method: str,
        processing_time: float,
        participation: Optional[Dict[str, Any]] = None,
        topics: Optional[List[str]] = None,
    ):
        """Update meeting with processed summary - delegates to MeetingRepository"""
        return self.meetings.update_meeting_summary(
            meeting_id, summary, processing_method, processing_time, participation, topics
        )

    def get_unprocessed_meetings(self, limit: int = 50) -> List[Meeting]:
        """Get meetings needing processing - delegates to MeetingRepository"""
        return self.meetings.get_unprocessed_meetings(limit)

    def get_meeting_by_packet_url(self, packet_url: str) -> Optional[Meeting]:
        """Get meeting by packet URL - delegates to MeetingRepository"""
        return self.meetings.get_meeting_by_packet_url(packet_url)

    # ========== Agenda Item Operations (delegate to ItemRepository) ==========

    def store_agenda_items(self, meeting_id: str, items: List[AgendaItem], defer_commit: bool = False) -> int:
        """Store agenda items - delegates to ItemRepository"""
        return self.items.store_agenda_items(meeting_id, items, defer_commit=defer_commit)

    def get_agenda_items(self, meeting_id: str, load_matters: bool = False) -> List[AgendaItem]:
        """Get agenda items for meeting - delegates to ItemRepository

        Args:
            meeting_id: The meeting ID
            load_matters: If True, eagerly load Matter objects for items (default: False)
        """
        return self.items.get_agenda_items(meeting_id, load_matters=load_matters)

    def update_agenda_item(self, item_id: str, summary: str, topics: List[str]) -> None:
        """Update agenda item with summary - delegates to ItemRepository"""
        return self.items.update_agenda_item(item_id, summary, topics)

    def get_agenda_item(self, item_id: str) -> Optional[AgendaItem]:
        """Get single agenda item by ID"""
        items = self.get_agenda_items_by_ids([item_id])
        return items[0] if items else None

    def get_agenda_items_by_ids(self, item_ids: List[str]) -> List[AgendaItem]:
        """Get multiple agenda items by IDs"""
        if not item_ids:
            return []

        placeholders = ",".join("?" * len(item_ids))
        rows = self.conn.execute(
            f"SELECT * FROM items WHERE id IN ({placeholders})",
            item_ids
        ).fetchall()

        return [AgendaItem.from_db_row(row) for row in rows]

    # ========== Matter Operations (delegate to MatterRepository) ==========

    def store_matter(self, matter: Matter, defer_commit: bool = False) -> bool:
        """Store or update a matter - delegates to MatterRepository"""
        return self.matters.store_matter(matter, defer_commit=defer_commit)

    def get_matter(self, matter_id: str) -> Optional[Matter]:
        """Get matter by composite ID - delegates to MatterRepository"""
        return self.matters.get_matter(matter_id)

    def get_matters_by_city(self, banana: str, include_processed: bool = True) -> List[Matter]:
        """Get all matters for a city - delegates to MatterRepository"""
        return self.matters.get_matters_by_city(banana, include_processed)

    def get_matter_by_keys(
        self, banana: str, matter_file: Optional[str] = None, matter_id: Optional[str] = None
    ) -> Optional[Matter]:
        """Get matter by matter_file or matter_id - delegates to MatterRepository"""
        return self.matters.get_matter_by_keys(banana, matter_file, matter_id)

    def update_matter_summary(
        self, matter_id: str, canonical_summary: str, canonical_topics: List[str], attachment_hash: str
    ) -> None:
        """Update matter canonical summary - delegates to MatterRepository"""
        return self.matters.update_matter_summary(matter_id, canonical_summary, canonical_topics, attachment_hash)

    def search_matters(
        self,
        search_term: str,
        banana: Optional[str] = None,
        state: Optional[str] = None,
        case_sensitive: bool = False
    ) -> List[Matter]:
        """Search matters by canonical summary text - delegates to MatterRepository"""
        return self.matters.search_matters(search_term, banana, state, case_sensitive)

    @staticmethod
    def generate_matter_id(
        banana: str,
        matter_file: Optional[str] = None,
        matter_id: Optional[str] = None
    ) -> str:
        """Generate deterministic matter ID from identifiers

        Convenience method for ID generation. Uses SHA256 hashing for determinism.

        Args:
            banana: City identifier
            matter_file: Public matter file (25-1234, BL2025-1098)
            matter_id: Backend matter ID (UUID, numeric)

        Returns:
            Composite ID: {banana}_{hash}

        Example:
            >>> UnifiedDatabase.generate_matter_id("nashvilleTN", matter_file="BL2025-1098")
            'nashvilleTN_7a8f3b2c1d9e4f5a'
        """
        from database.id_generation import generate_matter_id
        return generate_matter_id(banana, matter_file, matter_id)

    @staticmethod
    def validate_matter_id(matter_id: str) -> bool:
        """Validate matter ID format

        Args:
            matter_id: Matter ID to validate

        Returns:
            True if valid format, False otherwise
        """
        from database.id_generation import validate_matter_id
        return validate_matter_id(matter_id)

    # ========== Processing Queue Operations (delegate to QueueRepository) ==========

    def enqueue_for_processing(
        self,
        source_url: str,
        meeting_id: str,
        banana: str,
        priority: int = 0,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> int:
        """Enqueue item for processing - delegates to QueueRepository

        Args:
            source_url: agenda_url, packet_url, or items:// synthetic URL
        """
        return self.queue.enqueue_for_processing(source_url, meeting_id, banana, priority, metadata)

    def enqueue_meeting_job(
        self,
        meeting_id: str,
        source_url: str,
        banana: str,
        priority: int = 0,
    ) -> int:
        """Enqueue typed meeting job - delegates to QueueRepository"""
        return self.queue.enqueue_meeting_job(meeting_id, source_url, banana, priority)

    def enqueue_matter_job(
        self,
        matter_id: str,
        meeting_id: str,
        item_ids: List[str],
        banana: str,
        priority: int = 0,
    ) -> int:
        """Enqueue typed matter job - delegates to QueueRepository"""
        return self.queue.enqueue_matter_job(matter_id, meeting_id, item_ids, banana, priority)

    def get_next_for_processing(
        self, banana: Optional[str] = None
    ):
        """Get next typed job from queue - delegates to QueueRepository

        Returns:
            QueueJob with typed payload, or None if queue empty
        """
        return self.queue.get_next_for_processing(banana)

    def mark_processing_complete(self, queue_id: int) -> None:
        """Mark queue item as completed - delegates to QueueRepository"""
        return self.queue.mark_processing_complete(queue_id)

    def mark_processing_failed(
        self, queue_id: int, error_message: str, increment_retry: bool = True
    ) -> None:
        """Mark queue item as failed - delegates to QueueRepository"""
        return self.queue.mark_processing_failed(queue_id, error_message, increment_retry)

    def reset_failed_items(self, max_retries: int = 3) -> int:
        """Reset failed items - delegates to QueueRepository"""
        return self.queue.reset_failed_items(max_retries)

    def clear_queue(self) -> Dict[str, int]:
        """Clear entire queue - delegates to QueueRepository"""
        return self.queue.clear_queue()

    def get_queue_stats(self) -> Dict[str, Any]:
        """Get queue statistics - delegates to QueueRepository"""
        return self.queue.get_queue_stats()

    def get_dead_letter_jobs(self, limit: int = 100) -> List[Dict[str, Any]]:
        """Get dead letter queue jobs - delegates to QueueRepository"""
        return self.queue.get_dead_letter_jobs(limit)

    def bulk_enqueue_unprocessed_meetings(self, limit: Optional[int] = None) -> int:
        """Bulk enqueue meetings - delegates to QueueRepository"""
        return self.queue.bulk_enqueue_unprocessed_meetings(limit)

    # ========== Search & Discovery Operations (delegate to SearchRepository) ==========

    def get_random_meeting_with_items(self) -> Optional[Dict[str, Any]]:
        """Get random meeting with items - delegates to SearchRepository"""
        return self.search.get_random_meeting_with_items()

    def search_meetings_by_topic(
        self, topic: str, city_banana: Optional[str] = None, limit: int = 50
    ) -> List[Meeting]:
        """Search meetings by topic - delegates to SearchRepository"""
        return self.search.search_meetings_by_topic(topic, city_banana, limit)

    def get_items_by_topic(self, meeting_id: str, topic: str) -> List[AgendaItem]:
        """Get items matching topic - delegates to SearchRepository"""
        return self.search.get_items_by_topic(meeting_id, topic)

    def get_popular_topics(self, limit: int = 20) -> List[Dict[str, Any]]:
        """Get popular topics - delegates to SearchRepository"""
        return self.search.get_popular_topics(limit)

    def get_cached_summary(self, packet_url: str | List[str]) -> Optional[Meeting]:
        """Get cached meeting summary - delegates to SearchRepository"""
        return self.search.get_cached_summary(packet_url)

    def store_processing_result(
        self, packet_url: str, processing_method: str, processing_time: float
    ):
        """Store processing result in cache - delegates to SearchRepository"""
        return self.search.store_processing_result(packet_url, processing_method, processing_time)

    def get_stats(self) -> Dict[str, Any]:
        """Get database statistics - delegates to SearchRepository"""
        return self.search.get_stats()

    def validate_matter_tracking(self, meeting_id: str) -> Dict[str, int]:
        """
        Validate matter tracking integrity for a meeting.

        Checks:
        1. FK integrity: items.matter_id → city_matters.id
        2. ID format: items.matter_id uses composite hash format
        3. Timeline: matter_appearances links exist

        Args:
            meeting_id: Meeting ID to validate

        Returns:
            Dict with validation stats
        """
        if self.conn is None:
            raise DatabaseConnectionError("Database connection not established")

        from database.id_generation import validate_matter_id

        # Check 1: FK integrity (items → city_matters)
        cursor = self.conn.execute("""
            SELECT COUNT(*) as orphaned_count
            FROM items i
            WHERE i.meeting_id = ?
              AND i.matter_id IS NOT NULL
              AND NOT EXISTS (SELECT 1 FROM city_matters cm WHERE cm.id = i.matter_id)
        """, (meeting_id,))
        orphaned_count = cursor.fetchone()[0]

        # Check 2: ID format validation
        cursor = self.conn.execute("""
            SELECT matter_id FROM items
            WHERE meeting_id = ? AND matter_id IS NOT NULL
        """, (meeting_id,))
        invalid_format_count = 0
        for row in cursor.fetchall():
            if not validate_matter_id(row[0]):
                invalid_format_count += 1
                logger.error(f"[Matters] Invalid matter_id format: {row[0]}")

        # Check 3: Timeline tracking (matter_appearances)
        cursor = self.conn.execute("""
            SELECT COUNT(*) as missing_appearances
            FROM items i
            WHERE i.meeting_id = ?
              AND i.matter_id IS NOT NULL
              AND NOT EXISTS (
                SELECT 1 FROM matter_appearances ma
                WHERE ma.item_id = i.id AND ma.meeting_id = ?
              )
        """, (meeting_id, meeting_id))
        missing_appearances = cursor.fetchone()[0]

        # Total matter-tracked items
        cursor = self.conn.execute("""
            SELECT COUNT(*) as total
            FROM items
            WHERE meeting_id = ? AND matter_id IS NOT NULL
        """, (meeting_id,))
        total_items_with_matter = cursor.fetchone()[0]

        # Report results
        if orphaned_count > 0 or invalid_format_count > 0 or missing_appearances > 0:
            logger.error(
                f"[Matters] VALIDATION FAILED for meeting {meeting_id}:\n"
                f"  - Orphaned items (no city_matters): {orphaned_count}\n"
                f"  - Invalid matter_id format: {invalid_format_count}\n"
                f"  - Missing matter_appearances: {missing_appearances}\n"
                f"  - Total items with matters: {total_items_with_matter}"
            )
        else:
            logger.debug(
                f"[Matters] Validation passed: all {total_items_with_matter} items valid"
            )

        return {
            'orphaned_count': orphaned_count,
            'invalid_format_count': invalid_format_count,
            'missing_appearances': missing_appearances,
            'total_items_with_matter': total_items_with_matter,
        }

    # ========== Utilities ==========

    def close(self):
        """Close database connection"""
        if self.conn:
            self.conn.close()
            logger.info("Database connection closed")

    def __enter__(self):
        """Context manager entry"""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit - ensures connection cleanup"""
        self.close()
        return False
