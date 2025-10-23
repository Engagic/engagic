"""
Test script for Legistar Web API
Fetches upcoming events for the next month
"""

import requests
from datetime import datetime, timedelta
from urllib.parse import quote

def fetch_upcoming_events(client_name: str, token: str = None, days_forward: int = 30):
    """
    Fetch upcoming Legistar events for the next N days.

    Args:
        client_name: Legistar client slug (e.g., "cambridge", "nyc")
        token: Optional API token (required for some cities)
        days_forward: Number of days to look ahead (default 30)
    """
    # Build date range
    today = datetime.now()
    future_date = today + timedelta(days=days_forward)

    # Format dates for OData (YYYY-MM-DD)
    start_date = today.strftime("%Y-%m-%d")
    end_date = future_date.strftime("%Y-%m-%d")

    # Build OData filter for date range
    filter_str = f"EventDate ge datetime'{start_date}' and EventDate lt datetime'{end_date}'"

    # Build API URL
    base_url = f"https://webapi.legistar.com/v1/{client_name}/events"

    # Add parameters
    params = {
        "$filter": filter_str,
        "$orderby": "EventDate asc",
        "$top": 50  # Get first 50 events
    }

    if token:
        params["token"] = token

    print(f"Fetching events for {client_name} from {start_date} to {end_date}...")
    print(f"URL: {base_url}")
    print(f"Filter: {filter_str}\n")

    try:
        response = requests.get(base_url, params=params, timeout=30)
        response.raise_for_status()

        events = response.json()

        print(f"Found {len(events)} upcoming events:\n")

        # Show all available fields from first event
        if events:
            print("Available fields in API response:")
            print(f"{list(events[0].keys())}\n")

        for event in events:
            event_id = event.get("EventId")
            event_date = event.get("EventDate", "No date")
            event_name = event.get("EventBodyName", "Unknown")

            # Check for agenda packet
            packet_link = event.get("EventAgendaFile")
            has_packet = "YES" if packet_link else "NO"

            print(f"[{event_date[:10]}] {event_name}")
            print(f"  ID: {event_id} | Packet: {has_packet}")

            if packet_link:
                print(f"  Packet URL: {packet_link}")

            print()

        return events

    except requests.exceptions.RequestException as e:
        print(f"Error fetching events: {e}")
        return []


def fetch_event_items(client_name: str, event_id: int, token: str = None):
    """
    Fetch agenda items for a specific event.

    Args:
        client_name: Legistar client slug
        event_id: Event ID from events endpoint
        token: Optional API token
    """
    url = f"https://webapi.legistar.com/v1/{client_name}/events/{event_id}/eventitems"

    params = {}
    if token:
        params["token"] = token

    print(f"Fetching agenda items for event {event_id}...")

    try:
        response = requests.get(url, params=params, timeout=30)
        response.raise_for_status()

        items = response.json()

        print(f"Found {len(items)} agenda items:\n")

        for item in items:
            item_title = item.get("EventItemTitle", "No title")
            item_file = item.get("EventItemAgendaFile")

            print(f"  - {item_title}")
            if item_file:
                print(f"    Attachment: {item_file}")

        return items

    except requests.exceptions.RequestException as e:
        print(f"Error fetching event items: {e}")
        return []


if __name__ == "__main__":
    import os
    import sys

    # Get client and token from args or env
    CLIENT = sys.argv[1] if len(sys.argv) > 1 else "nyc"
    TOKEN = sys.argv[2] if len(sys.argv) > 2 else os.getenv("NYC_API_KEY")

    if not TOKEN:
        print("Warning: No API token provided. Some clients may require it.")
        print("Usage: python test_legistar_api.py <client> <token>")
        print("Or set NYC_API_KEY environment variable\n")

    # Fetch upcoming events
    events = fetch_upcoming_events(CLIENT, token=TOKEN, days_forward=30)

    # If events found, fetch items for the first one
    if events:
        first_event_id = events[0].get("EventId")
        if first_event_id:
            print("\n" + "="*60 + "\n")
            fetch_event_items(CLIENT, first_event_id, token=TOKEN)
