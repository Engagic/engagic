"""
Pipeline Conductor - Lightweight orchestration

Coordinates:
- Sync loop (via Fetcher)
- Processing loop (via Processor)
- Admin commands (force sync, status)

Pure async architecture - no threading, uses asyncio.create_task()
"""


import asyncio
import logging
import signal
import sys
from contextlib import contextmanager
from typing import Dict, Any, Optional, List

from database.db_postgres import Database
from pipeline.fetcher import Fetcher, SyncResult, SyncStatus
from pipeline.processor import Processor
from pipeline.click_types import BANANA

from config import get_logger

logger = get_logger(__name__).bind(component="engagic")

# Shutdown polling interval (seconds)
SHUTDOWN_POLL_INTERVAL = 1


class Conductor:
    """Lightweight orchestrator for sync and processing loops"""

    def __init__(self, db: Database):
        """Initialize the conductor

        Args:
            db: PostgreSQL database instance
        """
        self.db = db
        self.is_running = False

        # Initialize fetcher and processor with database
        self.fetcher = Fetcher(db=db)
        logger.info("fetcher initialized")

        self.processor = Processor(db=db)
        logger.info(
            "processor initialized",
            has_analyzer=self.processor.analyzer is not None
        )

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

    async def close(self):
        """Cleanup resources (HTTP sessions)"""
        await self.processor.close()

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()
        return False

    async def get_sync_status(self) -> Dict[str, Any]:
        """Get current sync status"""
        stats = await self.db.get_stats()
        return {
            "is_running": self.is_running,
            "active_cities": stats.get("active_cities", 0),
            "total_meetings": stats.get("total_meetings", 0),
            "summarized_meetings": stats.get("summarized_meetings", 0),
            "pending_meetings": stats.get("pending_meetings", 0),
            "failed_cities": list(self.fetcher.failed_cities),
            "failed_count": len(self.fetcher.failed_cities),
        }

    async def force_sync_city(self, city_banana: str) -> SyncResult:
        """Force sync a specific city

        Args:
            city_banana: City identifier

        Returns:
            SyncResult object
        """
        with self.enable_processing():
            result = await self.fetcher.sync_city(city_banana)

            # Update failed cities tracking
            if result.status == SyncStatus.FAILED:
                self.fetcher.failed_cities.add(city_banana)
            else:
                # Remove from failed set if it succeeds
                self.fetcher.failed_cities.discard(city_banana)

            return result

    async def sync_and_process_city(self, city_banana: str) -> Dict[str, Any]:
        """Sync a city and immediately process all its queued jobs

        Args:
            city_banana: City identifier

        Returns:
            Dictionary with sync_result and processing stats
        """
        logger.info("starting sync-and-process", city=city_banana)

        # Step 1: Sync the city (fetches meetings, stores, enqueues)
        sync_result = await self.force_sync_city(city_banana)

        if sync_result.status != SyncStatus.COMPLETED:
            logger.error(
                "sync failed for city",
                city=city_banana,
                error=sync_result.error_message
            )
            return {
                "sync_status": sync_result.status.value,
                "sync_error": sync_result.error_message,
                "meetings_found": sync_result.meetings_found,
                "processed_count": 0,
            }

        logger.info(
            "sync complete",
            meetings_found=sync_result.meetings_found
        )

        # Step 2: Process all queued jobs for this city
        if not self.processor.analyzer:
            logger.warning(
                "analyzer not available - meetings queued but not processed"
            )
            return {
                "sync_status": sync_result.status.value,
                "meetings_found": sync_result.meetings_found,
                "processed_count": 0,
                "warning": "Analyzer not available",
            }

        logger.info("processing queued jobs", city=city_banana)

        with self.enable_processing():
            processing_stats = await self.processor.process_city_jobs(city_banana)

            return {
                "sync_status": sync_result.status.value,
                "meetings_found": sync_result.meetings_found,
                "processed_count": processing_stats["processed_count"],
                "failed_count": processing_stats["failed_count"],
            }

    async def sync_cities(self, city_bananas: List[str]) -> List[Dict[str, Any]]:
        """Sync multiple cities (fetches meetings, enqueues for processing)

        Args:
            city_bananas: List of city banana identifiers

        Returns:
            List of sync results
        """
        logger.info("syncing cities", city_count=len(city_bananas))
        results = await self.fetcher.sync_cities(city_bananas)

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

    async def process_cities(self, city_bananas: List[str]) -> Dict[str, Any]:
        """Process queued meetings for multiple cities (no sync, just process)

        Args:
            city_bananas: List of city banana identifiers

        Returns:
            Summary of processing results
        """
        logger.info("processing queued jobs for cities", city_count=len(city_bananas))

        if not self.processor.analyzer:
            logger.warning(
                "analyzer not available - cannot process meetings"
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
            total_items_processed = 0
            total_items_new = 0
            total_items_skipped = 0
            total_items_failed = 0

            for banana in city_bananas:
                if not self.is_running:
                    break

                logger.info("processing jobs for city", city=banana)
                stats = await self.processor.process_city_jobs(banana)

                total_processed += stats["processed_count"]
                total_failed += stats["failed_count"]
                total_items_processed += stats.get("items_processed", 0)
                total_items_new += stats.get("items_new", 0)
                total_items_skipped += stats.get("items_skipped", 0)
                total_items_failed += stats.get("items_failed", 0)

                city_results.append({
                    "city_banana": banana,
                    "processed": stats["processed_count"],
                    "failed": stats["failed_count"],
                    "items_processed": stats.get("items_processed", 0),
                    "items_new": stats.get("items_new", 0),
                    "items_skipped": stats.get("items_skipped", 0),
                })

            return {
                "cities_count": len(city_bananas),
                "meetings_processed": total_processed,
                "meetings_failed": total_failed,
                "items_processed": total_items_processed,
                "items_new": total_items_new,
                "items_skipped": total_items_skipped,
                "items_failed": total_items_failed,
                "city_results": city_results,
            }

    async def sync_and_process_cities(self, city_bananas: List[str]) -> Dict[str, Any]:
        """Sync multiple cities and immediately process all their meetings

        Args:
            city_bananas: List of city banana identifiers

        Returns:
            Combined sync and processing results
        """
        logger.info("sync and process cities", city_count=len(city_bananas))

        # Step 1: Sync all cities
        sync_results = await self.sync_cities(city_bananas)
        total_meetings = sum(r["meetings_found"] for r in sync_results)

        logger.info("sync complete", total_meetings=total_meetings, city_count=len(city_bananas))

        # Step 2: Process all queued jobs for these cities
        process_results = await self.process_cities(city_bananas)

        return {
            "sync_results": sync_results,
            "processing_results": process_results,
            "total_meetings_found": total_meetings,
            "total_processed": process_results["processed_count"],
            "total_failed": process_results["failed_count"],
        }

    async def preview_queue(self, city_banana: Optional[str] = None, limit: int = 10) -> Dict[str, Any]:
        """Preview queued jobs without processing them

        Args:
            city_banana: Optional city filter
            limit: Max jobs to show

        Returns:
            List of queued jobs with meeting info
        """
        logger.info("previewing queue")

        # Get pending jobs from queue
        jobs = []
        if city_banana:
            # Get jobs for specific city
            job = await self.db.queue.get_next_for_processing(banana=city_banana)
            if job:
                jobs.append(job)
        else:
            # Get all pending jobs (need to implement this query)
            # For now, just show stats
            stats = await self.db.queue.get_queue_stats()
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

            meeting = await self.db.meetings.get_meeting(meeting_id)
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



# Global instance management removed - CLI commands create their own instances
# TODO: If needed for daemon mode, implement using asyncio.run()


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
    @click.argument("banana", type=BANANA)
    def sync_city(banana):
        """Sync specific city by city_banana"""
        async def run():
            db = await Database.create()
            try:
                async with Conductor(db) as conductor:
                    return await conductor.force_sync_city(banana)
            finally:
                await db.close()

        result = asyncio.run(run())
        click.echo(f"Sync result: {result}")

    @cli.command("sync-and-process-city")
    @click.argument("banana", type=BANANA)
    def sync_and_process_city(banana):
        """Sync city and immediately process all its meetings"""
        async def run():
            db = await Database.create()
            try:
                async with Conductor(db) as conductor:
                    return await conductor.sync_and_process_city(banana)
            finally:
                await db.close()

        result = asyncio.run(run())
        click.echo(json.dumps(result, indent=2))

    @cli.command("sync-cities")
    @click.argument("cities")
    def sync_cities(cities):
        """Sync multiple cities (comma-separated bananas or @file path)"""
        city_list = _parse_city_list(cities)
        click.echo(f"Syncing {len(city_list)} cities: {', '.join(city_list)}")

        async def run():
            db = await Database.create()
            try:
                async with Conductor(db) as conductor:
                    return await conductor.sync_cities(city_list)
            finally:
                await db.close()

        results = asyncio.run(run())
        click.echo(json.dumps(results, indent=2))

    @cli.command("process-cities")
    @click.argument("cities")
    def process_cities(cities):
        """Process queued jobs for multiple cities (comma-separated bananas or @file path)"""
        city_list = _parse_city_list(cities)
        click.echo(f"Processing queued jobs for {len(city_list)} cities: {', '.join(city_list)}")

        async def run():
            db = await Database.create()
            try:
                async with Conductor(db) as conductor:
                    return await conductor.process_cities(city_list)
            finally:
                await db.close()

        results = asyncio.run(run())
        click.echo(json.dumps(results, indent=2))

    @cli.command("sync-and-process-cities")
    @click.argument("cities")
    def sync_and_process_cities(cities):
        """Sync and process multiple cities (comma-separated bananas or @file path)"""
        city_list = _parse_city_list(cities)
        click.echo(f"Syncing and processing {len(city_list)} cities: {', '.join(city_list)}")

        async def run():
            db = await Database.create()
            try:
                async with Conductor(db) as conductor:
                    return await conductor.sync_and_process_cities(city_list)
            finally:
                await db.close()

        results = asyncio.run(run())
        click.echo(json.dumps(results, indent=2))

    @cli.command("full-sync")
    def full_sync():
        """Run full sync once"""
        async def run():
            db = await Database.create()
            try:
                async with Conductor(db) as conductor:
                    return await conductor.fetcher.sync_all()
            finally:
                await db.close()

        results = asyncio.run(run())
        click.echo(f"Full sync complete: {len(results)} cities processed")

    @cli.command("preview-watchlist")
    def preview_watchlist():
        """Show cities that users are watching (no sync or processing)

        Displays which cities have active alert subscriptions from users.
        """
        async def run():
            db = await Database.create()
            try:
                demanded = await db.userland.get_demanded_cities()
                if not demanded:
                    return {"message": "No cities in user watchlists", "valid": [], "unknown": []}

                valid_cities = []
                unknown_cities = []
                for banana in demanded:
                    city = await db.cities.get_city(banana)
                    if city:
                        valid_cities.append({"banana": banana, "name": city.name, "state": city.state})
                    else:
                        unknown_cities.append(banana)

                return {
                    "total": len(demanded),
                    "valid": valid_cities,
                    "unknown": unknown_cities
                }
            finally:
                await db.close()

        result = asyncio.run(run())
        if "message" in result:
            click.echo(result["message"])
        else:
            click.echo(f"Watchlist: {result['total']} cities")
            if result["valid"]:
                click.echo(f"\nValid ({len(result['valid'])}):")
                for city in result["valid"]:
                    click.echo(f"  {city['banana']} - {city['name']}, {city['state']}")
            if result["unknown"]:
                click.echo(f"\nUnknown (need setup): {', '.join(result['unknown'])}")

    @cli.command("sync-watchlist")
    def sync_watchlist():
        """Sync and process cities that users are watching

        Queries userland for cities with active alert subscriptions.
        These are cities users explicitly requested - they get priority.
        """
        async def run():
            db = await Database.create()
            try:
                # Get demanded cities from userland
                demanded = await db.userland.get_demanded_cities()
                if not demanded:
                    return {"message": "No cities in user watchlists", "cities": []}

                # Filter to cities that exist in our database
                valid_cities = []
                unknown_cities = []
                for banana in demanded:
                    city = await db.cities.get_city(banana)
                    if city:
                        valid_cities.append(banana)
                    else:
                        unknown_cities.append(banana)

                if unknown_cities:
                    click.echo(f"Unknown cities (need manual setup): {', '.join(unknown_cities)}")
                    # Record unknown cities for tracking
                    for banana in unknown_cities:
                        await db.userland.record_city_request(banana)

                if not valid_cities:
                    return {"message": "No valid cities to sync", "cities": []}

                click.echo(f"Syncing {len(valid_cities)} watchlist cities: {', '.join(valid_cities)}")

                # Sync and process
                async with Conductor(db) as conductor:
                    results = await conductor.sync_and_process_cities(valid_cities)
                    return {
                        "cities_synced": len(valid_cities),
                        "unknown_cities": unknown_cities,
                        "results": results
                    }
            finally:
                await db.close()

        results = asyncio.run(run())
        if "message" in results:
            click.echo(results["message"])
        else:
            click.echo(f"Watchlist sync complete: {results['cities_synced']} cities")

    @cli.command("process-watchlist")
    def process_watchlist():
        """Process queued jobs for cities that users are watching

        No sync - just processes existing queue for watchlist cities.
        """
        async def run():
            db = await Database.create()
            try:
                demanded = await db.userland.get_demanded_cities()
                if not demanded:
                    return {"message": "No cities in user watchlists"}

                # Filter to valid cities
                valid_cities = []
                unknown_cities = []
                for banana in demanded:
                    city = await db.cities.get_city(banana)
                    if city:
                        valid_cities.append(banana)
                    else:
                        unknown_cities.append(banana)

                if unknown_cities:
                    # Record unknown cities for tracking
                    for banana in unknown_cities:
                        await db.userland.record_city_request(banana)

                if not valid_cities:
                    return {"message": "No valid cities to process"}

                click.echo(f"Processing {len(valid_cities)} watchlist cities: {', '.join(valid_cities)}")

                async with Conductor(db) as conductor:
                    results = await conductor.process_cities(valid_cities)
                    return {"cities_processed": len(valid_cities), "results": results}
            finally:
                await db.close()

        results = asyncio.run(run())
        if "message" in results:
            click.echo(results["message"])
        else:
            click.echo(f"Watchlist processing complete: {results['cities_processed']} cities")

    @cli.command("city-requests")
    def city_requests():
        """Show pending city requests from users

        Lists cities that users have requested but don't exist in the database.
        Sorted by demand (request count).
        """
        async def run():
            db = await Database.create()
            try:
                requests = await db.userland.get_pending_city_requests()
                return requests
            finally:
                await db.close()

        requests = asyncio.run(run())
        if not requests:
            click.echo("No pending city requests")
            return

        click.echo(f"\nPending city requests ({len(requests)} total):\n")
        click.echo(f"{'City':<25} {'Requests':<10} {'First Requested':<20} {'Last Requested':<20}")
        click.echo("-" * 75)
        for req in requests:
            first = req['first_requested'].strftime('%Y-%m-%d %H:%M') if req['first_requested'] else '-'
            last = req['last_requested'].strftime('%Y-%m-%d %H:%M') if req['last_requested'] else '-'
            click.echo(f"{req['city_banana']:<25} {req['request_count']:<10} {first:<20} {last:<20}")

    @cli.command("status")
    def status():
        """Show sync status"""
        async def run():
            db = await Database.create()
            try:
                async with Conductor(db) as conductor:
                    return await conductor.get_sync_status()
            finally:
                await db.close()

        sync_status = asyncio.run(run())
        click.echo(f"Status: {sync_status}")

    @cli.command("fetcher")
    def fetcher():
        """Run as fetcher service (auto sync only, no processing)"""
        async def run():
            db = await Database.create()
            try:
                conductor = Conductor(db)

                def signal_handler(signum, frame):
                    sig_name = "SIGTERM" if signum == signal.SIGTERM else "SIGINT"
                    logger.info("received signal - graceful shutdown", signal=sig_name)
                    conductor.is_running = False
                    conductor.fetcher.is_running = False
                    logger.info("shutdown complete")
                    sys.exit(0)

                signal.signal(signal.SIGTERM, signal_handler)
                signal.signal(signal.SIGINT, signal_handler)

                logger.info("starting fetcher service (sync only, no processing)")
                logger.info("sync interval: 72 hours")

                conductor.is_running = True
                conductor.fetcher.is_running = True

                while conductor.is_running:
                    try:
                        logger.info("starting city sync cycle")
                        results = await conductor.fetcher.sync_all()

                        succeeded = len([r for r in results if r.status == SyncStatus.COMPLETED])
                        failed = len([r for r in results if r.status == SyncStatus.FAILED])
                        logger.info("sync cycle complete", succeeded=succeeded, failed=failed)

                        logger.info("sleeping for 72 hours until next sync")
                        for _ in range(72 * 60 * 60):
                            if not conductor.is_running:
                                break
                            await asyncio.sleep(SHUTDOWN_POLL_INTERVAL)

                    except Exception as e:  # Intentionally broad: daemon resilience
                        logger.error("sync loop error", error=str(e), error_type=type(e).__name__)
                        logger.info("sleeping for 2 hours after error")
                        for _ in range(2 * 60 * 60):
                            if not conductor.is_running:
                                break
                            await asyncio.sleep(SHUTDOWN_POLL_INTERVAL)
            finally:
                await conductor.close()
                await db.close()

        asyncio.run(run())

    @cli.command("preview-queue")
    @click.argument("banana", type=BANANA, required=False)
    def preview_queue(banana):
        """Preview queued jobs (optionally specify city_banana)"""
        async def run():
            db = await Database.create()
            try:
                async with Conductor(db) as conductor:
                    return await conductor.preview_queue(city_banana=banana)
            finally:
                await db.close()

        result = asyncio.run(run())
        click.echo(json.dumps(result, indent=2))

    @cli.command("extract-text")
    @click.argument("meeting_id")
    @click.option("--output-file", "-o", help="Output file for extracted text")
    def extract_text(meeting_id, output_file):
        """Extract text from meeting PDF for manual review"""
        async def run():
            from pipeline.admin import extract_text_preview
            return await extract_text_preview(meeting_id, output_file=output_file)

        result = asyncio.run(run())
        click.echo(json.dumps(result, indent=2))

    @cli.command("preview-items")
    @click.argument("meeting_id")
    @click.option("--extract-text", is_flag=True, help="Extract text from item attachments")
    @click.option("--output-dir", "-o", help="Output directory for item texts")
    def preview_items(meeting_id, extract_text, output_dir):
        """Preview items for a meeting"""
        async def run():
            from pipeline.admin import preview_items as preview_items_func
            return await preview_items_func(meeting_id, extract_text=extract_text, output_dir=output_dir)

        result = asyncio.run(run())
        click.echo(json.dumps(result, indent=2))

    @cli.command("daemon")
    def daemon():
        """Run as combined daemon (sync + processing)

        Pure async architecture using asyncio.create_task() for concurrent loops.
        Shares single event loop and connection pool.
        """
        async def run():

            db = await Database.create()
            try:
                conductor = Conductor(db)

                def signal_handler(signum, frame):
                    sig_name = "SIGTERM" if signum == signal.SIGTERM else "SIGINT"
                    logger.info("received signal - graceful shutdown", signal=sig_name)
                    conductor.is_running = False
                    conductor.fetcher.is_running = False
                    conductor.processor.is_running = False
                    logger.info("shutdown initiated")

                signal.signal(signal.SIGTERM, signal_handler)
                signal.signal(signal.SIGINT, signal_handler)

                logger.info("starting combined daemon (sync + processing)")
                logger.info("sync interval: 72 hours")

                conductor.is_running = True
                conductor.fetcher.is_running = True
                conductor.processor.is_running = True

                # Define sync loop as async task
                async def sync_task():
                    """Sync loop - runs every 72 hours"""
                    while conductor.is_running:
                        try:
                            logger.info("starting city sync cycle")
                            results = await conductor.fetcher.sync_all()

                            succeeded = len([r for r in results if r.status == SyncStatus.COMPLETED])
                            failed = len([r for r in results if r.status == SyncStatus.FAILED])
                            logger.info("sync cycle complete", succeeded=succeeded, failed=failed)

                            logger.info("sleeping for 72 hours until next sync")
                            for _ in range(72 * 60 * 60):
                                if not conductor.is_running:
                                    break
                                await asyncio.sleep(SHUTDOWN_POLL_INTERVAL)

                        except Exception as e:  # Intentionally broad: daemon resilience
                            logger.error("sync loop error", error=str(e), error_type=type(e).__name__)
                            logger.info("sleeping for 2 hours after error")
                            for _ in range(2 * 60 * 60):
                                if not conductor.is_running:
                                    break
                                await asyncio.sleep(SHUTDOWN_POLL_INTERVAL)

                # Define processing loop as async task
                async def processing_task():
                    """Processing loop - continuously processes queue"""
                    if not conductor.processor.analyzer:
                        logger.warning("analyzer not available - processing disabled")
                        return

                    try:
                        logger.info("starting processing loop")
                        await conductor.processor.process_queue()
                    except Exception as e:  # Intentionally broad: task isolation
                        logger.error("processing loop error", error=str(e), error_type=type(e).__name__)

                # Run both tasks concurrently (single event loop, shared connection pool)
                sync_loop = asyncio.create_task(sync_task())
                processing_loop = asyncio.create_task(processing_task())

                # Wait for both tasks (or until shutdown signal)
                try:
                    await asyncio.gather(sync_loop, processing_loop)
                except asyncio.CancelledError:
                    logger.info("tasks cancelled")
                except Exception as e:  # Intentionally broad: task cleanup on any failure
                    logger.error("task failed", error=str(e), error_type=type(e).__name__)
                    # Cancel the other task to prevent resource leak
                    sync_loop.cancel()
                    processing_loop.cancel()

                logger.info("shutdown complete")

            finally:
                await conductor.close()
                await db.close()

        asyncio.run(run())

    cli()


if __name__ == "__main__":
    main()
