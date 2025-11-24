"""
Pipeline Fetcher - City sync and vendor routing

Handles:
- Fetching meetings from vendor platforms
- Storing meetings and agenda items in database
- Vendor-aware rate limiting
- Adaptive sync scheduling
- Support for city lists, vendor lists, or full sync

Moved from: pipeline/conductor.py (refactored)
"""

import asyncio
import time
import random
from datetime import datetime
from typing import List, Optional, Set
from dataclasses import dataclass
from enum import Enum

from database.db_postgres import Database
from database.models import City
from exceptions import VendorError
from vendors.factory import get_async_adapter
from vendors.rate_limiter_async import AsyncRateLimiter
from config import config, get_logger
from server.metrics import metrics

logger = get_logger(__name__).bind(component="fetcher")

# Timing constants (seconds)
SYNC_ERROR_DELAY_BASE = 2  # Base delay after sync error
SYNC_ERROR_DELAY_JITTER = 1  # Random jitter to add


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
    meetings_skipped: int = 0
    duration_seconds: float = 0.0
    error_message: Optional[str] = None


class Fetcher:
    """City sync and meeting fetching orchestrator"""

    def __init__(self, db: Database):
        """Initialize the fetcher

        Args:
            db: Async Database instance (required)
        """
        self.db = db
        self.rate_limiter = AsyncRateLimiter()
        self.failed_cities: Set[str] = set()
        self.is_running = True  # Control flag for external stop

    async def sync_all(self) -> List[SyncResult]:
        """Sync all active cities with vendor-aware rate limiting

        Returns:
            List of SyncResult objects for each city
        """
        start_time = time.time()
        logger.info("Starting polite city sync...")

        self.failed_cities.clear()
        cities = await self.db.cities.get_all_cities(status="active")
        logger.info("syncing cities with rate limiting", city_count=len(cities))

        # Group cities by vendor for polite crawling (only supported vendors)
        # Temporarily disabled: granicus (VPS timeout issues), civicclerk, civicplus
        supported_vendors = {
            "primegov",
            "legistar",
            "novusagenda",  # Item-level processing enabled
            "iqm2",  # Item-level processing enabled
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
                    "skipping city with unsupported vendor",
                    city_name=city.name,
                    vendor=vendor
                )

        total_supported = sum(len(vendor_cities) for vendor_cities in by_vendor.values())
        logger.info(
            "processing cities with supported adapters",
            supported_count=total_supported,
            skipped_count=skipped_count
        )

        results = []

        # Process each vendor group sequentially with proper delays
        for vendor, vendor_cities in by_vendor.items():
            if not self.is_running:
                break

            # Sort cities by sync priority (high activity first)
            sorted_cities = await self._prioritize_cities(vendor_cities)
            logger.info(
                "syncing vendor cities",
                vendor=vendor,
                city_count=len(sorted_cities)
            )

            for city in sorted_cities:
                if not self.is_running:
                    break

                # Check if city needs syncing based on frequency
                if not await self._should_sync_city(city):
                    logger.debug("skipping city - not due for sync", city_name=city.name)
                    results.append(
                        SyncResult(
                            city_banana=city.banana,
                            status=SyncStatus.SKIPPED,
                            error_message="Not due for sync based on frequency",
                        )
                    )
                    continue

                # Apply rate limiting before sync
                await self.rate_limiter.wait_if_needed(vendor)

                # Sync with retry logic
                result = await self._sync_city_with_retry(city)
                logger.info("sync completed", city=city.banana, status=result.status.value)
                results.append(result)

                # Track failed cities
                if result.status == SyncStatus.FAILED:
                    self.failed_cities.add(city.banana)

            # Break between vendor groups to be extra polite
            if vendor_cities:
                vendor_break = 30 + random.uniform(0, 10)  # 30-40 seconds
                logger.info(
                    "completed vendor cities - taking break",
                    vendor=vendor,
                    break_seconds=round(vendor_break, 1)
                )
                time.sleep(vendor_break)

        # Log summary
        total_meetings = sum(r.meetings_found for r in results)
        total_processed = sum(r.meetings_processed for r in results)
        failed_count = len(self.failed_cities)
        duration = time.time() - start_time

        logger.info(
            "polite sync completed",
            duration_seconds=round(duration, 1),
            meetings_found=total_meetings,
            meetings_processed=total_processed,
            cities_failed=failed_count
        )
        if self.failed_cities:
            logger.warning("cities failed during sync", failed_cities=sorted(self.failed_cities))

        return results

    async def sync_cities(self, city_bananas: List[str]) -> List[SyncResult]:
        """Sync specific cities by city_banana

        Args:
            city_bananas: List of city_banana identifiers (e.g., ["paloaltoCA", "oaklandCA"])

        Returns:
            List of SyncResult objects
        """
        logger.info("syncing specific cities", city_count=len(city_bananas))
        results = []

        for banana in city_bananas:
            city = await self.db.cities.get_city(banana=banana)
            if not city:
                logger.warning("city not found", banana=banana)
                results.append(
                    SyncResult(
                        city_banana=banana,
                        status=SyncStatus.FAILED,
                        error_message="City not found in database",
                    )
                )
                continue

            # Apply rate limiting
            await self.rate_limiter.wait_if_needed(city.vendor)

            # Sync with retry
            result = await self._sync_city_with_retry(city)
            results.append(result)

            if result.status == SyncStatus.FAILED:
                self.failed_cities.add(banana)

        return results

    async def sync_vendors(self, vendor_names: List[str]) -> List[SyncResult]:
        """Sync all cities for specific vendors

        Args:
            vendor_names: List of vendor names (e.g., ["legistar", "primegov"])

        Returns:
            List of SyncResult objects
        """
        logger.info("syncing cities for vendors", vendors=vendor_names)
        results = []

        for vendor in vendor_names:
            cities = await self.db.cities.get_cities(vendor=vendor, status="active")
            logger.info("found cities for vendor", vendor=vendor, city_count=len(cities))

            for city in cities:
                if not self.is_running:
                    break

                # Apply rate limiting
                await self.rate_limiter.wait_if_needed(vendor)

                # Sync with retry
                result = await self._sync_city_with_retry(city)
                results.append(result)

                if result.status == SyncStatus.FAILED:
                    self.failed_cities.add(city.banana)

        return results

    async def sync_city(self, city_banana: str) -> SyncResult:
        """Sync a single city by city_banana

        Args:
            city_banana: City banana identifier

        Returns:
            SyncResult object
        """
        city = await self.db.get_city(banana=city_banana)
        if not city:
            return SyncResult(
                city_banana=city_banana,
                status=SyncStatus.FAILED,
                error_message="City not found",
            )

        return await self._sync_city_with_retry(city)

    async def _sync_city(self, city: City) -> SyncResult:
        """Sync a single city (internal method)

        Fetches meetings from vendor, stores in database, enqueues for processing
        """
        result = SyncResult(city_banana=city.banana, status=SyncStatus.PENDING)

        if not city.vendor:
            result.status = SyncStatus.SKIPPED
            result.error_message = "No vendor configured"
            return result

        start_time = time.time()

        # Get adapter (slug is vendor-specific identifier)
        kwargs = {}
        if city.vendor == "legistar" and city.slug == "nyc":
            kwargs["api_token"] = config.NYC_LEGISTAR_TOKEN

        try:
            adapter = get_async_adapter(city.vendor, city.slug, **kwargs)
        except VendorError as e:
            result.status = SyncStatus.SKIPPED
            result.error_message = str(e)
            logger.warning("vendor not supported", city=city.banana, vendor=city.vendor, error=str(e))
            metrics.record_error("vendor", e)
            return result

        # Async adapters don't use context managers (session managed by AsyncSessionManager)
        try:
            logger.info("starting sync", city=city.banana, vendor=city.vendor)
            result.status = SyncStatus.IN_PROGRESS

            # Fetch meetings using unified adapter interface
            try:
                all_meetings = await adapter.fetch_meetings()

                # Count different types of meeting data
                meetings_with_items = [m for m in all_meetings if m.get("items")]
                meetings_with_agenda_url = [m for m in all_meetings if m.get("agenda_url")]
                meetings_with_packet_url = [m for m in all_meetings if m.get("packet_url")]

                # Count total items
                total_items = sum(len(m.get("items", [])) for m in all_meetings)

                # Count items with matter tracking
                total_matters = 0
                for meeting in all_meetings:
                    for item in meeting.get("items", []):
                        if item.get("matter_file") or item.get("matter_id"):
                            total_matters += 1

            except (VendorError, ValueError, KeyError) as e:
                logger.error("error fetching meetings", city=city.banana, error=str(e), error_type=type(e).__name__)
                result.status = SyncStatus.FAILED
                result.error_message = str(e)
                # Record vendor failure metrics
                metrics.vendor_requests.labels(vendor=city.vendor, status='error').inc()
                metrics.record_error('vendor', e)
                return result

            result.meetings_found = len(all_meetings)

            # Log what we found with detailed breakdown
            logger.info(
                "found meetings for city",
                city=city.banana,
                meeting_count=len(all_meetings),
                total_items=total_items,
                matters_with_tracking=total_matters
            )
            logger.info(
                "meeting breakdown",
                city=city.banana,
                item_level_count=len(meetings_with_items),
                html_agenda_count=len(meetings_with_agenda_url),
                pdf_packet_count=len(meetings_with_packet_url)
            )

            # Store ALL meetings and enqueue for processing
            processed_count = 0
            items_stored_count = 0
            matters_tracked_count = 0
            matters_duplicate_count = 0
            skipped_meetings = 0

            logger.info(
                "storing meetings",
                city=city.banana,
                meeting_count=len(all_meetings)
            )
            for i, meeting_dict in enumerate(all_meetings):
                # Progress update every 10 meetings
                if (i + 1) % 10 == 0:
                    logger.info(
                        "storage progress",
                        city=city.banana,
                        progress=i + 1,
                        total=len(all_meetings)
                    )

                if not self.is_running:
                    logger.warning("processing stopped - is_running flag is false")
                    break

                # Use database method to handle all transformation and storage
                stored_meeting, storage_stats = await self.db.store_meeting_from_sync(meeting_dict, city)
                if not stored_meeting:
                    skipped = storage_stats.get('meetings_skipped', 0)
                    reason = storage_stats.get('skip_reason')
                    skipped_title = storage_stats.get('skipped_title') or meeting_dict.get("title", "Unknown")
                    if skipped:
                        skipped_meetings += skipped
                        logger.warning(
                            "skipped meeting",
                            meeting_title=skipped_title,
                            reason=reason or 'unknown reason'
                        )
                    else:
                        logger.warning(
                            "failed to store meeting without skip metadata",
                            meeting_title=skipped_title
                        )
                    continue

                processed_count += 1
                items_stored_count += storage_stats.get('items_stored', 0)
                matters_tracked_count += storage_stats.get('matters_tracked', 0)
                matters_duplicate_count += storage_stats.get('matters_duplicate', 0)

            result.meetings_processed = processed_count
            result.meetings_skipped = skipped_meetings
            result.status = SyncStatus.COMPLETED
            result.duration_seconds = time.time() - start_time

            # Record vendor success metrics
            metrics.vendor_requests.labels(vendor=city.vendor, status='success').inc()

            # Record metrics
            metrics.meetings_synced.labels(city=city.banana, vendor=city.vendor).inc(processed_count)
            metrics.items_extracted.labels(city=city.banana, vendor=city.vendor).inc(items_stored_count)
            metrics.matters_tracked.labels(city.banana).inc(matters_tracked_count)

            logger.info(
                "sync complete",
                city=city.banana,
                vendor=city.vendor,
                meetings=processed_count,
                skipped_meetings=skipped_meetings,
                items=items_stored_count,
                new_matters=matters_tracked_count,
                duplicate_matters=matters_duplicate_count,
                duration_seconds=round(result.duration_seconds, 1)
            )

        except Exception as e:
            result.status = SyncStatus.FAILED
            result.error_message = str(e)
            result.duration_seconds = time.time() - start_time

            # Record vendor failure metrics
            metrics.vendor_requests.labels(vendor=city.vendor, status='error').inc()
            metrics.record_error('vendor', e)

            # Record error metrics
            metrics.record_error(component="fetcher", error=e)

            logger.error("sync failed", city=city.banana, vendor=city.vendor, duration_seconds=round(result.duration_seconds, 1), error=str(e), error_type=type(e).__name__)

            # Add small delay on error with jitter (async)
            await asyncio.sleep(SYNC_ERROR_DELAY_BASE + random.uniform(0, SYNC_ERROR_DELAY_JITTER))

        return result

    async def _sync_city_with_retry(self, city: City, max_retries: int = 1) -> SyncResult:
        """Sync city with retry (5s, 20s delays)"""
        city_name = city.name
        city_banana = city.banana
        wait_times = [5, 20]
        last_error = "Unknown retry error"
        last_result: Optional[SyncResult] = None

        for attempt in range(max_retries):
            try:
                result = await self._sync_city(city)
                last_result = result  # Preserve for final failure case

                # Success or skip - return immediately
                if result.status in [SyncStatus.COMPLETED, SyncStatus.SKIPPED]:
                    return result

                # Failed - store error for potential retry
                last_error = result.error_message or "Sync failed"

            except Exception as e:
                # Exception - store error for potential retry
                last_error = str(e)

            # Retry logic (runs for both failure and exception paths)
            is_last_attempt = attempt >= max_retries - 1

            if is_last_attempt:
                logger.error("final sync failure after retries", city=city_name, attempts=max_retries, error=last_error)

                # Preserve structured data from last attempt if available
                if last_result:
                    last_result.status = SyncStatus.FAILED
                    last_result.error_message = last_error
                    return last_result

                # Exception path: create minimal result
                return SyncResult(city_banana=city_banana, status=SyncStatus.FAILED, error_message=last_error)

            # Wait before retry
            wait_time = wait_times[attempt] + random.uniform(0, 2)
            logger.warning(
                "sync failed - retrying",
                city=city_name,
                attempt=attempt + 1,
                max_retries=max_retries,
                wait_seconds=round(wait_time, 1),
                error=last_error
            )
            time.sleep(wait_time)

        # Shouldn't reach here due to is_last_attempt logic, but preserve data if we do
        if last_result:
            last_result.status = SyncStatus.FAILED
            last_result.error_message = last_error
            return last_result
        return SyncResult(city_banana=city_banana, status=SyncStatus.FAILED, error_message=last_error)

    async def _should_sync_city(self, city: City) -> bool:
        """Determine if city needs syncing based on activity patterns"""
        try:
            # Check recent meeting frequency
            recent_meetings = await self.db.cities.get_city_meeting_frequency(city.banana, days=30)
            last_sync = await self.db.cities.get_city_last_sync(city.banana)

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
            logger.warning("error checking sync schedule", city=city.banana, error=str(e))
            return True  # Sync on error to be safe

    async def _prioritize_cities(self, cities: List[City]) -> List[City]:
        """Sort cities by sync priority (high activity first)"""

        async def get_priority(city: City) -> float:
            try:
                # Get recent activity
                recent_meetings = await self.db.cities.get_city_meeting_frequency(
                    city.banana, days=30
                )
                last_sync = await self.db.cities.get_city_last_sync(city.banana)

                if not last_sync:
                    return 1000  # Never synced gets highest priority

                hours_since_sync = (datetime.now() - last_sync).total_seconds() / 3600

                # Priority score: activity + time pressure
                return recent_meetings * 10 + min(hours_since_sync / 24, 10)

            except (AttributeError, TypeError) as e:
                logger.warning("failed to calculate priority", city=city.banana, error=str(e), error_type=type(e).__name__)
                return 100  # Medium priority on error

        # Compute all priorities asynchronously
        priorities = []
        for city in cities:
            priority = await get_priority(city)
            priorities.append((priority, city))

        # Sort by priority (descending)
        priorities.sort(key=lambda x: x[0], reverse=True)
        return [city for _, city in priorities]
