"""
IQM2 Adapter - HTML scraping for IQM2 platform (Granicus subsidiary)

Cities using IQM2: Santa Monica CA, and others

IQM2 was acquired by Granicus and shares similar platform structure.
Calendar page lists meetings, Detail_Meeting pages contain item-level HTML agendas.
"""

import re
from typing import Dict, Any, List, Optional, Iterator
from datetime import datetime, timedelta
from urllib.parse import urljoin
from vendors.adapters.base_adapter import BaseAdapter, logger
from bs4 import BeautifulSoup


class IQM2Adapter(BaseAdapter):
    """Adapter for cities using IQM2 platform (Granicus subsidiary)"""

    def __init__(self, city_slug: str):
        """
        Initialize IQM2 adapter.

        Args:
            city_slug: IQM2 subdomain (e.g., "santamonicacityca" for santamonicacityca.iqm2.com)
        """
        super().__init__(city_slug, vendor="iqm2")
        self.base_url = f"https://{self.slug}.iqm2.com"

        # Try multiple calendar URL patterns (IQM2 sites vary)
        self.calendar_url_patterns = [
            f"{self.base_url}/Citizen",
            f"{self.base_url}/Citizen/Calendar.aspx",
            f"{self.base_url}/Citizen/Default.aspx",
            f"{self.base_url}/Citizens/Calendar.aspx",  # Legacy pattern
        ]

        logger.info(f"[iqm2:{self.slug}] Initialized IQM2 adapter")

    def fetch_meetings(
        self, days_forward: int = 14, days_back: int = 7
    ) -> Iterator[Dict[str, Any]]:
        """
        Scrape meetings from IQM2 calendar page.

        Calendar.aspx returns all meetings for the year. We filter by date range manually.

        Args:
            days_forward: Days to look ahead (default 14)
            days_back: Days to look back (default 7)

        Yields:
            Meeting dictionaries with meeting_id, title, start, items
        """
        # Try each calendar URL pattern until one works
        soup = None
        working_url = None
        meeting_rows = []

        for calendar_url in self.calendar_url_patterns:
            try:
                logger.info(f"[iqm2:{self.slug}] Trying calendar URL: {calendar_url}")
                soup = self._fetch_html(calendar_url)

                # Check if we got a valid calendar page with meetings
                meeting_rows = soup.find_all("div", class_="MeetingRow")
                if meeting_rows:
                    working_url = calendar_url
                    logger.info(
                        f"[iqm2:{self.slug}] Success with {calendar_url} - found {len(meeting_rows)} total meetings"
                    )
                    break
                else:
                    logger.debug(
                        f"[iqm2:{self.slug}] No meetings found at {calendar_url}, trying next pattern"
                    )
            except Exception as e:
                logger.debug(
                    f"[iqm2:{self.slug}] Failed to fetch {calendar_url}: {e}"
                )
                continue

        if not soup or not working_url or not meeting_rows:
            logger.error(
                f"[iqm2:{self.slug}] Could not find working calendar URL. Tried: {self.calendar_url_patterns}"
            )
            return

        # Date range filter
        today = datetime.now()
        start_date = today - timedelta(days=days_back)
        end_date = today + timedelta(days=days_forward)

        meetings_yielded = 0

        for row in meeting_rows:
            # Check if meeting is cancelled
            cancelled_elem = row.find("span", class_="MeetingCancelled")
            if cancelled_elem:
                continue

            # Extract meeting link
            link_elem = row.find("a", href=re.compile(r"Detail_Meeting\.aspx\?ID="))
            if not link_elem:
                continue

            meeting_url = urljoin(self.base_url, link_elem["href"])
            meeting_id_match = re.search(r"ID=(\d+)", meeting_url)
            if not meeting_id_match:
                continue

            meeting_id = meeting_id_match.group(1)

            # Extract date/time from link text
            # Format: "Jan 28, 2025 5:30 PM"
            datetime_text = link_elem.get_text(strip=True)
            try:
                meeting_dt = datetime.strptime(datetime_text, "%b %d, %Y %I:%M %p")
            except ValueError:
                logger.warning(
                    f"[iqm2:{self.slug}] Could not parse datetime: {datetime_text}"
                )
                continue

            # Filter by date range
            if not (start_date <= meeting_dt <= end_date):
                continue

            # Extract title from row details
            title_elem = row.find("div", class_="RowDetails")
            title = title_elem.get_text(strip=True) if title_elem else "Meeting"

            # Fetch Detail_Meeting page to extract items
            logger.info(
                f"[iqm2:{self.slug}] Fetching meeting details for ID={meeting_id}"
            )
            meeting_data = self._fetch_meeting_details(meeting_id, meeting_dt, title)

            if meeting_data:
                meetings_yielded += 1
                yield meeting_data

        logger.info(
            f"[iqm2:{self.slug}] Yielded {meetings_yielded} meetings in date range"
        )

    def _fetch_meeting_details(
        self, meeting_id: str, meeting_dt: datetime, title: str
    ) -> Optional[Dict[str, Any]]:
        """
        Fetch and parse Detail_Meeting page to extract agenda items.

        Args:
            meeting_id: Meeting ID from URL
            meeting_dt: Meeting datetime
            title: Meeting title from calendar

        Returns:
            Meeting dictionary with items array
        """
        detail_url = f"{self.base_url}/Citizens/Detail_Meeting.aspx?ID={meeting_id}"
        soup = self._fetch_html(detail_url)

        # Extract items from MeetingDetail table
        items = self._parse_agenda_items(soup, meeting_id)

        # Extract packet URL if available
        packet_url = None
        packet_link = soup.find("a", id=re.compile(r"hlFullAgendaFile"))
        if packet_link and packet_link.get("href"):
            packet_url = urljoin(self.base_url, packet_link["href"])

        meeting_data = {
            "meeting_id": f"iqm2-{self.slug}-{meeting_id}",
            "title": title,
            "start": meeting_dt.isoformat(),
            "packet_url": packet_url,
            "items": items,
        }

        logger.info(
            f"[iqm2:{self.slug}] Meeting {meeting_id}: {len(items)} items extracted"
        )

        return meeting_data

    def _parse_agenda_items(
        self, soup: BeautifulSoup, meeting_id: str
    ) -> List[Dict[str, Any]]:
        """
        Parse agenda items from MeetingDetail table.

        Structure:
        - Section headers: <td class='Num'><strong>1. </strong></td>
        - Items: <td class='Num'>A. </td> or numbered items
        - Comments: <td class='Comments'>
        - Attachments: <td class='Num'>a. </td> with FileOpen.aspx links

        Args:
            soup: BeautifulSoup object of Detail_Meeting page
            meeting_id: Meeting ID for item IDs

        Returns:
            List of agenda item dictionaries
        """
        items = []

        table = soup.find("table", id="MeetingDetail")
        if not table:
            logger.warning(f"[iqm2:{self.slug}] No MeetingDetail table found")
            return items

        rows = table.find_all("tr")

        current_section = None
        current_item = None
        item_counter = 0

        for row in rows:
            cells = row.find_all("td")
            if len(cells) < 2:
                continue

            # Check if this is a section header (strong tag in first cell)
            first_cell_strong = cells[0].find("strong")
            title_cell = cells[1] if len(cells) > 1 else None

            # Section header
            if first_cell_strong and title_cell:
                title_strong = title_cell.find("strong")
                if title_strong:
                    section_text = title_strong.get_text(strip=True)
                    if section_text:
                        current_section = section_text
                        logger.debug(
                            f"[iqm2:{self.slug}] Found section: {current_section}"
                        )
                    continue

            # Check for main agenda item (letter numbering: A., B., C.)
            # Pattern: <td></td><td class='Num'>A. </td><td class='Title'>...</td>
            if len(cells) >= 3:
                num_cell = cells[1]
                title_cell = cells[2]

                # Main item with letter numbering
                if num_cell.get("class") == ["Num"]:
                    num_text = num_cell.get_text(strip=True)
                    # Match letter numbering: "A.", "B.", etc.
                    if re.match(r"^[A-Z]\.\s*$", num_text):
                        # Save previous item
                        if current_item:
                            items.append(current_item)

                        # Start new item
                        item_counter += 1
                        item_number = num_text.strip()

                        # Extract title (might be a link)
                        title_link = title_cell.find("a", href=True)
                        if title_link:
                            item_title = title_link.get_text(strip=True)
                        else:
                            item_title = title_cell.get_text(strip=True)

                        current_item = {
                            "item_id": f"iqm2-{self.slug}-{meeting_id}-{item_counter}",
                            "title": item_title,
                            "sequence": item_counter,
                            "item_number": item_number,  # Keep letter (A., B., etc.)
                            "section": current_section,  # Keep section context
                            "description": "",  # Will be filled from Comments rows
                            "attachments": [],
                        }

                        logger.debug(
                            f"[iqm2:{self.slug}] Found item {item_number}: {item_title[:50]}"
                        )
                        continue

                # Item description/comments
                if title_cell.get("class") == ["Comments"]:
                    if current_item:
                        desc_text = title_cell.get_text(strip=True)
                        current_item["description"] = desc_text
                    continue

            # Check for attachments (4-cell rows: <td></td><td></td><td class='Num'>a.</td><td class='Title'>...</td>)
            if len(cells) >= 4:
                # Check if first two cells are empty and third has Num class
                if (
                    not cells[0].get_text(strip=True)
                    and not cells[1].get_text(strip=True)
                    and cells[2].get("class") == ["Num"]
                ):
                    num_cell = cells[2]
                    title_cell = cells[3]
                    num_text = num_cell.get_text(strip=True)

                    # Match lowercase letter (a., b., c.) or doc icon
                    if re.match(r"^[a-z]\.\s*$", num_text) or num_cell.find("img"):
                        if current_item:
                            # Extract PDF/doc link
                            pdf_link = title_cell.find("a", href=True)
                            if pdf_link:
                                pdf_url = urljoin(self.base_url, pdf_link["href"])
                                pdf_name = pdf_link.get_text(strip=True)

                                # Determine file type from URL or name
                                file_type = "pdf"
                                if ".doc" in pdf_url.lower() or ".doc" in pdf_name.lower():
                                    file_type = "doc"
                                elif ".xls" in pdf_url.lower() or ".xls" in pdf_name.lower():
                                    file_type = "xls"

                                current_item["attachments"].append(
                                    {"name": pdf_name, "url": pdf_url, "type": file_type}
                                )
                                logger.debug(
                                    f"[iqm2:{self.slug}] Added attachment: {pdf_name[:40]}"
                                )

        # Don't forget the last item
        if current_item:
            items.append(current_item)

        logger.info(
            f"[iqm2:{self.slug}] Parsed {len(items)} items from MeetingDetail table"
        )

        return items
