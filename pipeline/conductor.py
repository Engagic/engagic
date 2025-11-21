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
import signal
import sys
import time
import threading
from contextlib import contextmanager
from datetime import datetime
from typing import Dict, Any, Optional, List

from database.db import UnifiedDatabase
from pipeline.fetcher import Fetcher, SyncResult, SyncStatus
from pipeline.processor import Processor
from config import config

from config import get_logger

logger = get_logger(__name__).bind(component="engagic")

# Shutdown polling interval (seconds)
SHUTDOWN_POLL_INTERVAL = 1


class Conductor:
    """Lightweight orchestrator for sync and processing loops"""

    def __init__(self, unified_db_path: Optional[str] = None):
        """Initialize the conductor

        Args:
            unified_db_path: Database path (or uses config default)
        """
        # Use config path if not provided
        db_path = unified_db_path or config.UNIFIED_DB_PATH

        # Conductor's own connection (for status queries, admin commands)
        self.db = UnifiedDatabase(db_path)
        self.is_running = False
        self.sync_thread = None
        self.processing_thread = None

        # Initialize fetcher with its own connection (for sync_thread)
        # CRITICAL: Each background thread needs its own SQLite connection
        # to avoid "database is locked" errors and race conditions
        self.fetcher = Fetcher(db=None)  # Creates own connection
        logger.info("[Conductor] Fetcher initialized with dedicated connection")

        # Initialize processor with its own connection (for processing_thread)
        self.processor = Processor(db=None)  # Creates own connection
        logger.info(
            f"[Conductor] Processor initialized with dedicated connection "
            f"({'with' if self.processor.analyzer else 'without'} LLM analyzer)"
        )

        # Track sync status
        self.last_full_sync = None

    @contextmanager
    def enable_processing(self):
        """Context manager for temporarily enabling processing state"""
        old_state = self.is_running
        self.is_running = True
        self.fetcher.is_running = True
        self.processor.is_running = True
        try:
            yield
        finally:
            self.is_running = old_state
            self.fetcher.is_running = old_state
            self.processor.is_running = old_state

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
                    time.sleep(SHUTDOWN_POLL_INTERVAL)

            except Exception as e:
                logger.error("sync loop error", error=str(e), error_type=type(e).__name__)
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
            logger.error("processing loop error", error=str(e), error_type=type(e).__name__)
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
        with self.enable_processing():
            result = self.fetcher.sync_city(city_banana)

            # Update failed cities tracking
            if result.status == SyncStatus.FAILED:
                self.fetcher.failed_cities.add(city_banana)
            else:
                # Remove from failed set if it succeeds
                self.fetcher.failed_cities.discard(city_banana)

            return result

    def sync_and_process_city(self, city_banana: str) -> Dict[str, Any]:
        """Sync a city and immediately process all its queued jobs

        Args:
            city_banana: City identifier

        Returns:
            Dictionary with sync_result and processing stats
        """
        logger.info("starting sync-and-process", city=city_banana)

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

        logger.info("processing queued jobs", city=city_banana)

        with self.enable_processing():
            processing_stats = self.processor.process_city_jobs(city_banana)

            return {
                "sync_status": sync_result.status.value,
                "meetings_found": sync_result.meetings_found,
                "processed_count": processing_stats["processed_count"],
                "failed_count": processing_stats["failed_count"],
            }

    def sync_cities(self, city_bananas: List[str]) -> List[Dict[str, Any]]:
        """Sync multiple cities (fetches meetings, enqueues for processing)

        Args:
            city_bananas: List of city banana identifiers

        Returns:
            List of sync results
        """
        logger.info("syncing cities", city_count=len(city_bananas))
        results = self.fetcher.sync_cities(city_bananas)

        # Convert SyncResult objects to dicts
        return [
            {
                "city_banana": r.city_banana,
                "status": r.status.value,
                "meetings_found": r.meetings_found,
                "meetings_processed": r.meetings_processed,
                "duration": r.duration_seconds,
                "error": r.error_message,
            }
            for r in results
        ]

    def process_cities(self, city_bananas: List[str]) -> Dict[str, Any]:
        """Process queued meetings for multiple cities (no sync, just process)

        Args:
            city_bananas: List of city banana identifiers

        Returns:
            Summary of processing results
        """
        logger.info("processing queued jobs for cities", city_count=len(city_bananas))

        if not self.processor.analyzer:
            logger.warning(
                "[Conductor] Analyzer not available - cannot process meetings"
            )
            return {
                "cities_count": len(city_bananas),
                "processed_count": 0,
                "error": "Analyzer not available",
            }

        total_processed = 0
        total_failed = 0
        city_results = []

        with self.enable_processing():
            for banana in city_bananas:
                if not self.is_running:
                    break

                logger.info("processing jobs for city", city=banana)
                stats = self.processor.process_city_jobs(banana)

                total_processed += stats["processed_count"]
                total_failed += stats["failed_count"]

                city_results.append({
                    "city_banana": banana,
                    "processed": stats["processed_count"],
                    "failed": stats["failed_count"],
                })

            return {
                "cities_count": len(city_bananas),
                "processed_count": total_processed,
                "failed_count": total_failed,
                "city_results": city_results,
            }

    def sync_and_process_cities(self, city_bananas: List[str]) -> Dict[str, Any]:
        """Sync multiple cities and immediately process all their meetings

        Args:
            city_bananas: List of city banana identifiers

        Returns:
            Combined sync and processing results
        """
        logger.info("sync and process cities", city_count=len(city_bananas))

        # Step 1: Sync all cities
        sync_results = self.sync_cities(city_bananas)
        total_meetings = sum(r["meetings_found"] for r in sync_results)

        logger.info("sync complete", total_meetings=total_meetings, city_count=len(city_bananas))

        # Step 2: Process all queued jobs for these cities
        process_results = self.process_cities(city_bananas)

        return {
            "sync_results": sync_results,
            "processing_results": process_results,
            "total_meetings_found": total_meetings,
            "total_processed": process_results["processed_count"],
            "total_failed": process_results["failed_count"],
        }

    def preview_queue(self, city_banana: Optional[str] = None, limit: int = 10) -> Dict[str, Any]:
        """Preview queued jobs without processing them

        Args:
            city_banana: Optional city filter
            limit: Max jobs to show

        Returns:
            List of queued jobs with meeting info
        """
        logger.info("[Conductor] Previewing queue...")

        # Get pending jobs from queue
        jobs = []
        if city_banana:
            # Get jobs for specific city
            job = self.db.queue.get_next_for_processing(banana=city_banana)
            if job:
                jobs.append(job)
        else:
            # Get all pending jobs (need to implement this query)
            # For now, just show stats
            stats = self.db.queue.get_queue_stats()
            return stats

        previews = []
        for job in jobs[:limit]:
            # QueueJob is a dataclass, access attributes with dot notation
            # Get meeting_id from the payload based on job type
            if job.job_type == "meeting":
                meeting_id = job.payload.meeting_id
            elif job.job_type == "matter":
                meeting_id = job.payload.meeting_id
            else:
                continue

            meeting = self.db.meetings.get_meeting(meeting_id)
            if meeting:
                previews.append({
                    "queue_id": job.id,
                    "job_type": job.job_type,
                    "meeting_id": meeting.id,
                    "city_banana": job.banana,
                    "title": meeting.title,
                    "date": meeting.date.isoformat() if meeting.date else None,
                    "priority": job.priority,
                    "status": job.status,
                })

        return {
            "total_queued": len(jobs),
            "previews": previews,
        }



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


def _parse_city_list(arg: str) -> List[str]:
    """Helper to parse city list (supports comma-separated or @file)"""
    if arg.startswith("@"):
        file_path = arg[1:]
        with open(file_path, "r") as f:
            cities = []
            for line in f:
                line = line.split('#')[0].strip()
                if line:
                    cities.append(line)
            return cities
    return [c.strip() for c in arg.split(",") if c.strip()]


def main():
    """Entry point for engagic-conductor and engagic-daemon CLI"""
    import click
    import json

    # Configure logging for CLI usage
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=[logging.StreamHandler()],
    )

    @click.group(invoke_without_command=True)
    @click.pass_context
    def cli(ctx):
        """Background processor for engagic"""
        if ctx.invoked_subcommand is None:
            click.echo(ctx.get_help())

    @cli.command("sync-city")
    @click.argument("banana")
    def sync_city(banana):
        """Sync specific city by city_banana"""
        conductor = Conductor()
        result = conductor.force_sync_city(banana)
        click.echo(f"Sync result: {result}")

    @cli.command("sync-and-process-city")
    @click.argument("banana")
    def sync_and_process_city(banana):
        """Sync city and immediately process all its meetings"""
        conductor = Conductor()
        result = conductor.sync_and_process_city(banana)
        click.echo(json.dumps(result, indent=2))

    @cli.command("sync-cities")
    @click.argument("cities")
    def sync_cities(cities):
        """Sync multiple cities (comma-separated bananas or @file path)"""
        conductor = Conductor()
        city_list = _parse_city_list(cities)
        click.echo(f"Syncing {len(city_list)} cities: {', '.join(city_list)}")
        results = conductor.sync_cities(city_list)
        click.echo(json.dumps(results, indent=2))

    @cli.command("process-cities")
    @click.argument("cities")
    def process_cities(cities):
        """Process queued jobs for multiple cities (comma-separated bananas or @file path)"""
        conductor = Conductor()
        city_list = _parse_city_list(cities)
        click.echo(f"Processing queued jobs for {len(city_list)} cities: {', '.join(city_list)}")
        results = conductor.process_cities(city_list)
        click.echo(json.dumps(results, indent=2))

    @cli.command("sync-and-process-cities")
    @click.argument("cities")
    def sync_and_process_cities(cities):
        """Sync and process multiple cities (comma-separated bananas or @file path)"""
        conductor = Conductor()
        city_list = _parse_city_list(cities)
        click.echo(f"Syncing and processing {len(city_list)} cities: {', '.join(city_list)}")
        results = conductor.sync_and_process_cities(city_list)
        click.echo(json.dumps(results, indent=2))

    @cli.command("full-sync")
    def full_sync():
        """Run full sync once"""
        conductor = Conductor()
        results = conductor.fetcher.sync_all()
        click.echo(f"Full sync complete: {len(results)} cities processed")

    @cli.command("status")
    def status():
        """Show sync status"""
        conductor = Conductor()
        sync_status = conductor.get_sync_status()
        click.echo(f"Status: {sync_status}")

    @cli.command("fetcher")
    def fetcher():
        """Run as fetcher service (auto sync only, no processing)"""
        conductor = Conductor()

        def signal_handler(signum, frame):
            sig_name = "SIGTERM" if signum == signal.SIGTERM else "SIGINT"
            logger.info("received signal - graceful shutdown", signal=sig_name)
            conductor.is_running = False
            conductor.fetcher.is_running = False
            logger.info("[Fetcher] Shutdown complete")
            sys.exit(0)

        signal.signal(signal.SIGTERM, signal_handler)
        signal.signal(signal.SIGINT, signal_handler)

        logger.info("[Fetcher] Starting fetcher service (sync only, no processing)")
        logger.info("[Fetcher] Sync interval: 72 hours")

        conductor.is_running = True
        conductor.fetcher.is_running = True

        while conductor.is_running:
            try:
                logger.info("[Fetcher] Starting city sync cycle...")
                results = conductor.fetcher.sync_all()
                conductor.last_full_sync = datetime.now()

                succeeded = len([r for r in results if r.status == SyncStatus.COMPLETED])
                failed = len([r for r in results if r.status == SyncStatus.FAILED])
                logger.info("sync cycle complete", succeeded=succeeded, failed=failed)

                logger.info("[Fetcher] Sleeping for 72 hours until next sync...")
                for _ in range(72 * 60 * 60):
                    if not conductor.is_running:
                        break
                    time.sleep(SHUTDOWN_POLL_INTERVAL)

            except Exception as e:
                logger.error("sync loop error", error=str(e), error_type=type(e).__name__)
                logger.info("[Fetcher] Sleeping for 2 hours after error...")
                for _ in range(2 * 60 * 60):
                    if not conductor.is_running:
                        break
                    time.sleep(SHUTDOWN_POLL_INTERVAL)

    @cli.command("preview-queue")
    @click.argument("banana", required=False)
    def preview_queue(banana):
        """Preview queued jobs (optionally specify city_banana)"""
        conductor = Conductor()
        result = conductor.preview_queue(city_banana=banana)
        click.echo(json.dumps(result, indent=2))

    @cli.command("extract-text")
    @click.argument("meeting_id")
    @click.option("--output-file", "-o", help="Output file for extracted text")
    def extract_text(meeting_id, output_file):
        """Extract text from meeting PDF for manual review"""
        from pipeline.admin import extract_text_preview
        result = extract_text_preview(meeting_id, output_file=output_file)
        click.echo(json.dumps(result, indent=2))

    @cli.command("preview-items")
    @click.argument("meeting_id")
    @click.option("--extract-text", is_flag=True, help="Extract text from item attachments")
    @click.option("--output-dir", "-o", help="Output directory for item texts")
    def preview_items(meeting_id, extract_text, output_dir):
        """Preview items for a meeting"""
        from pipeline.admin import preview_items as preview_items_func
        result = preview_items_func(meeting_id, extract_text=extract_text, output_dir=output_dir)
        click.echo(json.dumps(result, indent=2))

    cli()


if __name__ == "__main__":
    main()
