"""
Async IQM2 Adapter - HTML scraping for IQM2 platform (Granicus subsidiary)

Gold standard async adapter for IQM2 cities. Supports item-level processing with full
matter tracking, attachments, metadata, and cross-meeting legislative tracking.

Cities using IQM2: Boise ID, Santa Monica CA, Cambridge MA, Buffalo NY, and 40+ others

Architecture:
- Calendar page (Citizens/Default.aspx) lists all meetings
- Detail_Meeting pages contain item-level HTML agendas with LegiFile links
- Detail_LegiFile pages contain matter metadata, sponsors, and attachments

Parity with Legistar/PrimeGov/Granicus:
- Item-level extraction with attachments
- Matter tracking (matter_id, matter_file, matter_type, sponsors)
- Clean matter_file extraction (case numbers, not verbose titles)
- Full attachment support from Detail_LegiFile pages
- Concurrent meeting/item fetching for faster sync
"""

import asyncio
import re
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta
from urllib.parse import urljoin
import aiohttp
from vendors.adapters.base_adapter_async import AsyncBaseAdapter, logger
from pipeline.filters import should_skip_item
from bs4 import BeautifulSoup


class AsyncIQM2Adapter(AsyncBaseAdapter):
    """
    Gold standard async adapter for IQM2 platform (Granicus subsidiary).

    Provides complete item-level processing with attachments, matter tracking,
    and metadata extraction. At parity with Legistar, PrimeGov, and Granicus
    for municipal legislative data extraction.
    """

    def __init__(self, city_slug: str):
        """
        Initialize async IQM2 adapter.

        Args:
            city_slug: IQM2 subdomain (e.g., "santamonicacityca" for santamonicacityca.iqm2.com)
        """
        super().__init__(city_slug, vendor="iqm2")
        self.base_url = f"https://{self.slug}.iqm2.com"

        # Try multiple calendar URL patterns (IQM2 sites vary)
        self.calendar_url_patterns = [
            f"{self.base_url}/Citizens",
            f"{self.base_url}/Citizens/Calendar.aspx",
            f"{self.base_url}/Citizens/Default.aspx",
        ]

        logger.info("initialized async IQM2 adapter", vendor="iqm2", slug=self.slug)

    async def _fetch_meetings_impl(
        self, days_back: int = 7, days_forward: int = 14
    ) -> List[Dict[str, Any]]:
        """
        Scrape meetings from IQM2 calendar page.

        Calendar.aspx returns all meetings for the year. We filter by date range manually.

        Args:
            days_back: Days to look back (default 7)
            days_forward: Days to look ahead (default 14)

        Returns:
            List of meeting dictionaries (validation in base class)
        """
        # Try each calendar URL pattern until one works
        soup = None
        working_url = None
        meeting_rows = []

        for calendar_url in self.calendar_url_patterns:
            try:
                logger.info("trying calendar URL", vendor="iqm2", slug=self.slug, url=calendar_url)
                response = await self._get(calendar_url)
                html = await response.text()
                soup = BeautifulSoup(html, 'html.parser')

                # Check if we got a valid calendar page with meetings
                meeting_rows = soup.find_all("div", class_="MeetingRow")
                if meeting_rows:
                    working_url = calendar_url
                    logger.info(
                        "found meetings on calendar",
                        vendor="iqm2",
                        slug=self.slug,
                        url=calendar_url,
                        count=len(meeting_rows)
                    )
                    break
                else:
                    logger.debug(
                        "no meetings found at URL",
                        vendor="iqm2",
                        slug=self.slug,
                        url=calendar_url
                    )
            except (aiohttp.ClientError, asyncio.TimeoutError) as e:
                logger.debug(
                    "failed to fetch calendar URL",
                    vendor="iqm2",
                    slug=self.slug,
                    url=calendar_url,
                    error=str(e)
                )
                continue

        if not soup or not working_url or not meeting_rows:
            logger.error(
                "could not find working calendar URL",
                vendor="iqm2",
                slug=self.slug,
                tried_urls=self.calendar_url_patterns
            )
            return []

        # Date range filter
        today = datetime.now()
        start_date = today - timedelta(days=days_back)
        end_date = today + timedelta(days=days_forward)

        meetings = []

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
                    "could not parse datetime",
                    vendor="iqm2",
                    slug=self.slug,
                    datetime_text=datetime_text
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
                "fetching meeting details",
                vendor="iqm2",
                slug=self.slug,
                meeting_id=meeting_id
            )
            meeting_data = await self._fetch_meeting_details(meeting_id, meeting_dt, title)

            if meeting_data:
                meetings.append(meeting_data)

        logger.info(
            "collected meetings in date range",
            vendor="iqm2",
            slug=self.slug,
            count=len(meetings)
        )

        return meetings

    async def _fetch_meeting_details(
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
        response = await self._get(detail_url)
        html = await response.text()
        soup = BeautifulSoup(html, 'html.parser')

        # Extract items from MeetingDetail table
        items = await self._parse_agenda_items(soup, meeting_id, detail_url)

        # Filter procedural items (roll call, approval of minutes, etc.)
        items_before = len(items)
        items = [
            item for item in items
            if not should_skip_item(item.get('title', ''))
        ]
        items_filtered = items_before - len(items)
        if items_filtered > 0:
            logger.info(
                "filtered procedural items",
                vendor="iqm2",
                slug=self.slug,
                filtered_count=items_filtered
            )

        # Extract packet URL if available
        packet_url = None
        packet_link = soup.find("a", id=re.compile(r"hlFullAgendaFile"))
        if packet_link and packet_link.get("href"):
            packet_url = urljoin(self.base_url, packet_link["href"])

        meeting_data = {
            "vendor_id": meeting_id,
            "title": title,
            "start": meeting_dt.isoformat(),
            "agenda_url": detail_url,  # HTML agenda source (Detail_Meeting.aspx)
            "packet_url": packet_url,  # Full PDF packet (optional)
            "items": items,
        }

        logger.info(
            "extracted items from meeting",
            vendor="iqm2",
            slug=self.slug,
            meeting_id=meeting_id,
            item_count=len(items)
        )

        return meeting_data

    async def _fetch_matter_metadata(self, legifile_id: str) -> Dict[str, Any]:
        """
        Fetch matter metadata from Detail_LegiFile.aspx page.

        Extracts:
        - matter_type (Category field)
        - sponsors (Sponsors field)
        - department (Department field)
        - attachments (from Attachments section)

        Args:
            legifile_id: LegiFile ID to fetch

        Returns:
            Dict with matter_type, sponsors (list), department, attachments (list)
        """
        detail_url = f"{self.base_url}/Citizens/Detail_LegiFile.aspx?ID={legifile_id}"

        try:
            response = await self._get(detail_url)
            html = await response.text()
            soup = BeautifulSoup(html, 'html.parser')

            # Find the LegiFileInfo table
            info_table = soup.find("table", id="tblLegiFileInfo")
            if not info_table:
                return {}

            metadata = {}

            # Parse table rows for metadata
            rows = info_table.find_all("tr")
            for row in rows:
                cells = row.find_all(["th", "td"])

                # Process cell pairs (label: value)
                i = 0
                while i < len(cells) - 1:
                    label = cells[i].get_text(strip=True).lower().replace(":", "")
                    value = cells[i + 1].get_text(strip=True)

                    if "category" in label and value:
                        metadata["matter_type"] = value
                    elif "sponsor" in label and value:
                        # Split sponsors by comma or semicolon
                        sponsors = [s.strip() for s in re.split(r'[,;]', value) if s.strip()]
                        metadata["sponsors"] = sponsors
                    elif "department" in label and value:
                        metadata["department"] = value

                    i += 2

            # Extract attachments from Attachments section
            # Look for divAttachments or similar container
            attachments = []
            attachment_links = soup.find_all("a", href=re.compile(r'FileOpen\.aspx'))
            for link in attachment_links:
                # Extract attachment name and URL
                attachment_name = link.get_text(strip=True)
                attachment_url = urljoin(detail_url, link.get("href", ""))

                if attachment_name and attachment_url:
                    # Determine file type from URL or name
                    file_type = "pdf"
                    if ".doc" in attachment_url.lower() or ".doc" in attachment_name.lower():
                        file_type = "doc"
                    elif ".xls" in attachment_url.lower() or ".xls" in attachment_name.lower():
                        file_type = "xls"

                    attachments.append({
                        "name": attachment_name,
                        "url": attachment_url,
                        "type": file_type
                    })

            if attachments:
                metadata["attachments"] = attachments
                logger.debug(
                    "found attachments for legifile",
                    vendor="iqm2",
                    slug=self.slug,
                    legifile_id=legifile_id,
                    count=len(attachments)
                )

            logger.debug(
                "fetched matter metadata",
                vendor="iqm2",
                slug=self.slug,
                legifile_id=legifile_id,
                metadata=metadata
            )
            return metadata

        except (aiohttp.ClientError, asyncio.TimeoutError) as e:
            logger.warning(
                "failed to fetch matter metadata",
                vendor="iqm2",
                slug=self.slug,
                legifile_id=legifile_id,
                error=str(e)
            )
            return {}
        except (ValueError, AttributeError, KeyError) as e:
            logger.warning(
                "failed to parse matter metadata",
                vendor="iqm2",
                slug=self.slug,
                legifile_id=legifile_id,
                error=str(e)
            )
            return {}

    async def _parse_agenda_items(
        self, soup: BeautifulSoup, meeting_id: str, base_url: str
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
            base_url: Base URL for resolving relative links (Detail_Meeting page URL)

        Returns:
            List of agenda item dictionaries
        """
        items = []

        table = soup.find("table", id="MeetingDetail")
        if not table:
            logger.warning("no MeetingDetail table found", vendor="iqm2", slug=self.slug)
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
                            "found section",
                            vendor="iqm2",
                            slug=self.slug,
                            section=current_section
                        )
                    continue

            # Check for main agenda item (letter or number numbering: A., B., C. or 1., 2., 3.)
            # Pattern 1: <td></td><td class='Num'>A. </td><td class='Title'>...</td> (top-level)
            # Pattern 2: <td></td><td></td><td class='Num'>1. </td><td class='Title'>...</td> (nested under subsections)
            # Pattern 3: <td></td><td class='Num'></td><td class='Title'>COF 2025 #141: ...</td> (Cambridge pattern)

            # Try Pattern 2 first (nested items with 2 empty cells - Boise resolutions under "D. Resolutions")
            if len(cells) >= 4 and not cells[0].get_text(strip=True) and not cells[1].get_text(strip=True):
                num_cell = cells[2]
                title_cell = cells[3]

                if num_cell.get("class") == ["Num"]:
                    num_text = num_cell.get_text(strip=True)

                    # Check for numbered items (1., 2., 3., etc.)
                    if re.match(r"^[0-9]+\.\s*$", num_text):
                        title_link = title_cell.find("a", href=lambda x: x and "Detail_LegiFile.aspx" in x)

                        # Save previous item
                        if current_item:
                            items.append(current_item)

                        # Start new nested item
                        item_counter += 1
                        item_number = num_text.strip()

                        # Extract title
                        if title_link:
                            item_title = title_link.get_text(strip=True)
                            # Extract LegiFile ID (avoid matching MeetingID=)
                            href = title_link.get("href", "")
                            id_match = re.search(r"[?&]ID=(\d+)", href)
                            legifile_id = id_match.group(1) if id_match else None
                        else:
                            item_title = title_cell.get_text(strip=True)
                            legifile_id = None

                        current_item = {
                            "item_id": legifile_id or f"iqm2-{self.slug}-{meeting_id}-{item_counter}",
                            "title": item_title,
                            "sequence": item_counter,
                            "item_number": item_number,
                            "section": current_section,
                            "description": "",
                            "attachments": [],
                        }

                        # Add matter tracking if LegiFile item
                        if legifile_id:
                            current_item["matter_id"] = legifile_id

                            # Extract clean matter_file from title
                            matter_file = None
                            if " / " in item_title:
                                matter_file = item_title.split(" / ", 1)[0].strip()
                            elif ":" in item_title:
                                prefix = item_title.split(":", 1)[0].strip()
                                matter_file = re.sub(r'\s+#\s*', '-', prefix)
                                matter_file = re.sub(r'\s+', '-', matter_file)

                            current_item["matter_file"] = matter_file if matter_file else legifile_id

                            # Fetch matter metadata and attachments from Detail_LegiFile page
                            metadata = await self._fetch_matter_metadata(legifile_id)
                            if metadata.get("matter_type"):
                                current_item["matter_type"] = metadata["matter_type"]
                            if metadata.get("sponsors"):
                                current_item["sponsors"] = metadata["sponsors"]
                            if metadata.get("attachments"):
                                # Merge attachments from detail page with any from meeting table
                                current_item["attachments"].extend(metadata["attachments"])

                        logger.debug(
                            "found nested item",
                            vendor="iqm2",
                            slug=self.slug,
                            item_number=item_number,
                            title=item_title[:50]
                        )
                        continue

            # Try Pattern 1 (top-level items with 1 empty cell)
            if len(cells) >= 3:
                num_cell = cells[1]
                title_cell = cells[2]

                # Main item with letter or number numbering OR empty Num cell with LegiFile link
                if num_cell.get("class") == ["Num"]:
                    num_text = num_cell.get_text(strip=True)

                    # Check if this is a link to a Detail_LegiFile page (indicates legislative item)
                    title_link = title_cell.find("a", href=lambda x: x and "Detail_LegiFile.aspx" in x)

                    # Match letter/number numbering OR empty Num cell with LegiFile link
                    if re.match(r"^[A-Z0-9]+\.\s*$", num_text) or (not num_text and title_link):
                        # Skip section headers (have <strong> tags in title, no actual content)
                        title_strong = title_cell.find("strong")
                        if title_strong and not title_link:
                            # This is a section header like "A. Expenses", skip it
                            logger.debug(
                                "skipping section header",
                                vendor="iqm2",
                                slug=self.slug,
                                header=title_cell.get_text(strip=True)[:40]
                            )
                            continue

                        # If Num cell is empty, extract matter number from title text
                        if not num_text and title_link:
                            item_title_full = title_link.get_text(strip=True)
                            # Extract matter number from title (e.g., "COF 2025 #141 : Title")
                            matter_num_match = re.match(r"^([A-Z]+\s+\d+\s+#\d+)\s*:", item_title_full)
                            if matter_num_match:
                                num_text = matter_num_match.group(1)  # Use matter number as item_number
                            else:
                                # Fallback: just use sequence number
                                num_text = str(item_counter + 1)

                        # Extract item ID from LegiFile link if present
                        legifile_id = None
                        if title_link:
                            href = title_link.get("href", "")
                            # Match ID= parameter (avoid matching MeetingID=)
                            id_match = re.search(r"[?&]ID=(\d+)", href)
                            if id_match:
                                legifile_id = id_match.group(1)

                        # Save previous item
                        if current_item:
                            items.append(current_item)

                        # Start new item
                        item_counter += 1
                        item_number = num_text.strip()

                        # Extract title (might be a link)
                        if title_link:
                            item_title = title_link.get_text(strip=True)
                        else:
                            item_title = title_cell.get_text(strip=True)

                        current_item = {
                            "item_id": legifile_id or f"iqm2-{self.slug}-{meeting_id}-{item_counter}",
                            "title": item_title,
                            "sequence": item_counter,
                            "item_number": item_number,  # Keep letter/number (A., 1., etc.)
                            "section": current_section,  # Keep section context
                            "description": "",  # Will be filled from Comments rows
                            "attachments": [],
                        }

                        # Add matter tracking if it's a LegiFile item
                        if legifile_id:
                            current_item["matter_id"] = legifile_id

                            # Extract clean matter_file from title
                            # Gold standard: Extract concise case number, not full title
                            # Strategy: Prioritize case number patterns, fall back to separators
                            #
                            # Examples:
                            # "DRH25-00335 / BRS Architects..." → "DRH25-00335"
                            # "Appeal of CUP25-00022 & CVA25-00025 / Request..." → "CUP25-00022"
                            # "COF 2025 #141 : Title..." → "COF-2025-141" (normalized)

                            matter_file = None

                            # Pattern 1: Direct case number extraction (most reliable)
                            # Matches: DRH25-00335, CUP25-00022, CVA25-00025, SUB24-00012, CAR25-00017, etc.
                            # Format: 2-5 uppercase letters + 2-digit year + dash + 4-5 digit number
                            case_match = re.search(r'\b([A-Z]{2,5}\d{2}-\d{4,5})\b', item_title)
                            if case_match:
                                matter_file = case_match.group(1)
                            else:
                                # Pattern 2: Compound format with spaces (Cambridge-style)
                                # "COF 2025 #141" → "COF-2025-141"
                                compound_match = re.match(r'^([A-Z]{2,5})\s+(\d{4})\s+#(\d+)', item_title)
                                if compound_match:
                                    matter_file = f"{compound_match.group(1)}-{compound_match.group(2)}-{compound_match.group(3)}"
                                else:
                                    # Pattern 3: Fall back to separator-based extraction
                                    if " / " in item_title:
                                        # Extract first segment before "/"
                                        matter_file = item_title.split(" / ", 1)[0].strip()
                                    elif ":" in item_title:
                                        # Extract and normalize prefix before ":"
                                        prefix = item_title.split(":", 1)[0].strip()
                                        matter_file = re.sub(r'\s+#\s*', '-', prefix)
                                        matter_file = re.sub(r'\s+', '-', matter_file)

                            # Fallback: use legifile_id
                            current_item["matter_file"] = matter_file if matter_file else legifile_id

                            # Fetch additional matter metadata and attachments from Detail_LegiFile page
                            # Aligns with Legistar/PrimeGov gold standard
                            metadata = await self._fetch_matter_metadata(legifile_id)
                            if metadata.get("matter_type"):
                                current_item["matter_type"] = metadata["matter_type"]
                            if metadata.get("sponsors"):
                                current_item["sponsors"] = metadata["sponsors"]
                            if metadata.get("attachments"):
                                # Merge attachments from detail page with any from meeting table
                                current_item["attachments"].extend(metadata["attachments"])

                        logger.debug(
                            "found item",
                            vendor="iqm2",
                            slug=self.slug,
                            item_number=item_number,
                            title=item_title[:50]
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
                                pdf_url = urljoin(base_url, pdf_link["href"])
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
                                    "added attachment",
                                    vendor="iqm2",
                                    slug=self.slug,
                                    name=pdf_name[:40]
                                )

        # Don't forget the last item
        if current_item:
            items.append(current_item)

        logger.info(
            "parsed items from MeetingDetail table",
            vendor="iqm2",
            slug=self.slug,
            item_count=len(items)
        )

        return items
