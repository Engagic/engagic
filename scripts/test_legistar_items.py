#!/usr/bin/env python3
"""
Test script for Legistar item fetching
Validates that LegistarAdapter correctly fetches agenda items with attachments
"""

import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from backend.adapters.legistar_adapter import LegistarAdapter
import logging

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

def test_legistar_items(city_slug: str, num_meetings: int = 1):
    """
    Test fetching Legistar meetings with agenda items.

    Args:
        city_slug: Legistar client name (e.g., "seattle", "cambridge")
        num_meetings: Number of meetings to fetch
    """
    print(f"\n{'='*80}")
    print(f"Testing Legistar Item Fetching: {city_slug}")
    print(f"{'='*80}\n")

    adapter = LegistarAdapter(city_slug)

    meetings_processed = 0

    for meeting in adapter.fetch_meetings(days_forward=60):
        if meetings_processed >= num_meetings:
            break

        meeting_id = meeting.get("meeting_id")
        title = meeting.get("title")
        date = meeting.get("start", "")[:10]
        packet_url = meeting.get("packet_url")
        items = meeting.get("items", [])

        print(f"Meeting: {title}")
        print(f"Date: {date}")
        print(f"ID: {meeting_id}")
        print(f"Packet URL: {packet_url}")
        print(f"Agenda Items: {len(items)}")
        print()

        if items:
            items_with_attachments = [item for item in items if item.get("attachments")]
            print(f"Items with attachments: {len(items_with_attachments)}")

            # Show first few items
            for i, item in enumerate(items[:5], 1):
                item_title = item.get("title", "")[:80]
                attachments = item.get("attachments", [])

                print(f"\n  {i}. {item_title}")
                print(f"     Sequence: {item.get('sequence')}")
                print(f"     Matter ID: {item.get('matter_id')}")
                print(f"     Attachments: {len(attachments)}")

                if attachments:
                    for att in attachments[:3]:
                        att_type = att.get("type", "").upper()
                        att_name = att.get("name", "")
                        print(f"       [{att_type}] {att_name}")

                    if len(attachments) > 3:
                        print(f"       ... and {len(attachments) - 3} more")

            if len(items) > 5:
                print(f"\n  ... and {len(items) - 5} more items")
        else:
            print("No agenda items found for this meeting")

        print(f"\n{'-'*80}\n")
        meetings_processed += 1

    if meetings_processed == 0:
        print("No meetings found")
    else:
        print(f"Successfully tested {meetings_processed} meeting(s)")


if __name__ == "__main__":
    # Default to Seattle, allow override via command line
    city = sys.argv[1] if len(sys.argv) > 1 else "seattle"
    num = int(sys.argv[2]) if len(sys.argv) > 2 else 1

    test_legistar_items(city, num)
