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
from datetime import datetime
from typing import Dict, Any, Optional, List

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

    def sync_cities(self, city_bananas: List[str]) -> List[Dict[str, Any]]:
        """Sync multiple cities (fetches meetings, enqueues for processing)

        Args:
            city_bananas: List of city banana identifiers

        Returns:
            List of sync results
        """
        logger.info(f"[Conductor] Syncing {len(city_bananas)} cities...")
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
        logger.info(f"[Conductor] Processing queued jobs for {len(city_bananas)} cities...")

        if not self.processor.analyzer:
            logger.warning(
                "[Conductor] Analyzer not available - cannot process meetings"
            )
            return {
                "cities_count": len(city_bananas),
                "processed_count": 0,
                "error": "Analyzer not available",
            }

        # Temporarily enable processing
        old_is_running = self.is_running
        self.is_running = True
        self.processor.is_running = True

        total_processed = 0
        total_failed = 0
        city_results = []

        try:
            for banana in city_bananas:
                if not self.is_running:
                    break

                logger.info(f"[Conductor] Processing jobs for {banana}...")
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

        finally:
            # Restore original is_running state
            self.is_running = old_is_running
            self.processor.is_running = old_is_running

    def sync_and_process_cities(self, city_bananas: List[str]) -> Dict[str, Any]:
        """Sync multiple cities and immediately process all their meetings

        Args:
            city_bananas: List of city banana identifiers

        Returns:
            Combined sync and processing results
        """
        logger.info(f"[Conductor] Sync and process {len(city_bananas)} cities...")

        # Step 1: Sync all cities
        sync_results = self.sync_cities(city_bananas)
        total_meetings = sum(r["meetings_found"] for r in sync_results)

        logger.info(f"[Conductor] Sync complete: {total_meetings} meetings found across {len(city_bananas)} cities")

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
            job = self.db.get_next_for_processing(banana=city_banana)
            if job:
                jobs.append(job)
        else:
            # Get all pending jobs (need to implement this query)
            # For now, just show stats
            stats = self.db.get_queue_stats()
            return stats

        previews = []
        for job in jobs[:limit]:
            meeting = self.db.get_meeting(job["meeting_id"])
            if meeting:
                previews.append({
                    "queue_id": job["id"],
                    "meeting_id": meeting.id,
                    "city_banana": job["banana"],
                    "title": meeting.title,
                    "date": meeting.date.isoformat() if meeting.date else None,
                    "source_url": job["source_url"],
                    "priority": job.get("priority", 0),
                    "status": job["status"],
                })

        return {
            "total_queued": len(jobs),
            "previews": previews,
        }

    def extract_text_preview(self, meeting_id: str, output_file: Optional[str] = None) -> Dict[str, Any]:
        """Extract text from meeting PDF without processing (for manual review)

        Args:
            meeting_id: Meeting identifier
            output_file: Optional file path to save extracted text

        Returns:
            Dictionary with text preview and stats
        """
        logger.info(f"[Conductor] Extracting text preview for {meeting_id}...")

        meeting = self.db.get_meeting(meeting_id)
        if not meeting:
            return {"error": "Meeting not found"}

        # Try agenda_url first (item-level), fallback to packet_url (monolithic)
        source_url = meeting.agenda_url or meeting.packet_url
        if not source_url:
            return {"error": "No agenda or packet URL for this meeting"}

        try:
            # Extract text using PDF extractor (doesn't need LLM analyzer)
            from parsing.pdf import PdfExtractor
            extractor = PdfExtractor()

            # Handle URL being either str or List[str]
            url = source_url[0] if isinstance(source_url, list) else source_url

            logger.info(f"[Conductor] Downloading PDF: {url}")
            extraction_result = extractor.extract_from_url(url)

            if not extraction_result["success"]:
                return {
                    "error": extraction_result.get("error", "Failed to extract text"),
                    "meeting_id": meeting_id,
                }

            text = extraction_result["text"]
            page_count = extraction_result.get("page_count", 0)
            text_length = len(text)

            # Optionally save to file
            if output_file:
                with open(output_file, "w") as f:
                    f.write(f"Meeting: {meeting.title}\n")
                    f.write(f"Date: {meeting.date}\n")
                    f.write(f"URL: {source_url}\n")
                    f.write(f"Pages: {page_count}\n")
                    f.write(f"Characters: {text_length}\n")
                    f.write("=" * 80 + "\n\n")
                    f.write(text)
                logger.info(f"[Conductor] Saved text to {output_file}")

            # Return preview (first 2000 chars)
            preview_text = text[:2000] + ("..." if len(text) > 2000 else "")

            return {
                "success": True,
                "meeting_id": meeting_id,
                "title": meeting.title,
                "date": meeting.date.isoformat() if meeting.date else None,
                "page_count": page_count,
                "text_length": text_length,
                "preview": preview_text,
                "saved_to": output_file,
            }

        except Exception as e:
            logger.error(f"[Conductor] Failed to extract text: {e}")
            return {
                "error": str(e),
                "meeting_id": meeting_id,
            }

    def preview_items(self, meeting_id: str, extract_text: bool = False, output_dir: Optional[str] = None) -> Dict[str, Any]:
        """Preview items and optionally extract text from their attachments

        Args:
            meeting_id: Meeting identifier
            extract_text: Whether to extract text from item attachments (default False)
            output_dir: Optional directory to save extracted texts

        Returns:
            Dictionary with items structure and optional text previews
        """
        logger.info(f"[Conductor] Previewing items for {meeting_id}...")

        meeting = self.db.get_meeting(meeting_id)
        if not meeting:
            return {"error": "Meeting not found"}

        # Get items from database
        agenda_items = self.db.get_agenda_items(meeting_id)
        if not agenda_items:
            return {
                "error": "No items found for this meeting",
                "meeting_id": meeting_id,
                "meeting_title": meeting.title,
            }

        items_preview = []

        for item in agenda_items:
            item_data = {
                "item_id": item.id,  # AgendaItem uses 'id', not 'item_id'
                "title": item.title,
                "sequence": item.sequence,
                "attachments": [
                    {
                        "name": att.get("name", "Unknown"),
                        "url": att.get("url", ""),
                        "type": att.get("type", "unknown"),
                    }
                    for att in (item.attachments or [])
                ],
                "has_summary": bool(item.summary),
            }

            # Optionally extract text from first attachment
            if extract_text and item.attachments:
                first_attachment = item.attachments[0]
                att_url = first_attachment.get("url")

                if att_url and att_url.endswith(".pdf"):
                    try:
                        from parsing.pdf import PdfExtractor
                        extractor = PdfExtractor()

                        logger.info(f"[Conductor] Extracting text from {item.id} attachment...")
                        extraction_result = extractor.extract_from_url(att_url)

                        if extraction_result["success"]:
                            text = extraction_result["text"]
                            page_count = extraction_result.get("page_count", 0)

                            # Preview first 500 chars
                            item_data["text_preview"] = text[:500] + ("..." if len(text) > 500 else "")
                            item_data["page_count"] = page_count
                            item_data["text_length"] = len(text)

                            # Optionally save to file
                            if output_dir:
                                import os
                                os.makedirs(output_dir, exist_ok=True)
                                filename = f"{item.id}.txt"
                                filepath = os.path.join(output_dir, filename)

                                with open(filepath, "w") as f:
                                    f.write(f"Item: {item.title}\n")
                                    f.write(f"Attachment: {first_attachment.get('name')}\n")
                                    f.write(f"URL: {att_url}\n")
                                    f.write(f"Pages: {page_count}\n")
                                    f.write(f"Characters: {len(text)}\n")
                                    f.write("=" * 80 + "\n\n")
                                    f.write(text)

                                item_data["saved_to"] = filepath
                                logger.info(f"[Conductor] Saved {item.id} text to {filepath}")
                        else:
                            item_data["text_error"] = extraction_result.get("error", "Failed to extract")

                    except Exception as e:
                        logger.warning(f"[Conductor] Failed to extract text for {item.id}: {e}")
                        item_data["text_error"] = str(e)

            items_preview.append(item_data)

        return {
            "success": True,
            "meeting_id": meeting_id,
            "meeting_title": meeting.title,
            "meeting_date": meeting.date.isoformat() if meeting.date else None,
            "total_items": len(agenda_items),
            "items": items_preview,
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


def main():
    """Entry point for engagic-conductor and engagic-daemon CLI"""
    import argparse
    import json

    parser = argparse.ArgumentParser(description="Background processor for engagic")

    # Single city operations
    parser.add_argument("--sync-city", help="Sync specific city by city_banana")
    parser.add_argument(
        "--sync-and-process-city",
        help="Sync city and immediately process all its meetings",
    )

    # Multi-city operations
    parser.add_argument(
        "--sync-cities",
        help="Sync multiple cities (comma-separated bananas or @file path)",
    )
    parser.add_argument(
        "--process-cities",
        help="Process queued jobs for multiple cities (comma-separated bananas or @file path)",
    )
    parser.add_argument(
        "--sync-and-process-cities",
        help="Sync and process multiple cities (comma-separated bananas or @file path)",
    )

    # Batch operations
    parser.add_argument("--full-sync", action="store_true", help="Run full sync once")
    parser.add_argument("--status", action="store_true", help="Show status")
    parser.add_argument("--fetcher", action="store_true", help="Run as fetcher service (auto sync only, no processing)")

    # Preview and inspection
    parser.add_argument(
        "--preview-queue",
        nargs="?",
        const="all",
        help="Preview queued jobs (optionally specify city_banana)",
    )
    parser.add_argument(
        "--extract-text",
        help="Extract text from meeting PDF for manual review (meeting_id)",
    )
    parser.add_argument(
        "--output-file",
        help="Output file for extracted text (use with --extract-text)",
    )
    parser.add_argument(
        "--preview-items",
        help="Preview items for a meeting (meeting_id)",
    )
    parser.add_argument(
        "--extract-item-text",
        action="store_true",
        help="Extract text from item attachments (use with --preview-items)",
    )
    parser.add_argument(
        "--output-dir",
        help="Output directory for item texts (use with --preview-items --extract-item-text)",
    )

    args = parser.parse_args()

    # Configure logging for CLI usage
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=[logging.StreamHandler()],
    )

    conductor = Conductor()

    # Helper to parse city list (supports comma-separated or @file)
    def parse_city_list(arg: str) -> List[str]:
        if arg.startswith("@"):
            # Read from file
            file_path = arg[1:]
            with open(file_path, "r") as f:
                cities = []
                for line in f:
                    # Strip comments (everything after #)
                    line = line.split('#')[0].strip()
                    # Skip empty lines
                    if line:
                        cities.append(line)
                return cities
        else:
            # Comma-separated
            return [c.strip() for c in arg.split(",") if c.strip()]

    # Single city operations
    if args.sync_city:
        result = conductor.force_sync_city(args.sync_city)
        print(f"Sync result: {result}")
    elif args.sync_and_process_city:
        result = conductor.sync_and_process_city(args.sync_and_process_city)
        print(json.dumps(result, indent=2))

    # Multi-city operations
    elif args.sync_cities:
        cities = parse_city_list(args.sync_cities)
        print(f"Syncing {len(cities)} cities: {', '.join(cities)}")
        results = conductor.sync_cities(cities)
        print(json.dumps(results, indent=2))
    elif args.process_cities:
        cities = parse_city_list(args.process_cities)
        print(f"Processing queued jobs for {len(cities)} cities: {', '.join(cities)}")
        results = conductor.process_cities(cities)
        print(json.dumps(results, indent=2))
    elif args.sync_and_process_cities:
        cities = parse_city_list(args.sync_and_process_cities)
        print(f"Syncing and processing {len(cities)} cities: {', '.join(cities)}")
        results = conductor.sync_and_process_cities(cities)
        print(json.dumps(results, indent=2))

    # Batch operations
    elif args.full_sync:
        results = conductor.fetcher.sync_all()
        print(f"Full sync complete: {len(results)} cities processed")
    elif args.status:
        status = conductor.get_sync_status()
        print(f"Status: {status}")
    elif args.fetcher:
        # Setup signal handlers for graceful shutdown
        def signal_handler(signum, frame):
            sig_name = "SIGTERM" if signum == signal.SIGTERM else "SIGINT"
            logger.info(f"[Fetcher] Received {sig_name}, initiating graceful shutdown...")
            conductor.is_running = False
            conductor.fetcher.is_running = False
            logger.info("[Fetcher] Shutdown complete")
            sys.exit(0)

        signal.signal(signal.SIGTERM, signal_handler)
        signal.signal(signal.SIGINT, signal_handler)

        logger.info("[Fetcher] Starting fetcher service (sync only, no processing)")
        logger.info("[Fetcher] Sync interval: 72 hours")

        # Enable running state for fetcher only
        conductor.is_running = True
        conductor.fetcher.is_running = True

        # Run sync loop (same as _sync_loop but without starting processing thread)
        while conductor.is_running:
            try:
                logger.info("[Fetcher] Starting city sync cycle...")
                results = conductor.fetcher.sync_all()
                conductor.last_full_sync = datetime.now()

                succeeded = len([r for r in results if r.status == SyncStatus.COMPLETED])
                failed = len([r for r in results if r.status == SyncStatus.FAILED])
                logger.info(f"[Fetcher] Sync cycle complete: {succeeded} succeeded, {failed} failed")

                # Sleep for 72 hours (checking every second for shutdown signal)
                logger.info("[Fetcher] Sleeping for 72 hours until next sync...")
                for _ in range(72 * 60 * 60):
                    if not conductor.is_running:
                        break
                    time.sleep(1)

            except Exception as e:
                logger.error(f"[Fetcher] Sync loop error: {e}")
                # Sleep for 2 hours on error
                logger.info("[Fetcher] Sleeping for 2 hours after error...")
                for _ in range(2 * 60 * 60):
                    if not conductor.is_running:
                        break
                    time.sleep(1)

    # Preview and inspection
    elif args.preview_queue:
        city_banana = None if args.preview_queue == "all" else args.preview_queue
        result = conductor.preview_queue(city_banana=city_banana)
        print(json.dumps(result, indent=2))
    elif args.extract_text:
        meeting_id = args.extract_text
        output_file = args.output_file
        result = conductor.extract_text_preview(meeting_id, output_file=output_file)
        print(json.dumps(result, indent=2))

    elif args.preview_items:
        meeting_id = args.preview_items
        extract_text = args.extract_item_text
        output_dir = args.output_dir
        result = conductor.preview_items(meeting_id, extract_text=extract_text, output_dir=output_dir)
        print(json.dumps(result, indent=2))

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
