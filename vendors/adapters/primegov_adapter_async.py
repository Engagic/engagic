"""
Async PrimeGov Adapter - Concurrent API fetching for PrimeGov municipal calendar

Async version with:
- Concurrent API calls (upcoming + archived in parallel)
- Async HTML agenda parsing
- Same item-level extraction as sync version

Cities using PrimeGov: Palo Alto CA, Mountain View CA, Sunnyvale CA, and many others
"""

from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
from urllib.parse import urlencode
import asyncio
import aiohttp
from vendors.adapters.base_adapter_async import AsyncBaseAdapter, logger
from vendors.adapters.parsers.primegov_parser import parse_html_agenda
from vendors.utils.item_filters import should_skip_procedural_item


class AsyncPrimeGovAdapter(AsyncBaseAdapter):
    """Async adapter for cities using PrimeGov platform"""

    def __init__(self, city_slug: str):
        """
        Initialize async PrimeGov adapter.

        Args:
            city_slug: PrimeGov subdomain (e.g., "cityofpaloalto")
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

    async def _fetch_meetings_impl(self, days_back: int = 7, days_forward: int = 14) -> List[Dict[str, Any]]:
        """
        Fetch meetings from PrimeGov API within date range.

        Fetches upcoming and archived meetings concurrently for better performance.

        Args:
            days_back: Days to look backward (default 7)
            days_forward: Days to look forward (default 14)

        Returns:
            List of meeting dictionaries (validation in base class)
        """
        # Calculate date range
        today = datetime.now()
        start_date = today - timedelta(days=days_back)
        end_date = today + timedelta(days=days_forward)

        # Fetch upcoming and archived meetings concurrently
        upcoming_url = f"{self.base_url}/api/v2/PublicPortal/ListUpcomingMeetings"

        # Concurrent API calls
        upcoming_task = asyncio.create_task(self._fetch_upcoming_meetings(upcoming_url))
        archived_task = asyncio.create_task(self._fetch_archived_meetings(start_date, today))

        upcoming_meetings, archived_meetings = await asyncio.gather(upcoming_task, archived_task)

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
            "primegov meetings retrieved",
            slug=self.slug,
            upcoming=len(upcoming_meetings),
            archived=len(archived_meetings),
            unique=len(unique_meetings)
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
                meeting_date = meeting_date.replace(tzinfo=None)

                # Check if within range
                if start_date <= meeting_date <= end_date:
                    meetings_in_range.append(meeting)
            except (ValueError, AttributeError):
                # If date parsing fails, include it anyway (defensive)
                logger.debug(
                    "failed to parse date, including anyway",
                    slug=self.slug,
                    date_str=date_str
                )
                meetings_in_range.append(meeting)

        logger.info(
            "primegov meetings filtered to date range",
            slug=self.slug,
            count=len(meetings_in_range),
            start_date=start_date.date(),
            end_date=end_date.date()
        )

        # Process meetings concurrently
        meeting_tasks = [self._process_meeting(meeting) for meeting in meetings_in_range]
        processed_meetings = await asyncio.gather(*meeting_tasks)

        # Filter out None values (skipped meetings)
        return [m for m in processed_meetings if m is not None]

    async def _fetch_upcoming_meetings(self, url: str) -> List[Dict[str, Any]]:
        """Fetch upcoming meetings from API"""
        try:
            response = await self._get(url)
            return await response.json()
        except (aiohttp.ClientError, asyncio.TimeoutError) as e:
            logger.error("failed to fetch upcoming meetings", vendor="primegov", slug=self.slug, error=str(e))
            return []
        except ValueError as e:
            logger.error("invalid json from upcoming meetings", vendor="primegov", slug=self.slug, error=str(e))
            return []

    async def _fetch_archived_meetings(self, start_date: datetime, today: datetime) -> List[Dict[str, Any]]:
        """Fetch archived meetings (handles multiple years if needed)"""
        years_to_fetch = set([start_date.year, today.year])
        archived_meetings = []

        # Fetch multiple years concurrently
        tasks = []
        for year in years_to_fetch:
            url = f"{self.base_url}/api/v2/PublicPortal/ListArchivedMeetings?year={year}"
            tasks.append(self._fetch_archived_year(url, year))

        results = await asyncio.gather(*tasks)
        for year_meetings in results:
            archived_meetings.extend(year_meetings)

        return archived_meetings

    async def _fetch_archived_year(self, url: str, year: int) -> List[Dict[str, Any]]:
        """Fetch archived meetings for a single year"""
        try:
            response = await self._get(url)
            return await response.json()
        except (aiohttp.ClientError, asyncio.TimeoutError) as e:
            logger.error("failed to fetch archived meetings", vendor="primegov", slug=self.slug, year=year, error=str(e))
            return []
        except ValueError as e:
            logger.error("invalid json from archived meetings", vendor="primegov", slug=self.slug, year=year, error=str(e))
            return []

    async def _process_meeting(self, meeting: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Process a single meeting (async HTML fetching if needed)"""
        title = meeting.get("title", "")

        # Skip SAP broadcast duplicates
        if " - SAP" in title:
            logger.debug("skipping SAP broadcast", slug=self.slug, title=title)
            return None

        # Find packet document
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
        meeting_status = self._parse_meeting_status(title, date_time)

        # Check meeting state (3 = cancelled/recess)
        meeting_state = meeting.get("meetingState")
        if meeting_state == 3 and not meeting_status:
            meeting_status = "cancelled"

        # Check document names for cancellation
        if not meeting_status:
            for doc in meeting.get("documentList", []):
                doc_name = doc.get("templateName", "").lower()
                if "cancel" in doc_name or "recess" in doc_name:
                    meeting_status = "cancelled"
                    break

        result = {
            "vendor_id": str(meeting["id"]),
            "title": title,
            "start": date_time,
        }

        if packet_doc:
            # HTML Agendas → agenda_url (item-level)
            if "HTML Agenda" in packet_doc.get("templateName", ""):
                query = urlencode({"meetingTemplateId": packet_doc["templateId"]})
                html_url = f"{self.base_url}/Portal/Meeting?{query}"
                result["agenda_url"] = html_url

                # Fetch HTML agenda items (async)
                try:
                    logger.info("fetching HTML agenda", slug=self.slug, url=html_url)
                    items_data = await self.fetch_html_agenda_items_async(html_url)
                    if items_data["items"]:
                        result["items"] = items_data["items"]
                        logger.info(
                            "found agenda items",
                            slug=self.slug,
                            title=title,
                            count=len(items_data["items"])
                        )
                    if items_data["participation"]:
                        result["participation"] = items_data["participation"]
                except (aiohttp.ClientError, asyncio.TimeoutError, ValueError, KeyError) as e:
                    logger.warning(
                        "failed to fetch HTML agenda items",
                        vendor="primegov",
                        slug=self.slug,
                        title=title,
                        error=str(e)
                    )
            else:
                # PDF packet
                result["packet_url"] = self._build_packet_url(packet_doc)
                logger.info(
                    "found PDF packet",
                    slug=self.slug,
                    title=title,
                    packet_url=result["packet_url"]
                )
        else:
            logger.warning(
                "no agenda or packet found",
                slug=self.slug,
                title=title,
                doc_count=len(meeting.get("documentList", []))
            )

        if meeting_status:
            result["meeting_status"] = meeting_status

        return result

    async def fetch_html_agenda_items_async(self, html_url: str) -> Dict[str, Any]:
        """
        Fetch and parse HTML agenda to extract items and participation info (async).

        Args:
            html_url: URL to Portal/Meeting page

        Returns:
            {
                'participation': {...},
                'items': [{'item_id': str, 'title': str, 'sequence': int, 'attachments': [...]}]
            }
        """
        # Fetch HTML (async)
        response = await self._get(html_url)
        html = await response.text()

        # Parse it (sync - BeautifulSoup is CPU-bound, run in thread pool)
        parsed = await asyncio.to_thread(parse_html_agenda, html)

        # Filter procedural items
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
                "filtered procedural items",
                slug=self.slug,
                count=items_filtered
            )

        # Convert relative attachment URLs to absolute
        total_attachments = 0
        for item in parsed['items']:
            for attachment in item.get('attachments', []):
                url = attachment.get('url', '')
                if url.startswith('/'):
                    attachment['url'] = f"{self.base_url}{url}"
                if 'type' not in attachment:
                    attachment['type'] = 'pdf'
                total_attachments += 1

        logger.info(
            "parsed HTML agenda",
            slug=self.slug,
            items=len(parsed['items']),
            attachments=total_attachments
        )

        return parsed

    def _parse_meeting_status(self, title: str, date_str: Optional[str] = None) -> Optional[str]:
        """Parse meeting status from title and datetime"""
        title_lower = title.lower()
        if "cancel" in title_lower or "recess" in title_lower:
            return "cancelled"
        return None

    async def download_attachment_async(self, history_id: str) -> bytes:
        """
        Download attachment PDF via PrimeGov API (async).

        Args:
            history_id: UUID from attachment link

        Returns:
            PDF bytes
        """
        url = f"{self.base_url}/api/compilemeetingattachmenthistory/historyattachment/?historyId={history_id}"

        response = await self._get(url)

        if response.status >= 400:
            raise ValueError(f"Failed to download attachment: HTTP {response.status}")

        return await response.read()
