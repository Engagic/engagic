import logging
import time
import random
from datetime import datetime
from typing import Dict, List, Any, Optional
from concurrent.futures import ThreadPoolExecutor
import threading
from dataclasses import dataclass
from enum import Enum
from collections import defaultdict

from backend.database import UnifiedDatabase, City, Meeting
from backend.core.processor import AgendaProcessor
from backend.adapters.all_adapters import (
    PrimeGovAdapter,
    CivicClerkAdapter,
    LegistarAdapter,
    GranicusAdapter,
    NovusAgendaAdapter,
    CivicPlusAdapter
)
from backend.core.config import config

logger = logging.getLogger("engagic")


class RateLimiter:
    """Vendor-aware rate limiter to be respectful to city websites"""

    def __init__(self):
        self.last_request = defaultdict(float)
        self.lock = threading.Lock()

    def wait_if_needed(self, vendor: str):
        """Enforce minimum delay between requests to same vendor"""
        delays = {
            'primegov': 3.0,      # PrimeGov cities
            'granicus': 4.0,      # Granicus/Legistar cities
            'civicclerk': 3.0,    # CivicClerk cities
            'legistar': 3.0,      # Direct Legistar
            'civicplus': 4.0,     # CivicPlus cities
            'novusagenda': 4.0,   # NovusAgenda cities
            'unknown': 5.0        # Unknown vendors get longest delay
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


class BackgroundProcessor:
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
            target=self._processing_loop,
            daemon=True
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
            "primegov", "civicclerk", "legistar",
            "granicus", "novusagenda", "civicplus"
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
                    f"Skipping city {city.name} "
                    f"with unsupported vendor: {vendor}"
                )

        total_supported = sum(len(vendor_cities) for vendor_cities in by_vendor.values())
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
                    logger.debug(
                        f"Skipping {city.name} - doesn't need sync yet"
                    )
                    results.append(SyncResult(
                        city_banana=city.banana,
                        status=SyncStatus.SKIPPED,
                        error_message="Not due for sync based on frequency"
                    ))
                    continue

                # Apply rate limiting before sync
                self.rate_limiter.wait_if_needed(vendor)

                # Sync with retry logic
                result = self._sync_city_with_retry(city)
                logger.info(
                    f"Sync completed for {city.banana}: "
                    f"{result.status}"
                )
                results.append(result)

                # Track failed cities
                if result.status == SyncStatus.FAILED:
                    self.failed_cities.add(city.banana)

            # Break between vendor groups to be extra polite
            if vendor_cities:  # Only sleep if we processed cities
                vendor_break = 30 + random.uniform(0, 10)  # 30-40 seconds
                logger.info(
                    f"Completed {vendor} cities, taking {vendor_break:.1f}s break..."
                )
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

        try:
            logger.info(f"Syncing {city.banana} with {city.vendor}")
            result.status = SyncStatus.IN_PROGRESS

            # Get adapter (vendor_slug is vendor-specific identifier)
            adapter = self._get_adapter(city.vendor, city.vendor_slug)

            if not adapter:
                result.status = SyncStatus.SKIPPED
                result.error_message = f"Unsupported vendor: {city.vendor}"
                logger.debug(f"Skipping {city.banana} - unsupported vendor: {city.vendor}")
                return result

            # Fetch meetings using unified adapter interface
            try:
                all_meetings = list(adapter.fetch_meetings())
                meetings_with_packets = [m for m in all_meetings if m.get('packet_url')]

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

            logger.info(f"Starting to process {len(all_meetings)} meetings for storage")
            for i, meeting in enumerate(all_meetings):
                logger.debug(
                    f"Processing meeting {i+1}/{len(all_meetings)}: "
                    f"{meeting.get('title')}"
                )
                if not self.is_running:
                    logger.warning("Processing stopped - is_running is False")
                    break

                try:
                    # Parse date from adapter format
                    from backend.database.unified_db import Meeting
                    from datetime import datetime

                    meeting_date = None
                    if meeting.get("start"):
                        try:
                            # Try parsing ISO format first
                            meeting_date = datetime.fromisoformat(meeting["start"].replace('Z', '+00:00'))
                        except Exception:
                            # Adapter's _parse_date will handle other formats
                            pass

                    # Create Meeting object
                    meeting_obj = Meeting(
                        id=meeting.get("meeting_id", ""),
                        city_banana=city.banana,
                        title=meeting.get("title", ""),
                        date=meeting_date,
                        packet_url=meeting.get("packet_url"),
                        summary=None,
                        processing_status="pending"
                    )

                    # Store meeting (upsert) - unified DB handles duplicates
                    stored_meeting = self.db.store_meeting(meeting_obj)
                    processed_count += 1

                    logger.debug(
                        f"Stored meeting: {stored_meeting.title} (id: {stored_meeting.id})"
                    )

                    # Enqueue for processing if it has a packet URL
                    if meeting.get("packet_url"):
                        # Calculate priority based on meeting date recency
                        if meeting_date:
                            days_old = (datetime.now() - meeting_date).days
                        else:
                            days_old = 999
                        priority = max(0, 100 - days_old)  # Recent meetings get higher priority

                        self.db.enqueue_for_processing(
                            packet_url=meeting["packet_url"],
                            meeting_id=stored_meeting.id,
                            city_banana=city.banana,
                            priority=priority
                        )
                        logger.debug(f"Enqueued {meeting['packet_url']} with priority {priority}")
                    else:
                        logger.debug("Meeting has no packet - stored for display only")

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

        except Exception as e:
            result.status = SyncStatus.FAILED
            result.error_message = str(e)
            result.duration_seconds = time.time() - start_time
            logger.error(f"Failed to sync {city.banana}: {e}")

            # Add small delay on error to avoid hammering
            time.sleep(2 + random.uniform(0, 1))

        return result

    def _sync_city_with_retry(self, city: City,
                              max_retries: int = 2) -> SyncResult:
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
                    wait_time = wait_times[attempt] + random.uniform(0, 2)  # Add 0-2s jitter
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
                        error_message=str(e)
                    )

        # Shouldn't reach here, but just in case
        return SyncResult(
            city_banana=city_banana,
            status=SyncStatus.FAILED,
            error_message="Unknown retry error"
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
                recent_meetings = self.db.get_city_meeting_frequency(city.banana, days=30)
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
            "primegov", "civicclerk", "legistar",
            "granicus", "novusagenda", "civicplus"
        }

        if vendor not in supported_vendors:
            logger.debug(f"Skipping unsupported vendor: {vendor} for city {city_slug}")
            return None

        if vendor == "primegov":
            return PrimeGovAdapter(city_slug)
        elif vendor == "civicclerk":
            return CivicClerkAdapter(city_slug)
        elif vendor == "legistar":
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
                        "city_banana": meeting.city_banana,
                        "meeting_name": meeting.title,
                        "meeting_date": meeting.date.isoformat() if meeting.date else None,
                        "meeting_id": meeting.id,
                    }

                    if self.processor:
                        result = self.processor.process_agenda_with_cache(meeting_data)

                        if result.get("success"):
                            success_count += 1
                            logger.info(f"Processed {meeting.packet_url} in {result.get('processing_time', 0):.1f}s")
                        else:
                            logger.error(f"Failed to process {meeting.packet_url}: {result.get('error')}")
                    else:
                        logger.warning(f"Skipping {meeting.packet_url} - processor not available")

                except Exception as e:
                    logger.error(f"Error processing {meeting.packet_url}: {e}")

            logger.info(f"Successfully processed {success_count}/{len(unprocessed)} meetings")

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

                queue_id = job['id']
                packet_url = job['packet_url']
                meeting_id = job['meeting_id']
                city_banana = job['city_banana']

                logger.info(f"Processing queue job {queue_id}: {packet_url}")

                try:
                    # Get meeting from database
                    meeting = self.db.get_meeting(meeting_id)
                    if not meeting:
                        self.db.mark_processing_failed(
                            queue_id,
                            "Meeting not found in database"
                        )
                        continue

                    # Process the meeting using existing logic
                    meeting_data = {
                        "packet_url": packet_url,
                        "city_banana": city_banana,
                        "meeting_name": meeting.title,
                        "meeting_date": meeting.date.isoformat() if meeting.date else None,
                        "meeting_id": meeting_id,
                    }

                    if self.processor:
                        result = self.processor.process_agenda_with_cache(meeting_data)

                        if result.get("success"):
                            self.db.mark_processing_complete(queue_id)
                            logger.info(
                                f"Queue job {queue_id} completed in {result.get('processing_time', 0):.1f}s"
                            )
                        else:
                            error_msg = result.get("error", "Unknown error")
                            self.db.mark_processing_failed(queue_id, error_msg)
                            logger.error(f"Queue job {queue_id} failed: {error_msg}")
                    else:
                        self.db.mark_processing_failed(
                            queue_id,
                            "Processor not available",
                            increment_retry=False
                        )
                        logger.warning(f"Skipping queue job {queue_id} - processor not available")

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
        """Process summary for a single meeting"""
        if not meeting.packet_url:
            return

        try:
            logger.info(f"Processing summary for {meeting.packet_url}")

            # Check if still unprocessed (avoid race conditions)
            cached = self.db.get_cached_summary(meeting.packet_url)
            if cached:
                logger.debug(f"Meeting {meeting.packet_url} already processed, skipping")
                return

            # Process with cache - use the meeting data directly
            meeting_data = {
                "packet_url": meeting.packet_url,
                "city_banana": meeting.city_banana,
                "meeting_name": meeting.title,
                "meeting_date": meeting.date.isoformat() if meeting.date else None,
                "meeting_id": meeting.id,
            }

            if self.processor:
                result = self.processor.process_agenda_with_cache(meeting_data)
                logger.info(f"Processed {meeting.packet_url} in {result['processing_time']:.1f}s")
            else:
                logger.warning(f"Skipping {meeting.packet_url} - processor not available")

        except Exception as e:
            logger.error(f"Error processing summary for {meeting.packet_url}: {e}")

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
            "current_sync_status": dict(self.current_sync_status)
        }

    def force_sync_city(self, city_banana: str) -> SyncResult:
        """Force sync a specific city"""
        city = self.db.get_city(banana=city_banana)
        if not city:
            return SyncResult(
                city_banana=city_banana,
                status=SyncStatus.FAILED,
                error_message="City not found"
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
_background_processor = None


def get_background_processor() -> BackgroundProcessor:
    """Get global background processor instance"""
    global _background_processor
    if _background_processor is None:
        _background_processor = BackgroundProcessor()
    return _background_processor


def start_background_processor():
    """Start the global background processor"""
    processor = get_background_processor()
    processor.start()


def stop_background_processor():
    """Stop the global background processor"""
    global _background_processor
    if _background_processor:
        _background_processor.stop()
        _background_processor = None


if __name__ == "__main__":
    # CLI for testing
    import argparse

    parser = argparse.ArgumentParser(description="Background processor for engagic")
    parser.add_argument("--sync-city", help="Sync specific city by city_banana")
    parser.add_argument("--process-meeting", help="Process specific meeting by packet URL")
    parser.add_argument("--full-sync", action="store_true", help="Run full sync once")
    parser.add_argument(
        "--process-all-unprocessed", 
        action="store_true", 
        help="Process ALL unprocessed meetings"
    )
    parser.add_argument(
        "--batch-size", 
        type=int, 
        default=20, 
        help="Batch size for processing (default: 20)"
    )
    parser.add_argument("--status", action="store_true", help="Show status")
    parser.add_argument("--daemon", action="store_true", help="Run as daemon")

    args = parser.parse_args()

    processor = BackgroundProcessor()

    if args.sync_city:
        result = processor.force_sync_city(args.sync_city)
        print(f"Sync result: {result}")
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