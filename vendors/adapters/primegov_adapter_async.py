"""
Async PrimeGov Adapter - API integration for PrimeGov municipal calendar

Cities using PrimeGov: Palo Alto CA, Mountain View CA, Sunnyvale CA, and many others
"""

from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
from urllib.parse import urlencode
import asyncio
import aiohttp
from vendors.adapters.base_adapter_async import AsyncBaseAdapter, logger
from vendors.adapters.parsers.primegov_parser import parse_html_agenda
from pipeline.filters import should_skip_item
from pipeline.protocols import MetricsCollector


# Priority order for agenda types: regular > continuation > special
AGENDA_TYPES = [
    ("HTML Agenda", "agenda"),
    ("HTML Continuation Agenda", "continuation"),
    ("HTML Special Agenda", "special"),
]


class AsyncPrimeGovAdapter(AsyncBaseAdapter):
    """Async adapter for cities using PrimeGov platform."""

    def __init__(self, city_slug: str, metrics: Optional[MetricsCollector] = None):
        super().__init__(city_slug, vendor="primegov", metrics=metrics)
        self.base_url = f"https://{self.slug}.primegov.com"

    def _build_packet_url(self, doc: Dict[str, Any]) -> str:
        """Build compiled packet URL from document metadata."""
        query = urlencode(
            {
                "meetingTemplateId": doc["templateId"],
                "compileOutputType": doc["compileOutputType"],
            }
        )
        return f"{self.base_url}/Public/CompiledDocument?{query}"

    def _find_agenda_docs(self, document_list: List[Dict[str, Any]]) -> List[tuple]:
        """Find all HTML agenda documents in priority order (regular > continuation > special)."""
        found = []
        for template_name, agenda_type in AGENDA_TYPES:
            for doc in document_list:
                if doc.get("templateName") == template_name:
                    found.append((doc, agenda_type))
                    break
        return found

    async def _fetch_meetings_impl(self, days_back: int = 7, days_forward: int = 14) -> List[Dict[str, Any]]:
        """Fetch meetings from PrimeGov API (upcoming + archived concurrently)."""
        today = datetime.now()
        start_date = today - timedelta(days=days_back)
        end_date = today + timedelta(days=days_forward)

        upcoming_url = f"{self.base_url}/api/v2/PublicPortal/ListUpcomingMeetings"
        upcoming_task = asyncio.create_task(self._fetch_upcoming_meetings(upcoming_url))
        archived_task = asyncio.create_task(self._fetch_archived_meetings(start_date, today))

        upcoming_meetings, archived_meetings = await asyncio.gather(upcoming_task, archived_task)

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

        meetings_in_range = []
        for meeting in unique_meetings:
            date_str = meeting.get("dateTime", "")
            if not date_str:
                continue

            try:
                meeting_date = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
                meeting_date = meeting_date.replace(tzinfo=None)
                if start_date <= meeting_date <= end_date:
                    meetings_in_range.append(meeting)
            except (ValueError, AttributeError):
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

        meeting_tasks = [self._process_meeting(meeting) for meeting in meetings_in_range]
        processed_meetings = await asyncio.gather(*meeting_tasks)

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
        """Fetch archived meetings for relevant years."""
        years_to_fetch = set([start_date.year, today.year])
        archived_meetings = []
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
        """Process a single meeting, fetching all agenda types in parallel."""
        title = meeting.get("title", "")
        if " - SAP" in title:
            return None

        date_time = meeting.get("dateTime", "")
        meeting_status = self._parse_meeting_status(title, date_time)

        # Note: meetingState values appear to be:
        # 1 = scheduled, 2 = in progress, 3 = completed/archived
        # Do NOT treat meetingState == 3 as cancelled (it just means past/completed)

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

        agenda_docs = self._find_agenda_docs(meeting.get("documentList", []))

        if not agenda_docs:
            if meeting_status:
                result["meeting_status"] = meeting_status
            return result

        # Build agenda_sources and fetch tasks in single pass
        label_map = {"agenda": "Agenda", "continuation": "Continuation", "special": "Special"}
        agenda_sources = []
        fetch_tasks = []
        for doc, agenda_type in agenda_docs:
            url = f"{self.base_url}/Portal/Meeting?{urlencode({'meetingTemplateId': doc['templateId']})}"
            agenda_sources.append({"type": agenda_type, "url": url, "label": label_map[agenda_type]})
            fetch_tasks.append(self._fetch_agenda_with_type(url, agenda_type, title))

        result["agenda_url"] = agenda_sources[0]["url"]
        result["agenda_sources"] = agenda_sources

        if len(agenda_docs) > 1:
            logger.info(
                "fetching multiple agendas",
                slug=self.slug,
                title=title,
                agenda_types=[t for _, t in agenda_docs]
            )

        results = await asyncio.gather(*fetch_tasks, return_exceptions=True)

        # Merge items in priority order, deduplicate by vendor_item_id
        seen_ids = set()
        merged_items = []
        participation = {}

        for items_data in results:
            if isinstance(items_data, Exception):
                continue
            if items_data.get("participation") and not participation:
                participation = items_data["participation"]
            for item in items_data.get("items", []):
                item_id = item.get("vendor_item_id")
                if item_id and item_id not in seen_ids:
                    seen_ids.add(item_id)
                    merged_items.append(item)

        if merged_items:
            result["items"] = merged_items
            logger.info(
                "merged agenda items",
                slug=self.slug,
                title=title,
                count=len(merged_items),
                sources=len([r for r in results if not isinstance(r, Exception)])
            )
        if participation:
            result["participation"] = participation
        if meeting_status:
            result["meeting_status"] = meeting_status

        return result

    async def _fetch_agenda_with_type(
        self, url: str, agenda_type: str, title: str
    ) -> Dict[str, Any]:
        """Fetch and parse a single agenda, with error handling."""
        try:
            return await self.fetch_html_agenda_items_async(url)
        except (aiohttp.ClientError, asyncio.TimeoutError, ValueError, KeyError) as e:
            logger.warning(
                "failed to fetch agenda",
                vendor="primegov",
                slug=self.slug,
                title=title,
                agenda_type=agenda_type,
                error=str(e)
            )
            return {"items": [], "participation": {}}

    async def fetch_html_agenda_items_async(self, html_url: str) -> Dict[str, Any]:
        """Fetch and parse HTML agenda for items and participation info."""
        response = await self._get(html_url)
        html = await response.text()
        parsed = await asyncio.to_thread(parse_html_agenda, html)

        items_before = len(parsed['items'])
        parsed['items'] = [
            item for item in parsed['items']
            if not should_skip_item(
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
        """Parse meeting status from title and datetime. Extends parent with recess handling."""
        # Use parent's comprehensive status detection first
        status = super()._parse_meeting_status(title, date_str)
        if status:
            return status

        # PrimeGov-specific: "recess" also means cancelled
        if title and "recess" in title.lower():
            return "cancelled"

        return None

    async def download_attachment_async(self, history_id: str) -> bytes:
        """Download attachment PDF via PrimeGov API."""
        url = f"{self.base_url}/api/compilemeetingattachmenthistory/historyattachment/?historyId={history_id}"

        response = await self._get(url)

        if response.status >= 400:
            raise ValueError(f"Failed to download attachment: HTTP {response.status}")

        return await response.read()
