import logging
import time
import random
import os
from datetime import datetime
from typing import Dict, List, Any, Optional
from concurrent.futures import ThreadPoolExecutor
import threading
from dataclasses import dataclass
from enum import Enum
from collections import defaultdict

from infocore.database import UnifiedDatabase, City, Meeting
from infocore.processing.processor import AgendaProcessor
from infocore.processing.topic_normalizer import get_normalizer
from infocore.adapters.all_adapters import (
    PrimeGovAdapter,
    CivicClerkAdapter,
    LegistarAdapter,
    GranicusAdapter,
    NovusAgendaAdapter,
    CivicPlusAdapter,
)
from infocore.config import config

logger = logging.getLogger("engagic")

# Memory monitoring
try:
    import psutil

    PSUTIL_AVAILABLE = True
except ImportError:
    PSUTIL_AVAILABLE = False
    logger.warning("psutil not available - memory monitoring disabled")


def log_memory_usage(context: str = ""):
    """Log current memory usage in MB"""
    if not PSUTIL_AVAILABLE:
        return
    try:
        process = psutil.Process(os.getpid())
        mem_info = process.memory_info()
        mem_mb = mem_info.rss / 1024 / 1024
        logger.info(f"[Memory] {context}: {mem_mb:.1f}MB RSS")
    except Exception as e:
        logger.debug(f"[Memory] Failed to log: {e}")


class RateLimiter:
    """Vendor-aware rate limiter to be respectful to city websites"""

    def __init__(self):
        self.last_request = defaultdict(float)
        self.lock = threading.Lock()

    def wait_if_needed(self, vendor: str):
        """Enforce minimum delay between requests to same vendor"""
        delays = {
            "primegov": 3.0,  # PrimeGov cities
            "granicus": 4.0,  # Granicus/Legistar cities
            "civicclerk": 3.0,  # CivicClerk cities
            "legistar": 3.0,  # Direct Legistar
            "civicplus": 4.0,  # CivicPlus cities
            "novusagenda": 4.0,  # NovusAgenda cities
            "unknown": 5.0,  # Unknown vendors get longest delay
        }

        min_delay = delays.get(vendor, 5.0)

        with self.lock:
            now = time.time()
            last = self.last_request[vendor]

            if last > 0:
                elapsed = now - last
                if elapsed < min_delay:
                    sleep_time = min_delay - elapsed + random.uniform(0, 1)
                    logger.info(f"Rate limiting {vendor}: sleeping {sleep_time:.1f}s")
                    time.sleep(sleep_time)

            self.last_request[vendor] = time.time()


class SyncStatus(Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass
class SyncResult:
    city_banana: str
    status: SyncStatus
    meetings_found: int = 0
    meetings_processed: int = 0
    duration_seconds: float = 0.0
    error_message: Optional[str] = None


class Conductor:
    def __init__(self, unified_db_path: Optional[str] = None):
        # Use config path if not provided
        db_path = unified_db_path or config.UNIFIED_DB_PATH

        self.db = UnifiedDatabase(db_path)
        self.processor = None
        self.is_running = False
        self.sync_thread = None
        self.processing_thread = None
        self.max_workers = 1  # Reduced to 1 for polite scraping
        self.rate_limiter = RateLimiter()  # Add rate limiter

        # Initialize LLM processor if available
        try:
            self.processor = AgendaProcessor(api_key=config.get_api_key())
            logger.info("Background processor initialized with LLM capabilities")
        except ValueError:
            logger.warning("LLM processor not available - summaries will be skipped")

        # Track sync status - use limited-size dict to prevent memory growth
        self.current_sync_status = {}
        self.last_full_sync = None
        self.sync_lock = threading.Lock()
        self.max_sync_status_entries = 100  # Limit status tracking
        self.failed_cities = set()  # Track cities that failed to sync

    def start(self):
        """Start background processing threads"""
        if self.is_running:
            logger.warning("Background processor already running")
            return

        logger.info("Starting background processor...")
        self.is_running = True

        # Start sync thread (runs every 7 days)
        self.sync_thread = threading.Thread(target=self._sync_loop, daemon=True)
        self.sync_thread.start()

        # Start processing thread (continuously processes jobs from the queue)
        self.processing_thread = threading.Thread(
            target=self._processing_loop, daemon=True
        )
        self.processing_thread.start()

        logger.info("Background processor started")

    def stop(self):
        """Stop background processing"""
        logger.info("Stopping background processor...")
        self.is_running = False

        if self.sync_thread:
            self.sync_thread.join(timeout=30)
        if self.processing_thread:
            self.processing_thread.join(timeout=30)

        logger.info("Background processor stopped")

    def _sync_loop(self):
        """Main sync loop - runs every 7 days"""
        while self.is_running:
            try:
                # Run full sync
                self._run_full_sync()

                # Sleep for 7 days
                for _ in range(7 * 24 * 60 * 60):  # 7 days in seconds
                    if not self.is_running:
                        break
                    time.sleep(1)

            except Exception as e:
                logger.error(f"Sync loop error: {e}")
                # Sleep for 2 days on error
                for _ in range(2 * 24 * 60 * 60):
                    if not self.is_running:
                        break
                    time.sleep(1)

    def _processing_loop(self):
        """Processing loop - continuously processes jobs from the queue (Phase 4)"""
        if not self.processor:
            logger.warning("Processor not available - processing loop will not run")
            return

        try:
            # Run the queue processor continuously
            self._process_queue()
        except Exception as e:
            logger.error(f"Processing loop error: {e}")
            # Processing loop will be restarted by daemon if it crashes

    def _run_full_sync(self):
        """Run full sync of all cities with vendor-aware rate limiting"""
        start_time = time.time()
        logger.info("Starting polite city sync...")

        # Clean up sync status to prevent memory growth (no lock needed)
        if len(self.current_sync_status) > self.max_sync_status_entries:
            self.current_sync_status = {}

        # Clear failed cities from previous run
        self.failed_cities.clear()

        cities = self.db.get_cities(status="active")
        logger.info(f"Syncing {len(cities)} cities with rate limiting...")

        # Group cities by vendor for polite crawling (only supported vendors)
        supported_vendors = {
            "primegov",
            "civicclerk",
            "legistar",
            "granicus",
            "novusagenda",
            "civicplus",
        }
        by_vendor = {}
        skipped_count = 0

        for city in cities:
            vendor = city.vendor
            if vendor in supported_vendors:
                by_vendor.setdefault(vendor, []).append(city)
            else:
                skipped_count += 1
                logger.debug(
                    f"Skipping city {city.name} with unsupported vendor: {vendor}"
                )

        total_supported = sum(
            len(vendor_cities) for vendor_cities in by_vendor.values()
        )
        logger.info(
            f"Processing {total_supported} cities with supported adapters, "
            f"skipping {skipped_count} unsupported"
        )

        results = []

        # Process each vendor group sequentially with proper delays
        for vendor, vendor_cities in by_vendor.items():
            if not self.is_running:
                break

            # Sort cities by sync priority (high activity first)
            sorted_cities = self._prioritize_cities(vendor_cities)
            logger.info(
                f"Syncing {len(sorted_cities)} {vendor} cities "
                f"(prioritized by activity)"
            )

            for city in sorted_cities:
                if not self.is_running:
                    break

                # Check if city needs syncing based on frequency
                if not self._should_sync_city(city):
                    logger.debug(f"Skipping {city.name} - doesn't need sync yet")
                    results.append(
                        SyncResult(
                            city_banana=city.banana,
                            status=SyncStatus.SKIPPED,
                            error_message="Not due for sync based on frequency",
                        )
                    )
                    continue

                # Apply rate limiting before sync
                self.rate_limiter.wait_if_needed(vendor)

                # Sync with retry logic
                result = self._sync_city_with_retry(city)
                logger.info(f"Sync completed for {city.banana}: {result.status}")
                results.append(result)

                # Track failed cities
                if result.status == SyncStatus.FAILED:
                    self.failed_cities.add(city.banana)

                # Log memory every 10 cities to track leak fixes
                if len(results) % 10 == 0:
                    log_memory_usage(f"After {len(results)} cities")

            # Break between vendor groups to be extra polite
            if vendor_cities:  # Only sleep if we processed cities
                vendor_break = 30 + random.uniform(0, 10)  # 30-40 seconds
                logger.info(
                    f"Completed {vendor} cities, taking {vendor_break:.1f}s break..."
                )
                log_memory_usage(f"After {vendor} vendor group")
                time.sleep(vendor_break)

        # Log summary
        total_meetings = sum(r.meetings_found for r in results)
        total_processed = sum(r.meetings_processed for r in results)
        failed_count = len(self.failed_cities)
        duration = time.time() - start_time

        logger.info(
            f"Polite sync completed in {duration:.1f}s: {total_meetings} meetings found, "
            f"{total_processed} processed, {failed_count} cities failed"
        )
        if self.failed_cities:
            logger.warning(f"Failed cities: {', '.join(sorted(self.failed_cities))}")
        self.last_full_sync = datetime.now()

    def _sync_city(self, city: City) -> SyncResult:
        """Sync a single city"""
        result = SyncResult(city_banana=city.banana, status=SyncStatus.PENDING)

        if not city.vendor:
            result.status = SyncStatus.SKIPPED
            result.error_message = "No vendor configured"
            return result

        start_time = time.time()

        # Get adapter (slug is vendor-specific identifier)
        adapter = self._get_adapter(city.vendor, city.slug)

        if not adapter:
            result.status = SyncStatus.SKIPPED
            result.error_message = f"Unsupported vendor: {city.vendor}"
            logger.debug(f"Skipping {city.banana} - unsupported vendor: {city.vendor}")
            return result

        # Use context manager to ensure session cleanup
        with adapter:
            try:
                logger.info(f"Syncing {city.banana} with {city.vendor}")
                result.status = SyncStatus.IN_PROGRESS

                # Fetch meetings using unified adapter interface
                try:
                    all_meetings = list(adapter.fetch_meetings())
                    meetings_with_packets = [
                        m for m in all_meetings if m.get("packet_url")
                    ]

                except Exception as e:
                    logger.error(f"Error fetching meetings for {city.banana}: {e}")
                    result.status = SyncStatus.FAILED
                    result.error_message = str(e)
                    return result

                result.meetings_found = len(all_meetings)
                logger.info(
                    f"Found {len(all_meetings)} total meetings for {city.banana}, "
                    f"{len(meetings_with_packets)} have packets"
                )

                # Store ALL meetings (for user display) and process summaries for packet meetings
                processed_count = 0

                logger.info(
                    f"Starting to process {len(all_meetings)} meetings for storage"
                )
                for i, meeting in enumerate(all_meetings):
                    logger.debug(
                        f"Processing meeting {i + 1}/{len(all_meetings)}: "
                        f"{meeting.get('title')}"
                    )
                    if not self.is_running:
                        logger.warning("Processing stopped - is_running is False")
                        break

                    try:
                        # Parse date from adapter format
                        from infocore.database.unified_db import Meeting
                        from datetime import datetime

                        meeting_date = None
                        if meeting.get("start"):
                            try:
                                # Try parsing ISO format first
                                meeting_date = datetime.fromisoformat(
                                    meeting["start"].replace("Z", "+00:00")
                                )
                            except Exception:
                                # Adapter's _parse_date will handle other formats
                                pass

                        # Create Meeting object
                        meeting_obj = Meeting(
                            id=meeting.get("meeting_id", ""),
                            banana=city.banana,
                            title=meeting.get("title", ""),
                            date=meeting_date,
                            packet_url=meeting.get("packet_url"),
                            summary=None,
                            status=meeting.get("meeting_status"),
                            processing_status="pending",
                        )

                        # Validate meeting before storing (prevent corruption)
                        from jobs.meeting_validator import MeetingValidator

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
                            logger.warning(
                                f"Skipping corrupted meeting: {meeting_obj.title}"
                            )
                            continue

                        # Store meeting (upsert) - unified DB handles duplicates
                        stored_meeting = self.db.store_meeting(meeting_obj)
                        processed_count += 1

                        logger.debug(
                            f"Stored meeting: {stored_meeting.title} (id: {stored_meeting.id})"
                        )

                        # Store agenda items if present (Legistar provides this)
                        if meeting.get("items"):
                            from infocore.database.unified_db import AgendaItem

                            items = meeting["items"]
                            agenda_items = []

                            for item_data in items:
                                agenda_item = AgendaItem(
                                    id=f"{stored_meeting.id}_{item_data['item_id']}",  # Composite ID
                                    meeting_id=stored_meeting.id,
                                    title=item_data.get("title", ""),
                                    sequence=item_data.get("sequence", 0),
                                    attachments=item_data.get(
                                        "attachments", []
                                    ),  # Full metadata as JSON
                                    summary=None,  # Will be filled during processing
                                    topics=None,  # Will be filled during processing
                                )
                                agenda_items.append(agenda_item)

                            if agenda_items:
                                count = self.db.store_agenda_items(
                                    stored_meeting.id, agenda_items
                                )
                                logger.debug(
                                    f"Stored {count} agenda items for {stored_meeting.title}"
                                )

                        # Enqueue for processing if it has a packet URL
                        if meeting.get("packet_url"):
                            # Calculate priority based on meeting date recency
                            if meeting_date:
                                days_old = (datetime.now() - meeting_date).days
                            else:
                                days_old = 999
                            priority = max(
                                0, 100 - days_old
                            )  # Recent meetings get higher priority

                            self.db.enqueue_for_processing(
                                packet_url=meeting["packet_url"],
                                meeting_id=stored_meeting.id,
                                banana=city.banana,
                                priority=priority,
                            )
                            logger.debug(
                                f"Enqueued {meeting['packet_url']} with priority {priority}"
                            )
                        else:
                            logger.debug(
                                "Meeting has no packet - stored for display only"
                            )

                    except Exception as e:
                        logger.error(
                            f"Error storing meeting {meeting.get('packet_url', 'unknown')}: {e}"
                        )

                result.meetings_processed = processed_count
                result.status = SyncStatus.COMPLETED
                result.duration_seconds = time.time() - start_time

                logger.info(
                    f"Synced {city.banana}: {result.meetings_found} meetings found, "
                    f"{len(meetings_with_packets)} have packets, {processed_count} processed"
                )

                # Log memory after adapter cleanup to verify session closed
                log_memory_usage(f"After {city.banana}")

            except Exception as e:
                result.status = SyncStatus.FAILED
                result.error_message = str(e)
                result.duration_seconds = time.time() - start_time
                logger.error(f"Failed to sync {city.banana}: {e}")

                # Add small delay on error to avoid hammering
                time.sleep(2 + random.uniform(0, 1))

            return result

    def _sync_city_with_retry(self, city: City, max_retries: int = 1) -> SyncResult:
        """Sync city with retry (5s, 20s delays)"""
        city_name = city.name
        city_banana = city.banana

        wait_times = [5, 20]  # Fixed wait times for attempts

        for attempt in range(max_retries):
            try:
                result = self._sync_city(city)

                # If successful or skipped, return immediately
                if result.status in [SyncStatus.COMPLETED, SyncStatus.SKIPPED]:
                    return result

                # If failed and we have retries left, wait and retry
                if attempt < max_retries - 1:
                    wait_time = wait_times[attempt] + random.uniform(
                        0, 2
                    )  # Add 0-2s jitter
                    logger.warning(
                        f"Sync failed for {city_name} (attempt {attempt + 1}/{max_retries}), "
                        f"retrying in {wait_time:.1f}s: {result.error_message}"
                    )
                    time.sleep(wait_time)
                else:
                    logger.error(
                        f"Final sync failure for {city_name} after {max_retries} attempts: "
                        f"{result.error_message}"
                    )
                    return result

            except Exception as e:
                if attempt < max_retries - 1:
                    wait_time = wait_times[attempt] + random.uniform(0, 2)
                    logger.warning(
                        f"Exception syncing {city_name} (attempt {attempt + 1}/{max_retries}), "
                        f"retrying in {wait_time:.1f}s: {e}"
                    )
                    time.sleep(wait_time)
                else:
                    logger.error(
                        f"Final exception for {city_name} after {max_retries} attempts: {e}"
                    )
                    return SyncResult(
                        city_banana=city_banana,
                        status=SyncStatus.FAILED,
                        error_message=str(e),
                    )

        # Shouldn't reach here, but just in case
        return SyncResult(
            city_banana=city_banana,
            status=SyncStatus.FAILED,
            error_message="Unknown retry error",
        )

    def _should_sync_city(self, city: City) -> bool:
        """Determine if city needs syncing based on activity patterns"""
        try:
            # Check recent meeting frequency
            recent_meetings = self.db.get_city_meeting_frequency(city.banana, days=30)
            last_sync = self.db.get_city_last_sync(city.banana)

            if not last_sync:
                return True  # Never synced before

            hours_since_sync = (datetime.now() - last_sync).total_seconds() / 3600

            # Adaptive scheduling based on activity
            if recent_meetings >= 8:  # High activity (2+ meetings/week)
                return hours_since_sync >= 12  # Sync every 12 hours
            elif recent_meetings >= 4:  # Medium activity (1+ meeting/week)
                return hours_since_sync >= 24  # Sync daily
            elif recent_meetings >= 1:  # Low activity (some meetings)
                return hours_since_sync >= 168  # Sync every 7 days
            else:  # Very low activity (no recent meetings)
                return hours_since_sync >= 168  # Sync weekly

        except Exception as e:
            logger.warning(f"Error checking sync schedule for {city.banana}: {e}")
            return True  # Sync on error to be safe

    def _prioritize_cities(self, cities: List[City]) -> List[City]:
        """Sort cities by sync priority (high activity first)"""

        def get_priority(city: City) -> float:
            try:
                # Get recent activity
                recent_meetings = self.db.get_city_meeting_frequency(
                    city.banana, days=30
                )
                last_sync = self.db.get_city_last_sync(city.banana)

                if not last_sync:
                    return 1000  # Never synced gets highest priority

                hours_since_sync = (datetime.now() - last_sync).total_seconds() / 3600

                # Priority score: activity + time pressure
                return recent_meetings * 10 + min(hours_since_sync / 24, 10)

            except Exception:
                return 100  # Medium priority on error

        return sorted(cities, key=get_priority, reverse=True)

    def _get_adapter(self, vendor: str, city_slug: str):
        """Get appropriate adapter for vendor"""
        # Only process cities with supported adapters
        supported_vendors = {
            "primegov",
            "civicclerk",
            "legistar",
            "granicus",
            "novusagenda",
            "civicplus",
        }

        if vendor not in supported_vendors:
            logger.debug(f"Skipping unsupported vendor: {vendor} for city {city_slug}")
            return None

        if vendor == "primegov":
            return PrimeGovAdapter(city_slug)
        elif vendor == "civicclerk":
            return CivicClerkAdapter(city_slug)
        elif vendor == "legistar":
            # NYC requires API token
            if city_slug == "nyc":
                return LegistarAdapter(city_slug, api_token=config.NYC_LEGISTAR_TOKEN)
            return LegistarAdapter(city_slug)
        elif vendor == "granicus":
            return GranicusAdapter(city_slug)
        elif vendor == "novusagenda":
            return NovusAgendaAdapter(city_slug)
        elif vendor == "civicplus":
            return CivicPlusAdapter(city_slug)
        else:
            return None

    def _process_unprocessed_meetings(self, limit=20):
        """Process meetings that don't have summaries yet
        (cleanup for any missed during sync)"""
        logger.info("Checking for unprocessed meetings...")

        # Get meetings without summaries
        unprocessed = self.db.get_unprocessed_meetings(limit=limit)

        if not unprocessed:
            logger.debug("No unprocessed meetings found")
            return

        logger.info(f"Found {len(unprocessed)} unprocessed meetings")

        # TODO(Phase 4): Implement batch processing via job queue for efficiency
        # For now, process meetings individually
        if self.processor:
            logger.info(f"Processing {len(unprocessed)} meetings individually...")

            success_count = 0
            for meeting in unprocessed:
                if not meeting.packet_url:
                    continue

                try:
                    meeting_data = {
                        "packet_url": meeting.packet_url,
                        "city_banana": meeting.banana,
                        "meeting_name": meeting.title,
                        "meeting_date": meeting.date.isoformat()
                        if meeting.date
                        else None,
                        "meeting_id": meeting.id,
                    }

                    if self.processor:
                        result = self.processor.process_agenda_with_cache(meeting_data)

                        if result.get("success"):
                            success_count += 1
                            logger.info(
                                f"Processed {meeting.packet_url} in {result.get('processing_time', 0):.1f}s"
                            )
                        else:
                            logger.error(
                                f"Failed to process {meeting.packet_url}: {result.get('error')}"
                            )
                    else:
                        logger.warning(
                            f"Skipping {meeting.packet_url} - processor not available"
                        )

                except Exception as e:
                    logger.error(f"Error processing {meeting.packet_url}: {e}")

            logger.info(
                f"Successfully processed {success_count}/{len(unprocessed)} meetings"
            )

    def _process_queue(self):
        """Process jobs from the processing queue (Phase 4)"""
        logger.info("Starting queue processor...")

        while self.is_running:
            try:
                # Get next job from queue
                job = self.db.get_next_for_processing()

                if not job:
                    # No jobs available, sleep briefly
                    time.sleep(5)
                    continue

                queue_id = job["id"]
                packet_url = job["packet_url"]
                meeting_id = job["meeting_id"]

                logger.info(f"Processing queue job {queue_id}: {packet_url}")

                try:
                    # Get meeting from database
                    meeting = self.db.get_meeting(meeting_id)
                    if not meeting:
                        self.db.mark_processing_failed(
                            queue_id, "Meeting not found in database"
                        )
                        continue

                    # Use item-aware processing path (checks for items automatically)
                    if self.processor:
                        try:
                            self._process_meeting_summary(meeting)
                            self.db.mark_processing_complete(queue_id)
                            logger.info(f"Queue job {queue_id} completed successfully")
                        except Exception as e:
                            error_msg = str(e)
                            self.db.mark_processing_failed(queue_id, error_msg)
                            logger.error(f"Queue job {queue_id} failed: {error_msg}")
                    else:
                        self.db.mark_processing_failed(
                            queue_id, "Processor not available", increment_retry=False
                        )
                        logger.warning(
                            f"Skipping queue job {queue_id} - processor not available"
                        )

                except Exception as e:
                    error_msg = str(e)
                    self.db.mark_processing_failed(queue_id, error_msg)
                    logger.error(f"Error processing queue job {queue_id}: {e}")
                    # Sleep briefly on error to avoid tight loop
                    time.sleep(2)

            except Exception as e:
                logger.error(f"Queue processor error: {e}")
                # Sleep on error to avoid tight loop
                time.sleep(10)

    def _process_meetings_individually(self, meetings):
        """Process meetings individually (fallback - should rarely be used)"""
        with ThreadPoolExecutor(max_workers=1) as executor:  # Only 1 at a time
            futures = []

            for meeting in meetings:
                if not self.is_running:
                    break

                future = executor.submit(self._process_meeting_summary, meeting)
                futures.append(future)

            # Wait for completion
            for future in futures:
                try:
                    future.result(timeout=600)  # 10 minute timeout per meeting
                except Exception as e:
                    logger.error(f"Meeting processing future failed: {e}")

    def _process_meeting_summary(self, meeting: Meeting):
        """Process summary for a single meeting (with item-level processing if available)"""
        if not meeting.packet_url:
            return

        try:
            logger.info(f"Processing summary for {meeting.packet_url}")

            # Check if still unprocessed (avoid race conditions)
            cached = self.db.get_cached_summary(meeting.packet_url)
            if cached:
                logger.debug(
                    f"Meeting {meeting.packet_url} already processed, skipping"
                )
                return

            if not self.processor:
                logger.warning(
                    f"Skipping {meeting.packet_url} - processor not available"
                )
                return

            # Check if meeting has agenda items (item-level processing)
            agenda_items = self.db.get_agenda_items(meeting.id)

            if agenda_items:
                logger.info(
                    f"[ItemProcessing] Found {len(agenda_items)} items for {meeting.title}"
                )
                self._process_meeting_with_items(meeting, agenda_items)
            else:
                # Try to detect items from PDF structure
                logger.info(
                    "[ItemDetection] No items in DB, attempting to detect from PDF"
                )
                try:
                    # Extract text from PDF (handle list or single URL)
                    packet_url = (
                        meeting.packet_url[0]
                        if isinstance(meeting.packet_url, list)
                        else meeting.packet_url
                    )
                    result = self.processor.pdf_extractor.extract_from_url(packet_url)
                    if result.get("success") and result.get("text"):
                        extracted_text = result["text"]

                        # Check document size - skip item detection for small packets
                        page_count = self.processor.summarizer._estimate_page_count(
                            extracted_text
                        )
                        text_size = len(extracted_text)

                        if page_count <= 10 or text_size < 30000:
                            logger.info(
                                f"[ItemDetection] Small packet ({page_count} pages, {text_size} chars) - processing monolithically"
                            )
                            # Fall back to monolithic processing
                            meeting_data = {
                                "packet_url": meeting.packet_url,
                                "city_banana": meeting.banana,
                                "meeting_name": meeting.title,
                                "meeting_date": meeting.date.isoformat()
                                if meeting.date
                                else None,
                                "meeting_id": meeting.id,
                            }
                            result = self.processor.process_agenda_with_cache(
                                meeting_data
                            )
                            logger.info(
                                f"Processed {meeting.packet_url} in {result['processing_time']:.1f}s"
                            )
                            return

                        # Detect items using pattern matching (for larger packets)
                        # Try structural chunking first, fall back to pattern-based
                        detected_items = self.processor.chunker.chunk_by_structure(
                            extracted_text
                        )
                        if not detected_items:
                            detected_items = self.processor.chunker.chunk_by_patterns(
                                extracted_text
                            )

                        if detected_items:
                            # Convert detected items to AgendaItem objects and store
                            from infocore.database.unified_db import AgendaItem

                            agenda_item_objects = []
                            for item in detected_items:
                                agenda_item = AgendaItem(
                                    id=f"{meeting.id}_item_{item['sequence']}",
                                    meeting_id=meeting.id,
                                    title=item["title"],
                                    sequence=item["sequence"],
                                    attachments=[
                                        {
                                            "type": "text_segment",
                                            "content": item["text"][
                                                :5000
                                            ],  # First 5000 chars
                                            "start_page": item.get("start_page"),
                                        }
                                    ],
                                    summary=None,
                                    topics=None,
                                )
                                agenda_item_objects.append(agenda_item)

                            # Store detected items
                            count = self.db.store_agenda_items(
                                meeting.id, agenda_item_objects
                            )
                            logger.info(
                                f"[ItemDetection] Stored {count} detected items for {meeting.title}"
                            )

                            # Now process with items
                            self._process_meeting_with_items(
                                meeting, agenda_item_objects
                            )
                        else:
                            # No clear item structure - fall back to monolithic
                            logger.info(
                                "[MonolithicProcessing] No item structure detected, processing as single unit"
                            )
                            meeting_data = {
                                "packet_url": meeting.packet_url,
                                "city_banana": meeting.banana,
                                "meeting_name": meeting.title,
                                "meeting_date": meeting.date.isoformat()
                                if meeting.date
                                else None,
                                "meeting_id": meeting.id,
                            }
                            result = self.processor.process_agenda_with_cache(
                                meeting_data
                            )
                            logger.info(
                                f"Processed {meeting.packet_url} in {result['processing_time']:.1f}s"
                            )
                    else:
                        logger.warning(
                            "[ItemDetection] PDF extraction failed, falling back to monolithic"
                        )
                        meeting_data = {
                            "packet_url": meeting.packet_url,
                            "city_banana": meeting.banana,
                            "meeting_name": meeting.title,
                            "meeting_date": meeting.date.isoformat()
                            if meeting.date
                            else None,
                            "meeting_id": meeting.id,
                        }
                        result = self.processor.process_agenda_with_cache(meeting_data)
                        logger.info(
                            f"Processed {meeting.packet_url} in {result['processing_time']:.1f}s"
                        )
                except Exception as e:
                    logger.error(
                        f"[ItemDetection] Failed: {e}, falling back to monolithic processing"
                    )
                    meeting_data = {
                        "packet_url": meeting.packet_url,
                        "city_banana": meeting.banana,
                        "meeting_name": meeting.title,
                        "meeting_date": meeting.date.isoformat()
                        if meeting.date
                        else None,
                        "meeting_id": meeting.id,
                    }
                    result = self.processor.process_agenda_with_cache(meeting_data)
                    logger.info(
                        f"Processed {meeting.packet_url} in {result['processing_time']:.1f}s"
                    )

        except Exception as e:
            logger.error(f"Error processing summary for {meeting.packet_url}: {e}")

    def _process_meeting_with_items(self, meeting: Meeting, agenda_items: List):
        """Process a meeting at item-level granularity using batch API"""

        start_time = time.time()
        processed_items = []
        failed_items = []

        if not self.processor:
            logger.warning("[ItemProcessing] Processor not available")
            return

        # Separate already-processed items from items that need processing
        already_processed = []
        need_processing = []

        for item in agenda_items:
            if not item.attachments:
                logger.debug(
                    f"[ItemProcessing] Skipping item without attachments: {item.title[:50]}"
                )
                continue

            if item.summary:
                logger.debug(
                    f"[ItemProcessing] Item already processed: {item.title[:50]}"
                )
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

                    for att in item.attachments:
                        att_type = att.get("type", "unknown")

                        # Text segment (from detected items)
                        if att_type == "text_segment":
                            text_content = att.get("content", "")
                            if text_content:
                                all_text_parts.append(text_content)

                        # PDF attachment (from Legistar)
                        elif att_type == "pdf":
                            att_url = att.get("url")
                            att_name = att.get("name", "Attachment")

                            if att_url:
                                try:
                                    result = (
                                        self.processor.pdf_extractor.extract_from_url(
                                            att_url
                                        )
                                    )
                                    if result.get("success") and result.get("text"):
                                        all_text_parts.append(
                                            f"=== {att_name} ===\n{result['text']}"
                                        )
                                        logger.debug(
                                            f"[ItemProcessing] Extracted {len(result['text'])} chars from {att_name}"
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
                            }
                        )
                        item_map[item.id] = item
                        logger.debug(
                            f"[ItemProcessing] Prepared {item.title[:50]} ({len(combined_text)} chars)"
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

            # STEP 2: Batch process all items at once (50% cost savings!)
            if batch_requests:
                logger.info(
                    f"[ItemProcessing] Submitting batch with {len(batch_requests)} items to Gemini"
                )
                batch_results = self.processor.process_batch_items(batch_requests)

                # STEP 3: Store all results
                for result in batch_results:
                    item_id = result["item_id"]
                    item = item_map.get(item_id)

                    if not item:
                        logger.warning(
                            f"[ItemProcessing] No item mapping for {item_id}"
                        )
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

        # Combine item summaries into meeting summary
        if processed_items and self.processor:
            # Build combined summary directly (no wrapper function needed)
            summary_parts = [f"Meeting: {meeting.title}\n"]
            for item in processed_items:
                title = item.get("title", "Untitled Item")
                summary = item.get("summary", "No summary available")
                summary_parts.append(f"\n{title}\n{summary}")
            summary_parts.append(f"\n\n[Processed {len(processed_items)} items]")
            combined_summary = "\n".join(summary_parts)

            # Aggregate topics from all items
            all_topics = []
            for item in processed_items:
                all_topics.extend(item.get("topics", []))

            # Count topic frequency and sort by frequency
            topic_counts = {}
            for topic in all_topics:
                topic_counts[topic] = topic_counts.get(topic, 0) + 1

            # Keep topics sorted by frequency (most common first)
            meeting_topics = sorted(
                topic_counts.keys(), key=lambda t: topic_counts[t], reverse=True
            )

            logger.info(
                f"[TopicAggregation] Aggregated {len(meeting_topics)} unique topics "
                f"from {len(processed_items)} items: {meeting_topics}"
            )

            # Update meeting with combined summary and aggregated topics
            processing_time = time.time() - start_time
            self.db.update_meeting_summary(
                meeting_id=meeting.id,
                summary=combined_summary,
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

    def get_sync_status(self) -> Dict[str, Any]:
        """Get current sync status"""
        stats = self.db.get_stats()
        return {
            "is_running": self.is_running,
            "last_full_sync": (
                self.last_full_sync.isoformat() if self.last_full_sync else None
            ),
            "active_cities": stats.get("active_cities", 0),
            "total_meetings": stats.get("total_meetings", 0),
            "summarized_meetings": stats.get("summarized_meetings", 0),
            "pending_meetings": stats.get("pending_meetings", 0),
            "failed_cities": list(self.failed_cities),
            "failed_count": len(self.failed_cities),
            "current_sync_status": dict(self.current_sync_status),
        }

    def force_sync_city(self, city_banana: str) -> SyncResult:
        """Force sync a specific city"""
        city = self.db.get_city(banana=city_banana)
        if not city:
            return SyncResult(
                city_banana=city_banana,
                status=SyncStatus.FAILED,
                error_message="City not found",
            )

        # Temporarily set is_running to True for the sync
        old_is_running = self.is_running
        self.is_running = True

        try:
            result = self._sync_city_with_retry(city)

            # Track failed cities (no locks needed)
            if result.status == SyncStatus.FAILED:
                self.failed_cities.add(city_banana)
            else:
                # Remove from failed set if it succeeds
                self.failed_cities.discard(city_banana)

            return result
        finally:
            # Restore original is_running state
            self.is_running = old_is_running

    def sync_and_process_city(self, city_banana: str) -> Dict[str, Any]:
        """Sync a city and immediately process all its queued jobs

        Returns:
            Dictionary with sync_result and processing stats
        """
        logger.info(f"Starting sync-and-process for {city_banana}")

        # Step 1: Sync the city (fetches meetings, stores, enqueues)
        sync_result = self.force_sync_city(city_banana)

        if sync_result.status != SyncStatus.COMPLETED:
            logger.error(f"Sync failed for {city_banana}: {sync_result.error_message}")
            return {
                "sync_status": sync_result.status.value,
                "sync_error": sync_result.error_message,
                "meetings_found": sync_result.meetings_found,
                "processed_count": 0,
            }

        logger.info(f"Sync complete: {sync_result.meetings_found} meetings found")

        # Step 2: Process all queued jobs for this city
        if not self.processor:
            logger.warning(
                "Processor not available - meetings queued but not processed"
            )
            return {
                "sync_status": sync_result.status.value,
                "meetings_found": sync_result.meetings_found,
                "processed_count": 0,
                "warning": "Processor not available",
            }

        logger.info(f"Processing queued jobs for {city_banana}...")
        processed_count = 0
        failed_count = 0

        # Temporarily enable processing
        old_is_running = self.is_running
        self.is_running = True

        try:
            # Process all jobs for this city
            while True:
                # Get next job for this city
                job = self.db.get_next_for_processing(banana=city_banana)

                if not job:
                    break  # No more jobs for this city

                queue_id = job["id"]
                meeting_id = job["meeting_id"]
                packet_url = job["packet_url"]

                logger.info(f"Processing job {queue_id}: {packet_url}")

                try:
                    meeting = self.db.get_meeting(meeting_id)
                    if not meeting:
                        self.db.mark_processing_failed(queue_id, "Meeting not found")
                        failed_count += 1
                        continue

                    # Process the meeting (item-aware)
                    self._process_meeting_summary(meeting)
                    self.db.mark_processing_complete(queue_id)
                    processed_count += 1
                    logger.info(f"Processed {packet_url}")

                except Exception as e:
                    error_msg = str(e)
                    self.db.mark_processing_failed(queue_id, error_msg)
                    failed_count += 1
                    logger.error(f"Failed to process {packet_url}: {e}")

            logger.info(
                f"Processing complete for {city_banana}: "
                f"{processed_count} succeeded, {failed_count} failed"
            )

            return {
                "sync_status": sync_result.status.value,
                "meetings_found": sync_result.meetings_found,
                "processed_count": processed_count,
                "failed_count": failed_count,
            }

        finally:
            # Restore original is_running state
            self.is_running = old_is_running

    def force_process_meeting(self, packet_url: str) -> bool:
        """Force process a specific meeting"""
        if not self.processor:
            return False

        try:
            meeting = self.db.get_meeting_by_packet_url(packet_url)
            if not meeting:
                return False

            self._process_meeting_summary(meeting)
            return True

        except Exception as e:
            logger.error(f"Error force processing {packet_url}: {e}")
            return False

    def process_all_unprocessed_meetings(self, batch_size=20):
        """Process ALL unprocessed meetings in batches"""
        if not self.processor:
            logger.error("LLM processor not available - cannot process summaries")
            return

        logger.info("Starting to process ALL unprocessed meetings...")
        total_processed = 0
        batch_count = 0

        while True:
            # Get next batch of unprocessed meetings
            unprocessed = self.db.get_unprocessed_meetings(limit=batch_size)

            if not unprocessed:
                logger.info(
                    f"No more unprocessed meetings found. Total processed: {total_processed}"
                )
                break

            batch_count += 1
            logger.info(f"Processing batch {batch_count}: {len(unprocessed)} meetings")

            # Use the same batch processing logic as _process_unprocessed_meetings
            self._process_unprocessed_meetings(limit=batch_size)

            # Count how many were processed (check database)
            remaining = self.db.get_unprocessed_meetings(limit=1)
            batch_processed = (
                batch_size if not remaining else batch_size - len(remaining)
            )
            total_processed += batch_processed

            logger.info(f"Batch {batch_count} complete using batch API")

            # Small delay between batches to avoid overwhelming the LLM API
            if len(unprocessed) == batch_size:  # More batches to come
                logger.info("Waiting 10 seconds before next batch...")
                time.sleep(10)

        logger.info(
            f"Finished processing all unprocessed meetings. Total: {total_processed}"
        )


# Global instance
_conductor = None


def get_conductor() -> Conductor:
    """Get global conductor instance"""
    global _conductor
    if _conductor is None:
        _conductor = Conductor()
    return _conductor


def start_conductor():
    """Start the global conductor"""
    conductor = get_conductor()
    conductor.start()


def stop_conductor():
    """Stop the global conductor"""
    global _conductor
    if _conductor:
        _conductor.stop()
        _conductor = None


if __name__ == "__main__":
    # CLI for testing
    import argparse

    parser = argparse.ArgumentParser(description="Background processor for engagic")
    parser.add_argument("--sync-city", help="Sync specific city by city_banana")
    parser.add_argument(
        "--sync-and-process-city",
        help="Sync city and immediately process all its meetings",
    )
    parser.add_argument(
        "--process-meeting", help="Process specific meeting by packet URL"
    )
    parser.add_argument("--full-sync", action="store_true", help="Run full sync once")
    parser.add_argument(
        "--process-all-unprocessed",
        action="store_true",
        help="Process ALL unprocessed meetings",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=20,
        help="Batch size for processing (default: 20)",
    )
    parser.add_argument("--status", action="store_true", help="Show status")
    parser.add_argument("--daemon", action="store_true", help="Run as daemon")

    args = parser.parse_args()

    # Configure logging for CLI usage
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=[logging.StreamHandler()],
    )

    processor = Conductor()

    if args.sync_city:
        result = processor.force_sync_city(args.sync_city)
        print(f"Sync result: {result}")
    elif args.sync_and_process_city:
        result = processor.sync_and_process_city(args.sync_and_process_city)
        print(f"Sync and process result: {result}")
    elif args.process_meeting:
        success = processor.force_process_meeting(args.process_meeting)
        print(f"Process result: {'Success' if success else 'Failed'}")
    elif args.full_sync:
        processor._run_full_sync()
    elif args.process_all_unprocessed:
        processor.process_all_unprocessed_meetings(batch_size=args.batch_size)
    elif args.status:
        status = processor.get_sync_status()
        print(f"Status: {status}")
    elif args.daemon:
        processor.start()
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            processor.stop()
    else:
        parser.print_help()
