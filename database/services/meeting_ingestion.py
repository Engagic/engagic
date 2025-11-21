"""
Meeting Ingestion Service

Extracted from UnifiedDatabase.store_meeting_from_sync (343-line God function).
Handles the complex orchestration of:
1. Date parsing from vendor formats
2. Meeting validation and creation
3. Agenda item processing with matter tracking
4. Atomic transactions for matters + items + appearances
5. Queue enqueuing with priority calculation
"""

import logging
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime

from database.models import City, Meeting, AgendaItem
from database.id_generation import generate_matter_id
from pipeline.utils import hash_attachments
from vendors.validator import MeetingValidator
from vendors.utils.item_filters import should_skip_procedural_item, should_skip_matter
from vendors.schemas import validate_meeting_output
from pydantic import ValidationError

logger = logging.getLogger("engagic")


class MeetingIngestionService:
    """
    Service for ingesting meetings from vendor adapters into the database.

    Orchestrates the complex flow of parsing, validation, storage, and enqueueing.
    """

    def __init__(self, db):
        """
        Args:
            db: UnifiedDatabase instance for repository access
        """
        self.db = db

    def ingest_meeting(
        self, meeting_dict: Dict[str, Any], city: City
    ) -> Tuple[Optional[Meeting], Dict[str, Any]]:
        """
        Main entry point: Transform vendor meeting dict → validate → store → enqueue.

        Args:
            meeting_dict: Raw meeting dict from vendor adapter
            city: City object for this meeting

        Returns:
            Tuple of (stored Meeting object or None, stats dict)
        """
        stats = self._init_stats()

        try:
            # VALIDATION BOUNDARY: Validate adapter output schema
            try:
                validate_meeting_output(meeting_dict)
            except ValidationError as e:
                logger.error(
                    f"[{city.banana}] Adapter output validation failed for meeting "
                    f"'{meeting_dict.get('title', 'Unknown')}': {e}"
                )
                stats['meetings_skipped'] = 1
                stats['skip_reason'] = "schema_validation_failed"
                stats['skipped_title'] = meeting_dict.get("title", "Unknown")
                return None, stats

            # Phase 1: Parse and validate
            meeting_date = self._parse_meeting_date(meeting_dict)
            meeting_id = self._validate_meeting_id(meeting_dict, city, stats)
            if not meeting_id:
                return None, stats

            # Phase 2: Create and store meeting
            meeting_obj = self._create_meeting_object(
                meeting_dict, city, meeting_id, meeting_date
            )
            if not self._validate_meeting_urls(meeting_obj, city, stats):
                return None, stats

            stored_meeting = self.db.store_meeting(meeting_obj)

            # Phase 3: Process agenda items
            agenda_items = []
            items_data = meeting_dict.get("items")
            if items_data:
                agenda_items = self._process_agenda_items(
                    items_data, stored_meeting, city, stats
                )

                if agenda_items:
                    self._store_items_atomically(
                        stored_meeting, items_data, agenda_items, stats
                    )

            # Phase 4: Enqueue for processing
            self._enqueue_if_needed(
                stored_meeting, city, meeting_date, agenda_items, items_data, stats
            )

            # Phase 5: Validate matter tracking
            if agenda_items:
                self.db.validate_matter_tracking(stored_meeting.id)

            return stored_meeting, stats

        except Exception as e:
            import traceback
            logger.error(
                f"Error storing meeting {meeting_dict.get('packet_url', 'unknown')}: {e}\n{traceback.format_exc()}"
            )
            if not stats.get('meetings_skipped'):
                stats['meetings_skipped'] = 1
                stats['skip_reason'] = "exception"
                stats['skipped_title'] = meeting_dict.get("title", "Unknown")
            return None, stats

    def _init_stats(self) -> Dict[str, Any]:
        """Initialize stats tracking"""
        return {
            'items_stored': 0,
            'items_skipped_procedural': 0,
            'matters_tracked': 0,
            'matters_duplicate': 0,
            'meetings_skipped': 0,
            'skip_reason': None,
            'skipped_title': None,
        }

    def _parse_meeting_date(self, meeting_dict: Dict[str, Any]) -> Optional[datetime]:
        """Parse date from adapter format, trying multiple formats"""
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
                        meeting_date = datetime.fromisoformat(
                            date_str.replace("Z", "+00:00")
                        )
                    else:
                        meeting_date = datetime.strptime(date_str, fmt)
                    break
                except ValueError:
                    continue

        return meeting_date

    def _validate_meeting_id(
        self, meeting_dict: Dict[str, Any], city: City, stats: Dict[str, Any]
    ) -> Optional[str]:
        """Validate meeting_id (fail fast if adapter didn't provide one)"""
        meeting_id = meeting_dict.get("meeting_id")
        if not meeting_id or not meeting_id.strip():
            logger.error(
                f"[{city.banana}] CRITICAL: Adapter returned blank meeting_id for "
                f"'{meeting_dict.get('title', 'Unknown')}' on {meeting_dict.get('date', 'Unknown')}. "
                f"Adapter should use _generate_meeting_id() fallback."
            )
            stats['meetings_skipped'] = 1
            stats['skip_reason'] = "missing_meeting_id"
            stats['skipped_title'] = meeting_dict.get("title", "Unknown")
            return None

        return meeting_id

    def _create_meeting_object(
        self,
        meeting_dict: Dict[str, Any],
        city: City,
        meeting_id: str,
        meeting_date: Optional[datetime]
    ) -> Meeting:
        """Create Meeting object and preserve existing summary if already processed"""
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
        existing_meeting = self.db.get_meeting(meeting_obj.id)
        if existing_meeting and existing_meeting.summary:
            meeting_obj.summary = existing_meeting.summary
            meeting_obj.processing_status = existing_meeting.processing_status
            meeting_obj.processing_method = existing_meeting.processing_method
            meeting_obj.processing_time = existing_meeting.processing_time
            meeting_obj.topics = existing_meeting.topics
            logger.debug(f"Preserved existing summary for {meeting_obj.title}")

        return meeting_obj

    def _validate_meeting_urls(
        self, meeting_obj: Meeting, city: City, stats: Dict[str, Any]
    ) -> bool:
        """Validate meeting URLs before storing"""
        if not MeetingValidator.validate_and_store(
            {
                "packet_url": meeting_obj.packet_url,
                "agenda_url": meeting_obj.agenda_url,
                "title": meeting_obj.title,
            },
            city.banana,
            city.name,
            city.vendor,
            city.slug,
        ):
            logger.warning(f"[Items] Skipping corrupted meeting: {meeting_obj.title}")
            stats['meetings_skipped'] = 1
            stats['skip_reason'] = "url_validation"
            stats['skipped_title'] = meeting_obj.title or "Unknown"
            return False

        return True

    def _process_agenda_items(
        self,
        items_data: List[Dict[str, Any]],
        stored_meeting: Meeting,
        city: City,
        stats: Dict[str, Any]
    ) -> List[AgendaItem]:
        """Process agenda items: filter procedural, generate matter IDs, preserve summaries"""
        agenda_items = []

        # Build map of existing items to preserve summaries
        existing_items = self.db.get_agenda_items(stored_meeting.id)
        existing_items_map = {item.id: item for item in existing_items}

        for item_data in items_data:
            item_id = f"{stored_meeting.id}_{item_data['item_id']}"
            item_title = item_data.get("title", "")
            item_type = item_data.get("matter_type", "")

            # Check if procedural (for matter tracking only)
            is_procedural = should_skip_procedural_item(item_title, item_type)

            # Generate composite matter_id for FK relationship
            composite_matter_id = self._generate_composite_matter_id(
                city, item_data, item_type, item_title, is_procedural
            )

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
                matter_id=composite_matter_id,
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
            if agenda_item.matter_file or composite_matter_id:
                logger.info(
                    f"[Items] {item_title[:50]} | Matter: {agenda_item.matter_file} "
                    f"({composite_matter_id[:24]}...)" if composite_matter_id
                    else f"[Items] {item_title[:50]} | Matter: {agenda_item.matter_file}"
                )
            else:
                logger.info(f"[Items] {item_title[:50]}")

            agenda_items.append(agenda_item)

        return agenda_items

    def _generate_composite_matter_id(
        self,
        city: City,
        item_data: Dict[str, Any],
        item_type: str,
        item_title: str,
        is_procedural: bool
    ) -> Optional[str]:
        """Generate composite matter_id for FK relationship (or None if procedural)"""
        raw_matter_id = item_data.get("matter_id")
        raw_matter_file = item_data.get("matter_file")

        # Skip matter tracking for procedural items
        if is_procedural or not (raw_matter_id or raw_matter_file):
            return None

        # Additional check: skip if matter_type is procedural
        if should_skip_matter(item_type):
            logger.debug(
                f"[Items] Skipping matter tracking for procedural type: "
                f"{item_title[:40]} ({item_type})"
            )
            return None

        try:
            return generate_matter_id(
                banana=city.banana,
                matter_file=raw_matter_file,
                matter_id=raw_matter_id
            )
        except ValueError as e:
            logger.error(
                f"[Items] FATAL: Invalid matter data for {item_title[:40]}: {e}"
            )
            raise ValueError(
                f"Item '{item_title}' has invalid matter data "
                f"(matter_id={raw_matter_id}, matter_file={raw_matter_file}): {e}"
            ) from e

    def _store_items_atomically(
        self,
        stored_meeting: Meeting,
        items_data: List[Dict[str, Any]],
        agenda_items: List[AgendaItem],
        stats: Dict[str, Any]
    ):
        """Store items atomically: track matters → store items → create appearances"""
        try:
            # Track matters FIRST in city_matters table (creates FK targets)
            matters_stats = self.db._track_matters(
                stored_meeting, items_data, agenda_items, defer_commit=True
            )
            stats['matters_tracked'] = matters_stats.get('tracked', 0)
            stats['matters_duplicate'] = matters_stats.get('duplicate', 0)

            # THEN store items (FK targets exist now)
            count = self.db.store_agenda_items(
                stored_meeting.id, agenda_items, defer_commit=True
            )
            stats['items_stored'] = count
            items_with_summaries = sum(1 for item in agenda_items if item.summary)

            # FINALLY create matter_appearances
            appearances_count = self.db._create_matter_appearances(
                stored_meeting, agenda_items, defer_commit=True
            )
            stats['appearances_created'] = appearances_count

            # Commit transaction atomically
            self.db.conn.commit()

            logger.info(
                f"[Items] Stored {count} items "
                f"({stats['items_skipped_procedural']} procedural, "
                f"{items_with_summaries} with preserved summaries)"
            )

        except Exception as e:
            self.db.conn.rollback()
            logger.error(f"[Items] Transaction rolled back due to error: {e}")
            raise

    def _enqueue_if_needed(
        self,
        stored_meeting: Meeting,
        city: City,
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
                f"Skipping enqueue for {stored_meeting.title} - {skip_reason}"
            )
            return

        if not (has_items or packet_url):
            logger.debug(
                f"Meeting {stored_meeting.title} has no agenda/packet/items "
                f"- stored for display only"
            )
            return

        # Calculate priority based on meeting date proximity
        priority = self._calculate_priority(meeting_date)

        # MATTERS-FIRST: Deduplicate summarization work across meetings
        if has_items and agenda_items:
            matters_enqueued = self.db._enqueue_matters_first(
                city.banana, stored_meeting, agenda_items, priority
            )

            if matters_enqueued > 0:
                logger.debug(
                    f"Enqueued {matters_enqueued} matters for {stored_meeting.title} "
                    f"(priority {priority})"
                )
            else:
                logger.debug(
                    f"All matters already processed for {stored_meeting.title}"
                )

        # MONOLITH FALLBACK: No items at all, process entire packet
        elif packet_url:
            self.db.enqueue_meeting_job(
                meeting_id=stored_meeting.id,
                source_url=packet_url,
                banana=city.banana,
                priority=priority,
            )
            logger.debug(
                f"Enqueued monolithic-packet processing for {stored_meeting.title} "
                f"(priority {priority})"
            )
        else:
            logger.warning(
                f"[DB] Meeting {stored_meeting.id} has no items or packet URL "
                f"- skipping queue"
            )

    def _should_skip_enqueue(
        self,
        agenda_items: List[AgendaItem],
        stored_meeting: Meeting,
        has_items: bool
    ) -> Tuple[bool, Optional[str]]:
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

    def _calculate_priority(self, meeting_date: Optional[datetime]) -> int:
        """Calculate priority based on meeting date proximity"""
        if meeting_date:
            # Handle timezone-aware dates from adapters
            now = datetime.now(meeting_date.tzinfo) if meeting_date.tzinfo else datetime.now()
            days_from_now = (meeting_date - now).days
            days_distance = abs(days_from_now)
        else:
            days_distance = 999

        return max(0, 150 - days_distance)
