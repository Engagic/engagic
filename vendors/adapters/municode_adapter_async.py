"""
Async Municode Adapter - API integration for Municode municipal meetings

Cities using Municode: Columbus GA, Tomball TX, Los Gatos CA, Cedar Park TX, and many others
Platform owned by CivicPlus, uses REST API + HTML agenda packets.

URL patterns:
  Subdomain API (columbus-ga, tomball-tx):
    - API base: https://{slug}.municodemeetings.com
    - HTML packet: https://meetings.municode.com/adaHtmlDocument/index?cc={CITY_CODE}&me={GUID}&ip=True
    - PDF packet: https://mccmeetings.blob.core.usgovcloudapi.net/{slug-no-hyphens}-pubu/MEET-Packet-{GUID}.pdf

  PublishPage HTML (CPTX, etc.):
    - Listing: https://meetings.municode.com/PublishPage/index?cid={CODE}&ppid=0&p=-1
    - Uses city code as slug directly (e.g., "CPTX" for Cedar Park TX)
"""

import asyncio
import re
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
from urllib.parse import urljoin

import aiohttp
from bs4 import BeautifulSoup

from config import get_logger
from pipeline.filters import should_skip_item
from pipeline.protocols import MetricsCollector
from vendors.adapters.base_adapter_async import AsyncBaseAdapter
from vendors.adapters.parsers.municode_parser import parse_html_agenda

logger = get_logger(__name__).bind(component="vendor")


class AsyncMunicodeAdapter(AsyncBaseAdapter):
    """Async adapter for cities using Municode platform."""

    # Known city codes as fallback (only used if auto-discovery fails)
    CITY_CODE_FALLBACKS = {
        "columbus-ga": "COLUMGA",  # Truncated: colum + ga
        # Add more as discovered...
    }

    def __init__(self, city_slug: str, city_code: Optional[str] = None, metrics: Optional[MetricsCollector] = None):
        super().__init__(city_slug, vendor="municode", metrics=metrics)

        # Detect if slug is a city code (short, no hyphens, uppercase-ish like "CPTX")
        # vs a subdomain slug (like "columbus-ga")
        self._is_publish_page = self._detect_publish_page_mode(self.slug)

        if self._is_publish_page:
            # PublishPage mode: slug IS the city code
            self.base_url = "https://meetings.municode.com"
            self._city_code_override = self.slug.upper()
        else:
            # Subdomain API mode
            self.base_url = f"https://{self.slug}.municodemeetings.com"
            self._city_code_override = city_code

        self._discovered_city_code: Optional[str] = None

    def _detect_publish_page_mode(self, slug: str) -> bool:
        """Detect if slug is a city code for PublishPage vs subdomain slug.

        City codes: short (2-8 chars), no hyphens, alphanumeric (e.g., CPTX, COLUMGA)
        Subdomain slugs: longer, have hyphens (e.g., columbus-ga, tomball-tx)
        """
        # If it has a hyphen, it's a subdomain slug
        if "-" in slug:
            return False
        # Short alphanumeric strings are likely city codes
        if len(slug) <= 10 and slug.replace("-", "").isalnum():
            return True
        return False

    @property
    def city_code(self) -> str:
        """Get city code (override > discovered > fallback > derived)."""
        if self._city_code_override:
            return self._city_code_override
        if self._discovered_city_code:
            return self._discovered_city_code
        if self.slug in self.CITY_CODE_FALLBACKS:
            return self.CITY_CODE_FALLBACKS[self.slug]
        # Default derivation
        return self.slug.replace('-', '').upper()

    def _extract_city_code_from_url(self, url: str) -> Optional[str]:
        """
        Extract city code from a URL containing cc= parameter or blob path.

        Examples:
            ?cc=COLUMGA&me=... -> COLUMGA
            /columga-meet-{guid}/... -> COLUMGA (uppercased)
        """
        # Try cc= parameter
        cc_match = re.search(r'[?&]cc=([A-Z0-9]+)', url, re.IGNORECASE)
        if cc_match:
            return cc_match.group(1).upper()

        # Try blob storage path pattern: {code}-meet-{guid} or {code}-pubu
        blob_match = re.search(r'/([a-z0-9]+)-(meet|pubu)-', url, re.IGNORECASE)
        if blob_match:
            return blob_match.group(1).upper()

        return None

    def _try_discover_city_code(self, data: Any) -> None:
        """Discover city code from API response URLs containing cc= or blob paths."""
        if self._discovered_city_code:
            return

        # Fields that might contain URLs with city codes
        url_fields = [
            'AgendaLinksHtmlURL', 'AgendaLinksURL', 'PacketLinksHtmlURL',
            'PacketLinksURL', 'MinutesLinksHtmlURL', 'MinutesLinksURL'
        ]

        if isinstance(data, dict):
            for field in url_fields:
                url = data.get(field)
                if url:
                    code = self._extract_city_code_from_url(str(url))
                    if code:
                        self._discovered_city_code = code
                        logger.debug("discovered city code from API", vendor="municode", slug=self.slug, city_code=code, field=field)
                        return

        elif isinstance(data, list):
            # Try first few items
            for item in data[:3]:
                if isinstance(item, dict):
                    self._try_discover_city_code(item)

    def _build_html_packet_url(self, meeting_guid: str) -> str:
        """Build HTML agenda packet URL with full attachments (ip=True)."""
        return f"https://meetings.municode.com/adaHtmlDocument/index?cc={self.city_code}&me={meeting_guid}&ip=True"

    def _build_pdf_packet_url(self, meeting_guid: str) -> str:
        """Build PDF packet URL as fallback."""
        slug_clean = self.slug.replace('-', '')
        return f"https://mccmeetings.blob.core.usgovcloudapi.net/{slug_clean}-pubu/MEET-Packet-{meeting_guid}.pdf"

    def _parse_calendar_date(self, calendar_date: List[int]) -> Optional[datetime]:
        """Parse [year, month, day, hour?, minute?, second?, ms?] to datetime."""
        if not calendar_date or len(calendar_date) < 3:
            return None

        try:
            # Pad with zeros for optional time components
            padded = (calendar_date + [0, 0, 0])[:6]
            return datetime(*padded)
        except (ValueError, TypeError) as e:
            logger.warning("failed to parse CalendarDate", vendor="municode", slug=self.slug, calendar_date=calendar_date, error=str(e))
            return None

    async def _fetch_meetings_impl(self, days_back: int = 7, days_forward: int = 14) -> List[Dict[str, Any]]:
        """Fetch meetings from Municode API or PublishPage HTML."""
        if self._is_publish_page:
            return await self._fetch_publish_page_meetings(days_back, days_forward)

        # Subdomain API mode
        meetings = await self._fetch_meeting_list(days_back, days_forward)

        logger.info("municode meetings retrieved", vendor="municode", slug=self.slug, count=len(meetings))

        # Process meetings concurrently (with limit)
        semaphore = asyncio.Semaphore(5)

        async def process_with_limit(meeting: Dict[str, Any]) -> Optional[Dict[str, Any]]:
            async with semaphore:
                return await self._process_meeting(meeting)

        tasks = [process_with_limit(m) for m in meetings]
        results = await asyncio.gather(*tasks)

        processed = [r for r in results if r is not None]
        logger.info("municode meetings processed", vendor="municode", slug=self.slug, processed=len(processed), total=len(meetings))

        return processed

    async def _fetch_publish_page_meetings(self, days_back: int, days_forward: int) -> List[Dict[str, Any]]:
        """Fetch meetings from PublishPage HTML table (Cedar Park style)."""
        today = datetime.now()
        start_date = today - timedelta(days=days_back)
        end_date = today + timedelta(days=days_forward)

        # PublishPage URL: cid=CITYCODE, ppid=0 for main page, p=-1 for all meetings
        url = f"{self.base_url}/PublishPage/index?cid={self.city_code}&ppid=0&p=-1"

        try:
            response = await self._get(url)
            html = await response.text()
            meetings = await asyncio.to_thread(self._parse_publish_page_html, html)

            # Filter by date range
            filtered = []
            for meeting in meetings:
                meeting_date = meeting.get("_parsed_date")
                if meeting_date:
                    if start_date <= meeting_date <= end_date:
                        filtered.append(meeting)
                else:
                    # Include meetings with unparseable dates
                    filtered.append(meeting)

            logger.info(
                "municode PublishPage meetings fetched",
                vendor="municode",
                slug=self.slug,
                total=len(meetings),
                in_range=len(filtered)
            )

            return filtered

        except (aiohttp.ClientError, asyncio.TimeoutError) as e:
            logger.error("failed to fetch PublishPage", vendor="municode", slug=self.slug, error=str(e))
            return []

    def _parse_publish_page_html(self, html: str) -> List[Dict[str, Any]]:
        """Parse PublishPage HTML table into meeting dicts.

        Table columns: Meeting | Date | Time | Venue | Agenda | Packet | Minutes
        """
        soup = BeautifulSoup(html, "html.parser")
        meetings = []

        # Find the meeting table - look for table with expected headers
        table = soup.find("table")
        if not table:
            logger.warning("no table found in PublishPage", vendor="municode", slug=self.slug)
            return []

        rows = table.find_all("tr")
        if len(rows) < 2:
            return []

        # Skip header row
        for row in rows[1:]:
            cells = row.find_all("td")
            if len(cells) < 5:
                continue

            try:
                meeting_type = cells[0].get_text(strip=True)
                date_str = cells[1].get_text(strip=True)
                time_str = cells[2].get_text(strip=True)
                venue = cells[3].get_text(strip=True)

                # Parse date
                parsed_date = self._parse_publish_page_date(date_str, time_str)

                # Extract PDF links
                agenda_link = cells[4].find("a", href=True) if len(cells) > 4 else None
                packet_link = cells[5].find("a", href=True) if len(cells) > 5 else None
                minutes_link = cells[6].find("a", href=True) if len(cells) > 6 else None

                agenda_url = urljoin(self.base_url, agenda_link["href"]) if agenda_link else None
                packet_url = urljoin(self.base_url, packet_link["href"]) if packet_link else None

                # Build vendor_id from date + meeting type
                vendor_id = f"{date_str.replace('/', '-')}_{meeting_type[:20]}".replace(" ", "_")

                title = f"{meeting_type} - {date_str}" if meeting_type else date_str

                meeting: Dict[str, Any] = {
                    "vendor_id": vendor_id,
                    "title": title,
                    "start": parsed_date.isoformat() if parsed_date else None,
                    "_parsed_date": parsed_date,  # For filtering, removed later
                }

                if agenda_url:
                    meeting["agenda_url"] = agenda_url
                if packet_url:
                    meeting["packet_url"] = packet_url
                if venue:
                    meeting["location"] = venue

                # Check for meeting status in title
                meeting_status = self._parse_meeting_status(meeting_type)
                if meeting_status:
                    meeting["meeting_status"] = meeting_status

                meetings.append(meeting)

            except (IndexError, AttributeError) as e:
                logger.debug("failed to parse PublishPage row", vendor="municode", slug=self.slug, error=str(e))
                continue

        # Remove internal _parsed_date field
        for meeting in meetings:
            meeting.pop("_parsed_date", None)

        return meetings

    def _parse_publish_page_date(self, date_str: str, time_str: str) -> Optional[datetime]:
        """Parse date and time from PublishPage table cells."""
        if not date_str:
            return None

        # Try common date formats: 1/22/2026, 01/22/2026
        date_formats = ["%m/%d/%Y", "%m/%d/%y"]

        for fmt in date_formats:
            try:
                parsed = datetime.strptime(date_str, fmt)

                # Try to add time if available
                if time_str:
                    time_match = re.match(r"(\d{1,2}):(\d{2})\s*(AM|PM)?", time_str, re.I)
                    if time_match:
                        hour = int(time_match.group(1))
                        minute = int(time_match.group(2))
                        ampm = time_match.group(3)
                        if ampm and ampm.upper() == "PM" and hour != 12:
                            hour += 12
                        elif ampm and ampm.upper() == "AM" and hour == 12:
                            hour = 0
                        parsed = parsed.replace(hour=hour, minute=minute)

                return parsed
            except ValueError:
                continue

        return None

    async def _fetch_meeting_list(self, days_back: int, days_forward: int) -> List[Dict[str, Any]]:
        """Fetch meeting list from API with date range."""
        start_date = (datetime.now() - timedelta(days=days_back)).strftime("%Y-%m-%d")
        end_date = (datetime.now() + timedelta(days=days_forward)).strftime("%Y-%m-%d")

        url = f"{self.base_url}/api/v1/public/meeting/list.json"
        params = {"datefrom": start_date, "dateto": end_date}

        try:
            response = await self._get(url, params=params)
            data = await response.json()
            meetings = data.get("Meetings", [])

            # Try to discover city code from API response
            if meetings:
                self._try_discover_city_code(meetings)

            return meetings
        except (aiohttp.ClientError, asyncio.TimeoutError, ValueError) as e:
            logger.error("failed to fetch meeting list", vendor="municode", slug=self.slug, error=str(e))
            return []

    async def _fetch_meeting_details(self, meeting_id: int) -> Optional[Dict[str, Any]]:
        """Fetch meeting details for doc URLs (varies by city)."""
        url = f"{self.base_url}/api/v1/public/meeting/{meeting_id}/details.json"

        try:
            response = await self._get(url)
            return await response.json()
        except (aiohttp.ClientError, asyncio.TimeoutError, ValueError) as e:
            logger.debug("failed to fetch meeting details", vendor="municode", slug=self.slug, meeting_id=meeting_id, error=str(e))
            return None

    def _extract_meeting_guid(self, meeting: Dict[str, Any]) -> Optional[str]:
        """
        Extract meeting GUID for HTML URL construction.

        OriginMeetingID in API response is the GUID used in URLs.
        Format: "7b067cbee37b476bab57c9ccac496c34" (32 hex chars, no hyphens)
        """
        origin_id = meeting.get("OriginMeetingID", "")
        if origin_id:
            # Remove any hyphens (some may have UUID format)
            return origin_id.replace("-", "")
        return None

    async def _process_meeting(self, meeting: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Process a single meeting, fetching HTML agenda if available."""
        meeting_id = meeting.get("MeetingID")
        title = meeting.get("Title", "")
        group_name = meeting.get("GroupName", "")

        # Parse meeting datetime
        calendar_date = meeting.get("CalendarDate", [])
        start_dt = self._parse_calendar_date(calendar_date)
        if not start_dt:
            logger.warning("meeting has no valid date", vendor="municode", slug=self.slug, meeting_id=meeting_id, title=title[:50])
            return None

        # Use group name + title for better meeting title
        full_title = f"{group_name} - {title}" if group_name and title else (group_name or title)

        # Check for meeting status
        meeting_status = self._parse_meeting_status(full_title)

        result: Dict[str, Any] = {
            "vendor_id": str(meeting_id),
            "title": full_title,
            "start": start_dt.isoformat(),
        }

        if meeting_status:
            result["meeting_status"] = meeting_status

        # Get meeting GUID for URL construction
        meeting_guid = self._extract_meeting_guid(meeting)

        if meeting_guid:
            # Build HTML packet URL
            html_url = self._build_html_packet_url(meeting_guid)
            result["agenda_url"] = html_url

            # Fetch and parse HTML agenda
            items_data = await self._fetch_html_agenda_items(html_url)
            if items_data and items_data.get("items"):
                result["items"] = items_data["items"]
                if items_data.get("participation"):
                    result["participation"] = items_data["participation"]

                logger.info("found agenda items", vendor="municode", slug=self.slug, title=full_title[:50], count=len(items_data["items"]))

            # Add PDF fallback URL
            result["packet_url"] = self._build_pdf_packet_url(meeting_guid)
        else:
            logger.debug("meeting has no GUID", vendor="municode", slug=self.slug, meeting_id=meeting_id)

        return result

    async def _fetch_html_agenda_items(self, html_url: str) -> Optional[Dict[str, Any]]:
        """Fetch and parse HTML agenda packet for items and participation."""
        try:
            response = await self._get(html_url)
            html = await response.text()

            # Parse in thread to avoid blocking
            parsed = await asyncio.to_thread(parse_html_agenda, html)

            # Fallback: discover city code from attachment URLs
            if not self._discovered_city_code:
                self._try_discover_city_code_from_items(parsed.get("items", []))

            # Filter procedural items
            items_before = len(parsed.get("items", []))
            parsed["items"] = [
                item for item in parsed.get("items", [])
                if not should_skip_item(
                    item.get("title", ""),
                    item.get("item_type", "")
                )
            ]
            items_filtered = items_before - len(parsed["items"])
            if items_filtered > 0:
                logger.debug("filtered procedural items", vendor="municode", slug=self.slug, count=items_filtered)

            # Count attachments for logging
            total_attachments = sum(
                len(item.get("attachments", []))
                for item in parsed.get("items", [])
            )

            logger.debug(
                "parsed HTML agenda",
                vendor="municode",
                slug=self.slug,
                items=len(parsed["items"]),
                attachments=total_attachments
            )

            return parsed

        except (aiohttp.ClientError, asyncio.TimeoutError, ValueError) as e:
            logger.warning("failed to fetch/parse HTML agenda", vendor="municode", slug=self.slug, url=html_url[:80], error=str(e))
            return None

    def _try_discover_city_code_from_items(self, items: List[Dict[str, Any]]) -> None:
        """Discover city code from attachment URLs in parsed items."""
        for item in items[:3]:
            for att in item.get("attachments", [])[:2]:
                url = att.get("url", "")
                if url and (code := self._extract_city_code_from_url(url)):
                    self._discovered_city_code = code
                    logger.debug("discovered city code from HTML attachment", vendor="municode", slug=self.slug, city_code=code)
                    return


# Confidence: 7/10 - Tested against columbus-ga and tomball-tx HTML samples.
# API response format confirmed through exploration.
# Further city validation recommended before broader rollout.
