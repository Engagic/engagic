"""
Async CivicClerk Adapter - OData API integration for CivicClerk platform

Cities using CivicClerk: Montpelier VT, Burlington VT, and others

Async version with:
- aiohttp for async HTTP requests
- AsyncSessionManager for connection pooling
- Non-blocking I/O for concurrent city fetching
"""

from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta

from vendors.adapters.base_adapter_async import AsyncBaseAdapter, logger
from pipeline.protocols import MetricsCollector


class AsyncCivicClerkAdapter(AsyncBaseAdapter):
    """Async adapter for cities using CivicClerk platform"""

    def __init__(self, city_slug: str, metrics: Optional[MetricsCollector] = None):
        """city_slug is the CivicClerk subdomain (e.g., "montpelliervt")"""
        super().__init__(city_slug, vendor="civicclerk", metrics=metrics)
        self.base_url = f"https://{self.slug}.api.civicclerk.com"

    def _build_packet_url(self, doc: Dict[str, Any]) -> str:
        """Build packet URL from document dict containing fileId."""
        file_id = doc.get("fileId")
        return f"{self.base_url}/v1/Meetings/GetMeetingFileStream(fileId={file_id},plainText=false)"

    async def _fetch_meetings_impl(self, days_back: int = 7, days_forward: int = 14) -> List[Dict[str, Any]]:
        """Fetch meetings from CivicClerk OData API using $filter and $orderby."""
        today = datetime.now()
        start_date = today - timedelta(days=days_back)
        end_date = today + timedelta(days=days_forward)

        start_time_str = start_date.strftime("%Y-%m-%dT%H:%M:%S.%fZ")[:-3] + "Z"
        end_time_str = end_date.strftime("%Y-%m-%dT%H:%M:%S.%fZ")[:-3] + "Z"
        params = {
            "$filter": f"startDateTime gt {start_time_str} and startDateTime lt {end_time_str}",
            "$orderby": "startDateTime asc, eventName asc",
        }

        logger.debug(
            "fetching meetings",
            vendor="civicclerk",
            slug=self.slug,
            start_date=str(start_date.date()),
            end_date=str(end_date.date())
        )

        api_url = f"{self.base_url}/v1/Events"
        response = await self._get(api_url, params=params)
        data = await response.json()

        meetings_data = data.get("value", [])
        logger.info(
            "retrieved meetings from API",
            vendor="civicclerk",
            slug=self.slug,
            meeting_count=len(meetings_data)
        )

        results = []
        for meeting in meetings_data:
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
            meeting_status = self._parse_meeting_status(event_name, start_time)

            if not packet:
                file_types = [
                    doc.get("type") for doc in meeting.get("publishedFiles", [])
                ]
                logger.debug(
                    "no packet for meeting",
                    vendor="civicclerk",
                    slug=self.slug,
                    event_name=event_name,
                    available_files=file_types
                )

            result = {
                "vendor_id": str(meeting["id"]),
                "title": event_name,
                "start": meeting.get("startDateTime", ""),
                "packet_url": self._build_packet_url(packet) if packet else None,
            }

            if meeting_status:
                result["meeting_status"] = meeting_status

            results.append(result)

        return results
