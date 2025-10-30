"""
Probe PrimeGov deeper - check if they expose agenda item structure.
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from infocore.adapters.primegov_adapter import PrimeGovAdapter


def check_meeting_details():
    """Check if PrimeGov has an endpoint for meeting details with agenda items"""
    print("PRIMEGOV DEEP PROBE - Looking for agenda items")
    print("="*80)

    adapter = PrimeGovAdapter("cityofpaloalto")

    # Get first meeting
    api_url = f"{adapter.base_url}/api/v2/PublicPortal/ListUpcomingMeetings"
    response = adapter._get(api_url)
    meetings = response.json()

    if not meetings:
        print("No meetings found")
        return

    first_meeting = meetings[0]
    meeting_id = first_meeting['id']

    print(f"Meeting ID: {meeting_id}")
    print(f"Title: {first_meeting['title']}")
    print()

    # Try different endpoints that might have agenda items
    endpoints_to_try = [
        f"/api/v2/PublicPortal/GetMeetingDetails?meetingId={meeting_id}",
        f"/api/v2/PublicPortal/GetAgendaItems?meetingId={meeting_id}",
        f"/api/v2/PublicPortal/GetMeeting?id={meeting_id}",
        f"/api/v2/PublicPortal/Meeting/{meeting_id}",
        f"/api/v2/PublicPortal/AgendaItems/{meeting_id}",
    ]

    for endpoint in endpoints_to_try:
        full_url = f"{adapter.base_url}{endpoint}"
        print(f"\nTrying: {endpoint}")
        print("-" * 80)

        try:
            response = adapter._get(full_url)
            data = response.json()

            print(f"SUCCESS! Status: {response.status_code}")
            print(f"Response keys: {list(data.keys()) if isinstance(data, dict) else 'List'}")

            # Check for agenda items
            if isinstance(data, dict):
                for key in data.keys():
                    if 'item' in key.lower() or 'agenda' in key.lower():
                        print(f"\n  FOUND KEY: {key}")
                        items = data[key]
                        if isinstance(items, list) and items:
                            print(f"    Contains {len(items)} items")
                            print(f"    First item keys: {list(items[0].keys()) if isinstance(items[0], dict) else 'N/A'}")

            # Show full structure if it looks promising
            if isinstance(data, dict) and any('item' in k.lower() for k in data.keys()):
                print("\n  FULL STRUCTURE:")
                print(json.dumps(data, indent=2, default=str)[:2000])

        except Exception as e:
            print(f"Failed: {e}")

    adapter.close()


if __name__ == "__main__":
    check_meeting_details()
