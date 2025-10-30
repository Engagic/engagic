"""
Legistar Adapter - API integration for Legistar platform

Cities using Legistar: Seattle WA, NYC, Cambridge MA, and many others
"""

from typing import Dict, Any, Iterator, Optional, List
from datetime import datetime, timedelta
from infocore.adapters.base_adapter import BaseAdapter, logger


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
        filter_str = (
            f"EventDate ge datetime'{start_date}' and EventDate lt datetime'{end_date}'"
        )

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
            event_agenda_status = event.get("EventAgendaStatusName", "")

            # Get packet URL (EventAgendaFile is the agenda packet PDF)
            packet_url = event.get("EventAgendaFile")

            # Parse meeting status from title and agenda status
            meeting_status = self._parse_meeting_status(event_name, event_agenda_status)

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

            # Fetch agenda items with attachments (Legistar always has this structure)
            items = self.fetch_event_items(event_id)
            if items:
                result["items"] = items

            yield result

    def fetch_event_items(self, event_id: int) -> List[Dict[str, Any]]:
        """
        Fetch agenda items and their attachments for a specific event.

        Args:
            event_id: Legistar event ID

        Returns:
            List of agenda items with structure:
            [{
                'item_id': str,
                'title': str,
                'sequence': int,
                'matter_id': str | None,
                'attachments': [{'name': str, 'url': str, 'type': str}]
            }]
        """
        # Fetch event items
        items_url = f"{self.base_url}/events/{event_id}/eventitems"
        params = {}
        if self.api_token:
            params["token"] = self.api_token

        try:
            response = self._get(items_url, params=params)
            event_items = response.json()
        except Exception as e:
            logger.error(
                f"[legistar:{self.slug}] Failed to fetch items for event {event_id}: {e}"
            )
            return []

        logger.debug(
            f"[legistar:{self.slug}] Fetched {len(event_items)} items for event {event_id}"
        )

        processed_items = []

        for item in event_items:
            item_id = item.get("EventItemId")
            title = (item.get("EventItemTitle") or "").strip()
            sequence = item.get("EventItemAgendaSequence", 0)
            matter_id = item.get("EventItemMatterId")

            # Fetch attachments if matter exists
            attachments = []
            if matter_id:
                attachments = self._fetch_matter_attachments(matter_id)

            processed_items.append(
                {
                    "item_id": str(item_id),
                    "title": title,
                    "sequence": sequence,
                    "matter_id": str(matter_id) if matter_id else None,
                    "attachments": attachments,
                }
            )

        items_with_attachments = sum(
            1 for item in processed_items if item["attachments"]
        )
        logger.info(
            f"[legistar:{self.slug}] Event {event_id}: {len(processed_items)} items total, {items_with_attachments} with attachments"
        )
        return processed_items

    def _fetch_matter_attachments(self, matter_id: int) -> List[Dict[str, Any]]:
        """
        Fetch attachments for a specific matter.

        Args:
            matter_id: Legistar matter ID

        Returns:
            List of attachments: [{'name': str, 'url': str, 'type': str}]
        """
        attachments_url = f"{self.base_url}/matters/{matter_id}/attachments"
        params = {}
        if self.api_token:
            params["token"] = self.api_token

        try:
            response = self._get(attachments_url, params=params)
            raw_attachments = response.json()
        except Exception as e:
            logger.warning(
                f"[legistar:{self.slug}] Failed to fetch attachments for matter {matter_id}: {e}"
            )
            return []

        attachments = []

        for att in raw_attachments:
            name = (att.get("MatterAttachmentName") or "").strip()
            url = (att.get("MatterAttachmentHyperlink") or "").strip()

            if not url:
                continue

            # Determine file type from URL
            url_lower = url.lower()
            if url_lower.endswith(".pdf"):
                file_type = "pdf"
            elif url_lower.endswith((".doc", ".docx")):
                file_type = "doc"
            else:
                # Unknown type, include it anyway
                file_type = "unknown"

            attachments.append({"name": name, "url": url, "type": file_type})

        return attachments
