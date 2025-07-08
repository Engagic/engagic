import asyncio
import logging
import time
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional
from concurrent.futures import ThreadPoolExecutor
import threading
from contextlib import contextmanager
from dataclasses import dataclass
from enum import Enum

from database import MeetingDatabase
from fullstack import AgendaProcessor
from adapters import PrimeGovAdapter, CivicClerkAdapter

logger = logging.getLogger("engagic")


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
    def __init__(self, db_path: str = "/root/engagic/app/meetings.db"):
        self.db = MeetingDatabase(db_path)
        self.processor = None
        self.is_running = False
        self.sync_thread = None
        self.processing_thread = None
        self.max_workers = 3  # Limit concurrent processing to avoid overwhelming servers
        
        # Initialize LLM processor if available
        try:
            self.processor = AgendaProcessor()
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
                for _ in range(3 * 24 * 60 * 60):  # 3 days in seconds
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
        """Run full sync of all cities"""
        start_time = time.time()
        logger.info("Starting full city sync...")
        
        with self.sync_lock:
            cities = self.db.get_all_cities()
            logger.info(f"Syncing {len(cities)} cities...")
            
            results = []
            with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
                futures = []
                
                for city in cities:
                    if not self.is_running:
                        break
                    
                    future = executor.submit(self._sync_city, city)
                    futures.append(future)
                
                # Collect results
                for future in futures:
                    try:
                        result = future.result(timeout=300)  # 5 minute timeout per city
                        results.append(result)
                    except Exception as e:
                        logger.error(f"City sync future failed: {e}")
            
            # Log summary
            total_meetings = sum(r.meetings_found for r in results)
            total_processed = sum(r.meetings_processed for r in results)
            duration = time.time() - start_time
            
            logger.info(f"Full sync completed in {duration:.1f}s: {total_meetings} meetings found, {total_processed} processed")
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
                result.status = SyncStatus.FAILED
                result.error_message = f"Unknown vendor: {vendor}"
                return result
            
            # Scrape meetings
            meetings = list(adapter.upcoming_packets())
            result.meetings_found = len(meetings)
            
            # Store meetings and process summaries immediately
            processed_count = 0
            for meeting in meetings:
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
                    
                    self.db.store_meeting_data(meeting_data, vendor)
                    
                    # Process summary immediately if LLM available and not already processed
                    if self.processor and meeting.get("packet_url"):
                        cached = self.db.get_cached_summary(meeting["packet_url"])
                        if not cached:
                            logger.info(f"Processing summary for {meeting['packet_url']} immediately")
                            try:
                                self.processor.process_agenda_with_cache(meeting_data)
                                processed_count += 1
                                logger.info(f"Successfully processed summary for {meeting['packet_url']}")
                            except Exception as proc_error:
                                logger.error(f"Error processing summary for {meeting['packet_url']}: {proc_error}")
                        else:
                            processed_count += 1
                            logger.debug(f"Summary already cached for {meeting['packet_url']}")
                            
                except Exception as e:
                    logger.error(f"Error storing meeting {meeting.get('packet_url', 'unknown')}: {e}")
            
            result.meetings_processed = processed_count
            result.status = SyncStatus.COMPLETED
            result.duration_seconds = time.time() - start_time
            
            logger.info(f"Synced {city_name}: {result.meetings_found} meetings, {processed_count} processed")
            
        except Exception as e:
            result.status = SyncStatus.FAILED
            result.error_message = str(e)
            result.duration_seconds = time.time() - start_time
            logger.error(f"Failed to sync {city_name}: {e}")
        
        return result

    def _get_adapter(self, vendor: str, city_slug: str):
        """Get appropriate adapter for vendor"""
        if vendor == "primegov":
            return PrimeGovAdapter(city_slug)
        elif vendor == "civicclerk":
            return CivicClerkAdapter(city_slug)
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