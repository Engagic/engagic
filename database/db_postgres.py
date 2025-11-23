"""PostgreSQL Database Layer with Repository Pattern

Clean architecture using async repositories for all data access.
Database class handles only orchestration and high-level operations.
"""

import asyncpg
import traceback
from typing import Optional, List, Dict, Any
from datetime import datetime
from pathlib import Path

from config import get_logger, config
from database.models import City, Meeting, AgendaItem
from database.repositories_async import (
    CityRepository,
    MeetingRepository,
    ItemRepository,
    MatterRepository,
    QueueRepository,
    SearchRepository,
)
from exceptions import DatabaseConnectionError, DatabaseError, ValidationError

logger = get_logger(__name__).bind(component="database_postgres")


class Database:
    """Async PostgreSQL database with repository pattern

    Repositories handle all CRUD operations.
    Database class provides orchestration for complex workflows.

    Architecture:
    - Connection pooling (asyncpg pool shared across all repositories)
    - Repository pattern (ItemRepository, MatterRepository, etc.)
    - Normalized topics (separate tables for topic filtering)
    - JSONB for complex data structures

    Usage:
        db = await Database.create()
        city = await db.cities.get_city("paloaltoCA")
        meetings = await db.meetings.get_meetings_for_city("paloaltoCA")
        await db.close()
    """

    pool: asyncpg.Pool

    # Repository attributes
    cities: CityRepository
    meetings: MeetingRepository
    items: ItemRepository
    matters: MatterRepository
    queue: QueueRepository
    search: SearchRepository

    def __init__(self, pool: asyncpg.Pool):
        """Initialize with connection pool and repositories

        Use Database.create() classmethod instead of direct instantiation.
        """
        self.pool = pool

        # Instantiate all repositories with shared pool
        self.cities = CityRepository(pool)
        self.meetings = MeetingRepository(pool)
        self.items = ItemRepository(pool)
        self.matters = MatterRepository(pool)
        self.queue = QueueRepository(pool)
        self.search = SearchRepository(pool)

        logger.info("database initialized with repositories", pool_size=f"{pool._minsize}-{pool._maxsize}")

    @classmethod
    async def create(
        cls,
        dsn: Optional[str] = None,
        min_size: int = 10,
        max_size: int = 100
    ) -> "Database":
        """Create database with connection pool

        Args:
            dsn: PostgreSQL connection string (defaults to config.get_postgres_dsn())
            min_size: Minimum pool size (default: 10)
            max_size: Maximum pool size (default: 100)

        Returns:
            Initialized Database instance

        Example:
            db = await Database.create()
            cities = await db.cities.get_all_cities()
            await db.close()
        """
        if dsn is None:
            dsn = config.get_postgres_dsn()

        try:
            pool = await asyncpg.create_pool(
                dsn,
                min_size=min_size,
                max_size=max_size,
                command_timeout=60,
            )
            logger.info("connection pool created", min_size=min_size, max_size=max_size)
            return cls(pool)
        except (asyncpg.PostgresError, OSError, ConnectionError) as e:
            # Connection-specific errors only - let programming errors fail loudly
            logger.error("failed to create connection pool", error=str(e))
            raise DatabaseConnectionError(f"Failed to connect to PostgreSQL: {e}")

    async def close(self):
        """Close connection pool"""
        await self.pool.close()
        logger.info("connection pool closed")

    async def init_schema(self):
        """Initialize database schema from schema_postgres.sql

        Creates all tables, indexes, and constraints.
        Safe to call multiple times (uses IF NOT EXISTS).
        """
        schema_path = Path(__file__).parent / "schema_postgres.sql"
        if not schema_path.exists():
            raise FileNotFoundError(f"Schema file not found: {schema_path}")

        schema_sql = schema_path.read_text()

        async with self.pool.acquire() as conn:
            await conn.execute(schema_sql)

        logger.info("schema initialized")

    # ==================
    # ORCHESTRATION METHODS
    # ==================

    async def store_meeting_from_sync(
        self,
        meeting_dict: Dict[str, Any],
        city: City
    ) -> tuple[Optional[Meeting], Dict[str, Any]]:
        """Transform vendor meeting dict -> validate -> store -> enqueue

        This is the primary method called by the fetcher after scraping.
        Orchestrates multiple repository operations in a coordinated workflow.

        Args:
            meeting_dict: Raw meeting dict from vendor adapter
            city: City object for this meeting

        Returns:
            Tuple of (stored Meeting object or None, stats dict)
        """
        stats = {
            'items_stored': 0,
            'items_skipped_procedural': 0,
            'matters_tracked': 0,
            'matters_duplicate': 0,
            'meetings_skipped': 0,
            'skip_reason': None,
            'skipped_title': None,
        }

        try:
            # Phase 1: Parse and validate
            meeting_date = self._parse_meeting_date(meeting_dict)
            meeting_id = meeting_dict.get("meeting_id")

            if not meeting_id or not meeting_id.strip():
                logger.error(
                    "adapter returned blank meeting_id",
                    city=city.banana,
                    meeting_title=meeting_dict.get('title', 'Unknown')
                )
                stats['meetings_skipped'] = 1
                stats['skip_reason'] = "missing_meeting_id"
                stats['skipped_title'] = meeting_dict.get("title", "Unknown")
                return None, stats

            # Phase 2: Create Meeting object
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
            existing_meeting = await self.meetings.get_meeting(meeting_obj.id)
            if existing_meeting and existing_meeting.summary:
                meeting_obj.summary = existing_meeting.summary
                meeting_obj.processing_status = existing_meeting.processing_status
                meeting_obj.processing_method = existing_meeting.processing_method
                meeting_obj.processing_time = existing_meeting.processing_time
                meeting_obj.topics = existing_meeting.topics
                logger.debug("preserved existing summary", title=meeting_obj.title)

            # Phase 3: Process agenda items (if present)
            agenda_items = []
            items_data = meeting_dict.get("items")
            if items_data:
                agenda_items = await self._process_agenda_items_async(
                    items_data, meeting_obj, stats
                )

            # Phase 4: Store meeting + items atomically
            async with self.pool.acquire() as conn:
                async with conn.transaction():
                    await self.meetings.store_meeting(meeting_obj)

                    if agenda_items:
                        stored_count = await self.items.store_agenda_items(meeting_obj.id, agenda_items)
                        stats['items_stored'] = stored_count

            # Phase 5: Enqueue for processing (if not already processed)
            await self._enqueue_if_needed_async(
                meeting_obj, meeting_date, agenda_items, items_data, stats
            )

            return meeting_obj, stats

        except (DatabaseError, ValidationError, ValueError) as e:
            # Business logic and data errors - log with traceback and re-raise
            logger.error(
                "error storing meeting",
                packet_url=meeting_dict.get('packet_url', 'unknown'),
                error=str(e),
                error_type=type(e).__name__,
                traceback=traceback.format_exc()
            )
            raise

    def _parse_meeting_date(self, meeting_dict: Dict[str, Any]) -> Optional[datetime]:
        """Parse date from adapter format, trying multiple formats"""
        meeting_date = None
        if meeting_dict.get("start"):
            date_str = meeting_dict["start"]
            for fmt in [
                None,  # ISO format via fromisoformat
                "%m/%d/%y",  # NovusAgenda: "11/05/25"
                "%Y-%m-%d",  # Standard: "2025-11-05"
                "%m/%d/%Y",  # US format: "11/05/2025"
            ]:
                try:
                    if fmt is None:
                        meeting_date = datetime.fromisoformat(
                            date_str.replace("Z", "+00:00")
                        )
                    else:
                        meeting_date = datetime.strptime(date_str, fmt)
                    break
                except ValueError:
                    continue

        return meeting_date

    async def _process_agenda_items_async(
        self,
        items_data: List[Dict[str, Any]],
        stored_meeting: Meeting,
        stats: Dict[str, Any]
    ) -> List[AgendaItem]:
        """Process agenda items: preserve summaries if already processed"""
        agenda_items = []

        # Build map of existing items to preserve summaries
        existing_items = await self.items.get_agenda_items(stored_meeting.id)
        existing_items_map = {item.id: item for item in existing_items}

        for item_data in items_data:
            item_id = f"{stored_meeting.id}_{item_data['item_id']}"

            # Parse attachments/sponsors
            item_attachments = item_data.get("attachments", [])
            sponsors = item_data.get("sponsors", [])

            agenda_item = AgendaItem(
                id=item_id,
                meeting_id=stored_meeting.id,
                title=item_data.get("title", ""),
                sequence=item_data.get("sequence", 0),
                attachments=item_attachments,
                attachment_hash=None,  # TODO: Compute hash for change detection
                matter_id=None,  # TODO: Matter tracking for PostgreSQL
                matter_file=item_data.get("matter_file"),
                matter_type=item_data.get("matter_type"),
                agenda_number=item_data.get("agenda_number"),
                sponsors=sponsors,
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

            agenda_items.append(agenda_item)

        return agenda_items

    async def _enqueue_if_needed_async(
        self,
        stored_meeting: Meeting,
        meeting_date: Optional[datetime],
        agenda_items: List[AgendaItem],
        items_data: Optional[List[Dict[str, Any]]],
        stats: Dict[str, Any]
    ):
        """Determine if meeting needs processing and enqueue appropriately"""
        has_items = bool(items_data)
        packet_url = stored_meeting.packet_url

        # Check if already processed
        skip_enqueue, skip_reason = self._should_skip_enqueue(
            agenda_items, stored_meeting, has_items
        )

        if skip_enqueue:
            logger.debug(
                "skipping enqueue",
                meeting_title=stored_meeting.title,
                reason=skip_reason
            )
            return

        if not (has_items or packet_url):
            logger.debug(
                "meeting has no agenda/packet/items - stored for display only",
                meeting_title=stored_meeting.title
            )
            return

        # Calculate priority based on meeting date proximity
        priority = self._calculate_priority_from_date(meeting_date)

        # Enqueue for processing
        source_url = stored_meeting.agenda_url or stored_meeting.packet_url or stored_meeting.id

        # Handle packet_url which can be str | List[str] (eScribe returns lists for multiple PDFs)
        if isinstance(source_url, list):
            if not source_url:
                logger.warning(
                    "empty packet_url list - using meeting ID",
                    meeting_id=stored_meeting.id
                )
                source_url = stored_meeting.id
            else:
                logger.debug(
                    "multiple packet URLs - using first for processing",
                    count=len(source_url),
                    meeting_id=stored_meeting.id
                )
                source_url = source_url[0]

        await self.queue.enqueue_job(
            source_url=source_url,
            job_type="meeting",
            payload={"meeting_id": stored_meeting.id, "banana": stored_meeting.banana},
            meeting_id=stored_meeting.id,
            banana=stored_meeting.banana,
            priority=priority,
        )

        logger.debug(
            "enqueued for processing",
            meeting_title=stored_meeting.title,
            priority=priority
        )

    def _should_skip_enqueue(
        self,
        agenda_items: List[AgendaItem],
        stored_meeting: Meeting,
        has_items: bool
    ) -> tuple[bool, Optional[str]]:
        """Determine if meeting should skip enqueueing (already processed)"""
        # Priority 1: Check for item-level summaries (GOLDEN PATH)
        if has_items and agenda_items:
            items_with_summaries = [item for item in agenda_items if item.summary]
            # Skip only if 100% complete
            if items_with_summaries and len(items_with_summaries) == len(agenda_items):
                return True, f"all {len(agenda_items)} items already have summaries"

        # Priority 2: Check for monolithic summary (fallback path)
        if stored_meeting.summary:
            return True, "meeting already has summary (monolithic)"

        return False, None

    def _calculate_priority_from_date(self, meeting_date: Optional[datetime]) -> int:
        """Calculate priority based on meeting date proximity"""
        if meeting_date:
            now = datetime.now(meeting_date.tzinfo) if meeting_date.tzinfo else datetime.now()
            days_from_now = (meeting_date - now).days
            days_distance = abs(days_from_now)
        else:
            days_distance = 999

        return max(0, 150 - days_distance)

    # ==================
    # MONITORING & STATS
    # ==================

    async def get_stats(self) -> dict:
        """Get database statistics for monitoring

        Returns:
            Dict with active_cities, total_meetings, summarized_meetings,
            pending_meetings, and summary_rate
        """
        async with self.pool.acquire() as conn:
            result = await conn.fetchrow("""
                SELECT
                    (SELECT COUNT(*) FROM cities WHERE status = 'active') as active_cities,
                    (SELECT COUNT(*) FROM meetings) as total_meetings,
                    (SELECT COUNT(*) FROM meetings WHERE summary IS NOT NULL) as summarized_meetings,
                    (SELECT COUNT(*) FROM meetings WHERE processing_status = 'pending') as pending_meetings
            """)

            stats = dict(result)

            # Calculate summary rate
            total = stats['total_meetings']
            summarized = stats['summarized_meetings']
            stats['summary_rate'] = f"{summarized / total * 100:.1f}%" if total > 0 else "0%"

            return stats

    # ==================
    # FACADE METHODS (Server API Convenience)
    # ==================

    async def get_city(
        self,
        banana: Optional[str] = None,
        name: Optional[str] = None,
        state: Optional[str] = None
    ) -> Optional[City]:
        """Get city by banana or name+state

        Facade method for server routes - delegates to CityRepository.
        """
        if banana:
            return await self.cities.get_city(banana)
        elif name and state:
            cities = await self.cities.get_cities(name=name, state=state, limit=1)
            return cities[0] if cities else None
        return None

    async def get_cities(
        self,
        state: Optional[str] = None,
        name: Optional[str] = None,
        vendor: Optional[str] = None,
        status: str = "active",
        limit: Optional[int] = None
    ) -> List[City]:
        """Get cities with optional filtering

        Facade method for server routes - delegates to CityRepository.
        """
        return await self.cities.get_cities(
            state=state,
            name=name,
            vendor=vendor,
            status=status,
            limit=limit
        )

    async def get_meeting(self, meeting_id: str) -> Optional[Meeting]:
        """Get meeting by ID

        Facade method for server routes - delegates to MeetingRepository.
        """
        return await self.meetings.get_meeting(meeting_id)

    async def get_meetings(
        self,
        bananas: Optional[List[str]] = None,
        limit: int = 50,
        exclude_cancelled: bool = False
    ) -> List[Meeting]:
        """Get meetings for multiple cities

        Facade method for server routes - delegates to MeetingRepository.
        """
        if not bananas:
            return await self.meetings.get_recent_meetings(limit=limit)

        all_meetings = []
        for banana in bananas:
            meetings = await self.meetings.get_meetings_for_city(banana, limit=limit)
            all_meetings.extend(meetings)

        # Sort by date descending and apply limit
        all_meetings.sort(key=lambda m: m.date if m.date else datetime.min, reverse=True)
        return all_meetings[:limit]

    async def get_agenda_items(
        self,
        meeting_id: str,
        load_matters: bool = False
    ) -> List[AgendaItem]:
        """Get agenda items for meeting

        Facade method for server routes - delegates to ItemRepository.
        """
        items = await self.items.get_agenda_items(meeting_id)

        if load_matters and items:
            # Load matter data for items that have matter_id
            for item in items:
                if item.matter_id:
                    matter = await self.matters.get_matter(item.matter_id)
                    if matter:
                        # Attach matter to item (extend model if needed)
                        item.matter = matter

        return items

    async def search_meetings_by_topic(
        self,
        topic: str,
        city_banana: Optional[str] = None,
        limit: int = 50
    ) -> List[Meeting]:
        """Search meetings by topic

        Facade method for server routes - delegates to SearchRepository.
        """
        return await self.search.search_meetings_by_topic(topic, city_banana, limit)

    async def get_popular_topics(self, limit: int = 20) -> List[dict]:
        """Get popular topics

        Facade method for server routes - delegates to SearchRepository.
        """
        return await self.search.get_popular_topics(limit)

    async def get_items_by_topic(
        self,
        meeting_id: str,
        topic: str
    ) -> List[AgendaItem]:
        """Get agenda items filtered by topic

        Facade method for server routes - delegates to ItemRepository.
        """
        return await self.items.get_items_by_topic(meeting_id, topic)

    async def get_random_meeting_with_items(self) -> Optional[Meeting]:
        """Get random meeting that has agenda items

        Facade method for server routes - delegates to MeetingRepository.
        """
        return await self.meetings.get_random_meeting_with_items()

    async def get_matter(self, matter_id: str) -> Optional[Any]:
        """Get matter by ID

        Facade method for server routes - delegates to MatterRepository.
        """
        return await self.matters.get_matter(matter_id)

    async def get_queue_stats(self) -> dict:
        """Get queue statistics

        Facade method for server routes - delegates to QueueRepository.
        """
        return await self.queue.get_queue_stats()

    async def get_city_meeting_stats(self, bananas: List[str]) -> dict:
        """Get meeting statistics for multiple cities

        Returns dict with city-level meeting counts and summary stats.
        """
        stats = {}

        for banana in bananas:
            async with self.pool.acquire() as conn:
                result = await conn.fetchrow("""
                    SELECT
                        COUNT(*) as total_meetings,
                        COUNT(CASE WHEN packet_url IS NOT NULL THEN 1 END) as meetings_with_packet,
                        COUNT(CASE WHEN summary IS NOT NULL THEN 1 END) as summarized_meetings
                    FROM meetings
                    WHERE banana = $1
                """, banana)

                stats[banana] = {
                    "total_meetings": result['total_meetings'],
                    "meetings_with_packet": result['meetings_with_packet'],
                    "summarized_meetings": result['summarized_meetings'],
                }

        return stats
