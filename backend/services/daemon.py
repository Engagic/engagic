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
            logger.info("Background processor running - syncing cities every 3 days, processing summaries every 2 hours")
            
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
            print("\n=== Engagic Daemon Status ===")
            print(f"Background processor running: {status['is_running']}")
            print(f"Last full sync: {status['last_full_sync'] or 'Never'}")
            print(f"Cities: {status['cities_count']}")
            print(f"Total meetings: {status['meetings_count']}")
            print(f"Processed meetings: {status['processed_count']}")
            print(f"Unprocessed queue: {status['unprocessed_count']}")
            print(f"Current sync status: {status['current_sync_status']}")
            
            # Show failed cities if any
            if status.get('failed_count', 0) > 0:
                print(f"\nFailed Cities ({status['failed_count']}):")
                for city in sorted(status.get('failed_cities', [])):
                    print(f"  - {city}")
            
            # Show recent activity
            queue_stats = self.processor.db.get_processing_queue_stats()
            print("\nProcessing Queue:")
            print(f"  Success rate: {queue_stats['success_rate']:.1f}%")
            print(f"  Recent meetings (24h): {queue_stats['recent_count']}")
            print(f"  Total with packet URLs: {queue_stats['total_meetings']}")
            
        except Exception as e:
            logger.error(f"Error getting status: {e}")
            print(f"Error getting status: {e}")


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
            print(f"Processing result: {'Success' if success else 'Failed'}")
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