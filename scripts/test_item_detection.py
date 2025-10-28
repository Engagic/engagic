#!/usr/bin/env python3
"""
Test item detection without using LLM credits.

Shows what items would be detected and their page ranges for each meeting.

Usage:
    python scripts/test_item_detection.py paloaltoCA
    python scripts/test_item_detection.py paloaltoCA --limit 5
    python scripts/test_item_detection.py paloaltoCA --meeting-url "https://..."
"""

import sys
import argparse
import re
from pathlib import Path


# Add app directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from backend.database.unified_db import UnifiedDatabase
from backend.core.processor import AgendaProcessor
from backend.core.config import config

import logging

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def test_meeting_detection(db, processor, meeting, meeting_num, total, debug=False):
    """Test item detection for a single meeting"""
    print(f"\n{'='*80}")
    print(f"Meeting {meeting_num}/{total}")
    print(f"{'='*80}")
    print(f"Title: {meeting.title}")
    print(f"Date: {meeting.date}")
    print(f"City: {meeting.banana}")
    print(f"Packet URL: {meeting.packet_url}")

    if not meeting.packet_url:
        print("❌ No packet URL - skipping")
        return

    # Extract PDF text
    print("\n📄 Extracting PDF...")
    try:
        extraction = processor.pdf_extractor.extract_from_url(meeting.packet_url)
        if not extraction['success']:
            print(f"❌ PDF extraction failed: {extraction.get('error', 'Unknown error')}")
            return

        text = extraction['text']
        page_count = processor._estimate_page_count(text)
        text_size = len(text)

        print(f"✓ Extracted {page_count} pages (~{text_size:,} chars)")

        # Debug mode: dump text samples
        if debug:
            print(f"\n{'─'*80}")
            print("DEBUG: Text Analysis")
            print(f"{'─'*80}")

            # Show first 3000 chars
            print("\n[First 3000 chars of document]")
            print(text[:3000])
            print("\n[...]\n")

            # Try to detect cover end
            try:
                cover_end = processor._detect_cover_end(text)
                print(f"\nCover ends at position: {cover_end} ({cover_end/len(text)*100:.1f}%)")

                # Show cover section
                print(f"\n[COVER SECTION ({len(text[:cover_end])} chars)]")
                print(text[:cover_end])
                print("\n[END COVER]\n")

                # Show start of body
                print("\n[BODY START (first 2000 chars)]")
                print(text[cover_end:cover_end+2000])
                print("\n[...]\n")

                # Try to parse cover
                cover_items = processor._parse_cover_agenda(text[:cover_end])
                print(f"\nAgenda items found in cover: {len(cover_items)}")
                for item in cover_items[:10]:
                    print(f"  {item['item_id']}: {item['title'][:80]}")
                if len(cover_items) > 10:
                    print(f"  ... and {len(cover_items) - 10} more")

            except Exception as e:
                print(f"\n❌ Debug analysis error: {e}")
                logger.exception("Debug error")

            print(f"\n{'─'*80}\n")

            # Don't continue with detection in debug mode
            return

    except Exception as e:
        print(f"❌ Error extracting PDF: {e}")
        return

    # Check size-based routing
    print("\n🔍 Checking size-based routing...")
    if page_count <= 10 or text_size < 30000:
        print(f"✓ Small packet ({page_count} pages, {text_size:,} chars)")
        print("   → Would process MONOLITHICALLY with flash-lite")
        return

    print(f"✓ Large packet ({page_count} pages, {text_size:,} chars)")
    print("   → Attempting item detection...")

    # Run item detection
    try:
        detected_items = processor.detect_agenda_items(text)

        if not detected_items:
            print("\n⚠️  No items detected - would process MONOLITHICALLY with flash")
            return

        print(f"\n✓ Detected {len(detected_items)} items:")
        print(f"\n{'#':<4} {'Title':<60} {'Pages':<15} {'Size':<10}")
        print(f"{'-'*4} {'-'*60} {'-'*15} {'-'*10}")

        for item in detected_items:
            title = item['title'][:57] + '...' if len(item['title']) > 60 else item['title']

            # Calculate page range from text positions
            start_page = item.get('start_page', '?')
            item_size = len(item['text'])
            pages_in_item = max(1, item_size // 3000)  # Rough estimate
            page_range = f"~{start_page}-{start_page + pages_in_item if isinstance(start_page, int) else '?'}"

            print(f"{item['sequence']:<4} {title:<60} {page_range:<15} {item_size//1000}K")

        # Show content previews
        print("\n" + "="*80)
        print("Content Preview (first 500 chars of each chunk):")
        print("="*80)
        for item in detected_items[:3]:  # Just first 3 to avoid spam
            print(f"\n--- Item {item['sequence']}: {item['title'][:50]} ---")
            preview = item['text'][:500].replace('\n', ' ')[:200]
            print(f"{preview}...")
            # Look for page markers
            page_markers = re.findall(r'--- PAGE (\d+) ---', item['text'][:5000])
            if page_markers:
                first_page = page_markers[0]
                last_page = page_markers[-1] if len(page_markers) > 1 else first_page
                print(f"  [Pages: {first_page}-{last_page} ({len(page_markers)} page markers)]")
            else:
                print("  [No PAGE markers in first 5000 chars]")

        print("\n📊 Summary:")
        print(f"   Total items: {len(detected_items)}")
        print("   Would batch process all items in ONE Gemini Batch API call")
        print(f"   Estimated cost: ~{len(detected_items) * 0.01:.2f} credits (vs ~{page_count * 0.005:.2f} monolithic)")

    except Exception as e:
        logger.exception("Error during item detection")
        print(f"❌ Error during item detection: {e}")


def main():
    parser = argparse.ArgumentParser(description="Test item detection without using credits")
    parser.add_argument("banana", help="City banana (e.g., paloaltoCA)")
    parser.add_argument("--limit", type=int, default=10, help="Max meetings to test (default: 10)")
    parser.add_argument("--meeting-url", help="Test specific meeting by packet URL")
    parser.add_argument("--debug", action="store_true", help="Dump extracted text for inspection")

    args = parser.parse_args()

    # Initialize database and processor
    db = UnifiedDatabase(config.UNIFIED_DB_PATH)
    processor = AgendaProcessor()

    print(f"\n{'='*80}")
    print("ITEM DETECTION TEST (No LLM calls, no credits used)")
    print(f"{'='*80}")

    if args.meeting_url:
        # Test specific meeting
        meeting = db.get_meeting_by_packet_url(args.meeting_url)
        if not meeting:
            print(f"❌ Meeting not found with URL: {args.meeting_url}")
            return

        test_meeting_detection(db, processor, meeting, 1, 1, debug=args.debug)
    else:
        # Test recent meetings for city
        city = db.get_city(args.banana)
        if not city:
            print(f"❌ City not found: {args.banana}")
            print("\nAvailable cities:")
            cities = db.get_cities()
            for c in sorted(cities, key=lambda x: x.name)[:20]:
                print(f"  - {c.banana} ({c.name})")
            return

        print(f"City: {city.name}")
        print(f"Banana: {city.banana}")

        # Get recent meetings with packets
        meetings = db.get_meetings(bananas=[city.banana], limit=args.limit * 2)
        meetings_with_packets = [m for m in meetings if m.packet_url][:args.limit]

        if not meetings_with_packets:
            print(f"\n❌ No meetings with packets found for {city.name}")
            return

        print(f"Testing {len(meetings_with_packets)} meetings with packets...\n")

        for i, meeting in enumerate(meetings_with_packets, 1):
            test_meeting_detection(db, processor, meeting, i, len(meetings_with_packets), debug=args.debug)

            # Brief pause between meetings
            if i < len(meetings_with_packets):
                print(f"\n{'─'*80}")

    print(f"\n{'='*80}")
    print("Test complete!")
    print(f"{'='*80}\n")


if __name__ == "__main__":
    main()
