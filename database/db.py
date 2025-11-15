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
from database.services.meeting_ingestion import MeetingIngestionService
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

        # Initialize services
        self.ingestion = MeetingIngestionService(self)

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
        """Initialize unified database schema from external SQL file"""
        if self.conn is None:
            raise DatabaseConnectionError("Database connection not established")

        schema_path = Path(__file__).parent / "schema.sql"
        schema = schema_path.read_text()

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
    ) -> tuple[Optional[Meeting], Dict[str, Any]]:
        """
        Transform vendor meeting dict → validate → store → enqueue for processing

        Delegates to MeetingIngestionService for complex orchestration logic.

        Args:
            meeting_dict: Raw meeting dict from vendor adapter
            city: City object for this meeting

        Returns:
            Tuple of (stored Meeting object or None, stats dict)
        """
        return self.ingestion.ingest_meeting(meeting_dict, city)

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

            except Exception as e:
                logger.error(f"[Matters] Error tracking matter {matter_composite_id}: {e}")
                raise  # Propagate to outer transaction handler for rollback

        return stats

    def _create_matter_appearances(
        self,
        meeting: Meeting,
        agenda_items: List[AgendaItem],
        defer_commit: bool = False
    ) -> int:
        """
        Create matter_appearances AFTER items are stored.

        CRITICAL: Must be called AFTER store_agenda_items to avoid FK constraint failures
        (matter_appearances.item_id → items.id)
        """
        count = 0
        committee = meeting.title.split("-")[0].strip() if meeting.title else None

        for agenda_item in agenda_items:
            if not (agenda_item.matter_id or agenda_item.matter_file):
                continue

            matter_composite_id = agenda_item.matter_id
            if not matter_composite_id:
                continue

            try:
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
                count += 1
            except Exception as e:
                logger.error(f"[Matters] Failed to create appearance for {matter_composite_id}: {e}")
                raise

        if not defer_commit:
            self.conn.commit()

        return count

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
