#!/usr/bin/env python3
"""
Process all cached packet URLs for a specific city
Usage: python scripts/process_city_summaries.py <city_banana> [--cached-only]
"""

import sys
import os
import time
import logging
import argparse
from pathlib import Path

# Add parent directory to path
sys.path.append(str(Path(__file__).parent.parent))

from backend.database.database_manager import DatabaseManager
from backend.core.processor import AgendaProcessor
from backend.core.config import config

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("engagic")


def process_city_meetings(city_banana: str):
    """Process all meetings with packet URLs for a specific city"""
    
    # Initialize database
    db = DatabaseManager(
        locations_db_path=config.LOCATIONS_DB_PATH,
        meetings_db_path=config.MEETINGS_DB_PATH,
        analytics_db_path=config.ANALYTICS_DB_PATH
    )
    
    # Initialize processor
    try:
        processor = AgendaProcessor(api_key=config.get_api_key())
        logger.info(f"Initialized processor for city: {city_banana}")
    except ValueError as e:
        logger.error(f"Failed to initialize processor: {e}")
        return
    
    # Get all meetings for this city
    logger.info(f"Fetching meetings for {city_banana}")
    meetings = db.get_meetings_by_city(city_banana)
    
    if not meetings:
        logger.warning(f"No meetings found for city: {city_banana}")
        return
    
    logger.info(f"Found {len(meetings)} total meetings for {city_banana}")
    
    # Filter meetings with packet URLs
    meetings_with_packets = [m for m in meetings if m.get('packet_url')]
    logger.info(f"Found {len(meetings_with_packets)} meetings with packet URLs")
    
    # Process statistics
    processed_count = 0
    cached_count = 0
    error_count = 0
    
    for i, meeting in enumerate(meetings_with_packets, 1):
        packet_url = meeting['packet_url']
        meeting_name = meeting.get('meeting_name', 'Unknown meeting')
        
        logger.info(f"[{i}/{len(meetings_with_packets)}] Processing: {meeting_name}")
        logger.info(f"  Packet URL: {packet_url}")
        
        # Check if already cached
        cached = db.get_cached_summary(packet_url)
        if cached:
            logger.info(f"  ✓ Summary already cached")
            cached_count += 1
            continue
        
        # Process the meeting
        try:
            meeting_data = {
                'packet_url': packet_url,
                'city_banana': city_banana,
                'meeting_id': meeting.get('meeting_id'),
                'meeting_name': meeting_name,
                'meeting_date': meeting.get('meeting_date'),
                'meeting_type': meeting.get('meeting_type'),
                'agenda_title': meeting.get('agenda_title')
            }
            
            result = processor.process_agenda_with_cache(meeting_data)
            
            if result.get('success'):
                if result.get('cached'):
                    logger.info(f"  ✓ Retrieved from cache")
                    cached_count += 1
                else:
                    logger.info(f"  ✓ Successfully processed (method: {result.get('processing_method', 'unknown')})")
                    processed_count += 1
            else:
                logger.error(f"  ✗ Failed to process: {result.get('error', 'Unknown error')}")
                error_count += 1
                
        except Exception as e:
            logger.error(f"  ✗ Exception during processing: {e}")
            error_count += 1
        
        # Add delay between processing to be respectful
        if not cached:
            time.sleep(2)
    
    # Print summary
    logger.info("\n" + "="*50)
    logger.info(f"Processing complete for {city_banana}")
    logger.info(f"  Total meetings: {len(meetings)}")
    logger.info(f"  Meetings with packets: {len(meetings_with_packets)}")
    logger.info(f"  Already cached: {cached_count}")
    logger.info(f"  Newly processed: {processed_count}")
    logger.info(f"  Errors: {error_count}")
    
    # Print processing statistics if available
    if hasattr(processor, 'stats'):
        logger.info("\nProcessing Statistics:")
        logger.info(f"  Tier 1 (PyPDF2) successes: {processor.stats.get('tier1_success', 0)}")
        logger.info(f"  Tier 2 (Mistral OCR) successes: {processor.stats.get('tier2_success', 0)}")
        logger.info(f"  Tier 3 (Claude PDF) successes: {processor.stats.get('tier3_success', 0)}")
        logger.info(f"  Total cost: ${processor.stats.get('total_cost', 0):.4f}")


def main():
    if len(sys.argv) != 2:
        print("Usage: python scripts/process_city_summaries.py <city_banana>")
        print("Example: python scripts/process_city_summaries.py paloaltoCA")
        sys.exit(1)
    
    city_banana = sys.argv[1]
    
    logger.info(f"Starting processing for city: {city_banana}")
    process_city_meetings(city_banana)


if __name__ == "__main__":
    main()