"""
Pipeline Processor - Queue processing and item assembly

Handles:
- Processing jobs from the queue
- Assembling item text from PDFs
- Orchestrating LLM analysis via Analyzer
- Topic normalization and aggregation
- Meeting summary updates

Moved from: pipeline/conductor.py (refactored)
"""

import time
from typing import List, Optional, Dict, Any

from database.db import UnifiedDatabase, Meeting
from database.models import Matter
from database.id_generation import validate_matter_id, extract_banana_from_matter_id
from database.transaction import transaction
from exceptions import ProcessingError, ExtractionError, LLMError
from pipeline.analyzer import Analyzer
from analysis.topics.normalizer import get_normalizer
from parsing.participation import parse_participation_info
from config import config, get_logger
from server.metrics import metrics

logger = get_logger(__name__).bind(component="processor")

# Skip procedural items (administrative overhead, not policy)
PROCEDURAL_PATTERNS = [
    "review of minutes",
    "approval of minutes",
    "adopt minutes",
    "roll call",
    "pledge of allegiance",
    "invocation",
    "adjournment",
    "proclamation",
    "commendation",
    "recognition",
    "ceremonial",
]

# Skip public comment attachments (high token cost, low informational value)
PUBLIC_COMMENT_PATTERNS = [
    "public comment",
    "public correspondence",
    "comment letter",
    "comment ltrs",  # SF abbreviation
    "written comment",
    "public hearing comment",
    "citizen comment",
    "correspondence received",
    "public input",
    "public testimony",
    "letters received",
    "petitions",  # SF uses "Petitions and Communications"
    "communications",  # Often paired with "Petitions"
    "pub corr",  # SF abbreviation for public correspondence
    "pulbic corr",  # Common typo seen in SF data
    "comm pkt",  # Committee packets (often contain public comments)
    "committee packet",  # Full form
]

# Skip parcel tables and property lists (massive PDFs with no civic value)
# Example: "Parcel Tables" (992 pages!) - just property IDs and addresses
PARCEL_TABLE_PATTERNS = [
    "parcel table",
    "parcel list",
    "parcel map",
    "tax parcel",
    "property list",
    "property table",
    "assessor",
    "apn list",  # Assessor Parcel Number
    "parcel number",
]

# Queue processing timing constants (seconds)
QUEUE_POLL_INTERVAL = 5  # Time to wait when queue is empty
QUEUE_ERROR_BACKOFF = 2  # Brief backoff after job processing error
QUEUE_FATAL_ERROR_BACKOFF = 10  # Longer backoff after fatal queue error

# File size thresholds (bytes)
MAX_ATTACHMENT_SIZE_MB = 50  # Skip attachments larger than 50MB (likely compilations)
MAX_ATTACHMENT_SIZE_BYTES = MAX_ATTACHMENT_SIZE_MB * 1024 * 1024


def is_procedural_item(title: str) -> bool:
    """Check if agenda item is procedural (skip to save API costs)"""
    title_lower = title.lower()
    return any(pattern in title_lower for pattern in PROCEDURAL_PATTERNS)


def is_public_comment_attachment(name: str) -> bool:
    """Check if attachment is public comments or parcel tables (high token cost, low signal)"""
    name_lower = name.lower()
    return (
        any(pattern in name_lower for pattern in PUBLIC_COMMENT_PATTERNS) or
        any(pattern in name_lower for pattern in PARCEL_TABLE_PATTERNS)
    )


def is_likely_public_comment_compilation(
    extraction_result: Dict[str, Any],
    url_path: str
) -> bool:
    """Detect public comment compilations after extraction based on document characteristics

    These are typically:
    - Very large PDFs (hundreds of pages)
    - Heavily reliant on OCR (scanned form letters)
    - Repetitive content patterns (many "Sincerely," signatures)

    Args:
        extraction_result: PDF extraction result dict with page_count, ocr_pages, text
        url_path: Filename/path for logging

    Returns:
        True if document appears to be public comment compilation
    """
    page_count = extraction_result.get("page_count", 0)
    ocr_pages = extraction_result.get("ocr_pages", 0)
    text = extraction_result.get("text", "")

    # Threshold 1: Excessive page count (> 1000 pages)
    # Legislative documents can be hundreds of pages, but 1000+ is likely a compilation
    if page_count > 1000:
        logger.info(
            "skipping likely compilation - excessive page count",
            url_path=url_path,
            page_count=page_count,
            threshold=1000
        )
        return True

    # Threshold 2: High OCR ratio + large document (suggests bulk scanned form letters)
    # If >30% of pages needed OCR and doc is >50 pages, likely public comments
    if page_count > 50 and ocr_pages > 0:
        ocr_ratio = ocr_pages / page_count
        if ocr_ratio > 0.3:
            logger.info(
                "skipping likely scanned compilation - high OCR ratio",
                url_path=url_path,
                ocr_pages=ocr_pages,
                total_pages=page_count,
                ocr_ratio=round(ocr_ratio, 2)
            )
            return True

    # Threshold 3: Repetitive signature patterns (public comment form letters)
    # Count "Sincerely," occurrences as proxy for individual letters
    if len(text) > 5000:  # Check documents with substantial content
        sincerely_count = text.lower().count("sincerely,")
        # If >20 signatures, likely public comment compilation
        if sincerely_count > 20:
            logger.info(
                "skipping likely comment compilation - repetitive signatures",
                url_path=url_path,
                signature_count=sincerely_count
            )
            return True

    return False


class Processor:
    """Queue processing and item assembly orchestrator"""

    def __init__(
        self,
        db: Optional[UnifiedDatabase] = None,
        analyzer: Optional[Analyzer] = None,
    ):
        """Initialize the processor

        Args:
            db: Database instance (or creates new one)
            analyzer: LLM analyzer instance (or creates new one if API key available)
        """
        self.db = db or UnifiedDatabase(config.UNIFIED_DB_PATH)
        self.is_running = True  # Control flag for external stop

        # Initialize analyzer if not provided
        if analyzer is not None:
            self.analyzer = analyzer
        else:
            try:
                self.analyzer = Analyzer(api_key=config.get_api_key())
                logger.info("initialized with llm analyzer", has_analyzer=True)
            except ValueError:
                logger.warning(
                    "llm analyzer not available, summaries will be skipped",
                    has_analyzer=False
                )
                self.analyzer = None

    def _filter_document_versions(self, urls: List[str]) -> List[str]:
        """Filter document URLs to keep only latest versions (Ver2 > Ver1, etc.)

        Args:
            urls: List of document URLs

        Returns:
            Filtered list with only latest versions
        """
        import re

        # Group URLs by base name (without version suffix)
        url_groups = {}  # base_name -> {version_num: url}
        non_versioned = []  # URLs without version numbers

        version_pattern = re.compile(r'(.+?)\s+Ver(\d+)', re.IGNORECASE)

        for url in urls:
            # Extract filename from URL
            filename = url.split('/')[-1] if url else ""

            match = version_pattern.search(filename)
            if match:
                base_name = match.group(1).strip()
                version_num = int(match.group(2))

                if base_name not in url_groups:
                    url_groups[base_name] = {}
                url_groups[base_name][version_num] = url
            else:
                non_versioned.append(url)

        # Keep only the highest version for each base name
        filtered = non_versioned.copy()
        for base_name, versions in url_groups.items():
            max_version = max(versions.keys())
            filtered.append(versions[max_version])

        return filtered

    def _dispatch_and_process_job(self, job, queue_id: int) -> bool:
        """Dispatch and process a single queue job

        Args:
            job: QueueJob instance
            queue_id: Queue ID

        Returns:
            True if job was processed (success or expected failure), False if should retry

        Confidence: 8/10 - Extracted from proven process_queue logic
        """
        # Guard: Check analyzer availability first
        if not self.analyzer:
            with transaction(self.db.conn):
                self.db.mark_processing_failed(
                    queue_id, "Analyzer not available", increment_retry=False
                )
            logger.warning("skipping queue job - analyzer not available", queue_id=queue_id)
            return True

        job_type = job.job_type

        # Dispatch based on job type
        try:
            if job_type == "matter":
                from pipeline.models import MatterJob
                if not isinstance(job.payload, MatterJob):
                    raise ValueError(f"Invalid payload type for matter job: {type(job.payload)}")

                self.process_matter(
                    job.payload.matter_id,
                    job.payload.meeting_id,
                    {"item_ids": job.payload.item_ids}
                )

            elif job_type == "meeting":
                from pipeline.models import MeetingJob
                if not isinstance(job.payload, MeetingJob):
                    raise ValueError(f"Invalid payload type for meeting job: {type(job.payload)}")

                meeting = self.db.get_meeting(job.payload.meeting_id)
                if not meeting:
                    with transaction(self.db.conn):
                        self.db.mark_processing_failed(queue_id, "Meeting not found in database")
                    return True

                self.process_meeting(meeting)

            else:
                raise ValueError(f"Unknown job type: {job_type}")

            # Success
            with transaction(self.db.conn):
                self.db.mark_processing_complete(queue_id)
            logger.info("queue job completed", queue_id=queue_id)
            return True

        except Exception as e:
            error_msg = str(e)
            with transaction(self.db.conn):
                self.db.mark_processing_failed(queue_id, error_msg)
            logger.error("queue job failed", queue_id=queue_id, error=error_msg)
            return True

    def process_queue(self):
        """Process jobs from the processing queue continuously"""
        logger.info("starting queue processor")

        while self.is_running:
            try:
                with transaction(self.db.conn):
                    job = self.db.get_next_for_processing()

                if not job:
                    time.sleep(QUEUE_POLL_INTERVAL)
                    continue

                queue_id = job.id
                logger.info("processing queue job", queue_id=queue_id, job_type=job.job_type)

                self._dispatch_and_process_job(job, queue_id)

            except Exception as e:
                logger.error("queue processor error", error=str(e), error_type=type(e).__name__)
                time.sleep(QUEUE_FATAL_ERROR_BACKOFF)

    def process_city_jobs(self, city_banana: str) -> dict:
        """Process all queued jobs for a specific city

        Args:
            city_banana: City identifier

        Returns:
            Dictionary with processing stats
        """
        logger.info("processing queued jobs for city", city=city_banana)
        processed_count = 0
        failed_count = 0

        while True:
            # Get next job for this city
            with transaction(self.db.conn):
                job = self.db.get_next_for_processing(banana=city_banana)

            if not job:
                break  # No more jobs for this city

            queue_id = job.id
            job_type = job.job_type

            logger.info("processing job", queue_id=queue_id, job_type=job_type)

            # Track processing duration
            job_start_time = time.time()
            job_success = False

            try:
                # Type-safe dispatch
                if job_type == "meeting":
                    from pipeline.models import MeetingJob
                    if isinstance(job.payload, MeetingJob):
                        meeting = self.db.get_meeting(job.payload.meeting_id)
                        if not meeting:
                            with transaction(self.db.conn):
                                self.db.mark_processing_failed(queue_id, "Meeting not found")
                            failed_count += 1
                            metrics.queue_jobs_processed.labels(job_type="meeting", status="failed").inc()
                            continue
                        # Process the meeting (item-aware)
                        with metrics.processing_duration.labels(job_type="meeting").time():
                            self.process_meeting(meeting)
                        with transaction(self.db.conn):
                            self.db.mark_processing_complete(queue_id)
                        processed_count += 1
                        job_success = True
                        logger.info("processed meeting", meeting_id=job.payload.meeting_id, duration_seconds=round(time.time() - job_start_time, 1))
                    else:
                        raise ValueError("Invalid payload type for meeting job")
                elif job_type == "matter":
                    from pipeline.models import MatterJob
                    if isinstance(job.payload, MatterJob):
                        with metrics.processing_duration.labels(job_type="matter").time():
                            self.process_matter(
                                job.payload.matter_id,
                                job.payload.meeting_id,
                                {"item_ids": job.payload.item_ids}
                            )
                        with transaction(self.db.conn):
                            self.db.mark_processing_complete(queue_id)
                        processed_count += 1
                        job_success = True
                        logger.info("processed matter", matter_id=job.payload.matter_id, duration_seconds=round(time.time() - job_start_time, 1))
                    else:
                        raise ValueError("Invalid payload type for matter job")
                else:
                    raise ValueError(f"Unknown job type: {job_type}")

                # Record successful job
                if job_success:
                    metrics.queue_jobs_processed.labels(job_type=job_type, status="completed").inc()

            except Exception as e:
                error_msg = str(e)
                with transaction(self.db.conn):
                    self.db.mark_processing_failed(queue_id, error_msg)
                failed_count += 1
                job_duration = time.time() - job_start_time

                # Record metrics
                metrics.queue_jobs_processed.labels(job_type=job_type, status="failed").inc()
                metrics.record_error(component="processor", error=e)

                logger.error("job processing failed", queue_id=queue_id, job_type=job_type, duration_seconds=round(job_duration, 1), error=str(e), error_type=type(e).__name__)

        logger.info(
            "processing complete for city",
            city=city_banana,
            succeeded=processed_count,
            failed=failed_count
        )

        return {
            "processed_count": processed_count,
            "failed_count": failed_count,
        }

    def _process_single_item(self, item):
        """Process a single agenda item (extract PDFs and summarize)

        Args:
            item: AgendaItem object to process

        Returns:
            Dict with 'success', 'summary', 'topics' keys, or None if processing fails
        """

        if not self.analyzer:
            raise ProcessingError(
                "Analyzer not initialized",
                context={"component": "processor", "function": "_process_single_item"}
            )

        # Skip procedural items
        if is_procedural_item(item.title):
            logger.debug("skipping procedural item", title=item.title[:50])
            return None

        if not item.attachments:
            logger.debug("no attachments for item", title=item.title[:50])
            return None

        # Check if entire item is public comments or parcel tables
        if is_public_comment_attachment(item.title):
            logger.info("skipping low-value item", title=item.title[:80], reason="public_comments_or_parcel_tables")
            return None

        # Extract text from attachments
        item_parts = []
        total_page_count = 0

        for att in item.attachments:
            if isinstance(att, str):
                att_url = att
                att_type = "pdf"
                att_name = ""
            elif isinstance(att, dict):
                att_url = att.get("url")
                att_type = att.get("type", "unknown")
                att_name = att.get("name", "")

                # Handle text segments directly
                if att_type == "text_segment":
                    text_content = att.get("content", "")
                    if text_content:
                        item_parts.append(text_content)
                    continue
            else:
                continue

            # Extract PDFs and documents
            if att_type in ("pdf", "doc", "unknown") or isinstance(att, str):
                if att_url:
                    # Skip public comment and parcel table attachments by name
                    if att_name and is_public_comment_attachment(att_name):
                        logger.info("skipping low-value attachment", name=att_name)
                        continue

                    try:
                        result = self.analyzer.pdf_extractor.extract_from_url(att_url)
                        if result.get("success") and result.get("text"):
                            # Post-extraction filter: Skip public comment compilations
                            if is_likely_public_comment_compilation(result, att_name or att_url):
                                logger.info(
                                    "skipping public comment compilation",
                                    name=att_name or att_url
                                )
                                continue

                            item_parts.append(f"=== {att_name or att_url} ===\n{result['text']}")
                            total_page_count += result.get("page_count", 0)
                            logger.debug(
                                "extracted attachment text",
                                attachment=att_name or att_url,
                                pages=result.get('page_count', 0),
                                chars=len(result['text'])
                            )
                    except (ExtractionError, OSError, IOError) as e:
                        logger.warning("failed to extract attachment", name=att_name or att_url, error=str(e))

        if not item_parts:
            logger.warning("no text extracted for item", title=item.title[:50])
            raise ProcessingError(
                "No text extracted from agenda item",
                context={"item_id": item.id, "item_title": item.title[:100]}
            )

        combined_text = "\n\n".join(item_parts)

        # Build batch request (single item)
        batch_request = [
            {
                "item_id": item.id,
                "title": item.title,
                "text": combined_text,
                "sequence": item.sequence,
                "page_count": total_page_count if total_page_count > 0 else None,
            }
        ]

        # Process via batch API (single item)
        try:
            for chunk_results in self.analyzer.process_batch_items(batch_request, shared_context=None, meeting_id=None):
                # Should only be one chunk with one result
                if chunk_results:
                    result = chunk_results[0]
                    if result.get("success"):
                        # Normalize topics
                        raw_topics = result.get("topics", [])
                        normalized_topics = get_normalizer().normalize(raw_topics)

                        return {
                            "success": True,
                            "summary": result["summary"],
                            "topics": normalized_topics,
                        }
                    else:
                        error_msg = result.get('error', 'Unknown error')
                        logger.warning("item processing failed", error=error_msg)
                        raise ProcessingError(
                            f"Item processing failed: {error_msg}",
                            context={"item_id": item.id, "item_title": item.title[:100]}
                        )
        except (ProcessingError, LLMError) as e:
            logger.error("item processing error", error=str(e), error_type=type(e).__name__)
            raise ProcessingError(
                f"Item processing failed: {e}",
                context={"item_id": item.id, "item_title": item.title[:100]}
            ) from e

        # If we reach here, no results were returned from batch processing
        raise ProcessingError(
            "No results returned from batch processing",
            context={"item_id": item.id, "item_title": item.title[:100]}
        )

    def process_matter(self, matter_id: str, meeting_id: str, metadata: Optional[Dict] = None):
        """Process a matter across all its appearances (matters-first path)

        STRICT IMPROVEMENT: Queries ALL items from database (not just payload)
        and atomically updates canonical_summary + all item summaries.

        Args:
            matter_id: Matter identifier (e.g., "sanfranciscoCA_251041")
            meeting_id: Meeting ID where matter appears
            metadata: Queue metadata with item_ids (deprecated - query from DB instead)
        """
        from pipeline.utils import hash_attachments

        logger.info("processing matter", matter_id=matter_id)

        # Validate matter_id format
        if not validate_matter_id(matter_id):
            logger.error("invalid matter_id format", matter_id=matter_id)
            return

        banana = extract_banana_from_matter_id(matter_id)
        if not banana:
            logger.error("could not extract banana from matter_id", matter_id=matter_id)
            return

        # STRICT IMPROVEMENT: Query ALL items from database (not just from payload)
        # This ensures we find all appearances even if payload is incomplete
        items = []

        # First try to get from payload for backward compat
        if metadata:
            item_ids = metadata.get("item_ids", [])
            for item_id in item_ids:
                item = self.db.get_agenda_item(item_id)
                if item:
                    items.append(item)

        # If no items from payload, query database directly
        if not items:
            logger.warning("no items in payload, querying database", matter_id=matter_id)
            # matter_id is already composite hash, get all items directly
            items = self.db._get_all_items_for_matter(matter_id)

        if not items:
            logger.error("no items found for matter", matter_id=matter_id)
            return

        # Aggregate ALL attachments from ALL items (deduplicate by URL)
        all_attachments = []
        seen_urls = set()

        for item in items:
            for att in item.attachments:
                # Normalize attachment to dict
                if isinstance(att, str):
                    att_url = att
                elif isinstance(att, dict):
                    att_url = att.get("url")
                else:
                    continue

                # Deduplicate by URL
                if att_url and att_url not in seen_urls:
                    seen_urls.add(att_url)
                    all_attachments.append(att)

        # Use first item as template (for metadata like title, matter_file, etc.)
        representative_item = items[0]

        # Override attachments with aggregated set
        representative_item.attachments = all_attachments

        logger.info(
            "matter aggregation complete",
            matter_id=matter_id,
            appearances=len(items),
            meetings=len(set(item.meeting_id for item in items)),
            unique_attachments=len(all_attachments)
        )

        # Process item with ALL aggregated attachments (extract PDFs and summarize)
        try:
            result = self._process_single_item(representative_item)
        except ProcessingError as e:
            logger.error(
                "matter processing failed",
                matter_id=matter_id,
                error=str(e),
                context=e.context
            )
            metrics.record_error("processor", e)
            return

        if not result:
            logger.warning("no result for matter", matter_id=matter_id)
            return

        summary = result.get("summary")
        topics = result.get("topics", [])

        if not summary:
            logger.warning("no summary generated for matter", matter_id=matter_id)
            return

        # STRICT IMPROVEMENT: Atomic update of canonical_summary + all items
        # Use transaction to ensure consistency
        from database.transaction import transaction

        attachment_hash = hash_attachments(representative_item.attachments)

        # Fetch existing matter to preserve raw matter_id (vendor UUID/numeric ID)
        # CRITICAL: items.matter_id contains composite hash (FK), not raw vendor ID
        # city_matters.matter_id must contain raw vendor ID for traceability
        existing_matter = self.db.get_matter(matter_id)
        raw_matter_id = existing_matter.matter_id if existing_matter else None

        with transaction(self.db.conn):
            # Step 1: Create Matter object with canonical summary
            matter_obj = Matter(
                id=matter_id,
                banana=banana,
                matter_id=raw_matter_id,  # Raw vendor ID for reference
                matter_file=representative_item.matter_file,
                matter_type=representative_item.matter_type,
                title=representative_item.title,
                sponsors=getattr(representative_item, 'sponsors', []),
                canonical_summary=summary,
                canonical_topics=topics,
                attachments=representative_item.attachments,
                metadata={'attachment_hash': attachment_hash},
                first_seen=None,  # Will preserve existing if matter already exists
                last_seen=None,   # Will preserve existing if matter already exists
                appearance_count=len(items),
            )

            # Upsert canonical summary in city_matters (via repository)
            self.db.store_matter(matter_obj)

            # Step 2: Backfill ALL items atomically (via repository)
            item_ids = [item.id for item in items]
            self.db.items.bulk_update_item_summaries(
                item_ids=item_ids,
                summary=summary,
                topics=topics
            )

            logger.info(
                "atomically stored canonical summary and backfilled items",
                matter_id=matter_id,
                item_count=len(items)
            )

    def process_meeting(self, meeting: Meeting):
        """Process summary for a single meeting (agenda-first: items > packet)

        Args:
            meeting: Meeting object to process
        """
        try:
            # AGENDA-FIRST ARCHITECTURE: Check for items before packet_url
            agenda_items = self.db.get_agenda_items(meeting.id)

            if agenda_items:
                # Item-level processing (HTML agenda path) - PRIMARY PATH
                logger.info(
                    "found items for meeting",
                    item_count=len(agenda_items),
                    meeting_title=meeting.title
                )
                if not self.analyzer:
                    logger.warning("analyzer not available")
                    return
                self._process_meeting_with_items(meeting, agenda_items)

            elif meeting.packet_url:
                # Monolithic processing (PDF packet path) - FALLBACK PATH
                logger.info(
                    "processing packet as monolithic unit - no items found",
                    meeting_title=meeting.title
                )

                # Check cache
                cached = self.db.get_cached_summary(meeting.packet_url)
                if cached:
                    logger.debug(
                        "meeting already processed - skipping",
                        packet_url=meeting.packet_url
                    )
                    return

                if not self.analyzer:
                    logger.warning(
                        "skipping meeting - analyzer not available",
                        packet_url=meeting.packet_url
                    )
                    return

                meeting_data = {
                    "packet_url": meeting.packet_url,
                    "city_banana": meeting.banana,
                    "meeting_name": meeting.title,
                    "meeting_date": meeting.date.isoformat() if meeting.date else None,
                    "meeting_id": meeting.id,
                }
                result = self.analyzer.process_agenda_with_cache(meeting_data)
                if result.get("success"):
                    logger.info(
                        "processed packet",
                        packet_url=meeting.packet_url,
                        processing_time_seconds=round(result['processing_time'], 1)
                    )
                else:
                    logger.error(
                        "failed to process packet",
                        packet_url=meeting.packet_url,
                        error=result.get('error')
                    )

        except Exception as e:
            logger.error("error processing summary", packet_url=meeting.packet_url, error=str(e), error_type=type(e).__name__)

    # ========== Item Processing Helpers (extracted from 424-line God function) ==========

    def _extract_participation_info(self, meeting: Meeting) -> Dict[str, Any]:
        """Extract participation info from agenda_url (PDF or HTML)"""
        participation_data: Dict[str, Any] = {}

        if not meeting.agenda_url:
            return participation_data

        try:
            agenda_url_lower = meeting.agenda_url.lower()

            # Handle PDF agendas (Legistar, etc.)
            if agenda_url_lower.endswith('.pdf') or '.ashx' in agenda_url_lower:
                logger.debug("extracting text from agenda_url PDF for participation info")
                agenda_result = self.analyzer.pdf_extractor.extract_from_url(meeting.agenda_url)
                if agenda_result.get("success") and agenda_result.get("text"):
                    # Parse only first 5000 chars (participation info is at the top)
                    agenda_text = agenda_result["text"][:5000]
                    agenda_participation = parse_participation_info(agenda_text)
                    if agenda_participation:
                        participation_data.update(agenda_participation)
                        logger.info(
                            "found participation info in agenda_url PDF",
                            participation_fields=list(agenda_participation.keys())
                        )
                    # Free memory immediately
                    del agenda_result
                    del agenda_text

            # Handle HTML agendas (PrimeGov, Granicus, etc.) - already parsed by adapter
            elif meeting.participation:
                participation_data.update(meeting.participation)
                logger.debug(
                    "using existing participation from adapter",
                    participation_fields=list(meeting.participation.keys())
                )

        except (ExtractionError, OSError, IOError) as e:
            logger.warning("failed to extract participation from agenda_url", error=str(e), error_type=type(e).__name__)

        return participation_data

    def _filter_processed_items(self, agenda_items: List) -> tuple[List[Dict], List]:
        """Separate already-processed items from items needing processing"""
        already_processed = []
        need_processing = []

        for item in agenda_items:
            # Skip procedural items (low informational value)
            if is_procedural_item(item.title):
                logger.debug(
                    "skipping procedural item",
                    title=item.title[:50]
                )
                continue

            if not item.attachments:
                logger.debug(
                    "skipping item without attachments",
                    title=item.title[:50]
                )
                continue

            # MATTERS-FIRST DEDUPLICATION: Check if item has matter with canonical summary
            if item.matter_id:
                matter = self.db.get_matter(item.matter_id)

                if matter and matter.canonical_summary:
                    # Reuse canonical summary from matter
                    logger.debug(
                        "reusing canonical summary from matter",
                        title=item.title[:50],
                        matter=item.matter_file or item.matter_id
                    )

                    # Update item with canonical summary if not already set
                    if not item.summary:
                        self.db.update_agenda_item(
                            item_id=item.id,
                            summary=matter.canonical_summary,
                            topics=matter.canonical_topics or []
                        )

                    already_processed.append({
                        "sequence": item.sequence,
                        "title": item.title,
                        "summary": matter.canonical_summary,
                        "topics": matter.canonical_topics or [],
                    })
                    continue

            # Check if item already has summary (from previous processing)
            if item.summary:
                logger.debug("item already processed", title=item.title[:50])
                already_processed.append({
                    "sequence": item.sequence,
                    "title": item.title,
                    "summary": item.summary,
                    "topics": item.topics or [],
                })
            else:
                need_processing.append(item)

        return already_processed, need_processing

    def _build_document_cache(self, need_processing: List) -> tuple[Dict, Dict, set]:
        """Build meeting-level document cache with version filtering and deduplication

        Returns:
            tuple of (document_cache, item_attachments, shared_urls)
        """
        logger.info("building meeting-level document cache")
        document_cache = {}  # url -> {text, page_count, name}
        item_attachments = {}  # item_id -> list of URLs (after version filtering)

        # First pass: Per-item version filtering, then collect unique URLs
        all_urls = set()
        url_to_items = {}  # url -> list of item IDs that reference this URL
        url_to_name = {}  # url -> attachment name

        for item in need_processing:
            # Collect this item's attachment URLs
            item_urls = []
            for att in item.attachments:
                if isinstance(att, str):
                    att_url = att
                    att_type = "pdf"
                    att_name = ""
                elif isinstance(att, dict):
                    att_url = att.get("url")
                    att_type = att.get("type", "unknown")
                    att_name = att.get("name", "")
                else:
                    continue

                # Only process PDF/document/unknown types (not text segments)
                if att_type in ("pdf", "doc", "unknown") or isinstance(att, str):
                    if att_url:
                        item_urls.append(att_url)
                        # Track name for this URL
                        if att_name and att_url not in url_to_name:
                            url_to_name[att_url] = att_name

            # Apply version filtering WITHIN this item's attachments
            filtered_item_urls = self._filter_document_versions(item_urls)
            item_attachments[item.id] = filtered_item_urls

            # Track which items use which URLs (after filtering)
            for url in filtered_item_urls:
                all_urls.add(url)
                if url not in url_to_items:
                    url_to_items[url] = []
                url_to_items[url].append(item.id)

        logger.info("collected unique URLs", url_count=len(all_urls), item_count=len(need_processing))

        # Second pass: Extract each unique URL once
        for att_url in all_urls:
            # Skip public comment and parcel table attachments by name
            att_name = url_to_name.get(att_url, "")
            if att_name and is_public_comment_attachment(att_name):
                logger.info("skipping low-value attachment", attachment_name=att_name)
                continue

            try:
                result = self.analyzer.pdf_extractor.extract_from_url(att_url)
                if result.get("success") and result.get("text"):
                    # Post-extraction filter: Skip public comment compilations
                    if is_likely_public_comment_compilation(result, att_name or att_url):
                        logger.info(
                            "skipping public comment compilation",
                            attachment=att_name or att_url
                        )
                        continue

                    document_cache[att_url] = {
                        "text": result["text"],
                        "page_count": result.get("page_count", 0),
                        "name": att_name or att_url
                    }

                    item_count = len(url_to_items[att_url])
                    cache_status = "shared" if item_count > 1 else "unique"
                    logger.info(
                        "extracted document",
                        attachment=att_name or att_url,
                        pages=result.get('page_count', 0),
                        chars=len(result['text']),
                        cache_status=cache_status,
                        item_count=item_count
                    )
            except (ExtractionError, OSError, IOError) as e:
                logger.warning("failed to extract document", attachment=att_name or att_url, error=str(e), error_type=type(e).__name__)

        # Separate shared vs item-specific documents
        shared_urls = {url for url, items in url_to_items.items() if len(items) > 1 and url in document_cache}
        shared_count = len(shared_urls)
        unique_count = len([url for url in all_urls if url not in shared_urls and url in document_cache])

        logger.info(
            "cached documents",
            total_cached=len(document_cache),
            shared_count=shared_count,
            unique_count=unique_count
        )

        return document_cache, item_attachments, shared_urls

    def _build_batch_requests(
        self,
        need_processing: List,
        document_cache: Dict,
        item_attachments: Dict,
        shared_urls: set,
        participation_data: Dict[str, Any],
        first_sequence: Optional[int],
        last_sequence: Optional[int]
    ) -> tuple[List[Dict], Dict, List[str]]:
        """Build batch requests from cached documents

        Returns:
            tuple of (batch_requests, item_map, failed_items)
        """
        batch_requests = []
        item_map = {}
        failed_items = []

        for item in need_processing:
            try:
                # Check if entire item is public comments or parcel tables
                item_is_low_value = is_public_comment_attachment(item.title)

                if item_is_low_value:
                    logger.info(
                        "skipping entire item - low value content",
                        title=item.title[:80],
                        reason="public_comments_or_parcel_tables"
                    )
                    continue

                # Build item-specific text (exclude shared documents)
                item_specific_parts = []
                total_page_count = 0

                # Use filtered URLs for this item (after version filtering)
                for att_url in item_attachments.get(item.id, []):
                    # Skip shared documents (they're in meeting context)
                    if att_url in shared_urls:
                        continue

                    # Include item-specific documents only
                    if att_url in document_cache:
                        doc = document_cache[att_url]
                        item_specific_parts.append(f"=== {doc['name']} ===\n{doc['text']}")
                        total_page_count += doc['page_count']

                # Also include text segments from item.attachments
                for att in item.attachments:
                    if isinstance(att, dict) and att.get("type") == "text_segment":
                        text_content = att.get("content", "")
                        if text_content:
                            item_specific_parts.append(text_content)

                if item_specific_parts:
                    combined_text = "\n\n".join(item_specific_parts)

                    # Extract participation info from first or last item
                    if item.sequence == first_sequence or item.sequence == last_sequence:
                        item_participation = parse_participation_info(combined_text)
                        if item_participation:
                            logger.debug(
                                "found participation info in item",
                                sequence=item.sequence,
                                participation_fields=list(item_participation.keys())
                            )
                            participation_data.update(item_participation)

                    batch_requests.append({
                        "item_id": item.id,
                        "title": item.title,
                        "text": combined_text,
                        "sequence": item.sequence,
                        "page_count": total_page_count if total_page_count > 0 else None,
                    })
                    item_map[item.id] = item
                    logger.debug(
                        "prepared item for batch processing",
                        title=item.title[:50],
                        chars=len(combined_text),
                        pages=total_page_count
                    )
                else:
                    logger.warning(
                        "no text extracted for item",
                        title=item.title[:50]
                    )
                    failed_items.append(item.title)

            except (ProcessingError, KeyError, AttributeError, TypeError) as e:
                logger.error(
                    "error extracting text for item",
                    title=item.title[:50],
                    error=str(e)
                )
                failed_items.append(item.title)

        return batch_requests, item_map, failed_items

    def _process_batch_incrementally(
        self,
        batch_requests: List[Dict],
        item_map: Dict,
        shared_context: Optional[str],
        meeting_id: str
    ) -> tuple[List[Dict], List[str]]:
        """Process batch requests incrementally, saving after each chunk

        Returns:
            tuple of (processed_items, failed_items)
        """
        processed_items = []
        failed_items = []

        if not batch_requests:
            return processed_items, failed_items

        logger.info(
            "submitting batch to Gemini",
            item_count=len(batch_requests)
        )

        # Process batch as generator - yields chunk results as they complete
        for chunk_results in self.analyzer.process_batch_items(
            batch_requests,
            shared_context=shared_context,
            meeting_id=meeting_id
        ):
            logger.info(
                "saving results from completed chunk",
                result_count=len(chunk_results)
            )

            for result in chunk_results:
                item_id = result["item_id"]
                item = item_map.get(item_id)

                if not item:
                    logger.warning("no item mapping found", item_id=item_id)
                    continue

                if result["success"]:
                    # Normalize topics before storing
                    raw_topics = result.get("topics", [])
                    normalized_topics = get_normalizer().normalize(raw_topics)

                    logger.debug(
                        "normalized topics",
                        raw_topics=raw_topics,
                        normalized_topics=normalized_topics
                    )

                    # Update item in database IMMEDIATELY with normalized topics
                    self.db.update_agenda_item(
                        item_id=item_id,
                        summary=result["summary"],
                        topics=normalized_topics,
                    )

                    processed_items.append({
                        "sequence": item.sequence,
                        "title": item.title,
                        "summary": result["summary"],
                        "topics": normalized_topics,
                    })

                    logger.info("item saved", title=item.title[:60])
                else:
                    failed_items.append(item.title)
                    logger.warning(
                        "item processing failed",
                        title=item.title[:60],
                        error=result.get('error')
                    )

        return processed_items, failed_items

    def _aggregate_meeting_topics(self, processed_items: List[Dict]) -> List[str]:
        """Aggregate topics from processed items, sorted by frequency"""
        # Collect all topics from all items
        all_topics = []
        for item in processed_items:
            all_topics.extend(item.get("topics", []))

        # Count topic frequency and sort by frequency (most common first)
        topic_counts = {}
        for topic in all_topics:
            topic_counts[topic] = topic_counts.get(topic, 0) + 1

        meeting_topics = sorted(
            topic_counts.keys(), key=lambda t: topic_counts[t], reverse=True
        )

        logger.info(
            "aggregated meeting topics",
            unique_topic_count=len(meeting_topics),
            item_count=len(processed_items),
            topics=meeting_topics
        )

        return meeting_topics

    # ========== Main Item Processing Method (refactored) ==========

    def _process_meeting_with_items(self, meeting: Meeting, agenda_items: List):
        """Process meeting at item-level granularity using batch API (REFACTORED)

        Orchestrates 7 focused phases via helper methods:
        1. Extract participation info
        2. Filter already-processed items
        3. Build document cache (deduplication + version filtering)
        4. Build shared context for batch API
        5. Build batch requests
        6. Process batch incrementally (save after each chunk)
        7. Aggregate topics and update meeting

        Args:
            meeting: Meeting object
            agenda_items: List of AgendaItem objects
        """
        start_time = time.time()

        if not self.analyzer:
            logger.warning("[ItemProcessing] Analyzer not available")
            return

        # Determine first and last item sequences for participation extraction
        item_sequences = [item.sequence for item in agenda_items]
        first_sequence = min(item_sequences) if item_sequences else None
        last_sequence = max(item_sequences) if item_sequences else None

        # PHASE 1: Extract participation info from agenda_url
        participation_data = self._extract_participation_info(meeting)

        # PHASE 2: Filter already-processed items from those needing processing
        already_processed, need_processing = self._filter_processed_items(agenda_items)
        processed_items = already_processed  # Start with pre-processed items

        if not need_processing:
            logger.info(
                "all items already processed",
                item_count=len(already_processed)
            )
        else:
            logger.info(
                "extracting text from items for batch processing",
                item_count=len(need_processing)
            )

            # PHASE 3: Build document cache with deduplication
            document_cache, item_attachments, shared_urls = self._build_document_cache(need_processing)

            # PHASE 4: Build shared context for batch API (if shared documents exist)
            shared_context = None
            if shared_urls:
                shared_parts = []
                shared_token_count = 0
                for url in sorted(shared_urls):  # Sort for consistency
                    doc = document_cache[url]
                    shared_parts.append(f"=== {doc['name']} ===\n{doc['text']}")
                    shared_token_count += len(doc['text']) // 4  # Rough token estimate

                shared_context = "\n\n".join(shared_parts)
                logger.info(
                    "built meeting-level shared context",
                    chars=len(shared_context),
                    estimated_tokens=shared_token_count,
                    shared_document_count=len(shared_urls)
                )

            # PHASE 5: Build batch requests from cached documents
            batch_requests, item_map, failed_items = self._build_batch_requests(
                need_processing,
                document_cache,
                item_attachments,
                shared_urls,
                participation_data,
                first_sequence,
                last_sequence
            )

            # PHASE 6: Process batch incrementally, saving after each chunk
            if batch_requests:
                new_processed, new_failed = self._process_batch_incrementally(
                    batch_requests,
                    item_map,
                    shared_context,
                    meeting.id
                )
                processed_items.extend(new_processed)
                failed_items.extend(new_failed)

                # Cleanup: free batch memory immediately
                del batch_requests

        # PHASE 7: Aggregate topics and update meeting metadata
        if processed_items and self.analyzer:
            meeting_topics = self._aggregate_meeting_topics(processed_items)

            # Merge participation data from items with existing meeting participation
            merged_participation = None
            if participation_data or meeting.participation:
                merged_participation = meeting.participation.copy() if meeting.participation else {}
                if participation_data:
                    merged_participation.update(participation_data)
                    logger.info(
                        "updated meeting with participation info from items",
                        participation_fields=list(participation_data.keys())
                    )

            # Update meeting with metadata only (items have their own summaries)
            processing_time = time.time() - start_time
            with transaction(self.db.conn):
                self.db.update_meeting_summary(
                    meeting_id=meeting.id,
                    summary=None,  # No concatenated summary - frontend composes from items
                    processing_method=f"item_level_{len(processed_items)}_items",
                    processing_time=processing_time,
                    topics=meeting_topics,
                    participation=merged_participation,
                )

            logger.info(
                "item processing completed",
                processed_count=len(processed_items),
                failed_count=len(failed_items) if 'failed_items' in locals() else 0,
                processing_time_seconds=round(processing_time, 1)
            )
        else:
            logger.warning("no items could be processed")
