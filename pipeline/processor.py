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

import logging
import time
from typing import List, Optional, Dict, Any

from database.db import UnifiedDatabase, Meeting
from pipeline.analyzer import Analyzer
from analysis.topics.normalizer import get_normalizer
from parsing.participation import parse_participation_info
from config import config

logger = logging.getLogger("engagic")

# Procedural items to skip (low informational value)
# Focus on substantive policy, not administrative overhead
PROCEDURAL_PATTERNS = [
    "review of minutes",
    "approval of minutes",
    "adopt minutes",
    "roll call",
    "pledge of allegiance",
    "invocation",
    "adjournment",
]

# Public comment attachment patterns (high token cost, low signal)
# These attachments often contain hundreds of pages of form letters
# Built from cross-city analysis of SF, LA, Palo Alto, Santa Clara, Oakland
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
]


def is_procedural_item(title: str) -> bool:
    """Check if agenda item is procedural (skip to save API costs)"""
    title_lower = title.lower()
    return any(pattern in title_lower for pattern in PROCEDURAL_PATTERNS)


def is_public_comment_attachment(name: str) -> bool:
    """Check if attachment is public comments (high token cost, low signal)"""
    name_lower = name.lower()
    return any(pattern in name_lower for pattern in PUBLIC_COMMENT_PATTERNS)


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
                logger.info("[Processor] Initialized with LLM analyzer")
            except ValueError:
                logger.warning(
                    "[Processor] LLM analyzer not available - summaries will be skipped"
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

    def process_queue(self):
        """Process jobs from the processing queue continuously"""
        logger.info("[Processor] Starting queue processor...")

        while self.is_running:
            try:
                # Get next job from queue
                job = self.db.get_next_for_processing()

                if not job:
                    # No jobs available, sleep briefly
                    time.sleep(5)
                    continue

                queue_id = job["id"]
                source_url = job["source_url"]
                meeting_id = job["meeting_id"]

                logger.info(f"[Processor] Processing queue job {queue_id}: {source_url}")

                try:
                    # Get meeting from database
                    meeting = self.db.get_meeting(meeting_id)
                    if not meeting:
                        self.db.mark_processing_failed(
                            queue_id, "Meeting not found in database"
                        )
                        continue

                    # Use item-aware processing path
                    if self.analyzer:
                        try:
                            self.process_meeting(meeting)
                            self.db.mark_processing_complete(queue_id)
                            logger.info(
                                f"[Processor] Queue job {queue_id} completed successfully"
                            )
                        except Exception as e:
                            error_msg = str(e)
                            self.db.mark_processing_failed(queue_id, error_msg)
                            logger.error(
                                f"[Processor] Queue job {queue_id} failed: {error_msg}"
                            )
                    else:
                        self.db.mark_processing_failed(
                            queue_id, "Analyzer not available", increment_retry=False
                        )
                        logger.warning(
                            f"[Processor] Skipping queue job {queue_id} - analyzer not available"
                        )

                except Exception as e:
                    error_msg = str(e)
                    self.db.mark_processing_failed(queue_id, error_msg)
                    logger.error(f"[Processor] Error processing queue job {queue_id}: {e}")
                    # Sleep briefly on error to avoid tight loop
                    time.sleep(2)

            except Exception as e:
                logger.error(f"[Processor] Queue processor error: {e}")
                # Sleep on error to avoid tight loop
                time.sleep(10)

    def process_city_jobs(self, city_banana: str) -> dict:
        """Process all queued jobs for a specific city

        Args:
            city_banana: City identifier

        Returns:
            Dictionary with processing stats
        """
        logger.info(f"[Processor] Processing queued jobs for {city_banana}...")
        processed_count = 0
        failed_count = 0

        while True:
            # Get next job for this city
            job = self.db.get_next_for_processing(banana=city_banana)

            if not job:
                break  # No more jobs for this city

            queue_id = job["id"]
            meeting_id = job["meeting_id"]
            source_url = job["source_url"]

            logger.info(f"[Processor] Processing job {queue_id}: {source_url}")

            try:
                meeting = self.db.get_meeting(meeting_id)
                if not meeting:
                    self.db.mark_processing_failed(queue_id, "Meeting not found")
                    failed_count += 1
                    continue

                # Process the meeting (item-aware)
                self.process_meeting(meeting)
                self.db.mark_processing_complete(queue_id)
                processed_count += 1
                logger.info(f"[Processor] Processed {source_url}")

            except Exception as e:
                error_msg = str(e)
                self.db.mark_processing_failed(queue_id, error_msg)
                failed_count += 1
                logger.error(f"[Processor] Failed to process {source_url}: {e}")

        logger.info(
            f"[Processor] Processing complete for {city_banana}: "
            f"{processed_count} succeeded, {failed_count} failed"
        )

        return {
            "processed_count": processed_count,
            "failed_count": failed_count,
        }

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
                    f"[ItemProcessing] Found {len(agenda_items)} items for {meeting.title}"
                )
                if not self.analyzer:
                    logger.warning("[ItemProcessing] Analyzer not available")
                    return
                self._process_meeting_with_items(meeting, agenda_items)

            elif meeting.packet_url:
                # Monolithic processing (PDF packet path) - FALLBACK PATH
                logger.info(
                    f"[MonolithicProcessing] No items for {meeting.title}, processing packet as single unit"
                )

                # Check cache
                cached = self.db.get_cached_summary(meeting.packet_url)
                if cached:
                    logger.debug(
                        f"Meeting {meeting.packet_url} already processed, skipping"
                    )
                    return

                if not self.analyzer:
                    logger.warning(
                        f"Skipping {meeting.packet_url} - analyzer not available"
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
                        f"Processed {meeting.packet_url} in {result['processing_time']:.1f}s"
                    )
                else:
                    logger.error(
                        f"Failed to process {meeting.packet_url}: {result.get('error')}"
                    )

        except Exception as e:
            logger.error(f"Error processing summary for {meeting.packet_url}: {e}")

    def _process_meeting_with_items(self, meeting: Meeting, agenda_items: List):
        """Process a meeting at item-level granularity using batch API

        Args:
            meeting: Meeting object
            agenda_items: List of AgendaItem objects
        """
        start_time = time.time()
        processed_items = []
        failed_items = []

        if not self.analyzer:
            logger.warning("[ItemProcessing] Analyzer not available")
            return

        # Determine first and last item sequences for participation extraction
        item_sequences = [item.sequence for item in agenda_items]
        first_sequence = min(item_sequences) if item_sequences else None
        last_sequence = max(item_sequences) if item_sequences else None

        # Collect participation info from agenda_url (if it's a PDF) and first/last items
        participation_data: Dict[str, Any] = {}

        # STEP 0: Extract participation from agenda_url (PDF or HTML)
        if meeting.agenda_url:
            try:
                agenda_url_lower = meeting.agenda_url.lower()

                # Handle PDF agendas (Legistar, etc.)
                if agenda_url_lower.endswith('.pdf') or '.ashx' in agenda_url_lower:
                    logger.debug("[Participation] Extracting text from agenda_url PDF for participation info")
                    agenda_result = self.analyzer.pdf_extractor.extract_from_url(meeting.agenda_url)
                    if agenda_result.get("success") and agenda_result.get("text"):
                        # Parse only first 5000 chars (participation info is at the top)
                        agenda_text = agenda_result["text"][:5000]
                        agenda_participation = parse_participation_info(agenda_text)
                        if agenda_participation:
                            participation_data.update(agenda_participation)
                            logger.info(
                                f"[Participation] Found info in agenda_url PDF: {list(agenda_participation.keys())}"
                            )
                        # Free memory immediately
                        del agenda_result
                        del agenda_text

                # Handle HTML agendas (PrimeGov, Granicus, etc.) - already parsed by adapter
                # If meeting.participation already exists from adapter, use it
                elif meeting.participation:
                    participation_data.update(meeting.participation)
                    logger.debug(
                        f"[Participation] Using existing participation from adapter: {list(meeting.participation.keys())}"
                    )

            except Exception as e:
                logger.warning(f"[Participation] Failed to extract from agenda_url: {e}")

        # Separate already-processed items from items that need processing
        already_processed = []
        need_processing = []

        for item in agenda_items:
            # Skip procedural items (low informational value)
            if is_procedural_item(item.title):
                logger.debug(
                    f"[ItemProcessing] Skipping procedural item: {item.title[:50]}"
                )
                continue

            if not item.attachments:
                logger.debug(
                    f"[ItemProcessing] Skipping item without attachments: {item.title[:50]}"
                )
                continue

            if item.summary:
                logger.debug(f"[ItemProcessing] Item already processed: {item.title[:50]}")
                already_processed.append(
                    {
                        "sequence": item.sequence,
                        "title": item.title,
                        "summary": item.summary,
                        "topics": item.topics or [],
                    }
                )
            else:
                need_processing.append(item)

        # Add already-processed to results
        processed_items.extend(already_processed)

        if not need_processing:
            logger.info(
                f"[ItemProcessing] All {len(already_processed)} items already processed"
            )
        else:
            logger.info(
                f"[ItemProcessing] Extracting text from {len(need_processing)} items for batch processing"
            )

            # STEP 1: Build meeting-level document cache (item-first architecture)
            logger.info("[DocumentCache] Building meeting-level document cache...")
            document_cache = {}  # url -> {text, page_count, name}
            item_attachments = {}  # item_id -> list of URLs (after version filtering)

            # First pass: Per-item version filtering, then collect unique URLs
            all_urls = set()
            url_to_items = {}  # url -> list of item IDs that reference this URL

            for item in need_processing:
                # Collect this item's attachment URLs
                item_urls = []
                for att in item.attachments:
                    if isinstance(att, str):
                        att_url = att
                        att_type = "pdf"
                    elif isinstance(att, dict):
                        att_url = att.get("url")
                        att_type = att.get("type", "unknown")
                    else:
                        continue

                    # Only process PDF/unknown types (not text segments)
                    if att_type in ("pdf", "unknown") or isinstance(att, str):
                        if att_url:
                            item_urls.append(att_url)

                # Apply version filtering WITHIN this item's attachments
                filtered_item_urls = self._filter_document_versions(item_urls)
                item_attachments[item.id] = filtered_item_urls

                # Track which items use which URLs (after filtering)
                for url in filtered_item_urls:
                    all_urls.add(url)
                    if url not in url_to_items:
                        url_to_items[url] = []
                    url_to_items[url].append(item.id)

            logger.info(f"[DocumentCache] Collected {len(all_urls)} unique URLs across {len(need_processing)} items")

            # Second pass: Extract each unique URL once
            for att_url in all_urls:
                # Skip public comment attachments
                url_path = att_url.split('/')[-1] if att_url else ""
                if is_public_comment_attachment(url_path):
                    logger.debug(f"[DocumentCache] Skipping public comments: {url_path}")
                    continue

                try:
                    result = self.analyzer.pdf_extractor.extract_from_url(att_url)
                    if result.get("success") and result.get("text"):
                        document_cache[att_url] = {
                            "text": result["text"],
                            "page_count": result.get("page_count", 0),
                            "name": url_path
                        }

                        item_count = len(url_to_items[att_url])
                        cache_status = "shared" if item_count > 1 else "unique"
                        logger.info(
                            f"[DocumentCache] Extracted '{url_path}': "
                            f"{result.get('page_count', 0)} pages, "
                            f"{len(result['text']):,} chars "
                            f"({cache_status}, {item_count} items)"
                        )
                except Exception as e:
                    logger.warning(f"[DocumentCache] Failed to extract {url_path}: {e}")

            # Separate shared vs item-specific documents
            shared_urls = {url for url, items in url_to_items.items() if len(items) > 1 and url in document_cache}
            shared_count = len(shared_urls)
            unique_count = len([url for url in all_urls if url not in shared_urls and url in document_cache])

            logger.info(
                f"[DocumentCache] Cached {len(document_cache)} documents: "
                f"{shared_count} shared, {unique_count} item-specific"
            )

            # Build shared context for caching (if any shared documents exist)
            shared_context = None
            shared_token_count = 0
            if shared_urls:
                shared_parts = []
                for url in sorted(shared_urls):  # Sort for consistency
                    doc = document_cache[url]
                    shared_parts.append(f"=== {doc['name']} ===\n{doc['text']}")
                    shared_token_count += len(doc['text']) // 4  # Rough token estimate

                shared_context = "\n\n".join(shared_parts)
                logger.info(
                    f"[SharedContext] Built meeting-level context: "
                    f"{len(shared_context):,} chars (~{shared_token_count:,} tokens) "
                    f"from {len(shared_urls)} shared documents"
                )

            # STEP 2: Build batch requests using cached documents
            batch_requests = []
            item_map = {}

            for item in need_processing:
                try:
                    # Check if entire item is public comments (e.g., "Petitions and Communications")
                    # If so, skip all its attachments
                    item_is_public_comments = is_public_comment_attachment(item.title)

                    if item_is_public_comments:
                        logger.info(
                            f"[ItemFilter] Skipping entire item (public comments): {item.title[:80]}"
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
                                    f"[Participation] Found in item {item.sequence}: {list(item_participation.keys())}"
                                )
                                # Merge with existing participation data (later items override earlier)
                                participation_data.update(item_participation)

                        batch_requests.append(
                            {
                                "item_id": item.id,
                                "title": item.title,
                                "text": combined_text,
                                "sequence": item.sequence,
                                "page_count": total_page_count if total_page_count > 0 else None,
                            }
                        )
                        item_map[item.id] = item
                        logger.debug(
                            f"[ItemProcessing] Prepared {item.title[:50]} ({len(combined_text):,} chars, {total_page_count} pages)"
                        )
                    else:
                        logger.warning(
                            f"[ItemProcessing] No text extracted for {item.title[:50]}"
                        )
                        failed_items.append(item.title)

                except Exception as e:
                    logger.error(
                        f"[ItemProcessing] Error extracting text for {item.title[:50]}: {e}"
                    )
                    failed_items.append(item.title)

            # STEP 2: Batch process all items, saving incrementally after each chunk
            if batch_requests:
                logger.info(
                    f"[ItemProcessing] Submitting batch with {len(batch_requests)} items to Gemini"
                )

                # Process batch as generator - yields chunk results as they complete
                for chunk_results in self.analyzer.process_batch_items(
                    batch_requests,
                    shared_context=shared_context,
                    meeting_id=meeting.id
                ):
                    # STEP 3: Save chunk results immediately (incremental saving)
                    logger.info(
                        f"[ItemProcessing] Saving {len(chunk_results)} results from completed chunk"
                    )

                    for result in chunk_results:
                        item_id = result["item_id"]
                        item = item_map.get(item_id)

                        if not item:
                            logger.warning(f"[ItemProcessing] No item mapping for {item_id}")
                            continue

                        if result["success"]:
                            # Normalize topics before storing
                            raw_topics = result.get("topics", [])
                            normalized_topics = get_normalizer().normalize(raw_topics)

                            logger.debug(
                                f"[TopicNormalization] {raw_topics} -> {normalized_topics}"
                            )

                            # Update item in database IMMEDIATELY with normalized topics
                            self.db.update_agenda_item(
                                item_id=item_id,
                                summary=result["summary"],
                                topics=normalized_topics,
                            )

                            processed_items.append(
                                {
                                    "sequence": item.sequence,
                                    "title": item.title,
                                    "summary": result["summary"],
                                    "topics": normalized_topics,
                                }
                            )

                            logger.info(f"[ItemProcessing] SAVED {item.title[:60]}")
                        else:
                            failed_items.append(item.title)
                            logger.warning(
                                f"[ItemProcessing] FAILED {item.title[:60]}: {result.get('error')}"
                            )

                # Cleanup: free batch memory immediately
                del batch_requests

        # Aggregate topics from items (for meeting-level filtering)
        # Frontend handles item display - no concatenation needed
        if processed_items and self.analyzer:
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
                f"[TopicAggregation] Aggregated {len(meeting_topics)} unique topics "
                f"from {len(processed_items)} items: {meeting_topics}"
            )

            # Merge participation data from items with existing meeting participation
            merged_participation = None
            if participation_data or meeting.participation:
                merged_participation = meeting.participation.copy() if meeting.participation else {}
                if participation_data:
                    merged_participation.update(participation_data)
                    logger.info(
                        f"[Participation] Updated meeting with info from items: {list(participation_data.keys())}"
                    )

            # Update meeting with metadata only (items have their own summaries)
            processing_time = time.time() - start_time
            self.db.update_meeting_summary(
                meeting_id=meeting.id,
                summary=None,  # No concatenated summary - frontend composes from items
                processing_method=f"item_level_{len(processed_items)}_items",
                processing_time=processing_time,
                topics=meeting_topics,
                participation=merged_participation,
            )

            logger.info(
                f"[ItemProcessing] Completed: {len(processed_items)} items processed, "
                f"{len(failed_items)} failed in {processing_time:.1f}s"
            )
        else:
            logger.warning("[ItemProcessing] No items could be processed")
