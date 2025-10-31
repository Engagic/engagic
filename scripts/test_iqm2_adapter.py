"""
Quick test of IQM2 adapter with Santa Monica
"""

import sys
sys.path.insert(0, '/Users/origami/engagic')

import logging
from vendors.factory import get_adapter

logging.basicConfig(level=logging.INFO, format='%(message)s')

def test_santa_monica():
    """Test IQM2 adapter with Santa Monica"""
    print("\n=== Testing IQM2 Adapter: Santa Monica ===\n")

    # Get adapter
    adapter = get_adapter("iqm2", "santamonicacityca")

    if not adapter:
        print("ERROR: Failed to get IQM2 adapter")
        return

    print(f"Adapter initialized: {adapter.__class__.__name__}")
    print(f"Base URL: {adapter.base_url}")
    print(f"Calendar URL: {adapter.calendar_url}\n")

    # Fetch meetings
    print("Fetching meetings (14 days forward, 7 days back)...\n")

    meetings = list(adapter.fetch_meetings(days_forward=14, days_back=7))

    print(f"\n=== RESULTS ===")
    print(f"Total meetings found: {len(meetings)}\n")

    # Show first meeting details
    if meetings:
        meeting = meetings[0]
        print(f"First meeting:")
        print(f"  ID: {meeting['meeting_id']}")
        print(f"  Title: {meeting['title']}")
        print(f"  Start: {meeting['start']}")
        print(f"  Packet URL: {meeting.get('packet_url', 'None')}")
        print(f"  Items: {len(meeting.get('items', []))}")

        # Show first few items
        items = meeting.get('items', [])
        if items:
            print(f"\n  First 3 items:")
            for i, item in enumerate(items[:3]):
                print(f"\n  Item {i+1}:")
                print(f"    Item ID: {item['item_id']}")
                print(f"    Number: {item.get('item_number', 'N/A')}")
                print(f"    Title: {item['title'][:60]}...")
                print(f"    Section: {item.get('section', 'N/A')}")
                print(f"    Attachments: {len(item.get('attachments', []))}")

                # Show first attachment
                attachments = item.get('attachments', [])
                if attachments:
                    att = attachments[0]
                    print(f"      First attachment:")
                    print(f"        Name: {att['name'][:50]}...")
                    print(f"        Type: {att['type']}")

if __name__ == "__main__":
    test_santa_monica()
