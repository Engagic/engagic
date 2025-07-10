import asyncio
import logging
import time
import random
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional
from concurrent.futures import ThreadPoolExecutor
import threading
from contextlib import contextmanager
from dataclasses import dataclass
from enum import Enum
from collections import defaultdict

from databases import DatabaseManager
from fullstack import AgendaProcessor
from adapters import PrimeGovAdapter, CivicClerkAdapter, LegistarAdapter, GranicusAdapter
from config import config

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
    city_slug: str
    status: SyncStatus
    meetings_found: int = 0
    meetings_processed: int = 0
    duration_seconds: float = 0.0
    error_message: Optional[str] = None


class BackgroundProcessor:
    def __init__(self, locations_db_path: str = None, meetings_db_path: str = None, analytics_db_path: str = None):
        # Use config paths if not provided
        locations_path = locations_db_path or config.LOCATIONS_DB_PATH
        meetings_path = meetings_db_path or config.MEETINGS_DB_PATH
        analytics_path = analytics_db_path or config.ANALYTICS_DB_PATH
        
        self.db = DatabaseManager(locations_path, meetings_path, analytics_path)
        self.processor = None
        self.is_running = False
        self.sync_thread = None
        self.processing_thread = None
        self.max_workers = 1  # Reduced to 1 for polite scraping
        self.rate_limiter = RateLimiter()  # Add rate limiter
        
        # Initialize LLM processor if available
        try:
            self.processor = AgendaProcessor(api_key=config.get_api_key(), db_path=meetings_path)
            logger.info("Background processor initialized with LLM capabilities")
        except ValueError:
            logger.warning("LLM processor not available - summaries will be skipped")
        
        # Track sync status
        self.current_sync_status = {}
        self.last_full_sync = None
        self.sync_lock = threading.Lock()

    def start(self):
        """Start background processing threads"""
        if self.is_running:
            logger.warning("Background processor already running")
            return
        
        logger.info("Starting background processor...")
        self.is_running = True
        
        # Start sync thread (runs every 3 days)
        self.sync_thread = threading.Thread(target=self._sync_loop, daemon=True)
        self.sync_thread.start()
        
        # Start processing thread (processes any remaining unprocessed meetings every 2 hours)
        self.processing_thread = threading.Thread(target=self._processing_loop, daemon=True)
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
        """Main sync loop - runs every 3 days"""
        while self.is_running:
            try:
                # Run full sync
                self._run_full_sync()
                
                # Sleep for 3 days
                for _ in range(7 * 24 * 60 * 60):  # 3 days in seconds
                    if not self.is_running:
                        break
                    time.sleep(1)
                    
            except Exception as e:
                logger.error(f"Sync loop error: {e}")
                # Sleep for 2 hours on error
                for _ in range(2 * 60 * 60):
                    if not self.is_running:
                        break
                    time.sleep(1)

    def _processing_loop(self):
        """Processing loop - processes any remaining unprocessed meetings (most should be processed during sync)"""
        while self.is_running:
            try:
                if self.processor:
                    self._process_unprocessed_meetings()
                
                # Sleep for 2 hours between processing runs (less aggressive)
                for _ in range(2 * 60 * 60):
                    if not self.is_running:
                        break
                    time.sleep(1)
                    
            except Exception as e:
                logger.error(f"Processing loop error: {e}")
                # Sleep for 10 minutes on error
                for _ in range(10 * 60):
                    if not self.is_running:
                        break
                    time.sleep(1)

    def _run_full_sync(self):
        """Run full sync of all cities with vendor-aware rate limiting"""
        start_time = time.time()
        logger.info("Starting polite city sync...")
        
        with self.sync_lock:
            cities = self.db.get_all_cities()
            logger.info(f"Syncing {len(cities)} cities with rate limiting...")
            
            # Group cities by vendor for polite crawling (only supported vendors)
            supported_vendors = {"primegov", "civicclerk", "legistar", "granicus", "novusagenda"}
            by_vendor = {}
            skipped_count = 0
            
            for city in cities:
                vendor = city.get('vendor', 'unknown')
                if vendor in supported_vendors:
                    by_vendor.setdefault(vendor, []).append(city)
                else:
                    skipped_count += 1
                    logger.debug(f"Skipping city {city.get('city_name', 'unknown')} with unsupported vendor: {vendor}")
            
            total_supported = sum(len(vendor_cities) for vendor_cities in by_vendor.values())
            logger.info(f"Processing {total_supported} cities with supported adapters, skipping {skipped_count} unsupported")
            
            results = []
            
            # Process each vendor group sequentially with proper delays
            for vendor, vendor_cities in by_vendor.items():
                if not self.is_running:
                    break
                    
                # Sort cities by sync priority (high activity first)
                sorted_cities = self._prioritize_cities(vendor_cities)
                logger.info(f"Syncing {len(sorted_cities)} {vendor} cities (prioritized by activity)")
                
                for city in sorted_cities:
                    if not self.is_running:
                        break
                    
                    # Check if city needs syncing based on frequency
                    if not self._should_sync_city(city):
                        logger.debug(f"Skipping {city.get('city_name', 'unknown')} - doesn't need sync yet")
                        results.append(SyncResult(
                            city_slug=city.get('city_slug', 'unknown'),
                            status=SyncStatus.SKIPPED,
                            error_message="Not due for sync based on frequency"
                        ))
                        continue
                    
                    # Apply rate limiting before sync
                    self.rate_limiter.wait_if_needed(vendor)
                    
                    # Sync with retry logic
                    result = self._sync_city_with_retry(city)
                    results.append(result)
                
                # Break between vendor groups to be extra polite
                if vendor_cities:  # Only sleep if we processed cities
                    vendor_break = 30 + random.uniform(0, 10)  # 30-40 seconds
                    logger.info(f"Completed {vendor} cities, taking {vendor_break:.1f}s break...")
                    time.sleep(vendor_break)
            
            # Log summary
            total_meetings = sum(r.meetings_found for r in results)
            total_processed = sum(r.meetings_processed for r in results)
            duration = time.time() - start_time
            
            logger.info(f"Polite sync completed in {duration:.1f}s: {total_meetings} meetings found, {total_processed} processed")
            self.last_full_sync = datetime.now()

    def _sync_city(self, city_info: Dict[str, Any]) -> SyncResult:
        """Sync a single city"""
        city_slug = city_info['city_slug']
        city_name = city_info['city_name']
        vendor = city_info.get('vendor', '')
        
        result = SyncResult(city_slug=city_slug, status=SyncStatus.PENDING)
        
        if not vendor:
            result.status = SyncStatus.SKIPPED
            result.error_message = "No vendor configured"
            return result
        
        start_time = time.time()
        
        try:
            logger.info(f"Syncing {city_name} ({city_slug}) with {vendor}")
            result.status = SyncStatus.IN_PROGRESS
            
            # Get adapter
            adapter = self._get_adapter(vendor, city_slug)
            if not adapter:
                result.status = SyncStatus.SKIPPED
                result.error_message = f"Unsupported vendor: {vendor}"
                logger.debug(f"Skipping {city_name} - unsupported vendor: {vendor}")
                return result
            
            # Scrape ALL meetings first (for user display)
            all_meetings = list(adapter.all_meetings()) if hasattr(adapter, 'all_meetings') else list(adapter.upcoming_packets())
            meetings_with_packets = [m for m in all_meetings if m.get('packet_url')]
            
            result.meetings_found = len(all_meetings)
            logger.info(f"Found {len(all_meetings)} total meetings, {len(meetings_with_packets)} have packets")
            
            # Store ALL meetings (for user display) and process summaries for packet meetings
            processed_count = 0
            for meeting in all_meetings:
                if not self.is_running:
                    break
                
                try:
                    # Store meeting data
                    meeting_data = {
                        "city_slug": city_slug,
                        "meeting_name": meeting.get("title"),
                        "packet_url": meeting.get("packet_url"),
                        "meeting_date": meeting.get("start"),
                        "meeting_id": meeting.get("meeting_id")
                    }
                    
                    # Check if meeting has changed before processing
                    has_changed = self.db.has_meeting_changed(meeting_data)
                    if not has_changed:
                        logger.debug(f"Meeting unchanged, skipping: {meeting.get('packet_url')}")
                        processed_count += 1  # Count as processed since it's unchanged
                        continue
                    
                    logger.debug(f"Meeting changed or new, updating: {meeting.get('packet_url')}")
                    self.db.store_meeting_data(meeting_data)
                    
                    # Process summary ONLY if meeting has a packet AND LLM available
                    if meeting.get("packet_url") and self.processor:
                        cached = self.db.get_cached_summary(meeting["packet_url"])
                        if not cached:
                            logger.info(f"Processing summary for {meeting['packet_url']} (has packet)")
                            try:
                                self.processor.process_agenda_with_cache(meeting_data)
                                processed_count += 1
                                logger.info(f"Successfully processed summary for {meeting['packet_url']}")
                            except Exception as proc_error:
                                logger.error(f"Error processing summary for {meeting['packet_url']}: {proc_error}")
                        else:
                            processed_count += 1
                            logger.debug(f"Summary already cached for {meeting['packet_url']}")
                    elif not meeting.get("packet_url"):
                        logger.debug(f"Meeting '{meeting.get('title')}' has no packet - stored for display only")
                            
                except Exception as e:
                    logger.error(f"Error storing meeting {meeting.get('packet_url', 'unknown')}: {e}")
            
            result.meetings_processed = processed_count
            result.status = SyncStatus.COMPLETED
            result.duration_seconds = time.time() - start_time
            
            logger.info(f"Synced {city_name}: {result.meetings_found} meetings found, {len(meetings_with_packets)} have packets, {processed_count} processed")
            
        except Exception as e:
            result.status = SyncStatus.FAILED
            result.error_message = str(e)
            result.duration_seconds = time.time() - start_time
            logger.error(f"Failed to sync {city_name}: {e}")
            
            # Add small delay on error to avoid hammering
            time.sleep(2 + random.uniform(0, 1))
        
        return result

    def _sync_city_with_retry(self, city_info: Dict[str, Any], max_retries: int = 3) -> SyncResult:
        """Sync city with exponential backoff retry"""
        city_slug = city_info['city_slug']
        city_name = city_info.get('city_name', city_slug)
        
        for attempt in range(max_retries):
            try:
                result = self._sync_city(city_info)
                
                # If successful or skipped, return immediately
                if result.status in [SyncStatus.COMPLETED, SyncStatus.SKIPPED]:
                    return result
                    
                # If failed and we have retries left, wait and retry
                if attempt < max_retries - 1:
                    wait_time = (2 ** attempt) * 5 + random.uniform(0, 3)  # 5s, 10s, 20s + jitter
                    logger.warning(f"Sync failed for {city_name} (attempt {attempt + 1}/{max_retries}), retrying in {wait_time:.1f}s: {result.error_message}")
                    time.sleep(wait_time)
                else:
                    logger.error(f"Final sync failure for {city_name} after {max_retries} attempts: {result.error_message}")
                    return result
                    
            except Exception as e:
                if attempt < max_retries - 1:
                    wait_time = (2 ** attempt) * 5 + random.uniform(0, 3)
                    logger.warning(f"Exception syncing {city_name} (attempt {attempt + 1}/{max_retries}), retrying in {wait_time:.1f}s: {e}")
                    time.sleep(wait_time)
                else:
                    logger.error(f"Final exception for {city_name} after {max_retries} attempts: {e}")
                    return SyncResult(
                        city_slug=city_slug,
                        status=SyncStatus.FAILED,
                        error_message=str(e)
                    )
        
        # Shouldn't reach here, but just in case
        return SyncResult(
            city_slug=city_slug,
            status=SyncStatus.FAILED,
            error_message="Unknown retry error"
        )
    
    def _should_sync_city(self, city_info: Dict[str, Any]) -> bool:
        """Determine if city needs syncing based on activity patterns"""
        city_slug = city_info.get('city_slug')
        if not city_slug:
            return True
            
        try:
            # Check recent meeting frequency
            recent_meetings = self.db.get_city_meeting_frequency(city_slug, days=30)
            last_sync = self.db.get_city_last_sync(city_slug)
            
            if not last_sync:
                return True  # Never synced before
            
            hours_since_sync = (datetime.now() - last_sync).total_seconds() / 3600
            
            # Adaptive scheduling based on activity
            if recent_meetings >= 8:  # High activity (2+ meetings/week)
                return hours_since_sync >= 12  # Sync every 12 hours
            elif recent_meetings >= 4:  # Medium activity (1+ meeting/week)
                return hours_since_sync >= 24  # Sync daily
            elif recent_meetings >= 1:  # Low activity (some meetings)
                return hours_since_sync >= 72  # Sync every 3 days
            else:  # Very low activity (no recent meetings)
                return hours_since_sync >= 168  # Sync weekly
                
        except Exception as e:
            logger.warning(f"Error checking sync schedule for {city_slug}: {e}")
            return True  # Sync on error to be safe
    
    def _prioritize_cities(self, cities: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Sort cities by sync priority (high activity first)"""
        def get_priority(city):
            try:
                city_slug = city.get('city_slug')
                if not city_slug:
                    return 0
                
                # Get recent activity
                recent_meetings = self.db.get_city_meeting_frequency(city_slug, days=30)
                last_sync = self.db.get_city_last_sync(city_slug)
                
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
        supported_vendors = {"primegov", "civicclerk", "legistar", "granicus", "novusagenda"}
        
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
            from adapters import GranicusAdapter
            return GranicusAdapter(city_slug)
        elif vendor == "novusagenda":
            from adapters import NovusAgendaAdapter
            return NovusAgendaAdapter(city_slug)
        else:
            return None

    def _process_unprocessed_meetings(self):
        """Process meetings that don't have summaries yet (cleanup for any missed during sync)"""
        logger.info("Checking for unprocessed meetings...")
        
        # Get meetings without summaries
        unprocessed = self.db.get_unprocessed_meetings(limit=20)  # Reduced limit since most should be processed during sync
        
        if not unprocessed:
            logger.debug("No unprocessed meetings found")
            return
        
        logger.info(f"Found {len(unprocessed)} unprocessed meetings (processing missed items)")
        
        with ThreadPoolExecutor(max_workers=2) as executor:  # Limit to 2 concurrent LLM requests
            futures = []
            
            for meeting in unprocessed:
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

    def _process_meeting_summary(self, meeting: Dict[str, Any]):
        """Process summary for a single meeting"""
        packet_url = meeting.get('packet_url')
        if not packet_url:
            return
        
        try:
            logger.info(f"Processing summary for {packet_url}")
            
            # Check if still unprocessed (avoid race conditions)
            cached = self.db.get_cached_summary(packet_url)
            if cached:
                logger.debug(f"Meeting {packet_url} already processed, skipping")
                return
            
            # Process with cache
            meeting_data = {
                "packet_url": packet_url,
                "city_slug": meeting.get('city_slug'),
                "meeting_name": meeting.get('meeting_name'),
                "meeting_date": meeting.get('meeting_date'),
                "meeting_id": meeting.get('meeting_id'),
            }
            
            result = self.processor.process_agenda_with_cache(meeting_data)
            logger.info(f"Processed {packet_url} in {result['processing_time']:.1f}s")
            
        except Exception as e:
            logger.error(f"Error processing summary for {packet_url}: {e}")

    def get_sync_status(self) -> Dict[str, Any]:
        """Get current sync status"""
        with self.sync_lock:
            stats = self.db.get_cache_stats()
            return {
                "is_running": self.is_running,
                "last_full_sync": self.last_full_sync.isoformat() if self.last_full_sync else None,
                "cities_count": stats.get("cities_count", 0),
                "meetings_count": stats.get("meetings_count", 0),
                "processed_count": stats.get("processed_count", 0),
                "unprocessed_count": stats.get("meetings_count", 0) - stats.get("processed_count", 0),
                "current_sync_status": dict(self.current_sync_status)
            }

    def force_sync_city(self, city_slug: str) -> SyncResult:
        """Force sync a specific city"""
        city_info = self.db.get_city_by_slug(city_slug)
        if not city_info:
            return SyncResult(city_slug=city_slug, status=SyncStatus.FAILED, error_message="City not found")
        
        return self._sync_city(city_info)

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
    parser.add_argument("--sync-city", help="Sync specific city by slug")
    parser.add_argument("--process-meeting", help="Process specific meeting by packet URL")
    parser.add_argument("--full-sync", action="store_true", help="Run full sync once")
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