"""
Async CivicClerk Adapter - OData API integration for CivicClerk platform

Cities using CivicClerk: St. Louis MO, Montpelier VT, Burlington VT, and others

Item-level adapter that extracts structured agenda items with:
- Bill/resolution numbers parsed from HTML titles
- Per-item attachments with direct blob URLs
- Hierarchical item flattening (sections -> leaf items)
"""

import asyncio
import re
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime, timedelta

from vendors.adapters.base_adapter_async import AsyncBaseAdapter, logger
from pipeline.protocols import MetricsCollector


class AsyncCivicClerkAdapter(AsyncBaseAdapter):
    """Async adapter for cities using CivicClerk platform"""

    def __init__(self, city_slug: str, metrics: Optional[MetricsCollector] = None):
        """city_slug is the CivicClerk subdomain (e.g., 'stlouismo', 'montpelliervt')"""
        super().__init__(city_slug, vendor="civicclerk", metrics=metrics)
        self.base_url = f"https://{self.slug}.api.civicclerk.com"

    def _build_packet_url(self, doc: Dict[str, Any]) -> str:
        """Build packet URL from document dict containing fileId."""
        file_id = doc.get("fileId")
        return f"{self.base_url}/v1/Meetings/GetMeetingFileStream(fileId={file_id},plainText=false)"

    async def _fetch_meetings_impl(self, days_back: int = 7, days_forward: int = 14) -> List[Dict[str, Any]]:
        """Fetch meetings with item-level extraction via OData API."""
        today = datetime.now()
        start_date = today - timedelta(days=days_back)
        end_date = today + timedelta(days=days_forward)

        # Fetch all events (handles pagination)
        events = await self._fetch_all_events(start_date, end_date)

        logger.info(
            "retrieved events from API",
            vendor="civicclerk",
            slug=self.slug,
            event_count=len(events)
        )

        # Process meetings concurrently to fetch items
        meeting_tasks = []
        for event in events:
            meeting_tasks.append(self._process_event(event))

        processed_meetings = await asyncio.gather(*meeting_tasks, return_exceptions=True)

        # Filter out errors
        results = []
        for idx, meeting in enumerate(processed_meetings):
            if isinstance(meeting, Exception):
                logger.warning(
                    "event processing failed",
                    vendor="civicclerk",
                    slug=self.slug,
                    error=str(meeting),
                    event_index=idx
                )
            elif isinstance(meeting, dict):
                results.append(meeting)

        return results

    async def _fetch_all_events(self, start_date: datetime, end_date: datetime) -> List[Dict[str, Any]]:
        """Fetch all events with OData pagination support."""
        all_events = []

        start_time_str = start_date.strftime("%Y-%m-%dT%H:%M:%S.%fZ")[:-3] + "Z"
        end_time_str = end_date.strftime("%Y-%m-%dT%H:%M:%S.%fZ")[:-3] + "Z"

        params = {
            "$filter": f"startDateTime gt {start_time_str} and startDateTime lt {end_time_str}",
            "$orderby": "startDateTime asc, eventName asc",
        }

        logger.debug(
            "fetching events",
            vendor="civicclerk",
            slug=self.slug,
            start_date=str(start_date.date()),
            end_date=str(end_date.date())
        )

        url = f"{self.base_url}/v1/Events"

        while url:
            response = await self._get(url, params=params if not all_events else None)
            data = await response.json()

            events = data.get("value", [])
            all_events.extend(events)

            # Check for pagination
            next_link = data.get("@odata.nextLink")
            if next_link:
                url = next_link
                params = None  # nextLink includes all params
            else:
                url = None

        return all_events

    async def _process_event(self, event: Dict[str, Any]) -> Dict[str, Any]:
        """Process a single event into a meeting with items."""
        event_id = event.get("id")
        event_name = event.get("eventName", "")
        start_time = event.get("startDateTime", "")
        agenda_id = event.get("agendaId")
        has_agenda = event.get("hasAgenda", False)

        meeting_status = self._parse_meeting_status(event_name, start_time)

        result = {
            "vendor_id": str(event_id),
            "title": event_name,
            "start": start_time,
        }

        if meeting_status:
            result["meeting_status"] = meeting_status

        # Extract location if available
        location = event.get("eventLocation", {})
        if location:
            addr_parts = []
            if location.get("address1"):
                addr_parts.append(location["address1"])
            if location.get("address2"):
                addr_parts.append(location["address2"])
            if location.get("city"):
                addr_parts.append(location["city"])
            if addr_parts:
                result["location"] = ", ".join(addr_parts)

        # Try to fetch structured items if agenda exists
        items = []
        if has_agenda and agenda_id:
            items = await self._fetch_meeting_items(agenda_id)

        if items:
            result["items"] = items
            # Also include agenda URL for reference
            agenda_doc = next(
                (doc for doc in event.get("publishedFiles", [])
                 if doc.get("type") == "Agenda"),
                None
            )
            if agenda_doc:
                result["agenda_url"] = self._build_packet_url(agenda_doc)
        else:
            # Fallback to packet URL (monolithic approach)
            packet = next(
                (doc for doc in event.get("publishedFiles", [])
                 if doc.get("type") in ["Agenda Packet", "Agenda"]),
                None
            )
            if packet:
                result["packet_url"] = self._build_packet_url(packet)
            else:
                file_types = [doc.get("type") for doc in event.get("publishedFiles", [])]
                logger.debug(
                    "no packet for meeting",
                    vendor="civicclerk",
                    slug=self.slug,
                    event_name=event_name,
                    available_files=file_types
                )

        return result

    async def _fetch_meeting_items(self, agenda_id: int) -> List[Dict[str, Any]]:
        """Fetch structured agenda items from /v1/Meetings/{agenda_id}."""
        try:
            url = f"{self.base_url}/v1/Meetings/{agenda_id}"
            # CivicClerk API requires Origin header for CORS
            headers = {
                "Origin": f"https://{self.slug}.portal.civicclerk.com",
                "Referer": f"https://{self.slug}.portal.civicclerk.com/",
            }
            response = await self._get(url, headers=headers)
            data = await response.json()

            raw_items = data.get("items", [])

            # Flatten hierarchy and process items
            items = self._flatten_items(raw_items)

            logger.debug(
                "extracted items from meeting",
                vendor="civicclerk",
                slug=self.slug,
                agenda_id=agenda_id,
                raw_count=len(raw_items),
                processed_count=len(items)
            )

            return items

        except Exception as e:
            logger.warning(
                "failed to fetch meeting items",
                vendor="civicclerk",
                slug=self.slug,
                agenda_id=agenda_id,
                error=str(e)
            )
            return []

    def _flatten_items(self, items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Recursively extract leaf items (isSection=0), skipping section containers."""
        result = []

        for item in items:
            is_section = item.get("isSection", 0)
            child_items = item.get("childItems", [])

            if is_section == 1:
                # Section - recurse into children
                if child_items:
                    result.extend(self._flatten_items(child_items))
            else:
                # Leaf item - process it
                processed = self._process_item(item)
                if processed:
                    result.append(processed)

                # Also process any children (items can have nested items)
                if child_items:
                    result.extend(self._flatten_items(child_items))

        return result

    def _process_item(self, item: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Convert CivicClerk item to our schema."""
        item_id = item.get("id")
        if not item_id:
            return None

        raw_title = item.get("agendaObjectItemName", "")
        if not raw_title:
            return None

        # Strip HTML and clean up title
        title = self._strip_html(raw_title)
        if not title:
            return None

        # Parse bill number and matter type from title
        matter_file, matter_type = self._parse_bill_number(raw_title)

        # Get sequence
        sequence = item.get("sortOrder", 0)
        try:
            sequence = int(sequence)
        except (ValueError, TypeError):
            sequence = 0

        # Process attachments
        attachments = []
        for att in item.get("attachmentsList", []):
            if att.get("isPublished", True) and not att.get("isDeleted", False):
                # Prefer pdfVersionFullPath, fall back to mediaFullPath
                url = att.get("pdfVersionFullPath") or att.get("mediaFullPath")
                name = att.get("fileName", "Attachment")

                if url:
                    # Determine file type
                    url_lower = url.lower()
                    if ".pdf" in url_lower:
                        file_type = "pdf"
                    elif ".doc" in url_lower:
                        file_type = "doc"
                    else:
                        file_type = "unknown"

                    attachments.append({
                        "name": name,
                        "url": url,
                        "type": file_type,
                    })

        result = {
            "vendor_item_id": str(item_id),
            "title": title,
            "sequence": sequence,
        }

        if matter_file:
            result["matter_file"] = matter_file
        if matter_type:
            result["matter_type"] = matter_type
        if attachments:
            result["attachments"] = attachments

        # Include agenda number if available
        agenda_number = item.get("agendaObjectItemNumber")
        if agenda_number:
            result["agenda_number"] = agenda_number

        return result

    def _strip_html(self, text: str) -> str:
        """Remove HTML tags and normalize whitespace."""
        if not text:
            return ""

        # Replace <br>, <br/>, <br /> with space
        text = re.sub(r'<br\s*/?>', ' ', text, flags=re.IGNORECASE)

        # Remove all other HTML tags
        text = re.sub(r'<[^>]+>', '', text)

        # Decode common HTML entities
        text = text.replace("&amp;", "&")
        text = text.replace("&lt;", "<")
        text = text.replace("&gt;", ">")
        text = text.replace("&quot;", '"')
        text = text.replace("&#39;", "'")
        text = text.replace("&nbsp;", " ")

        # Normalize whitespace
        text = re.sub(r'\s+', ' ', text).strip()

        return text

    def _parse_bill_number(self, html_title: str) -> Tuple[Optional[str], Optional[str]]:
        """Parse bill/resolution number from HTML title. Returns (matter_file, matter_type)."""
        # Strip HTML first for cleaner matching
        text = self._strip_html(html_title)

        patterns = [
            # Board Bill Number 107 -> BB107
            (r'Board\s+Bill\s+(?:Number\s+)?(\d+)', 'BB', 'Board Bill'),
            # Resolution Number 123 or Resolution 123 -> RES123
            (r'Resolution\s+(?:Number\s+)?(\d+)', 'RES', 'Resolution'),
            # Ordinance Number 456 or Ordinance No. 70333 -> ORD456
            (r'Ordinance\s+(?:Number\s+|No\.\s*)?(\d+)', 'ORD', 'Ordinance'),
            # BB 107 or BB107 -> BB107
            (r'\bBB\s*(\d+)\b', 'BB', 'Board Bill'),
            # RES 123 or RES123 -> RES123
            (r'\bRES\s*(\d+)\b', 'RES', 'Resolution'),
            # ORD 456 or ORD456 -> ORD456
            (r'\bORD\s*(\d+)\b', 'ORD', 'Ordinance'),
        ]

        for pattern, prefix, matter_type in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                number = match.group(1)
                matter_file = f"{prefix}{number}"
                return matter_file, matter_type

        return None, None
