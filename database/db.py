"""
Unified Database for Engagic - Repository Pattern

Consolidates locations.db, meetings.db, and analytics.db into a single database
with clean repository-based architecture.

This facade provides the same API as before but delegates to focused repositories:
- CityRepository: City and zipcode operations
- MeetingRepository: Meeting storage and retrieval
- ItemRepository: Agenda item operations
- QueueRepository: Processing queue management
- SearchRepository: Search, topics, cache, and stats
"""

import json
import logging
import sqlite3
from typing import Optional, List, Dict, Any
from datetime import datetime
from pathlib import Path

from database.models import City, Meeting, AgendaItem, DatabaseConnectionError
from database.repositories.cities import CityRepository
from database.repositories.meetings import MeetingRepository
from database.repositories.items import ItemRepository
from database.repositories.queue import QueueRepository
from database.repositories.search import SearchRepository

logger = logging.getLogger("engagic")


class UnifiedDatabase:
    """
    Single database interface for all Engagic data.
    Delegates to focused repositories for cleaner separation of concerns.
    """

    def __init__(self, db_path: str):
        """Initialize unified database connection and repositories"""
        self.db_path = db_path
        self.conn = None
        self._connect()
        self._init_schema()

        # Initialize repositories with shared connection
        self.cities = CityRepository(self.conn)
        self.meetings = MeetingRepository(self.conn)
        self.items = ItemRepository(self.conn)
        self.queue = QueueRepository(self.conn)
        self.search = SearchRepository(self.conn)

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

        -- Processing queue: Decoupled processing queue (agenda-first, item-level)
        CREATE TABLE IF NOT EXISTS queue (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source_url TEXT NOT NULL UNIQUE,
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

            # Create Meeting object
            meeting_obj = Meeting(
                id=meeting_dict.get("meeting_id", ""),
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
            if meeting_dict.get("items"):
                items = meeting_dict["items"]
                agenda_items = []
                procedural_items = []

                # Build map of existing items to preserve summaries
                existing_items = self.get_agenda_items(stored_meeting.id)
                existing_items_map = {item.id: item for item in existing_items}

                for item_data in items:
                    item_id = f"{stored_meeting.id}_{item_data['item_id']}"
                    item_title = item_data.get("title", "")
                    item_type = item_data.get("matter_type", "")

                    # Check if procedural (skip for processing but log)
                    if should_skip_procedural_item(item_title, item_type):
                        procedural_items.append(item_title[:50])
                        stats['items_skipped_procedural'] += 1
                        # Still store it, just mark it as skip
                        logger.info(f"[Items] Procedural (skipped): {item_title[:60]}")

                    agenda_item = AgendaItem(
                        id=item_id,
                        meeting_id=stored_meeting.id,
                        title=item_title,
                        sequence=item_data.get("sequence", 0),
                        attachments=item_data.get("attachments", []),
                        matter_id=item_data.get("matter_id"),
                        matter_file=item_data.get("matter_file"),
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
                    if agenda_item.matter_file or agenda_item.matter_id:
                        logger.info(
                            f"[Items] {item_title[:50]} | Matter: {agenda_item.matter_file or agenda_item.matter_id}"
                        )
                    else:
                        logger.info(f"[Items] {item_title[:50]}")

                    agenda_items.append(agenda_item)

                if agenda_items:
                    count = self.store_agenda_items(stored_meeting.id, agenda_items)
                    stats['items_stored'] = count
                    items_with_summaries = sum(1 for item in agenda_items if item.summary)

                    logger.info(
                        f"[Items] Stored {count} items ({stats['items_skipped_procedural']} procedural, "
                        f"{items_with_summaries} with preserved summaries)"
                    )

                    # Track matters in city_matters and matter_appearances tables
                    matters_stats = self._track_matters(stored_meeting, items, agenda_items)
                    stats['matters_tracked'] = matters_stats.get('tracked', 0)
                    stats['matters_duplicate'] = matters_stats.get('duplicate', 0)


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
                # Recent past + near future = HIGH priority
                # Far past + far future = LOW priority
                if meeting_date:
                    days_from_now = (meeting_date - datetime.now()).days
                    # Use absolute value: closer to today = higher priority
                    days_distance = abs(days_from_now)
                else:
                    days_distance = 999

                # Priority decreases as distance from today increases
                # Today: 150, Yesterday/Tomorrow: 149, 2 days: 148, etc.
                priority = max(0, 150 - days_distance)

                # Priority order: items:// (item-level) > packet_url (monolithic)
                # Note: agenda_url is NOT enqueued - it's already processed to extract items
                if has_items:
                    queue_url = f"items://{stored_meeting.id}"
                    processing_type = "item-level-batch"
                elif packet_url:
                    queue_url = packet_url
                    processing_type = "monolithic-packet"
                else:
                    # No items and no packet - nothing to process
                    logger.warning(
                        f"[DB] Meeting {stored_meeting.id} has no items or packet URL - skipping queue"
                    )
                    queue_url = None

                if queue_url:
                    self.enqueue_for_processing(
                        source_url=queue_url,
                        meeting_id=stored_meeting.id,
                        banana=city.banana,
                        priority=priority,
                        metadata={
                            "has_items": has_items,
                            "has_agenda": bool(agenda_url),
                            "has_packet": bool(packet_url),
                        },
                    )

                logger.debug(
                    f"Enqueued {processing_type} processing for {stored_meeting.title} (priority {priority})"
                )
            else:
                logger.debug(
                    f"Meeting {stored_meeting.title} has no agenda/packet/items - stored for display only"
                )

            return stored_meeting, stats

        except Exception as e:
            logger.error(
                f"Error storing meeting {meeting_dict.get('packet_url', 'unknown')}: {e}"
            )
            return None, stats

    def _track_matters(
        self, meeting: Meeting, items_data: List[Dict], agenda_items: List[AgendaItem]
    ) -> Dict[str, int]:
        """
        Track legislative matters across meetings for Intelligence Layer.

        For each agenda item with a matter_file:
        1. Upsert into city_matters (canonical bill representation)
        2. Create matter_appearance record (timeline tracking)

        Args:
            meeting: Stored Meeting object
            items_data: Raw item data from adapter (with sponsors, matter_type)
            agenda_items: Stored AgendaItem objects

        Returns:
            Dict with 'tracked' and 'duplicate' counts
        """
        stats = {'tracked': 0, 'duplicate': 0}

        if not items_data or not agenda_items:
            return stats

        # Build map from item_id to raw data for sponsor/type lookup
        items_map = {item["item_id"]: item for item in items_data}

        for agenda_item in agenda_items:
            # Skip items without any matter tracking
            if not agenda_item.matter_file and not agenda_item.matter_id:
                continue

            # Get raw item data for sponsors and matter_type
            item_id_short = agenda_item.id.split("_", 1)[1]  # Remove meeting_id prefix
            raw_item = items_map.get(item_id_short, {})
            sponsors = raw_item.get("sponsors", [])
            matter_type = raw_item.get("matter_type")

            # Build matter ID (prefer matter_file for Legistar, fallback to matter_id for PrimeGov)
            matter_key = agenda_item.matter_file or agenda_item.matter_id
            matter_id = f"{meeting.banana}_{matter_key}"

            try:
                # Check if matter exists
                existing = self.conn.execute(
                    "SELECT * FROM city_matters WHERE id = ?", (matter_id,)
                ).fetchone()

                if existing:
                    # Update last_seen and appearance_count
                    self.conn.execute(
                        """
                        UPDATE city_matters
                        SET last_seen = ?,
                            appearance_count = appearance_count + 1,
                            updated_at = CURRENT_TIMESTAMP
                        WHERE id = ?
                    """,
                        (meeting.date, matter_id),
                    )
                else:
                    # Insert new matter
                    self.conn.execute(
                        """
                        INSERT INTO city_matters (
                            id, banana, matter_id, matter_file, matter_type,
                            title, sponsors, first_seen, last_seen
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                        (
                            matter_id,
                            meeting.banana,
                            agenda_item.matter_id,
                            agenda_item.matter_file,
                            matter_type,
                            agenda_item.title,
                            json.dumps(sponsors) if sponsors else None,
                            meeting.date,
                            meeting.date,
                        ),
                    )

                # Create matter_appearance record
                # Extract committee from meeting title
                committee = meeting.title.split("-")[0].strip() if meeting.title else None

                self.conn.execute(
                    """
                    INSERT OR IGNORE INTO matter_appearances (
                        matter_id, meeting_id, item_id, appeared_at,
                        committee, sequence
                    ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                    (
                        matter_id,
                        meeting.id,
                        agenda_item.id,
                        meeting.date,
                        committee,
                        agenda_item.sequence,
                    ),
                )

                self.conn.commit()
                if existing:
                    stats['duplicate'] += 1
                    logger.info(f"[Matters] Duplicate: {matter_key} ({matter_type})")
                else:
                    stats['tracked'] += 1
                    logger.info(f"[Matters] New: {matter_key} ({matter_type}) - {len(sponsors)} sponsors")

            except Exception as e:
                logger.error(f"[Matters] Error tracking matter {matter_id}: {e}")
                continue

        return stats

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

    def store_agenda_items(self, meeting_id: str, items: List[AgendaItem]) -> int:
        """Store agenda items - delegates to ItemRepository"""
        return self.items.store_agenda_items(meeting_id, items)

    def get_agenda_items(self, meeting_id: str) -> List[AgendaItem]:
        """Get agenda items for meeting - delegates to ItemRepository"""
        return self.items.get_agenda_items(meeting_id)

    def update_agenda_item(self, item_id: str, summary: str, topics: List[str]) -> None:
        """Update agenda item with summary - delegates to ItemRepository"""
        return self.items.update_agenda_item(item_id, summary, topics)

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

    def get_next_for_processing(
        self, banana: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """Get next item from queue - delegates to QueueRepository"""
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

    # ========== Utilities ==========

    def close(self):
        """Close database connection"""
        if self.conn:
            self.conn.close()
            logger.info("Database connection closed")
