"""
Async Legistar Adapter - API integration for Legistar platform

Async version with:
- Async HTTP requests (aiohttp)
- Concurrent meeting/item fetching
- Same API-first, HTML-fallback strategy as sync version

Cities using Legistar: Seattle WA, NYC, Cambridge MA, and many others
"""

from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta
import re
import xml.etree.ElementTree as ET
from vendors.adapters.base_adapter_async import AsyncBaseAdapter, logger
from vendors.utils.item_filters import should_skip_procedural_item
from pipeline.utils import combine_date_time


class AsyncLegistarAdapter(AsyncBaseAdapter):
    """Async adapter for cities using Legistar platform"""

    def __init__(self, city_slug: str, api_token: Optional[str] = None):
        """
        Initialize async Legistar adapter.

        Args:
            city_slug: Legistar client name (e.g., "seattle", "nyc")
            api_token: Optional API token (required for some cities like NYC)
        """
        super().__init__(city_slug, vendor="legistar")
        self.api_token = api_token
        self.base_url = f"https://webapi.legistar.com/v1/{self.slug}"

    async def fetch_meetings(self, days_back: int = 7, days_forward: int = 14) -> List[Dict[str, Any]]:
        """
        Fetch meetings in moving window (tries API first, falls back to HTML).

        Args:
            days_back: Days to look backward (default 7, captures recent votes)
            days_forward: Days to look forward (default 14, captures upcoming meetings)

        Returns:
            List of meeting dictionaries with meeting_id, title, start, packet_url
        """
        meetings = []
        try:
            logger.info("legistar using API", slug=self.slug)
            meetings = await self._fetch_meetings_api(days_back, days_forward)
        except Exception as e:
            if hasattr(e, 'status') and e.status in [400, 403, 404]:
                logger.warning(
                    "legistar API failed, falling back to HTML",
                    slug=self.slug,
                    status=e.status
                )
                logger.info("legistar using HTML fallback", slug=self.slug)
                meetings = await self._fetch_meetings_html(days_back, days_forward)
            else:
                raise
            return meetings

        # If API succeeded but returned 0 events, fall back to HTML
        if len(meetings) == 0:
            logger.warning(
                "legistar API returned 0 events, falling back to HTML",
                slug=self.slug
            )
            logger.info("legistar using HTML fallback", slug=self.slug)
            meetings = await self._fetch_meetings_html(days_back, days_forward)
        else:
            logger.info("legistar API success", slug=self.slug, count=len(meetings))

        return meetings

    async def _fetch_meetings_api(self, days_back: int = 7, days_forward: int = 14) -> List[Dict[str, Any]]:
        """
        Fetch meetings in date range from Legistar Web API.

        Args:
            days_back: Days to look backward (default 7)
            days_forward: Days to look forward (default 14)

        Returns:
            List of meeting dictionaries
        """
        # Build date range
        today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        start_date_dt = today - timedelta(days=days_back)
        end_date_dt = today + timedelta(days=days_forward)

        # Format dates for OData filter
        start_date = start_date_dt.strftime("%Y-%m-%d")
        end_date = end_date_dt.strftime("%Y-%m-%d")

        # Build OData filter
        filter_str = (
            f"EventDate ge datetime'{start_date}' and EventDate lt datetime'{end_date}'"
        )

        # API parameters
        params = {
            "$filter": filter_str,
            "$orderby": "EventDate asc",
        }

        # Add API token if provided
        if self.api_token:
            params["token"] = self.api_token

        # Fetch events from API
        url = f"{self.base_url}/Events"
        response = await self._get(url, params=params)

        # Parse response (JSON or XML)
        content_type = response.headers.get('content-type', '').lower()

        if 'json' in content_type:
            events = await response.json()
        elif 'xml' in content_type:
            # Parse XML response
            text = await response.text()
            events = self._parse_xml_events(text)
        else:
            # Try JSON first, then XML
            try:
                events = await response.json()
            except:
                text = await response.text()
                events = self._parse_xml_events(text)

        # Process events
        meetings = []
        for event in events:
            meeting = await self._process_api_event(event)
            if meeting:
                meetings.append(meeting)

        return meetings

    def _parse_xml_events(self, xml_text: str) -> List[Dict]:
        """Parse XML response from Legistar API"""
        root = ET.fromstring(xml_text)

        # Find all entry elements (Atom feed format)
        ns = {'atom': 'http://www.w3.org/2005/Atom', 'd': 'http://schemas.microsoft.com/ado/2007/08/dataservices', 'm': 'http://schemas.microsoft.com/ado/2007/08/dataservices/metadata'}

        events = []
        for entry in root.findall('.//atom:entry', ns):
            content = entry.find('.//m:properties', ns)
            if content is not None:
                event = {}
                for prop in content:
                    # Remove namespace from tag
                    tag = prop.tag.split('}')[1] if '}' in prop.tag else prop.tag
                    event[tag] = prop.text
                events.append(event)

        return events

    async def _process_api_event(self, event: Dict) -> Optional[Dict[str, Any]]:
        """Process a single API event into meeting dictionary"""
        try:
            event_id = event.get("EventId")
            event_guid = event.get("EventGuid")

            if not event_id:
                return None

            # Parse date
            event_date_str = event.get("EventDate")
            event_time_str = event.get("EventTime")

            start_datetime = None
            if event_date_str:
                start_datetime = combine_date_time(event_date_str, event_time_str)

            # Build meeting dictionary
            meeting = {
                "meeting_id": str(event_id),
                "title": event.get("EventBodyName", "Unknown Body"),
                "start": start_datetime,
            }

            # Fetch agenda items for this event (concurrent with packet URL discovery)
            import asyncio
            items_task = asyncio.create_task(self._fetch_event_items_api(event_id))

            # Try to get agenda PDF URL from API
            agenda_url = event.get("EventAgendaFile")
            packet_url = event.get("EventMinutesFile")  # Sometimes agenda is in minutes field

            # If API didn't provide URLs, try to discover from HTML detail page
            if not agenda_url and event_guid:
                html_url = f"https://{self.slug}.legistar.com/MeetingDetail.aspx?GUID={event_guid}"
                try:
                    response = await self._get(html_url)
                    html = await response.text()

                    # Find agenda PDF link
                    if "Agenda.pdf" in html or "agenda.pdf" in html:
                        agenda_match = re.search(r'href="([^"]*Agenda\.pdf[^"]*)"', html, re.IGNORECASE)
                        if agenda_match:
                            agenda_url = f"https://{self.slug}.legistar.com/{agenda_match.group(1)}"
                except:
                    pass

            # Wait for items to finish fetching
            items = await items_task

            if items:
                meeting["items"] = items
                if agenda_url:
                    meeting["agenda_url"] = agenda_url
            elif agenda_url or packet_url:
                # Monolithic fallback
                meeting["packet_url"] = agenda_url or packet_url

            return meeting

        except Exception as e:
            logger.warning("failed to process API event", error=str(e), error_type=type(e).__name__)
            return None

    async def _fetch_event_items_api(self, event_id: int) -> List[Dict[str, Any]]:
        """Fetch agenda items for an event from API"""
        try:
            url = f"{self.base_url}/Events/{event_id}/EventItems"
            params = {}
            if self.api_token:
                params["token"] = self.api_token

            response = await self._get(url, params=params)

            # Parse response
            content_type = response.headers.get('content-type', '').lower()
            if 'json' in content_type:
                event_items = await response.json()
            else:
                text = await response.text()
                event_items = self._parse_xml_event_items(text)

            items = []
            for item_data in event_items:
                item = self._process_api_item(item_data)
                if item and not should_skip_procedural_item(item.get("title", "")):
                    items.append(item)

            return items

        except Exception as e:
            logger.debug("failed to fetch event items from API", event_id=event_id, error=str(e))
            return []

    def _parse_xml_event_items(self, xml_text: str) -> List[Dict]:
        """Parse XML event items response"""
        root = ET.fromstring(xml_text)
        ns = {'atom': 'http://www.w3.org/2005/Atom', 'd': 'http://schemas.microsoft.com/ado/2007/08/dataservices', 'm': 'http://schemas.microsoft.com/ado/2007/08/dataservices/metadata'}

        items = []
        for entry in root.findall('.//atom:entry', ns):
            content = entry.find('.//m:properties', ns)
            if content is not None:
                item = {}
                for prop in content:
                    tag = prop.tag.split('}')[1] if '}' in prop.tag else prop.tag
                    item[tag] = prop.text
                items.append(item)

        return items

    def _process_api_item(self, item_data: Dict) -> Optional[Dict[str, Any]]:
        """Process API item into standardized format"""
        try:
            item_id = item_data.get("EventItemId")
            if not item_id:
                return None

            # Get matter ID (for deduplication)
            matter_id = item_data.get("EventItemMatterId")
            matter_file = item_data.get("EventItemMatterFile")

            # Get title
            title = item_data.get("EventItemTitle") or item_data.get("EventItemMatterName") or "Untitled Item"

            # Get sequence
            sequence = item_data.get("EventItemAgendaSequence")
            if sequence:
                try:
                    sequence = int(sequence)
                except:
                    sequence = 0
            else:
                sequence = 0

            # Build item dictionary
            item = {
                "item_id": str(item_id),
                "title": title,
                "sequence": sequence,
            }

            if matter_id:
                item["matter_id"] = str(matter_id)
            if matter_file:
                item["matter_file"] = matter_file

            # Get attachments (if available in API response)
            # Note: Legistar API often requires separate call for attachments
            attachments = []

            # Check for direct attachment link in item data
            attachment_url = item_data.get("EventItemMatterAttachmentHyperlink")
            if attachment_url:
                attachments.append({
                    "url": attachment_url,
                    "name": f"{matter_file or item_id} Attachment",
                    "type": "pdf"
                })

            if attachments:
                item["attachments"] = attachments

            return item

        except Exception as e:
            logger.warning("failed to process API item", error=str(e))
            return None

    async def _fetch_meetings_html(self, days_back: int = 7, days_forward: int = 14) -> List[Dict[str, Any]]:
        """
        Fetch meetings from HTML calendar (fallback when API fails).

        Returns:
            List of meeting dictionaries
        """
        meetings = []

        # Legistar HTML calendar URL
        calendar_url = f"https://{self.slug}.legistar.com/Calendar.aspx"

        try:
            response = await self._get(calendar_url)
            html = await response.text()

            # Parse HTML (simplified - would need full HTML parsing logic here)
            # For now, return empty list (full HTML parsing would be ~200 lines)
            logger.warning(
                "HTML fallback not fully implemented yet",
                slug=self.slug
            )

        except Exception as e:
            logger.error("HTML fetch failed", slug=self.slug, error=str(e))

        return meetings
