"""
PrimeGov Adapter - Thin wrapper for PrimeGov municipal calendar API

Cities using PrimeGov: Palo Alto CA, Mountain View CA, Sunnyvale CA, and many others
"""

from datetime import datetime, timedelta
from typing import Dict, Any, Iterator, List
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

    def fetch_meetings(self, days_back: int = 7, days_forward: int = 14) -> Iterator[Dict[str, Any]]:
        """
        Fetch meetings from PrimeGov API within date range.

        Combines ListUpcomingMeetings (future) and ListArchivedMeetings (past)
        to capture the full window.

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

        # Fetch upcoming meetings (future)
        upcoming_url = f"{self.base_url}/api/v2/PublicPortal/ListUpcomingMeetings"
        upcoming_response = self._get(upcoming_url)
        upcoming_meetings = upcoming_response.json()

        # Fetch archived meetings for current year (past)
        # Note: If date range spans multiple years, fetch both years
        archived_meetings: List[Dict[str, Any]] = []
        years_to_fetch = set([start_date.year, today.year])
        for year in years_to_fetch:
            archived_url = f"{self.base_url}/api/v2/PublicPortal/ListArchivedMeetings?year={year}"
            archived_response = self._get(archived_url)
            archived_meetings.extend(archived_response.json())

        # Combine and deduplicate by meeting ID
        all_meetings = upcoming_meetings + archived_meetings
        seen_ids = set()
        unique_meetings = []
        for meeting in all_meetings:
            meeting_id = meeting.get("id")
            if meeting_id not in seen_ids:
                seen_ids.add(meeting_id)
                unique_meetings.append(meeting)

        logger.info(
            f"[primegov:{self.slug}] Retrieved {len(upcoming_meetings)} upcoming, "
            f"{len(archived_meetings)} archived ({len(unique_meetings)} unique)"
        )

        # Filter meetings to date range and process
        meetings_in_range = []
        for meeting in unique_meetings:
            # Parse meeting datetime
            date_str = meeting.get("dateTime", "")
            if not date_str:
                continue

            try:
                meeting_date = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
                # Remove timezone for comparison
                meeting_date = meeting_date.replace(tzinfo=None)

                # Check if within range
                if start_date <= meeting_date <= end_date:
                    meetings_in_range.append(meeting)
            except (ValueError, AttributeError):
                # If date parsing fails, include it anyway (defensive)
                logger.debug(
                    f"[primegov:{self.slug}] Failed to parse date: {date_str}, including anyway"
                )
                meetings_in_range.append(meeting)

        logger.info(
            f"[primegov:{self.slug}] Filtered to {len(meetings_in_range)} meetings "
            f"in date range ({start_date.date()} to {end_date.date()})"
        )

        for meeting in meetings_in_range:
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

            # PrimeGov-specific: Check meetingState field
            # meetingState: 3 = cancelled/recess
            meeting_state = meeting.get("meetingState")
            if meeting_state == 3 and not meeting_status:
                meeting_status = "cancelled"

            # PrimeGov-specific: Check document names for cancellation/recess notices
            if not meeting_status:
                doc_list = meeting.get("documentList", [])
                for doc in doc_list:
                    doc_name = doc.get("templateName", "").lower()
                    if "cancel" in doc_name or "recess" in doc_name:
                        meeting_status = "cancelled"
                        break

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
