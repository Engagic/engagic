#!/usr/bin/env python3
"""
Engagic Background Processing Daemon

This daemon runs continuously to:
1. Sync all cities with their websites every 4 hours
2. Process meeting summaries every 30 minutes
3. Maintain up-to-date cache of all meetings and summaries

Usage:
    python daemon.py                    # Run daemon
    python daemon.py --once            # Run sync once and exit
    python daemon.py --sync-city SLUG  # Sync specific city
    python daemon.py --status          # Show status and exit
"""

import sys
import time
import signal
import logging
from pathlib import Path

# Add app directory to path
sys.path.insert(0, str(Path(__file__).parent))

from backend.services.background_processor import BackgroundProcessor
from backend.core.config import config

# Configure logging
logging.basicConfig(
    level=getattr(logging, config.LOG_LEVEL),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(config.LOG_PATH, mode='a')
    ]
)
logger = logging.getLogger("engagic.daemon")


class EngagicDaemon:
    def __init__(self):
        self.processor = BackgroundProcessor()
        self.running = False
        self.shutdown_requested = False
        
        # Handle shutdown signals
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)
        
    def _signal_handler(self, signum, frame):
        """Handle shutdown signals gracefully"""
        logger.info(f"Received signal {signum}, shutting down...")
        self.shutdown_requested = True
        if self.running:
            self.processor.stop()
            
    def start(self):
        """Start the daemon"""
        logger.info("Starting Engagic background processing daemon...")
        
        try:
            self.running = True
            self.processor.start()
            
            logger.info("Daemon started successfully")
            logger.info("Background processor running - syncing cities every 7 days, processing queue continuously")
            
            # Keep main thread alive
            while not self.shutdown_requested:
                time.sleep(1)
                
        except Exception as e:
            logger.error(f"Daemon error: {e}")
            raise
        finally:
            self.cleanup()
            
    def cleanup(self):
        """Cleanup resources"""
        logger.info("Cleaning up daemon resources...")
        if self.running:
            self.processor.stop()
            self.running = False
        logger.info("Daemon stopped")
        
    def run_once(self):
        """Run one full sync cycle and exit"""
        logger.info("Running one-time sync...")
        self.processor._run_full_sync()
        logger.info("One-time sync completed")
        
    def sync_city(self, city_slug: str):
        """Sync specific city"""
        logger.info(f"Syncing city: {city_slug}")
        result = self.processor.force_sync_city(city_slug)
        logger.info(f"Sync result: {result}")
        return result
        
    def show_status(self):
        """Show daemon status"""
        try:
            status = self.processor.get_sync_status()
            logger.info("=== Engagic Daemon Status ===")
            logger.info(f"Background processor running: {status['is_running']}")
            logger.info(f"Last full sync: {status['last_full_sync'] or 'Never'}")
            logger.info(f"Active cities: {status.get('active_cities', 0)}")
            logger.info(f"Total meetings: {status.get('total_meetings', 0)}")
            logger.info(f"Summarized meetings: {status.get('summarized_meetings', 0)}")
            logger.info(f"Pending meetings: {status.get('pending_meetings', 0)}")

            # Show failed cities if any
            if status.get('failed_count', 0) > 0:
                logger.warning(f"Failed Cities ({status['failed_count']}):")
                for city in sorted(status.get('failed_cities', [])):
                    logger.warning(f"  - {city}")

            # Show database and queue stats
            stats = self.processor.db.get_stats()
            logger.info("Database Stats:")
            logger.info(f"  Total meetings: {stats.get('total_meetings', 0)}")
            logger.info(f"  Summarized: {stats.get('summarized_meetings', 0)}")
            logger.info(f"  Pending: {stats.get('pending_meetings', 0)}")
            logger.info(f"  Summary rate: {stats.get('summary_rate', '0%')}")

            # Show queue stats (Phase 4)
            queue_stats = self.processor.db.get_queue_stats()
            logger.info("Processing Queue Stats:")
            logger.info(f"  Pending: {queue_stats.get('pending_count', 0)}")
            logger.info(f"  Processing: {queue_stats.get('processing_count', 0)}")
            logger.info(f"  Completed: {queue_stats.get('completed_count', 0)}")
            logger.info(f"  Failed: {queue_stats.get('failed_count', 0)}")
            logger.info(f"  Permanently failed: {queue_stats.get('permanently_failed', 0)}")
            logger.info(f"  Avg processing time: {queue_stats.get('avg_processing_seconds', 0):.1f}s")

        except Exception as e:
            logger.error(f"Error getting status: {e}")


def main():
    import argparse
    
    parser = argparse.ArgumentParser(description="Engagic Background Processing Daemon")
    parser.add_argument("--once", action="store_true", help="Run sync once and exit")
    parser.add_argument("--sync-city", metavar="SLUG", help="Sync specific city by slug")
    parser.add_argument("--status", action="store_true", help="Show status and exit")
    parser.add_argument("--process-meeting", metavar="URL", help="Process specific meeting by packet URL")
    
    args = parser.parse_args()
    
    daemon = EngagicDaemon()
    
    try:
        if args.once:
            daemon.run_once()
        elif args.sync_city:
            daemon.sync_city(args.sync_city)
        elif args.status:
            daemon.show_status()
        elif args.process_meeting:
            success = daemon.processor.force_process_meeting(args.process_meeting)
            logger.info(f"Processing result: {'Success' if success else 'Failed'}")
        else:
            # Run as daemon
            daemon.start()
            
    except KeyboardInterrupt:
        logger.info("Daemon interrupted by user")
    except Exception as e:
        logger.error(f"Daemon failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()