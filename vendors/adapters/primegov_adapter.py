"""
PrimeGov Adapter - Thin wrapper for PrimeGov municipal calendar API

Cities using PrimeGov: Palo Alto CA, Mountain View CA, Sunnyvale CA, and many others
"""

from typing import Dict, Any, Iterator
from urllib.parse import urlencode
from vendors.adapters.base_adapter import BaseAdapter, logger
from vendors.adapters.parsers.primegov_parser import parse_html_agenda
from vendors.utils.item_filters import should_skip_procedural_item


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
        query = urlencode(
            {
                "meetingTemplateId": doc["templateId"],
                "compileOutputType": doc["compileOutputType"],
            }
        )
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
            title = meeting.get("title", "")

            # Skip SAP (Spanish Audio/Video) broadcast duplicates
            # These are just video links for the same meeting, no agenda content
            if " - SAP" in title:
                logger.debug(f"[primegov:{self.slug}] Skipping SAP broadcast: {title}")
                continue

            # Find packet document (prefer "Packet", fall back to "Agenda" if not HTML)
            packet_doc = next(
                (
                    doc
                    for doc in meeting.get("documentList", [])
                    if "HTML Agenda" in doc.get("templateName", "")
                    or "packet" in doc.get("templateName", "").lower()
                    or "agenda" in doc.get("templateName", "").lower()
                ),
                None,
            )

            date_time = meeting.get("dateTime", "")

            # Parse meeting status from title and datetime
            meeting_status = self._parse_meeting_status(title, date_time)

            result = {
                "meeting_id": str(meeting["id"]),
                "title": title,
                "start": date_time,
            }

            if packet_doc:
                # HTML Agendas → agenda_url (item-based, primary)
                # PDFs → packet_url (monolithic, fallback)
                if "HTML Agenda" in packet_doc.get("templateName", ""):
                    query = urlencode({"meetingTemplateId": packet_doc["templateId"]})
                    html_url = f"{self.base_url}/Portal/Meeting?{query}"
                    result["agenda_url"] = html_url

                    # Fetch HTML agenda items (item-level granularity)
                    try:
                        logger.info(f"[primegov:{self.slug}] GET {html_url}")
                        items_data = self.fetch_html_agenda_items(html_url)
                        if items_data["items"]:
                            result["items"] = items_data["items"]
                            logger.info(
                                f"[primegov:{self.slug}] Found {len(items_data['items'])} items "
                                f"for '{title}'"
                            )
                        if items_data["participation"]:
                            result["participation"] = items_data["participation"]
                    except Exception as e:
                        logger.warning(
                            f"[primegov:{self.slug}] Failed to fetch HTML agenda items for {title}: {e}"
                        )
                else:
                    # PDF packet
                    result["packet_url"] = self._build_packet_url(packet_doc)
                    logger.info(
                        f"[primegov:{self.slug}] Found PDF packet for '{title}': {result['packet_url']}"
                    )
            else:
                logger.warning(
                    f"[primegov:{self.slug}] No agenda or packet found for: {title} "
                    f"(documentList has {len(meeting.get('documentList', []))} docs)"
                )

            if meeting_status:
                result["meeting_status"] = meeting_status

            yield result

    def fetch_html_agenda_items(self, html_url: str) -> Dict[str, Any]:
        """
        Fetch and parse HTML agenda to extract items and participation info.

        Args:
            html_url: URL to Portal/Meeting page

        Returns:
            {
                'participation': {...},
                'items': [{'item_id': str, 'title': str, 'sequence': int, 'attachments': [...]}]
            }
        """
        # Fetch HTML
        response = self._get(html_url)
        html = response.text

        # Parse it
        parsed = parse_html_agenda(html)

        # Filter procedural items (roll call, approval of minutes, etc.)
        items_before = len(parsed['items'])
        parsed['items'] = [
            item for item in parsed['items']
            if not should_skip_procedural_item(
                item.get('title', ''),
                item.get('item_type', '')
            )
        ]
        items_filtered = items_before - len(parsed['items'])
        if items_filtered > 0:
            logger.info(
                f"[primegov:{self.slug}] Filtered {items_filtered} procedural items"
            )

        # Convert relative attachment URLs to absolute URLs
        # Also ensure type field is set (defense-in-depth)
        total_attachments = 0
        for item in parsed['items']:
            for attachment in item.get('attachments', []):
                url = attachment.get('url', '')
                # If URL is relative (starts with /), make it absolute
                if url.startswith('/'):
                    attachment['url'] = f"{self.base_url}{url}"
                # Ensure type field is set (PrimeGov attachments are PDFs)
                if 'type' not in attachment:
                    attachment['type'] = 'pdf'
                total_attachments += 1

        logger.info(
            f"[primegov:{self.slug}] Parsed HTML agenda: {len(parsed['items'])} items, "
            f"{total_attachments} total attachments"
        )

        return parsed

    def download_attachment(self, history_id: str) -> bytes:
        """
        Download attachment PDF via PrimeGov API.

        Args:
            history_id: UUID from attachment link

        Returns:
            PDF bytes
        """
        url = f"{self.base_url}/api/compilemeetingattachmenthistory/historyattachment/?historyId={history_id}"

        response = self._get(url)

        if response.status_code != 200:
            raise ValueError(f"Failed to download attachment: HTTP {response.status_code}")

        return response.content
