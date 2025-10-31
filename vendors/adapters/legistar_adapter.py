"""
Legistar Adapter - API integration for Legistar platform

Cities using Legistar: Seattle WA, NYC, Cambridge MA, and many others
"""

from typing import Dict, Any, Iterator, Optional, List
from datetime import datetime, timedelta
import re
import xml.etree.ElementTree as ET
from vendors.adapters.base_adapter import BaseAdapter, logger


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
        Fetch upcoming meetings (tries API first, falls back to HTML).

        Args:
            days_forward: Number of days to look ahead (default 60)

        Yields:
            Meeting dictionaries with meeting_id, title, start, packet_url
        """
        try:
            yield from self._fetch_meetings_api(days_forward)
        except Exception as e:
            if hasattr(e, 'response') and e.response.status_code in [400, 403, 404]:
                logger.warning(
                    f"[legistar:{self.slug}] API failed (HTTP {e.response.status_code}), "
                    f"falling back to HTML scraping"
                )
                yield from self._fetch_meetings_html(days_forward)
            else:
                raise

    def _fetch_meetings_api(self, days_forward: int = 60) -> Iterator[Dict[str, Any]]:
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

        # Try JSON first, fallback to XML
        events = []
        try:
            events = response.json()
            logger.info(f"[legistar:{self.slug}] Retrieved {len(events)} events (JSON)")
        except Exception as json_error:
            # Try XML parsing
            try:
                events = self._parse_xml_events(response.text)
                logger.info(f"[legistar:{self.slug}] Retrieved {len(events)} events (XML)")
            except Exception as xml_error:
                logger.error(
                    f"[legistar:{self.slug}] Failed to parse as JSON or XML. "
                    f"JSON error: {json_error}, XML error: {xml_error}"
                )
                logger.error(
                    f"[legistar:{self.slug}] Response text (first 1000 chars): {response.text[:1000]}"
                )
                return

        for event in events:
            # Extract event data
            event_id = event.get("EventId")
            event_date = event.get("EventDate")
            event_name = event.get("EventBodyName", "")
            event_location = event.get("EventLocation")
            event_agenda_status = event.get("EventAgendaStatusName", "")

            # Get agenda PDF (EventAgendaFile is the canonical agenda document)
            agenda_pdf = event.get("EventAgendaFile")

            # Parse meeting status from title and agenda status
            meeting_status = self._parse_meeting_status(event_name, event_agenda_status)

            # Fetch agenda items with attachments (Legistar provides via API)
            items = self.fetch_event_items(event_id)

            result = {
                "meeting_id": str(event_id),
                "title": event_name,
                "start": event_date,
            }

            # Architecture: items extracted → agenda_url, no items → packet_url
            # For Legistar, the agenda PDF is the canonical document
            if items:
                result["agenda_url"] = agenda_pdf  # PDF is the source document
                result["items"] = items
            elif agenda_pdf:
                result["packet_url"] = agenda_pdf  # Fallback for monolithic processing
            else:
                logger.debug(
                    f"[legistar:{self.slug}] No agenda for: {event_name} on {event_date}"
                )

            if event_location:
                result["location"] = event_location

            if meeting_status:
                result["meeting_status"] = meeting_status

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

        # Try JSON first, fallback to XML
        event_items = []
        try:
            response = self._get(items_url, params=params)
            event_items = response.json()
            logger.debug(f"[legistar:{self.slug}] Retrieved {len(event_items)} items (JSON)")
        except Exception as json_error:
            # Try XML parsing
            try:
                event_items = self._parse_xml_event_items(response.text)
                logger.debug(f"[legistar:{self.slug}] Retrieved {len(event_items)} items (XML)")
            except Exception as xml_error:
                logger.error(
                    f"[legistar:{self.slug}] Failed to parse items for event {event_id} as JSON or XML. "
                    f"JSON error: {json_error}, XML error: {xml_error}"
                )
                logger.error(
                    f"[legistar:{self.slug}] Response text (first 500 chars): {response.text[:500]}"
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

        # Try JSON first, fallback to XML
        raw_attachments = []
        try:
            response = self._get(attachments_url, params=params)
            raw_attachments = response.json()
        except Exception as json_error:
            # Try XML parsing
            try:
                raw_attachments = self._parse_xml_attachments(response.text)
            except Exception as xml_error:
                logger.warning(
                    f"[legistar:{self.slug}] Failed to fetch attachments for matter {matter_id} as JSON or XML. "
                    f"JSON error: {json_error}, XML error: {xml_error}"
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

    def _parse_xml_events(self, xml_text: str) -> List[Dict[str, Any]]:
        """
        Parse Legistar XML response into event dictionaries.

        Some cities return XML instead of JSON from the API.
        This method normalizes the XML structure to match the JSON format.

        Args:
            xml_text: Raw XML response text

        Returns:
            List of event dictionaries with same structure as JSON API
        """
        events = []

        try:
            root = ET.fromstring(xml_text)

            # Handle namespace
            ns = {'ns': 'http://schemas.datacontract.org/2004/07/LegistarWebAPI.Models.v1'}

            # Find all GranicusEvent elements
            for event_elem in root.findall('.//ns:GranicusEvent', ns):
                event = {}

                # Map XML fields to JSON field names
                field_map = {
                    'EventId': 'EventId',
                    'EventBodyName': 'EventBodyName',
                    'EventDate': 'EventDate',
                    'EventLocation': 'EventLocation',
                    'EventAgendaStatusName': 'EventAgendaStatusName',
                    'EventAgendaFile': 'EventAgendaFile',
                }

                for xml_field, json_field in field_map.items():
                    elem = event_elem.find(f'ns:{xml_field}', ns)
                    if elem is not None and elem.text:
                        # Convert EventId to int
                        if xml_field == 'EventId':
                            event[json_field] = int(elem.text)
                        else:
                            event[json_field] = elem.text

                # Only add events that have at least an ID
                if 'EventId' in event:
                    events.append(event)

            return events

        except ET.ParseError as e:
            logger.error(f"[legistar:{self.slug}] XML parsing error: {e}")
            raise

    def _parse_xml_event_items(self, xml_text: str) -> List[Dict[str, Any]]:
        """
        Parse Legistar XML response for event items.

        Args:
            xml_text: Raw XML response text

        Returns:
            List of event item dictionaries
        """
        items = []

        try:
            root = ET.fromstring(xml_text)

            # Handle namespace
            ns = {'ns': 'http://schemas.datacontract.org/2004/07/LegistarWebAPI.Models.v1'}

            # Find all GranicusEventItem elements
            for item_elem in root.findall('.//ns:GranicusEventItem', ns):
                item = {}

                # Map XML fields to JSON field names
                field_map = {
                    'EventItemId': 'EventItemId',
                    'EventItemTitle': 'EventItemTitle',
                    'EventItemAgendaSequence': 'EventItemAgendaSequence',
                    'EventItemMatterId': 'EventItemMatterId',
                }

                for xml_field, json_field in field_map.items():
                    elem = item_elem.find(f'ns:{xml_field}', ns)
                    if elem is not None and elem.text:
                        # Convert numeric fields
                        if xml_field in ('EventItemId', 'EventItemMatterId', 'EventItemAgendaSequence'):
                            item[json_field] = int(elem.text)
                        else:
                            item[json_field] = elem.text

                # Only add items that have at least an ID
                if 'EventItemId' in item:
                    items.append(item)

            return items

        except ET.ParseError as e:
            logger.error(f"[legistar:{self.slug}] XML parsing error for event items: {e}")
            raise

    def _parse_xml_attachments(self, xml_text: str) -> List[Dict[str, Any]]:
        """
        Parse Legistar XML response for matter attachments.

        Args:
            xml_text: Raw XML response text

        Returns:
            List of attachment dictionaries
        """
        attachments = []

        try:
            root = ET.fromstring(xml_text)

            # Handle namespace
            ns = {'ns': 'http://schemas.datacontract.org/2004/07/LegistarWebAPI.Models.v1'}

            # Find all GranicusMatterAttachment elements
            for att_elem in root.findall('.//ns:GranicusMatterAttachment', ns):
                attachment = {}

                # Map XML fields to JSON field names
                field_map = {
                    'MatterAttachmentName': 'MatterAttachmentName',
                    'MatterAttachmentHyperlink': 'MatterAttachmentHyperlink',
                }

                for xml_field, json_field in field_map.items():
                    elem = att_elem.find(f'ns:{xml_field}', ns)
                    if elem is not None and elem.text:
                        attachment[json_field] = elem.text

                # Only add attachments that have at least a hyperlink
                if 'MatterAttachmentHyperlink' in attachment:
                    attachments.append(attachment)

            return attachments

        except ET.ParseError as e:
            logger.error(f"[legistar:{self.slug}] XML parsing error for attachments: {e}")
            raise

    def _fetch_meetings_html(self, days_forward: int = 60) -> Iterator[Dict[str, Any]]:
        """
        Fetch meetings by scraping HTML calendar (fallback when API fails).

        Args:
            days_forward: Number of days to look ahead (default 60)

        Yields:
            Meeting dictionaries with meeting_id, title, start, items
        """
        from urllib.parse import urljoin

        # Legistar HTML calendar URL pattern: https://{city}.legistar.com/Calendar.aspx
        # Note: slug might be different from city subdomain
        # Try common patterns
        calendar_urls = [
            f"https://{self.slug}.legistar.com/Calendar.aspx",
            f"https://webapi.legistar.com/{self.slug}/Calendar.aspx",
        ]

        soup = None
        calendar_url = None
        for url in calendar_urls:
            try:
                soup = self._fetch_html(url)
                calendar_url = url
                logger.info(f"[legistar:{self.slug}] Found HTML calendar at {url}")
                break
            except Exception as e:
                logger.debug(f"[legistar:{self.slug}] Calendar not found at {url}: {e}")
                continue

        if not soup or not calendar_url:
            logger.error(
                f"[legistar:{self.slug}] Could not find HTML calendar at any known URL"
            )
            return

        # Extract base URL for building absolute URLs
        html_base_url = calendar_url.rsplit('/', 1)[0]

        # Date range filter
        today = datetime.now()
        start_date = today - timedelta(days=7)
        end_date = today + timedelta(days=days_forward)

        # Find meeting rows in RadGrid calendar table
        # Legistar uses Telerik RadGrid with specific row classes
        meeting_rows = soup.find_all("tr", class_=["rgRow", "rgAltRow"])

        if not meeting_rows:
            logger.warning(
                f"[legistar:{self.slug}] No meeting rows found in HTML calendar"
            )
            # Log a sample of all table rows for debugging
            all_tables = soup.find_all("table")
            logger.info(f"[legistar:{self.slug}] Found {len(all_tables)} tables in HTML")
            if all_tables:
                # Find the rgMasterTable specifically
                master_table = soup.find("table", class_="rgMasterTable")
                if master_table:
                    sample_rows = master_table.find_all("tr")[:5]
                    logger.info(f"[legistar:{self.slug}] Found rgMasterTable with {len(sample_rows)} rows")
                    for i, row in enumerate(sample_rows):
                        logger.info(f"[legistar:{self.slug}] Sample row {i}: {str(row)[:500]}")
            return

        logger.info(
            f"[legistar:{self.slug}] Found {len(meeting_rows)} meetings in HTML calendar"
        )

        meetings_yielded = 0

        for row in meeting_rows:
            try:
                cells = row.find_all("td")
                if len(cells) < 6:
                    continue

                # Extract meeting detail link (usually in cell 5 or 6)
                detail_link = row.find("a", href=lambda x: x and "MeetingDetail.aspx" in x)
                if not detail_link:
                    continue

                # Extract full detail URL (includes GUID which is required)
                detail_url = urljoin(html_base_url, detail_link["href"])
                meeting_id_match = re.search(r"ID=(\d+)", detail_url)
                if not meeting_id_match:
                    continue

                meeting_id = meeting_id_match.group(1)

                # Extract title - try multiple strategies for flexibility
                title = None

                # Strategy 1: Look for anchor with "hypBody" in id (SF format)
                title_link = row.find("a", id=lambda x: x and "hypBody" in x)
                if title_link:
                    title = title_link.get_text(strip=True)

                # Strategy 2: First cell with anchor (common pattern)
                if not title and len(cells) > 0:
                    first_link = cells[0].find("a")
                    if first_link:
                        title = first_link.get_text(strip=True)

                # Strategy 3: MeetingDetail.aspx link text (fallback)
                if not title:
                    title = detail_link.get_text(strip=True)

                if not title or title == "Details":
                    title = "Meeting"

                # Extract date - look for cells with date pattern or rgSorted class
                meeting_dt = None

                # Strategy 1: Cell with rgSorted class
                sorted_cell = row.find("td", class_="rgSorted")
                if sorted_cell:
                    parsed_date = self._parse_date(sorted_cell.get_text(strip=True))
                    if parsed_date:
                        meeting_dt = parsed_date

                # Strategy 2: Scan all cells for date pattern
                if not meeting_dt:
                    for cell in cells:
                        cell_text = cell.get_text(strip=True)
                        parsed_date = self._parse_date(cell_text)
                        if parsed_date:
                            meeting_dt = parsed_date
                            break

                if not meeting_dt:
                    logger.debug(
                        f"[legistar:{self.slug}] Could not parse date for meeting {meeting_id}"
                    )
                    continue

                # Filter by date range
                if not (start_date <= meeting_dt <= end_date):
                    continue

                # Extract agenda PDF from calendar row (fallback if detail page unavailable)
                packet_url = None
                agenda_link = row.find("a", href=lambda x: x and "View.ashx" in x and ("M=A" in x or "agenda" in x.lower()))
                if agenda_link:
                    packet_url = urljoin(html_base_url, agenda_link["href"])

                # Fetch meeting detail page for items
                meeting_data = self._fetch_meeting_detail_html(
                    meeting_id, meeting_dt, title, detail_url, packet_url
                )

                if meeting_data:
                    meetings_yielded += 1
                    yield meeting_data

            except Exception as e:
                logger.warning(
                    f"[legistar:{self.slug}] Error parsing meeting row: {e}"
                )
                continue

        logger.info(
            f"[legistar:{self.slug}] Yielded {meetings_yielded} meetings from HTML"
        )

    def _fetch_meeting_detail_html(
        self, meeting_id: str, meeting_dt: datetime, title: str, detail_url: str, calendar_packet_url: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Fetch and parse meeting detail page for agenda items.

        Args:
            meeting_id: Meeting ID from calendar
            meeting_dt: Meeting datetime
            title: Meeting title from calendar
            detail_url: Full URL to MeetingDetail.aspx (includes GUID)
            calendar_packet_url: Optional packet URL from calendar page (fallback)

        Returns:
            Meeting dictionary with items array
        """
        from urllib.parse import urljoin, urlparse

        items = []
        packet_url = calendar_packet_url

        # Extract base URL from detail_url for building relative URLs
        parsed = urlparse(detail_url)
        base_url = f"{parsed.scheme}://{parsed.netloc}"

        # Try to fetch detail page (may fail with 410 for old meetings)
        try:
            soup = self._fetch_html(detail_url)

            # Parse agenda items from detail page
            items = self._parse_html_agenda_items(soup, meeting_id, base_url)

            # Fetch attachments for each item (3rd layer)
            items_with_attachments = 0
            for item in items:
                attachments = self._fetch_item_attachments(item, base_url)
                if attachments:
                    item['attachments'] = attachments
                    items_with_attachments += 1

            if items_with_attachments > 0:
                logger.info(
                    f"[legistar:{self.slug}] Meeting {meeting_id}: {items_with_attachments}/{len(items)} items have attachments"
                )

            # Look for agenda PDF link if not provided from calendar
            if not packet_url:
                agenda_links = soup.find_all("a", href=lambda x: x and ".pdf" in x.lower() if x else False)
                for link in agenda_links:
                    link_text = link.get_text(strip=True).lower()
                    if "agenda" in link_text or "packet" in link_text:
                        packet_url = urljoin(base_url, link["href"])
                        break

        except Exception as e:
            logger.debug(
                f"[legistar:{self.slug}] Detail page unavailable for meeting {meeting_id}: {e}"
            )
            # Continue with calendar packet URL if available

        meeting_data = {
            "meeting_id": str(meeting_id),
            "title": title,
            "start": meeting_dt.isoformat(),
        }

        # Architecture: items extracted → agenda_url, no items → packet_url
        if items:
            if packet_url:
                meeting_data["agenda_url"] = packet_url
            meeting_data["items"] = items
            logger.info(
                f"[legistar:{self.slug}] Meeting {meeting_id}: extracted {len(items)} items from HTML"
            )
        elif packet_url:
            meeting_data["packet_url"] = packet_url
            logger.info(
                f"[legistar:{self.slug}] Meeting {meeting_id}: using packet URL from calendar (no items)"
            )
        else:
            # No items and no packet - skip this meeting
            logger.debug(
                f"[legistar:{self.slug}] Meeting {meeting_id}: no items or packet available, skipping"
            )
            return None

        return meeting_data

    def _parse_html_agenda_items(
        self, soup, meeting_id: str, base_url: str
    ) -> List[Dict[str, Any]]:
        """
        Parse agenda items from meeting detail HTML using dedicated parser.

        Args:
            soup: BeautifulSoup object of detail page
            meeting_id: Meeting ID for generating item IDs
            base_url: Base URL for building absolute URLs

        Returns:
            List of agenda item dictionaries
        """
        from vendors.adapters.html_agenda_parser import parse_legistar_html_agenda

        # Convert soup back to HTML string for the parser
        html = str(soup)

        # Use dedicated Legistar HTML parser
        parsed_data = parse_legistar_html_agenda(html, meeting_id, base_url)

        items = parsed_data.get('items', [])

        logger.debug(
            f"[legistar:{self.slug}] Parsed {len(items)} items from HTML for meeting {meeting_id}"
        )

        return items

    def _filter_leg_ver_attachments(self, attachments: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Filter attachments to include at most one 'Leg Ver' attachment.
        Prefer 'Leg Ver2' over 'Leg Ver1' if both exist.

        Args:
            attachments: List of attachment dictionaries

        Returns:
            Filtered list of attachments
        """
        leg_ver_attachments = []
        other_attachments = []

        for att in attachments:
            name = att.get('name', '').lower()
            if 'leg ver' in name:
                leg_ver_attachments.append(att)
            else:
                other_attachments.append(att)

        # Select best Leg Ver attachment
        selected_leg_ver = None
        if leg_ver_attachments:
            # Prefer Leg Ver2, then Leg Ver1, then any Leg Ver
            for att in leg_ver_attachments:
                name = att.get('name', '').lower()
                if 'leg ver2' in name or 'leg ver 2' in name:
                    selected_leg_ver = att
                    break

            # If no Ver2, look for Ver1
            if not selected_leg_ver:
                for att in leg_ver_attachments:
                    name = att.get('name', '').lower()
                    if 'leg ver1' in name or 'leg ver 1' in name:
                        selected_leg_ver = att
                        break

            # If no Ver1 or Ver2, just take the first one
            if not selected_leg_ver:
                selected_leg_ver = leg_ver_attachments[0]

        # Combine: at most one Leg Ver + all other attachments
        filtered = other_attachments
        if selected_leg_ver:
            filtered.insert(0, selected_leg_ver)

        return filtered

    def _fetch_item_attachments(
        self, item: Dict[str, Any], base_url: str
    ) -> List[Dict[str, Any]]:
        """
        Fetch attachments for a single item from its LegislationDetail page.

        Args:
            item: Item dictionary with legislation_url
            base_url: Base URL for building absolute URLs

        Returns:
            List of attachment dictionaries
        """
        from vendors.adapters.html_agenda_parser import parse_legistar_legislation_attachments

        legislation_url = item.get('legislation_url')
        if not legislation_url:
            return []

        try:
            soup = self._fetch_html(legislation_url)
            html = str(soup)
            attachments = parse_legistar_legislation_attachments(html, base_url)

            # Filter to include at most one Leg Ver attachment
            attachments = self._filter_leg_ver_attachments(attachments)

            logger.debug(
                f"[legistar:{self.slug}] Item {item.get('item_id')}: found {len(attachments)} attachments (after filtering)"
            )

            return attachments

        except Exception as e:
            logger.warning(
                f"[legistar:{self.slug}] Failed to fetch attachments for item {item.get('item_id')}: {e}"
            )
            return []
