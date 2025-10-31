"""
Test Granicus adapter with "Upcoming Programs" section targeting
"""

import sys
sys.path.insert(0, '/Users/origami/engagic')

from vendors.adapters.granicus_adapter import GranicusAdapter

def test_addison():
    """Test Addison IL - should get only upcoming meetings"""
    print("Testing Addison IL (addison.granicus.com)")
    print("=" * 60)

    adapter = GranicusAdapter("addison")
    meetings = list(adapter.fetch_meetings())

    print(f"\n✓ Found {len(meetings)} meetings\n")

    for i, meeting in enumerate(meetings, 1):
        print(f"{i}. {meeting['title']}")
        print(f"   Date: {meeting['start']}")
        print(f"   URL: {meeting.get('packet_url', 'N/A')[:80]}...")
        if meeting.get('items'):
            print(f"   Items: {len(meeting['items'])}")
        print()

    # Verify
    if len(meetings) <= 10:
        print(f"✓ SUCCESS: Got {len(meetings)} upcoming meetings (not 100+)")
    else:
        print(f"✗ FAILED: Still got {len(meetings)} meetings (should be ~3-5)")

    return meetings

if __name__ == "__main__":
    meetings = test_addison()
