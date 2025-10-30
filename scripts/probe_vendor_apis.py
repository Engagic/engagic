"""
Probe vendor APIs to see what data structures they actually return.

This helps us understand if vendors expose agenda items or just packets.
"""

import json
import sys
from pathlib import Path

# Add parent directory to path so we can import infocore
sys.path.insert(0, str(Path(__file__).parent.parent))

from infocore.adapters.primegov_adapter import PrimeGovAdapter
from infocore.adapters.civicclerk_adapter import CivicClerkAdapter
from infocore.adapters.legistar_adapter import LegistarAdapter


def probe_primegov():
    """Probe PrimeGov API - check what documentList contains"""
    print("\n" + "=" * 80)
    print("PRIMEGOV - Palo Alto, CA")
    print("=" * 80)

    adapter = PrimeGovAdapter("cityofpaloalto")
    api_url = f"{adapter.base_url}/api/v2/PublicPortal/ListUpcomingMeetings"

    try:
        response = adapter._get(api_url)
        meetings = response.json()

        if meetings:
            # Show first meeting in detail
            first = meetings[0]
            print(f"\nFirst meeting: {first.get('title')}")
            print(f"Date: {first.get('dateTime')}")
            print("\nFull structure:")
            print(json.dumps(first, indent=2, default=str))

            # Show what's in documentList
            print(
                f"\n\nDOCUMENT LIST ({len(first.get('documentList', []))} documents):"
            )
            for doc in first.get("documentList", []):
                print(f"  - {doc.get('templateName')}: {doc.get('compileOutputType')}")

        adapter.close()
    except Exception as e:
        print(f"Error: {e}")


def probe_civicclerk():
    """Probe CivicClerk API - check what publishedFiles contains"""
    print("\n" + "=" * 80)
    print("CIVICCLERK - Montpelier, VT")
    print("=" * 80)

    adapter = CivicClerkAdapter("montpelliervt")
    api_url = f"{adapter.base_url}/v1/Events"

    try:
        from datetime import datetime

        current_time = datetime.now().strftime("%Y-%m-%dT%H:%M:%S.%fZ")[:-3] + "Z"
        params = {
            "$filter": f"startDateTime gt {current_time}",
            "$orderby": "startDateTime asc",
            "$top": 5,
        }

        response = adapter._get(api_url, params=params)
        data = response.json()
        meetings = data.get("value", [])

        if meetings:
            first = meetings[0]
            print(f"\nFirst meeting: {first.get('eventName')}")
            print(f"Date: {first.get('startDateTime')}")
            print("\nFull structure:")
            print(json.dumps(first, indent=2, default=str))

            # Show what's in publishedFiles
            print(
                f"\n\nPUBLISHED FILES ({len(first.get('publishedFiles', []))} files):"
            )
            for doc in first.get("publishedFiles", []):
                print(f"  - {doc.get('type')}: {doc.get('name')}")

        adapter.close()
    except Exception as e:
        print(f"Error: {e}")


def probe_legistar():
    """Probe Legistar API - we know this one works, but show the structure"""
    print("\n" + "=" * 80)
    print("LEGISTAR - Seattle, WA")
    print("=" * 80)

    adapter = LegistarAdapter("seattle")
    api_url = f"{adapter.base_url}/events"

    try:
        from datetime import datetime, timedelta

        today = datetime.now()
        future = today + timedelta(days=30)

        params = {
            "$filter": f"EventDate ge datetime'{today.strftime('%Y-%m-%d')}' and EventDate lt datetime'{future.strftime('%Y-%m-%d')}'",
            "$orderby": "EventDate asc",
            "$top": 3,
        }

        response = adapter._get(api_url, params=params)
        events = response.json()

        if events:
            first = events[0]
            print(f"\nFirst event: {first.get('EventBodyName')}")
            print(f"Date: {first.get('EventDate')}")
            print(f"Has packet: {bool(first.get('EventAgendaFile'))}")

            # Fetch items for this event
            event_id = first.get("EventId")
            items = adapter.fetch_event_items(event_id)

            print(f"\n\nAGENDA ITEMS ({len(items)} items):")
            for item in items[:3]:  # First 3 items
                print(f"  - {item.get('title')}")
                print(f"    Attachments: {len(item.get('attachments', []))}")
                if item.get("attachments"):
                    for att in item["attachments"][:2]:
                        print(f"      * {att.get('name')} ({att.get('type')})")

        adapter.close()
    except Exception as e:
        print(f"Error: {e}")


def probe_granicus():
    """Probe Granicus - check if they expose items"""
    print("\n" + "=" * 80)
    print("GRANICUS - Example City")
    print("=" * 80)
    print("Note: Granicus is HTML scraping, not API - different approach needed")


def probe_novusagenda():
    """Probe NovusAgenda - check if they expose items"""
    print("\n" + "=" * 80)
    print("NOVUSAGENDA - Example City")
    print("=" * 80)
    print("Note: NovusAgenda varies by city - would need specific example")


def probe_civicplus():
    """Probe CivicPlus - check if they expose items"""
    print("\n" + "=" * 80)
    print("CIVICPLUS - Example City")
    print("=" * 80)
    print("Note: CivicPlus is HTML scraping - would need specific example")


if __name__ == "__main__":
    print("VENDOR API PROBE - Checking what data structures vendors expose")
    print("=" * 80)

    # Probe API-based vendors
    probe_primegov()
    probe_civicclerk()
    probe_legistar()

    # Note about HTML scrapers
    print("\n" + "=" * 80)
    print("HTML SCRAPERS (Granicus, NovusAgenda, CivicPlus)")
    print("=" * 80)
    print("These require actual scraping and vary by city.")
    print(
        "Would need to inspect specific city pages to see if agenda items are exposed."
    )

    print("\n" + "=" * 80)
    print("PROBE COMPLETE")
    print("=" * 80)
