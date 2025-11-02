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
from typing import List, Optional

from database.db import UnifiedDatabase, Meeting
from pipeline.analyzer import Analyzer
from analysis.topics.normalizer import get_normalizer
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


def is_procedural_item(title: str) -> bool:
    """Check if agenda item is procedural (skip to save API costs)"""
    title_lower = title.lower()
    return any(pattern in title_lower for pattern in PROCEDURAL_PATTERNS)


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

            # STEP 1: Extract text from all items (pre-batch)
            batch_requests = []
            item_map = {}

            for item in need_processing:
                try:
                    # Extract text from all attachments for this item
                    all_text_parts = []
                    total_page_count = 0

                    for att in item.attachments:
                        # Handle both plain URL strings and structured attachment objects
                        if isinstance(att, str):
                            # Plain URL string (Legistar format)
                            att_url = att
                            att_name = "Attachment"
                            att_type = "pdf"
                        elif isinstance(att, dict):
                            # Structured attachment object
                            att_type = att.get("type", "unknown")
                            att_url = att.get("url")
                            att_name = att.get("name", "Attachment")
                        else:
                            logger.warning(
                                f"[ItemProcessing] Unknown attachment format: {type(att)}"
                            )
                            continue

                        # Text segment (from detected items)
                        if att_type == "text_segment":
                            text_content = att.get("content", "") if isinstance(att, dict) else ""
                            if text_content:
                                all_text_parts.append(text_content)

                        # PDF/URL attachment (from Legistar or structured)
                        # Treat unknown types as PDFs if they have a URL (defensive coding)
                        elif att_type in ("pdf", "unknown") or isinstance(att, str):
                            if att_url:
                                try:
                                    result = self.analyzer.pdf_extractor.extract_from_url(
                                        att_url
                                    )
                                    if result.get("success") and result.get("text"):
                                        all_text_parts.append(
                                            f"=== {att_name} ===\n{result['text']}"
                                        )
                                        # Accumulate actual page counts from PDFs
                                        total_page_count += result.get("page_count", 0)
                                        logger.debug(
                                            f"[ItemProcessing] Extracted {len(result['text'])} chars, {result.get('page_count', 0)} pages from {att_name}"
                                        )
                                    else:
                                        logger.warning(
                                            f"[ItemProcessing] No text from {att_name}"
                                        )
                                except Exception as e:
                                    logger.warning(
                                        f"[ItemProcessing] Failed to extract from {att_name}: {e}"
                                    )

                    if all_text_parts:
                        combined_text = "\n\n".join(all_text_parts)
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
                            f"[ItemProcessing] Prepared {item.title[:50]} ({len(combined_text)} chars, {total_page_count} pages)"
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

            # STEP 2: Batch process all items at once (50% cost savings)
            if batch_requests:
                logger.info(
                    f"[ItemProcessing] Submitting batch with {len(batch_requests)} items to Gemini"
                )
                batch_results = self.analyzer.process_batch_items(batch_requests)

                # STEP 3: Store all results
                for result in batch_results:
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

                        # Update item in database with normalized topics
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

                        logger.info(f"[ItemProcessing] {item.title[:60]}")
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

            # Update meeting with metadata only (items have their own summaries)
            processing_time = time.time() - start_time
            self.db.update_meeting_summary(
                meeting_id=meeting.id,
                summary=None,  # No concatenated summary - frontend composes from items
                processing_method=f"item_level_{len(processed_items)}_items",
                processing_time=processing_time,
                topics=meeting_topics,
            )

            logger.info(
                f"[ItemProcessing] Completed: {len(processed_items)} items processed, "
                f"{len(failed_items)} failed in {processing_time:.1f}s"
            )
        else:
            logger.warning("[ItemProcessing] No items could be processed")
