"""Meeting Sync Orchestrator - Coordinates meeting storage workflow."""

from datetime import datetime
from typing import Optional, List, Dict, Any, TypedDict

from config import get_logger
from database.id_generation import generate_meeting_id, generate_matter_id, validate_matter_id
from database.models import City, Meeting, AgendaItem, Matter, MatterMetadata
from database.repositories_async.helpers import deserialize_attachments
from exceptions import DatabaseError, ValidationError
from pipeline.utils import hash_attachments
from pipeline.orchestrators.matter_filter import MatterFilter
from pipeline.orchestrators.enqueue_decider import EnqueueDecider
from pipeline.orchestrators.vote_processor import VoteProcessor

logger = get_logger(__name__).bind(component="meeting_sync")


class MeetingStoreStats(TypedDict):
    items_stored: int
    items_skipped_procedural: int
    matters_tracked: int
    matters_duplicate: int
    meetings_skipped: int
    appearances_created: int
    skip_reason: Optional[str]
    skipped_title: Optional[str]


QUEUE_PRIORITY_BASE_SCORE = 150


class MeetingSyncOrchestrator:
    """Single entry point for all meeting sync operations."""

    def __init__(self, db):
        self.db = db
        self.matter_filter = MatterFilter()
        self.enqueue_decider = EnqueueDecider()
        self.vote_processor = VoteProcessor()

    async def sync_meeting(
        self,
        meeting_dict: Dict[str, Any],
        city: City
    ) -> tuple[Optional[Meeting], MeetingStoreStats]:
        """Transform vendor meeting dict, store meeting and items, enqueue for processing."""
        stats: MeetingStoreStats = {
            'items_stored': 0,
            'items_skipped_procedural': 0,
            'matters_tracked': 0,
            'matters_duplicate': 0,
            'meetings_skipped': 0,
            'appearances_created': 0,
            'skip_reason': None,
            'skipped_title': None,
        }

        try:
            meeting_date = self._parse_meeting_date(meeting_dict)
            title = meeting_dict.get("title", "Meeting")

            vendor_id = meeting_dict.get("vendor_id") or meeting_dict.get("meeting_id")

            if not vendor_id:
                logger.error("adapter missing vendor_id", city=city.banana, meeting_title=title)
                stats['meetings_skipped'] = 1
                stats['skip_reason'] = "missing_vendor_id"
                stats['skipped_title'] = title
                return None, stats

            meeting_id = generate_meeting_id(
                banana=city.banana,
                vendor_id=str(vendor_id),
                date=meeting_date or datetime.now(),
                title=title
            )

            committee_id = await self._lookup_committee_id(city.banana, title)

            meeting_obj = Meeting(
                id=meeting_id,
                banana=city.banana,
                title=title,
                date=meeting_date,
                agenda_url=meeting_dict.get("agenda_url"),
                packet_url=meeting_dict.get("packet_url"),
                summary=None,
                participation=meeting_dict.get("participation"),
                status=meeting_dict.get("meeting_status"),
                processing_status="pending",
                committee_id=committee_id,
            )

            existing_meeting = await self.db.meetings.get_meeting(meeting_obj.id)
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
                agenda_items = await self._process_agenda_items(
                    items_data, meeting_obj, stats
                )

            async with self.db.pool.acquire() as conn:
                async with conn.transaction():
                    await self.db.meetings.store_meeting(meeting_obj)

                    if agenda_items:
                        matters_stats = await self._track_matters(
                            meeting_obj, items_data or [], agenda_items
                        )
                        stats['matters_tracked'] = matters_stats.get('tracked', 0)
                        stats['matters_duplicate'] = matters_stats.get('duplicate', 0)
                        stats['items_skipped_procedural'] = matters_stats.get('skipped_procedural', 0)

                        skipped_ids = matters_stats.get('skipped_item_ids', set())
                        for item in agenda_items:
                            if item.id in skipped_ids:
                                item.matter_id = None

                        stored_count = await self.db.items.store_agenda_items(meeting_obj.id, agenda_items)
                        stats['items_stored'] = stored_count

                        appearances_count = await self._create_matter_appearances(
                            meeting_obj, agenda_items
                        )
                        stats['appearances_created'] = appearances_count

            await self._enqueue_if_needed(
                meeting_obj, meeting_date, agenda_items, items_data, stats
            )

            return meeting_obj, stats

        except (DatabaseError, ValidationError, ValueError) as e:
            logger.error(
                "error storing meeting",
                packet_url=meeting_dict.get('packet_url', 'unknown'),
                error=str(e),
                error_type=type(e).__name__,
            )
            raise

    def _parse_meeting_date(self, meeting_dict: Dict[str, Any]) -> Optional[datetime]:
        """Parse date string, trying ISO then common US formats."""
        date_str = meeting_dict.get("start")
        if not date_str:
            return None

        try:
            return datetime.fromisoformat(date_str.replace("Z", "+00:00"))
        except ValueError:
            pass

        for fmt in ("%m/%d/%y", "%Y-%m-%d", "%m/%d/%Y"):
            try:
                return datetime.strptime(date_str, fmt)
            except ValueError:
                continue
        return None

    async def _lookup_committee_id(self, banana: str, meeting_title: str) -> Optional[str]:
        """Match meeting title to committee name."""
        if not meeting_title:
            return None
        committee_name = meeting_title.split("-")[0].strip() if "-" in meeting_title else meeting_title
        committee = await self.db.committees.find_by_name(banana, committee_name)
        return committee.id if committee else None

    async def _process_agenda_items(
        self,
        items_data: List[Dict[str, Any]],
        stored_meeting: Meeting,
        stats: MeetingStoreStats
    ) -> List[AgendaItem]:
        """Build AgendaItem list, preserving existing summaries."""
        existing_items = await self.db.items.get_agenda_items(stored_meeting.id)
        existing_items_map = {item.id: item for item in existing_items}

        agenda_items = []
        for item_data in items_data:
            item_id = f"{stored_meeting.id}_{item_data['item_id']}"
            item_attachments = deserialize_attachments(item_data.get("attachments"))
            matter_file = item_data.get("matter_file")
            matter_id_vendor = item_data.get("matter_id")

            matter_id = None
            if matter_file or matter_id_vendor:
                matter_id = generate_matter_id(
                    banana=stored_meeting.banana,
                    matter_file=matter_file,
                    matter_id=matter_id_vendor,
                )

            agenda_item = AgendaItem(
                id=item_id,
                meeting_id=stored_meeting.id,
                title=item_data.get("title", "Untitled Item"),
                sequence=item_data.get("sequence", 0),
                matter_file=matter_file,
                matter_id=matter_id,
                matter_type=item_data.get("matter_type"),
                sponsors=item_data.get("sponsors", []),
                attachments=item_attachments,
                summary=None,
                topics=None,
            )

            existing_item = existing_items_map.get(item_id)
            if existing_item and existing_item.summary:
                agenda_item.summary = existing_item.summary
                agenda_item.topics = existing_item.topics

            agenda_items.append(agenda_item)

        return agenda_items

    async def _track_matters(
        self,
        meeting: Meeting,
        items_data: List[Dict[str, Any]],
        agenda_items: List[AgendaItem]
    ) -> Dict[str, Any]:
        """Track legislative matters, creating new or updating existing."""
        stats: Dict[str, Any] = {'tracked': 0, 'duplicate': 0, 'skipped_procedural': 0, 'skipped_item_ids': set()}

        if not items_data or not agenda_items:
            return stats

        items_map = {item["item_id"]: item for item in items_data}

        for agenda_item in agenda_items:
            if not agenda_item.matter_id:
                continue

            if not validate_matter_id(agenda_item.matter_id):
                logger.error("invalid matter_id format", item_id=agenda_item.id, matter_id=agenda_item.matter_id)
                continue

            item_id_short = agenda_item.id.rsplit("_", 1)[1]
            raw_item = items_map.get(item_id_short, {})
            sponsors = raw_item.get("sponsors", [])
            matter_type = raw_item.get("matter_type")
            raw_vendor_matter_id = raw_item.get("matter_id")

            if self.matter_filter.should_skip(matter_type):
                stats['skipped_procedural'] += 1
                stats['skipped_item_ids'].add(agenda_item.id)
                logger.debug("skipping procedural matter", matter=agenda_item.matter_file or raw_vendor_matter_id, matter_type=matter_type)
                continue

            existing_matter = await self.db.matters.get_matter(agenda_item.matter_id)
            attachment_hash = hash_attachments(agenda_item.attachments or [])

            if existing_matter:
                appearance_exists = await self.db.matters.has_appearance(agenda_item.matter_id, meeting.id)
                await self.db.matters.update_matter_tracking(
                    matter_id=agenda_item.matter_id,
                    meeting_date=meeting.date,
                    attachments=agenda_item.attachments,
                    attachment_hash=attachment_hash,
                    increment_appearance_count=not appearance_exists
                )
                stats['duplicate'] += 1
                if not appearance_exists and (agenda_item.matter_file or raw_vendor_matter_id):
                    logger.info("matter new appearance", matter=agenda_item.matter_file or raw_vendor_matter_id, matter_type=matter_type)
            else:
                if not agenda_item.matter_file and not raw_vendor_matter_id and not agenda_item.title:
                    continue

                matter_obj = Matter(
                    id=agenda_item.matter_id,
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

                await self.db.matters.store_matter(matter_obj)
                stats['tracked'] += 1

                if agenda_item.matter_file or raw_vendor_matter_id:
                    logger.info("new matter tracked", matter=agenda_item.matter_file or raw_vendor_matter_id, matter_type=matter_type, sponsor_count=len(sponsors))

                if sponsors:
                    await self.db.council_members.link_sponsors_to_matter(
                        banana=meeting.banana, matter_id=agenda_item.matter_id, sponsor_names=sponsors, appeared_at=meeting.date
                    )

            votes = raw_item.get("votes", [])
            if votes:
                await self.db.council_members.record_votes_for_matter(
                    banana=meeting.banana, matter_id=agenda_item.matter_id, meeting_id=meeting.id, votes=votes, vote_date=meeting.date
                )
                result = self.vote_processor.process_votes(votes)
                await self.db.matters.update_appearance_outcome(
                    matter_id=agenda_item.matter_id, meeting_id=meeting.id, item_id=agenda_item.id, vote_outcome=result["outcome"], vote_tally=result["tally"]
                )

        return stats

    async def _create_matter_appearances(
        self,
        meeting: Meeting,
        agenda_items: List[AgendaItem]
    ) -> int:
        """Create matter_appearances after items are stored."""
        count = 0
        committee = meeting.title.split("-")[0].strip() if meeting.title else None

        for agenda_item in agenda_items:
            if not agenda_item.matter_id:
                continue

            await self.db.matters.create_appearance(
                matter_id=agenda_item.matter_id,
                meeting_id=meeting.id,
                item_id=agenda_item.id,
                appeared_at=meeting.date,
                committee=committee,
                committee_id=meeting.committee_id,
                sequence=agenda_item.sequence
            )
            count += 1

        return count

    async def _enqueue_if_needed(
        self,
        stored_meeting: Meeting,
        meeting_date: Optional[datetime],
        agenda_items: List[AgendaItem],
        items_data: Optional[List[Dict[str, Any]]],
        stats: MeetingStoreStats
    ) -> None:
        """Enqueue meeting for LLM processing if criteria are met."""
        should_enqueue, skip_reason = self.enqueue_decider.should_enqueue(stored_meeting, agenda_items, bool(agenda_items))

        if not should_enqueue:
            if skip_reason:
                logger.debug("skipping enqueue", reason=skip_reason, meeting_id=stored_meeting.id)
            return

        priority = self.enqueue_decider.calculate_priority(meeting_date)
        packet_url = stored_meeting.packet_url
        if isinstance(packet_url, list):
            packet_url = packet_url[0] if packet_url else None

        await self.db.queue.enqueue_job(
            job_type="meeting",
            payload={"meeting_id": stored_meeting.id, "packet_url": packet_url, "banana": stored_meeting.banana, "title": stored_meeting.title},
            priority=priority,
            banana=stored_meeting.banana,
        )

        logger.info("enqueued meeting for processing", meeting_id=stored_meeting.id, priority=priority)
