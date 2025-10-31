#!/usr/bin/env python3
"""
Unified meeting processor for Engagic

Usage:
    process_meetings.py [OPTIONS]

Options:
    --city CITY_BANANA     Process specific city (e.g., paloaltoCA)
    --unprocessed          Process only meetings without summaries
    --limit N              Limit to N meetings (default: 100)
    --skip-cached          Skip meetings that already have cached summaries
    --exclude-city CITY    Exclude specific city (e.g., newyorkNY)

Examples:
    # Process unprocessed meetings with Gemini
    ./process_meetings.py --unprocessed

    # Process all meetings for Palo Alto
    ./process_meetings.py --city paloaltoCA

    # Process 50 unprocessed meetings, excluding NYC
    ./process_meetings.py --unprocessed --limit 50 --exclude-city newyorkNY
"""

import sys
import time
import json
import sqlite3
import logging
import argparse
from pathlib import Path
from typing import List, Dict, Any

# Add parent directory to path
sys.path.append(str(Path(__file__).parent.parent))

from database.db import UnifiedDatabase
from config import config
from pipeline.processor import AgendaProcessor

# Setup logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("engagic")


def get_processor():
    """Get the processor"""
    api_key = config.GEMINI_API_KEY or config.get_api_key()
    return AgendaProcessor(api_key=api_key)


def parse_packet_urls(packet_url: str) -> List[str]:
    """Parse packet URL which might be JSON array or single URL"""
    if not packet_url:
        return []

    # Handle JSON array format
    if packet_url.startswith("["):
        try:
            urls = json.loads(packet_url)
            # Filter valid URLs
            return [u for u in urls if u and u.startswith("http")]
        except json.JSONDecodeError:
            logger.error(f"Invalid JSON in packet_url: {packet_url}")
            return []

    # Handle single URL
    if packet_url.startswith("http"):
        return [packet_url]

    logger.error(f"Invalid packet_url format: {packet_url}")
    return []


def process_meeting(
    processor: Any,
    db: UnifiedDatabase,
    meeting: Dict[str, Any],
    skip_cached: bool = True,
) -> bool:
    """Process a single meeting. Returns True if successful."""

    packet_url = meeting.get("packet_url")
    if not packet_url:
        return False

    # Parse URLs
    urls_to_process = parse_packet_urls(packet_url)
    if not urls_to_process:
        return False

    # Check cache if requested
    if skip_cached:
        # Use first URL as cache key
        cached = db.get_cached_summary(urls_to_process[0])
        if cached:
            logger.info(f"  Already cached: {meeting['meeting_name']}")
            return True

    # Build meeting data for processor
    meeting_data = {
        "packet_url": urls_to_process[0]
        if len(urls_to_process) == 1
        else urls_to_process,
        "city_banana": meeting["city_banana"],
        "meeting_id": meeting.get("meeting_id") or meeting.get("id"),
        "meeting_name": meeting["meeting_name"],
        "meeting_date": meeting.get("meeting_date"),
        "meeting_type": meeting.get("meeting_type"),
        "agenda_title": meeting.get("agenda_title"),
    }

    try:
        # Process with cache support
        result = processor.process_agenda_with_cache(meeting_data)

        if result.get("success"):
            method = result.get("processing_method", "unknown")
            if result.get("cached"):
                logger.info("  ✓ Retrieved from cache")
            else:
                logger.info(f"  ✓ Processed successfully (method: {method})")
            return True
        else:
            error = result.get("error", "Unknown error")
            logger.error(f"  ✗ Failed: {error}")
            return False

    except Exception as e:
        logger.error(f"  ✗ Exception: {e}")
        return False


def get_unprocessed_meetings(
    db_path: str, limit: int = 100, exclude_cities: List[str] = None
) -> List[Dict[str, Any]]:
    """Get meetings that need processing"""

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # Build exclusion clause
    exclude_clause = ""
    params = []
    if exclude_cities:
        placeholders = ",".join("?" * len(exclude_cities))
        exclude_clause = f"AND city_banana NOT IN ({placeholders})"
        params.extend(exclude_cities)

    params.append(limit)

    query = f"""
        SELECT id, city_banana, meeting_name, meeting_date, 
               meeting_type, agenda_title, packet_url, meeting_id
        FROM meetings 
        WHERE packet_url IS NOT NULL 
        AND packet_url != ''
        AND (processed_summary IS NULL OR processed_summary = '')
        {exclude_clause}
        ORDER BY city_banana, meeting_date DESC
        LIMIT ?
    """

    cursor.execute(query, params)
    meetings = [dict(row) for row in cursor.fetchall()]
    conn.close()

    return meetings


def main():
    parser = argparse.ArgumentParser(description="Process Engagic meeting summaries")
    parser.add_argument("--city", help="Process specific city (e.g., paloaltoCA)")
    parser.add_argument(
        "--unprocessed",
        action="store_true",
        help="Process only meetings without summaries",
    )
    parser.add_argument(
        "--limit", type=int, default=100, help="Maximum number of meetings to process"
    )
    parser.add_argument(
        "--skip-cached",
        action="store_true",
        default=True,
        help="Skip meetings that already have cached summaries",
    )
    parser.add_argument(
        "--exclude-city",
        action="append",
        dest="exclude_cities",
        help="Exclude specific cities (can be used multiple times)",
    )

    args = parser.parse_args()

    # Validate arguments
    if not args.city and not args.unprocessed:
        parser.error("Must specify either --city or --unprocessed")

    if args.city and args.unprocessed:
        parser.error("Cannot use both --city and --unprocessed")

    # Initialize database
    db = UnifiedDatabase(config.UNIFIED_DB_PATH)

    # Initialize processor
    try:
        processor = get_processor()
        logger.info("Initializing processor")
    except Exception as e:
        logger.error(f"Failed to initialize processor: {e}")
        sys.exit(1)

    # Get meetings to process
    if args.city:
        logger.info(f"Processing meetings for city: {args.city}")
        meetings = db.get_meetings(bananas=args.city)
    else:
        exclude_cities = args.exclude_cities or []
        if "newyorkNY" not in exclude_cities:
            # Default: always exclude NYC unless explicitly processing it
            exclude_cities.append("newyorkNY")

        logger.info(f"Finding unprocessed meetings (limit: {args.limit})")
        if exclude_cities:
            logger.info(f"Excluding cities: {', '.join(exclude_cities)}")

        meetings = get_unprocessed_meetings(
            config.MEETINGS_DB_PATH, args.limit, exclude_cities
        )

    if not meetings:
        logger.warning("No meetings found to process")
        return

    logger.info(f"Found {len(meetings)} meetings to process")

    # Group by city for better logging
    cities = {}
    for meeting in meetings:
        city = meeting["city_banana"]
        if city not in cities:
            cities[city] = []
        cities[city].append(meeting)

    logger.info(f"Cities to process: {', '.join(cities.keys())}")

    # Process meetings
    total_processed = 0
    total_cached = 0
    total_failed = 0

    for city_banana, city_meetings in cities.items():
        logger.info(f"\nProcessing {city_banana}: {len(city_meetings)} meetings")

        for i, meeting in enumerate(city_meetings, 1):
            meeting_name = meeting.get("meeting_name", "Unknown")
            logger.info(f"[{i}/{len(city_meetings)}] {meeting_name}")

            success = process_meeting(processor, db, meeting, args.skip_cached)

            if success:
                # Check if it was cached
                urls = parse_packet_urls(meeting["packet_url"])
                if urls and db.get_cached_summary(urls[0]):
                    total_cached += 1
                else:
                    total_processed += 1
            else:
                total_failed += 1

            # Rate limiting
            if not args.skip_cached or not success:
                time.sleep(0.5)

    # Summary
    logger.info("\n" + "=" * 50)
    logger.info("Processing Complete")
    logger.info(f"  Total meetings: {len(meetings)}")
    logger.info(f"  Already cached: {total_cached}")
    logger.info(f"  Newly processed: {total_processed}")
    logger.info(f"  Failed: {total_failed}")


if __name__ == "__main__":
    main()
