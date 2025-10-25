"""
Legistar Adapter - API integration for Legistar platform

Cities using Legistar: Seattle WA, NYC, Cambridge MA, and many others
"""

from typing import Dict, Any, Iterator, Optional
from datetime import datetime, timedelta
from backend.adapters.base_adapter import BaseAdapter, logger


class LegistarAdapter(BaseAdapter):
    """Adapter for cities using Legistar platform"""

    def __init__(self, city_slug: str, api_token: Optional[str] = None):
        """
        Initialize Legistar adapter.

        Args:
            city_slug: Legistar client name (e.g., "seattle", "nyc")
            api_token: Optional API token (required for some cities like NYC)
        """
        super().__init__(city_slug, vendor="legistar")
        self.api_token = api_token
        self.base_url = f"https://webapi.legistar.com/v1/{self.slug}"

    def fetch_meetings(self, days_forward: int = 60) -> Iterator[Dict[str, Any]]:
        """
        Fetch upcoming meetings from Legistar Web API.

        Args:
            days_forward: Number of days to look ahead (default 60)

        Yields:
            Meeting dictionaries with meeting_id, title, start, packet_url
        """
        # Build date range for upcoming events
        today = datetime.now()
        future_date = today + timedelta(days=days_forward)

        # Format dates for OData filter
        start_date = today.strftime("%Y-%m-%d")
        end_date = future_date.strftime("%Y-%m-%d")

        # Build OData filter
        filter_str = f"EventDate ge datetime'{start_date}' and EventDate lt datetime'{end_date}'"

        # API parameters
        params = {
            "$filter": filter_str,
            "$orderby": "EventDate asc",
            "$top": 1000,  # API max
        }

        if self.api_token:
            params["token"] = self.api_token

        # Fetch events
        api_url = f"{self.base_url}/events"
        response = self._get(api_url, params=params)
        events = response.json()

        logger.info(f"[legistar:{self.slug}] Retrieved {len(events)} events")

        for event in events:
            # Extract event data
            event_id = event.get("EventId")
            event_date = event.get("EventDate")
            event_name = event.get("EventBodyName", "")
            event_location = event.get("EventLocation")

            # Get packet URL (EventAgendaFile is the agenda packet PDF)
            packet_url = event.get("EventAgendaFile")

            # Parse meeting status from title
            meeting_status = self._parse_meeting_status(event_name)

            # Log if no packet (but still track the meeting)
            if not packet_url:
                logger.debug(
                    f"[legistar:{self.slug}] No packet for: {event_name} on {event_date}"
                )

            result = {
                "meeting_id": str(event_id),
                "title": event_name,
                "start": event_date,
                "packet_url": packet_url,
            }

            if event_location:
                result["location"] = event_location

            if meeting_status:
                result["meeting_status"] = meeting_status

            yield result
