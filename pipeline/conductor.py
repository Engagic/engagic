"""
Pipeline Conductor - Lightweight orchestration

Coordinates:
- Sync loop (via Fetcher)
- Processing loop (via Processor)
- Admin commands (force sync, status)
- Background daemon management

Refactored: Extracted fetcher and processor logic into separate modules
"""

import logging
import time
import threading
from datetime import datetime
from typing import Dict, Any, Optional

from database.db import UnifiedDatabase
from pipeline.fetcher import Fetcher, SyncResult, SyncStatus
from pipeline.processor import Processor
from config import config

logger = logging.getLogger("engagic")


class Conductor:
    """Lightweight orchestrator for sync and processing loops"""

    def __init__(self, unified_db_path: Optional[str] = None):
        """Initialize the conductor

        Args:
            unified_db_path: Database path (or uses config default)
        """
        # Use config path if not provided
        db_path = unified_db_path or config.UNIFIED_DB_PATH

        self.db = UnifiedDatabase(db_path)
        self.is_running = False
        self.sync_thread = None
        self.processing_thread = None

        # Initialize fetcher (handles city sync)
        self.fetcher = Fetcher(db=self.db)
        logger.info("[Conductor] Fetcher initialized")

        # Initialize processor (handles queue processing)
        self.processor = Processor(db=self.db)
        logger.info(
            f"[Conductor] Processor initialized "
            f"({'with' if self.processor.analyzer else 'without'} LLM analyzer)"
        )

        # Track sync status
        self.last_full_sync = None

    def start(self):
        """Start background processing threads"""
        if self.is_running:
            logger.warning("[Conductor] Already running")
            return

        logger.info("[Conductor] Starting background daemon...")
        self.is_running = True

        # Propagate running state to components
        self.fetcher.is_running = True
        self.processor.is_running = True

        # Start sync thread (runs every 7 days)
        self.sync_thread = threading.Thread(target=self._sync_loop, daemon=True)
        self.sync_thread.start()

        # Start processing thread (continuously processes jobs from the queue)
        self.processing_thread = threading.Thread(
            target=self._processing_loop, daemon=True
        )
        self.processing_thread.start()

        logger.info("[Conductor] Background daemon started")

    def stop(self):
        """Stop background processing"""
        logger.info("[Conductor] Stopping background daemon...")
        self.is_running = False

        # Propagate stop to components
        self.fetcher.is_running = False
        self.processor.is_running = False

        if self.sync_thread:
            self.sync_thread.join(timeout=30)
        if self.processing_thread:
            self.processing_thread.join(timeout=30)

        logger.info("[Conductor] Background daemon stopped")

    def _sync_loop(self):
        """Main sync loop - runs every 7 days"""
        while self.is_running:
            try:
                # Run full sync
                results = self.fetcher.sync_all()
                self.last_full_sync = datetime.now()

                logger.info(
                    f"[Conductor] Sync cycle complete: "
                    f"{len([r for r in results if r.status == SyncStatus.COMPLETED])} succeeded, "
                    f"{len([r for r in results if r.status == SyncStatus.FAILED])} failed"
                )

                # Sleep for 7 days
                for _ in range(7 * 24 * 60 * 60):  # 7 days in seconds
                    if not self.is_running:
                        break
                    time.sleep(1)

            except Exception as e:
                logger.error(f"[Conductor] Sync loop error: {e}")
                # Sleep for 2 days on error
                for _ in range(2 * 24 * 60 * 60):
                    if not self.is_running:
                        break
                    time.sleep(1)

    def _processing_loop(self):
        """Processing loop - continuously processes jobs from the queue"""
        if not self.processor.analyzer:
            logger.warning(
                "[Conductor] Analyzer not available - processing loop will not run"
            )
            return

        try:
            # Run the queue processor continuously
            self.processor.process_queue()
        except Exception as e:
            logger.error(f"[Conductor] Processing loop error: {e}")
            # Processing loop will be restarted by daemon if it crashes

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
            "failed_cities": list(self.fetcher.failed_cities),
            "failed_count": len(self.fetcher.failed_cities),
        }

    def force_sync_city(self, city_banana: str) -> SyncResult:
        """Force sync a specific city

        Args:
            city_banana: City identifier

        Returns:
            SyncResult object
        """
        # Temporarily enable running state
        old_is_running = self.is_running
        self.is_running = True
        self.fetcher.is_running = True

        try:
            result = self.fetcher.sync_city(city_banana)

            # Update failed cities tracking
            if result.status == SyncStatus.FAILED:
                self.fetcher.failed_cities.add(city_banana)
            else:
                # Remove from failed set if it succeeds
                self.fetcher.failed_cities.discard(city_banana)

            return result
        finally:
            # Restore original is_running state
            self.is_running = old_is_running
            self.fetcher.is_running = old_is_running

    def sync_and_process_city(self, city_banana: str) -> Dict[str, Any]:
        """Sync a city and immediately process all its queued jobs

        Args:
            city_banana: City identifier

        Returns:
            Dictionary with sync_result and processing stats
        """
        logger.info(f"[Conductor] Starting sync-and-process for {city_banana}")

        # Step 1: Sync the city (fetches meetings, stores, enqueues)
        sync_result = self.force_sync_city(city_banana)

        if sync_result.status != SyncStatus.COMPLETED:
            logger.error(
                f"[Conductor] Sync failed for {city_banana}: {sync_result.error_message}"
            )
            return {
                "sync_status": sync_result.status.value,
                "sync_error": sync_result.error_message,
                "meetings_found": sync_result.meetings_found,
                "processed_count": 0,
            }

        logger.info(
            f"[Conductor] Sync complete: {sync_result.meetings_found} meetings found"
        )

        # Step 2: Process all queued jobs for this city
        if not self.processor.analyzer:
            logger.warning(
                "[Conductor] Analyzer not available - meetings queued but not processed"
            )
            return {
                "sync_status": sync_result.status.value,
                "meetings_found": sync_result.meetings_found,
                "processed_count": 0,
                "warning": "Analyzer not available",
            }

        logger.info(f"[Conductor] Processing queued jobs for {city_banana}...")

        # Temporarily enable processing
        old_is_running = self.is_running
        self.is_running = True
        self.processor.is_running = True

        try:
            processing_stats = self.processor.process_city_jobs(city_banana)

            return {
                "sync_status": sync_result.status.value,
                "meetings_found": sync_result.meetings_found,
                "processed_count": processing_stats["processed_count"],
                "failed_count": processing_stats["failed_count"],
            }

        finally:
            # Restore original is_running state
            self.is_running = old_is_running
            self.processor.is_running = old_is_running


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


def main():
    """Entry point for engagic-conductor and engagic-daemon CLI"""
    import argparse

    parser = argparse.ArgumentParser(description="Background processor for engagic")
    parser.add_argument("--sync-city", help="Sync specific city by city_banana")
    parser.add_argument(
        "--sync-and-process-city",
        help="Sync city and immediately process all its meetings",
    )
    parser.add_argument("--full-sync", action="store_true", help="Run full sync once")
    parser.add_argument("--status", action="store_true", help="Show status")
    parser.add_argument("--daemon", action="store_true", help="Run as daemon")

    args = parser.parse_args()

    # Configure logging for CLI usage
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=[logging.StreamHandler()],
    )

    conductor = Conductor()

    if args.sync_city:
        result = conductor.force_sync_city(args.sync_city)
        print(f"Sync result: {result}")
    elif args.sync_and_process_city:
        result = conductor.sync_and_process_city(args.sync_and_process_city)
        print(f"Sync and process result: {result}")
    elif args.full_sync:
        results = conductor.fetcher.sync_all()
        print(f"Full sync complete: {len(results)} cities processed")
    elif args.status:
        status = conductor.get_sync_status()
        print(f"Status: {status}")
    elif args.daemon:
        conductor.start()
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            conductor.stop()
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
