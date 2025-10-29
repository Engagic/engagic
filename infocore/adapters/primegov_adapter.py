"""
PrimeGov Adapter - Thin wrapper for PrimeGov municipal calendar API

Cities using PrimeGov: Palo Alto CA, Mountain View CA, Sunnyvale CA, and many others
"""

from typing import Dict, Any, Iterator
from urllib.parse import urlencode
from infocore.adapters.base_adapter import BaseAdapter, logger


class PrimeGovAdapter(BaseAdapter):
    """Adapter for cities using PrimeGov platform"""

    def __init__(self, city_slug: str):
        """
        Initialize PrimeGov adapter.

        Args:
            city_slug: PrimeGov subdomain (e.g., "cityofpaloalto" for cityofpaloalto.primegov.com)
        """
        super().__init__(city_slug, vendor="primegov")
        self.base_url = f"https://{self.slug}.primegov.com"

    def _build_packet_url(self, doc: Dict[str, Any]) -> str:
        """
        Build compiled packet URL from document metadata.

        Args:
            doc: Document dict with templateId and compileOutputType

        Returns:
            URL to compiled PDF packet
        """
        query = urlencode({
            "meetingTemplateId": doc["templateId"],
            "compileOutputType": doc["compileOutputType"],
        })
        return f"{self.base_url}/Public/CompiledDocument?{query}"

    def fetch_meetings(self) -> Iterator[Dict[str, Any]]:
        """
        Fetch upcoming meetings from PrimeGov API.

        Yields:
            Meeting dictionaries with meeting_id, title, start, packet_url
        """
        # Fetch from PrimeGov API
        api_url = f"{self.base_url}/api/v2/PublicPortal/ListUpcomingMeetings"
        response = self._get(api_url)
        meetings = response.json()

        logger.info(f"[primegov:{self.slug}] Retrieved {len(meetings)} meetings")

        for meeting in meetings:
            # Find packet document (prefer "Packet", fall back to "Agenda" if not HTML)
            packet_doc = next(
                (
                    doc for doc in meeting.get("documentList", [])
                    if "Packet" in doc.get("templateName", "")
                    or (
                        "html" not in doc.get("templateName", "").lower()
                        and "agenda" in doc.get("templateName", "").lower()
                    )
                ),
                None
            )

            title = meeting.get("title", "")
            date_time = meeting.get("dateTime", "")

            # Parse meeting status from title and datetime
            meeting_status = self._parse_meeting_status(title, date_time)

            result = {
                "meeting_id": str(meeting["id"]),
                "title": title,
                "start": date_time,
            }

            if packet_doc:
                result["packet_url"] = self._build_packet_url(packet_doc)
            else:
                logger.debug(
                    f"[primegov:{self.slug}] No packet found for: {title} "
                    f"on {meeting.get('date')}"
                )

            if meeting_status:
                result["meeting_status"] = meeting_status

            yield result
