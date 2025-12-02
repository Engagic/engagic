"""PostgreSQL Database Layer with Repository Pattern

Clean architecture using async repositories for all data access.
Database class handles only orchestration and high-level operations.
"""

import asyncpg
import json
import traceback
from typing import Optional, List, Dict, Any
from datetime import datetime
from pathlib import Path

from config import get_logger, config
from database.id_generation import generate_matter_id
from database.models import City, Meeting, AgendaItem, Matter, MatterMetadata, AttachmentInfo
from database.repositories_async import (
    CityRepository,
    CommitteeRepository,
    CouncilMemberRepository,
    MeetingRepository,
    ItemRepository,
    MatterRepository,
    QueueRepository,
    SearchRepository,
)
from database.repositories_async.engagement import EngagementRepository
from database.repositories_async.feedback import FeedbackRepository
from database.repositories_async.userland import UserlandRepository
from database.vote_utils import compute_vote_tally, determine_vote_outcome
from exceptions import DatabaseConnectionError, DatabaseError, ValidationError
from pipeline.utils import hash_attachments

logger = get_logger(__name__).bind(component="database_postgres")


def _jsonb_encoder(obj):
    """JSONB encoder with automatic Pydantic model serialization.

    Handles:
    - Native Python types (dict, list, str, int, float, bool, None)
    - Pydantic models (via model_dump())
    - Nested structures containing Pydantic models

    This completes the automatic JSONB serialization migration.
    See database/ASYNCPG_JSONB_HANDLING.md for details.
    """
    def default(o):
        if hasattr(o, 'model_dump'):
            return o.model_dump()
        raise TypeError(f"Object of type {type(o).__name__} is not JSON serializable")

    return json.dumps(obj, default=default)


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
    council_members: CouncilMemberRepository
    meetings: MeetingRepository
    items: ItemRepository
    matters: MatterRepository
    queue: QueueRepository
    search: SearchRepository
    userland: UserlandRepository

    def __init__(self, pool: asyncpg.Pool):
        """Initialize with connection pool and repositories

        Use Database.create() classmethod instead of direct instantiation.
        """
        self.pool = pool

        # Instantiate all repositories with shared pool
        self.cities = CityRepository(pool)
        self.committees = CommitteeRepository(pool)
        self.council_members = CouncilMemberRepository(pool)
        self.meetings = MeetingRepository(pool)
        self.items = ItemRepository(pool)
        self.matters = MatterRepository(pool)
        self.queue = QueueRepository(pool)
        self.search = SearchRepository(pool)
        self.userland = UserlandRepository(pool)
        self.engagement = EngagementRepository(pool)
        self.feedback = FeedbackRepository(pool)

        logger.info("database initialized with repositories", pool_size=f"{pool._minsize}-{pool._maxsize}")

    @classmethod
    async def create(
        cls,
        dsn: Optional[str] = None,
        min_size: int = config.POSTGRES_POOL_MIN_SIZE,
        max_size: int = config.POSTGRES_POOL_MAX_SIZE
    ) -> "Database":
        """Create database with connection pool

        Args:
            dsn: PostgreSQL connection string (defaults to config.get_postgres_dsn())
            min_size: Minimum pool size (default: config.POSTGRES_POOL_MIN_SIZE)
            max_size: Maximum pool size (default: config.POSTGRES_POOL_MAX_SIZE)

        Returns:
            Initialized Database instance

        Example:
            db = await Database.create()
            cities = await db.cities.get_all_cities()
            await db.close()
        """
        if dsn is None:
            dsn = config.get_postgres_dsn()

        async def init_connection(conn):
            """Initialize connection with JSONB codec for automatic serialization"""
            await conn.set_type_codec(
                'jsonb',
                encoder=_jsonb_encoder,
                decoder=json.loads,
                schema='pg_catalog'
            )

        try:
            pool = await asyncpg.create_pool(
                dsn,
                min_size=min_size,
                max_size=max_size,
                command_timeout=60,
                init=init_connection,
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
        """Initialize database schema from SQL files

        Loads both main schema (public) and userland schema.
        Creates all tables, indexes, and constraints.
        Safe to call multiple times (uses IF NOT EXISTS).
        """
        # Load main schema (public)
        schema_path = Path(__file__).parent / "schema_postgres.sql"
        if not schema_path.exists():
            raise FileNotFoundError(f"Schema file not found: {schema_path}")

        schema_sql = schema_path.read_text()

        async with self.pool.acquire() as conn:
            await conn.execute(schema_sql)

        logger.info("main schema initialized")

        # Load userland schema (authentication, alerts)
        userland_schema_path = Path(__file__).parent / "schema_userland.sql"
        if not userland_schema_path.exists():
            raise FileNotFoundError(f"Userland schema file not found: {userland_schema_path}")

        userland_schema_sql = userland_schema_path.read_text()

        async with self.pool.acquire() as conn:
            await conn.execute(userland_schema_sql)

        logger.info("userland schema initialized")

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

            agenda_items = []
            items_data = meeting_dict.get("items")
            if items_data:
                agenda_items = await self._process_agenda_items_async(
                    items_data, meeting_obj, stats
                )

            async with self.pool.acquire() as conn:
                async with conn.transaction():
                    # 1. Store meeting
                    await self.meetings.store_meeting(meeting_obj)

                    if agenda_items:
                        # 2. Track matters (creates/updates city_matters records)
                        matters_stats = await self._track_matters_async(
                            meeting_obj, items_data or [], agenda_items
                        )
                        stats['matters_tracked'] = matters_stats.get('tracked', 0)
                        stats['matters_duplicate'] = matters_stats.get('duplicate', 0)
                        stats['items_skipped_procedural'] = matters_stats.get('skipped_procedural', 0)

                        # 3. Store items (FK targets exist now)
                        stored_count = await self.items.store_agenda_items(meeting_obj.id, agenda_items)
                        stats['items_stored'] = stored_count

                        # 4. Create matter appearances (timeline tracking)
                        appearances_count = await self._create_matter_appearances_async(
                            meeting_obj, agenda_items
                        )
                        stats['appearances_created'] = appearances_count

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
        """Process agenda items: preserve summaries if already processed

        NOTE: Does NOT create matters - that's handled by _track_matters_async
        """
        agenda_items = []

        existing_items = await self.items.get_agenda_items(stored_meeting.id)
        existing_items_map = {item.id: item for item in existing_items}

        for item_data in items_data:
            item_id = f"{stored_meeting.id}_{item_data['item_id']}"

            # BOUNDARY: Convert raw dicts to Pydantic models
            # All downstream code can trust AttachmentInfo objects
            raw_attachments = item_data.get("attachments", [])
            item_attachments = [AttachmentInfo(**att) for att in raw_attachments] if raw_attachments else []
            sponsors = item_data.get("sponsors", [])

            attachment_hash = hash_attachments(item_attachments) if item_attachments else None

            matter_file = item_data.get("matter_file")
            matter_id_vendor = item_data.get("matter_id")
            title = item_data.get("title", "")

            matter_id = None
            if matter_file or matter_id_vendor or title:
                matter_id = generate_matter_id(
                    banana=stored_meeting.banana,
                    matter_file=matter_file,
                    matter_id=matter_id_vendor,
                    title=title
                )

            agenda_item = AgendaItem(
                id=item_id,
                meeting_id=stored_meeting.id,
                title=title,
                sequence=item_data.get("sequence", 0),
                attachments=item_attachments,
                attachment_hash=attachment_hash,
                matter_id=matter_id,
                matter_file=matter_file,
                matter_type=item_data.get("matter_type"),
                agenda_number=item_data.get("agenda_number"),
                sponsors=sponsors,
                summary=None,
                topics=None,
            )

            if item_id in existing_items_map:
                existing_item = existing_items_map[item_id]
                if existing_item.summary:
                    agenda_item.summary = existing_item.summary
                if existing_item.topics:
                    agenda_item.topics = existing_item.topics

            agenda_items.append(agenda_item)

        return agenda_items

    async def _track_matters_async(
        self,
        meeting: Meeting,
        items_data: List[Dict[str, Any]],
        agenda_items: List[AgendaItem]
    ) -> Dict[str, int]:
        """Track legislative matters across meetings (Matters-First Architecture)

        For each agenda item with a matter_file:
        1. Create/update Matter object with attachments
        2. Store in city_matters table via MatterRepository
        3. Update appearance tracking

        Args:
            meeting: Stored Meeting object
            items_data: Raw item data from adapter (with sponsors, matter_type)
            agenda_items: Stored AgendaItem objects

        Returns:
            Dict with 'tracked', 'duplicate', and 'skipped_procedural' counts
        """
        from vendors.utils.item_filters import should_skip_matter

        stats = {'tracked': 0, 'duplicate': 0, 'skipped_procedural': 0}

        if not items_data or not agenda_items:
            return stats

        # Build map from item_id to raw data for sponsor/type lookup
        items_map = {item["item_id"]: item for item in items_data}

        for agenda_item in agenda_items:
            # Skip items without matter tracking
            if not agenda_item.matter_id:
                continue

            # Defensive validation
            from database.id_generation import validate_matter_id
            if not validate_matter_id(agenda_item.matter_id):
                logger.error(
                    "invalid matter_id format",
                    item_id=agenda_item.id,
                    matter_id=agenda_item.matter_id
                )
                continue

            matter_composite_id = agenda_item.matter_id

            # Get raw vendor data for storing in city_matters table
            item_id_short = agenda_item.id.rsplit("_", 1)[1]
            raw_item = items_map.get(item_id_short, {})
            sponsors = raw_item.get("sponsors", [])
            matter_type = raw_item.get("matter_type")
            raw_vendor_matter_id = raw_item.get("matter_id")

            # Skip procedural matter types
            if matter_type and should_skip_matter(matter_type):
                stats['skipped_procedural'] += 1
                # Clear FK reference since we're not creating the matter record
                agenda_item.matter_id = None
                logger.debug(
                    "skipping procedural matter",
                    matter=agenda_item.matter_file or raw_vendor_matter_id,
                    matter_type=matter_type
                )
                continue

            try:
                # Check if matter exists
                existing_matter = await self.matters.get_matter(matter_composite_id)

                # Compute attachment hash for deduplication
                attachment_hash = hash_attachments(agenda_item.attachments or [])

                if existing_matter:
                    # Check if this meeting_id is already counted for this matter
                    appearance_exists = await self.matters.check_appearance_exists(
                        matter_composite_id, meeting.id
                    )

                    # Update last_seen and appearance_count
                    await self.matters.update_matter_tracking(
                        matter_id=matter_composite_id,
                        meeting_date=meeting.date,  # Pass datetime directly
                        attachments=agenda_item.attachments,
                        attachment_hash=attachment_hash,
                        increment_appearance_count=not appearance_exists
                    )
                    stats['duplicate'] += 1

                    # Only log interesting cases (new appearances), skip reprocessing noise
                    if not appearance_exists:
                        matter_display = agenda_item.matter_file or raw_vendor_matter_id
                        if matter_display:  # Skip items without matter identifiers
                            logger.info(
                                "matter new appearance",
                                matter=matter_display,
                                matter_type=matter_type
                            )
                else:
                    # Guard: Skip matter creation if no identifiers available
                    # At least one of matter_file, raw_vendor_matter_id, or title must exist
                    if not agenda_item.matter_file and not raw_vendor_matter_id and not agenda_item.title:
                        logger.debug(
                            "skipping matter - no identifiers",
                            item_id=agenda_item.id,
                            matter_composite_id=matter_composite_id
                        )
                        continue

                    # Create new Matter object
                    matter_obj = Matter(
                        id=matter_composite_id,
                        banana=meeting.banana,
                        matter_id=raw_vendor_matter_id,
                        matter_file=agenda_item.matter_file,
                        matter_type=matter_type,
                        title=agenda_item.title,
                        sponsors=sponsors,
                        canonical_summary=None,
                        canonical_topics=None,
                        attachments=agenda_item.attachments,
                        metadata=MatterMetadata(attachment_hash=attachment_hash),
                        first_seen=meeting.date,
                        last_seen=meeting.date,
                        appearance_count=1,
                    )

                    await self.matters.store_matter(matter_obj)
                    stats['tracked'] += 1

                    # Only log if we have a displayable matter identifier
                    matter_display = agenda_item.matter_file or raw_vendor_matter_id
                    if matter_display:
                        logger.info(
                            "new matter tracked",
                            matter=matter_display,
                            matter_type=matter_type,
                            sponsor_count=len(sponsors)
                        )

                    # Link sponsors to matter (normalize JSONB array into relational table)
                    if sponsors:
                        await self.council_members.link_sponsors_to_matter(
                            banana=meeting.banana,
                            matter_id=matter_composite_id,
                            sponsor_names=sponsors,
                            appeared_at=meeting.date,
                        )

                # Record votes for this matter/meeting (both new and existing matters)
                votes = raw_item.get("votes", [])
                if votes:
                    await self.council_members.record_votes_for_matter(
                        banana=meeting.banana,
                        matter_id=matter_composite_id,
                        meeting_id=meeting.id,
                        votes=votes,
                        vote_date=meeting.date,
                    )

                    # Compute vote tally and outcome for matter_appearances
                    vote_tally = compute_vote_tally(votes)
                    vote_outcome = determine_vote_outcome(vote_tally)

                    # Update matter_appearances with outcome (closed loop tracking)
                    await self.matters.update_appearance_outcome(
                        matter_id=matter_composite_id,
                        meeting_id=meeting.id,
                        item_id=agenda_item.id,
                        vote_outcome=vote_outcome,
                        vote_tally=vote_tally,
                    )

                    logger.debug(
                        "recorded vote outcome",
                        matter_id=matter_composite_id,
                        outcome=vote_outcome,
                        tally=vote_tally,
                    )

            except Exception as e:
                logger.error(
                    "error tracking matter",
                    matter_id=matter_composite_id,
                    error=str(e),
                    error_type=type(e).__name__
                )
                raise

        return stats

    async def _create_matter_appearances_async(
        self,
        meeting: Meeting,
        agenda_items: List[AgendaItem]
    ) -> int:
        """Create matter_appearances after items are stored

        CRITICAL: Must be called AFTER store_agenda_items to avoid FK constraint failures

        Args:
            meeting: Stored Meeting object
            agenda_items: List of stored agenda items

        Returns:
            Number of appearances created
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
                await self.matters.create_appearance(
                    matter_id=matter_composite_id,
                    meeting_id=meeting.id,
                    item_id=agenda_item.id,
                    appeared_at=meeting.date,  # Pass datetime directly, not ISO string
                    committee=committee,
                    sequence=agenda_item.sequence
                )
                count += 1
            except Exception as e:
                logger.error(
                    "failed to create appearance for matter",
                    matter_id=matter_composite_id,
                    error=str(e),
                    error_type=type(e).__name__
                )
                raise

        return count

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
            payload={"meeting_id": stored_meeting.id, "source_url": source_url},
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
        state: Optional[str] = None,
        zipcode: Optional[str] = None
    ) -> Optional[City]:
        """Get city by banana, name+state, or zipcode

        Facade method for server routes - delegates to CityRepository.
        """
        if banana:
            return await self.cities.get_city(banana)
        elif zipcode:
            return await self.cities.get_city_by_zipcode(zipcode)
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
        limit: Optional[int] = None,
        include_zipcodes: bool = False,
    ) -> List[City]:
        """Get cities with optional filtering

        Facade method for server routes - delegates to CityRepository.

        Args:
            include_zipcodes: If True, fetch zipcodes (N+1). Default False for
                             performance in search contexts where zipcodes unused.
        """
        return await self.cities.get_cities(
            state=state,
            name=name,
            vendor=vendor,
            status=status,
            limit=limit,
            include_zipcodes=include_zipcodes,
        )

    async def get_city_names(self, status: str = "active") -> List[str]:
        """Get city names for fuzzy matching (lightweight, no N+1)

        Facade method for search service - delegates to CityRepository.
        """
        return await self.cities.get_city_names(status=status)

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
        For batch loading across multiple meetings, use get_items_for_meetings().
        """
        items = await self.items.get_agenda_items(meeting_id)

        if load_matters and items:
            # Batch load matters instead of N+1
            matter_ids = [item.matter_id for item in items if item.matter_id]
            if matter_ids:
                matters = await self.matters.get_matters_batch(matter_ids)
                for item in items:
                    if item.matter_id and item.matter_id in matters:
                        item.matter = matters[item.matter_id]

        return items

    async def get_items_for_meetings(
        self,
        meeting_ids: List[str],
        load_matters: bool = False
    ) -> Dict[str, List[AgendaItem]]:
        """Batch fetch items for multiple meetings - eliminates N+1

        This is the preferred method for search results where you have
        multiple meetings and need their items. Uses only 4-5 queries total
        instead of N*M queries.

        Args:
            meeting_ids: List of meeting identifiers
            load_matters: If True, batch load Matter objects for all items

        Returns:
            Dict mapping meeting_id to list of AgendaItem objects
        """
        if not meeting_ids:
            return {}

        # Batch fetch items (1 query for items, 1 for topics)
        items_by_meeting = await self.items.get_items_for_meetings(meeting_ids)

        if load_matters:
            # Collect all matter_ids across all items
            all_matter_ids = []
            for items in items_by_meeting.values():
                for item in items:
                    if item.matter_id:
                        all_matter_ids.append(item.matter_id)

            # Batch fetch all matters (1 query for matters, 1 for topics)
            if all_matter_ids:
                matters = await self.matters.get_matters_batch(all_matter_ids)

                # Attach matters to items
                for items in items_by_meeting.values():
                    for item in items:
                        if item.matter_id and item.matter_id in matters:
                            item.matter = matters[item.matter_id]

        return items_by_meeting

    async def get_matters_batch(self, matter_ids: List[str]) -> Dict[str, "Matter"]:
        """Batch fetch multiple matters - eliminates N+1

        Facade method for server routes - delegates to MatterRepository.
        """
        return await self.matters.get_matters_batch(matter_ids)

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
        """Get meeting statistics for multiple cities (batch query)

        Returns dict with city-level meeting counts and summary stats.
        Uses single batch query with LEFT JOIN to avoid N+1 pattern.

        Metrics:
        - total_meetings: All meetings for city
        - meetings_with_packet: Meetings with agenda_url OR packet_url
        - summarized_meetings: Meetings that have at least one item with summary
        """
        if not bananas:
            return {}

        # Initialize all bananas with zeros (handles cities with no meetings)
        stats = {
            b: {"total_meetings": 0, "meetings_with_packet": 0, "summarized_meetings": 0}
            for b in bananas
        }

        async with self.pool.acquire() as conn:
            # Single batch query: JOIN items once, GROUP BY banana
            # Uses subquery to identify meetings with summarized items
            rows = await conn.fetch("""
                WITH summarized_meetings AS (
                    SELECT DISTINCT meeting_id
                    FROM items
                    WHERE summary IS NOT NULL
                )
                SELECT
                    m.banana,
                    COUNT(*) as total_meetings,
                    COUNT(CASE WHEN m.packet_url IS NOT NULL OR m.agenda_url IS NOT NULL THEN 1 END) as meetings_with_packet,
                    COUNT(sm.meeting_id) as summarized_meetings
                FROM meetings m
                LEFT JOIN summarized_meetings sm ON sm.meeting_id = m.id
                WHERE m.banana = ANY($1::text[])
                GROUP BY m.banana
            """, bananas)

            for row in rows:
                stats[row['banana']] = {
                    "total_meetings": row['total_meetings'],
                    "meetings_with_packet": row['meetings_with_packet'],
                    "summarized_meetings": row['summarized_meetings'],
                }

        return stats
