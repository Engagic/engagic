"""
CivicClerk Adapter - OData API integration for CivicClerk platform

Cities using CivicClerk: Montpelier VT, Burlington VT, and others
"""

from typing import Dict, Any, Iterator
from datetime import datetime, timedelta
from vendors.adapters.base_adapter import BaseAdapter, logger


class CivicClerkAdapter(BaseAdapter):
    """Adapter for cities using CivicClerk platform"""

    def __init__(self, city_slug: str):
        """
        Initialize CivicClerk adapter.

        Args:
            city_slug: CivicClerk subdomain (e.g., "montpelliervt" for montpelliervt.api.civicclerk.com)
        """
        super().__init__(city_slug, vendor="civicclerk")
        self.base_url = f"https://{self.slug}.api.civicclerk.com"

    def _build_packet_url(self, doc: Dict[str, Any]) -> str:
        """
        Build packet URL from file metadata.

        Args:
            doc: Document dict with fileId

        Returns:
            URL to download packet PDF
        """
        file_id = doc.get("fileId")
        return f"{self.base_url}/v1/Meetings/GetMeetingFileStream(fileId={file_id},plainText=false)"

    def fetch_meetings(self, days_back: int = 7, days_forward: int = 14) -> Iterator[Dict[str, Any]]:
        """
        Fetch meetings from CivicClerk OData API within date range.

        Uses OData $filter and $orderby parameters to get meetings in range.

        Args:
            days_back: Days to look backward (default 7)
            days_forward: Days to look forward (default 14)

        Yields:
            Meeting dictionaries with meeting_id, title, start, packet_url
        """
        # Calculate date range
        today = datetime.now()
        start_date = today - timedelta(days=days_back)
        end_date = today + timedelta(days=days_forward)

        # Build OData query for date range
        start_time_str = start_date.strftime("%Y-%m-%dT%H:%M:%S.%fZ")[:-3] + "Z"
        end_time_str = end_date.strftime("%Y-%m-%dT%H:%M:%S.%fZ")[:-3] + "Z"
        params = {
            "$filter": f"startDateTime gt {start_time_str} and startDateTime lt {end_time_str}",
            "$orderby": "startDateTime asc, eventName asc",
        }

        logger.debug(
            f"[civicclerk:{self.slug}] Fetching meetings from {start_date.date()} to {end_date.date()}"
        )

        # Fetch from CivicClerk API
        api_url = f"{self.base_url}/v1/Events"
        response = self._get(api_url, params=params)
        data = response.json()

        meetings = data.get("value", [])
        logger.info("retrieved meetings from API", vendor="civicclerk", slug=self.slug, meeting_count=len(meetings))

        for meeting in meetings:
            # Find agenda packet in published files
            packet = next(
                (
                    doc
                    for doc in meeting.get("publishedFiles", [])
                    if doc.get("type") in ["Agenda Packet", "Agenda"]
                ),
                None,
            )

            event_name = meeting.get("eventName", "")
            start_time = meeting.get("startDateTime", "")

            # Parse meeting status from title and start time
            meeting_status = self._parse_meeting_status(event_name, start_time)

            # Log if no packet (but still track the meeting)
            if not packet:
                file_types = [
                    doc.get("type") for doc in meeting.get("publishedFiles", [])
                ]
                logger.debug(
                    f"[civicclerk:{self.slug}] No packet for: {event_name}, "
                    f"available files: {file_types}"
                )

            result = {
                "meeting_id": str(meeting["id"]),
                "title": event_name,
                "start": meeting.get("startDateTime", ""),
                "packet_url": self._build_packet_url(packet) if packet else None,
            }

            if meeting_status:
                result["meeting_status"] = meeting_status

            yield result
