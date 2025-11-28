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
from urllib.parse import urljoin, urlparse
from json import JSONDecodeError
import re
import asyncio
import xml.etree.ElementTree as ET
from vendors.adapters.base_adapter_async import AsyncBaseAdapter, logger
from vendors.adapters.parsers.legistar_parser import parse_html_agenda, parse_legislation_attachments
from vendors.utils.item_filters import should_skip_procedural_item
from pipeline.utils import combine_date_time
from exceptions import VendorHTTPError, VendorParsingError
import aiohttp


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
        except (VendorHTTPError, aiohttp.ClientError) as e:
            if isinstance(e, VendorHTTPError) and e.status_code in [400, 403, 404]:
                logger.warning(
                    "legistar API failed, falling back to HTML",
                    slug=self.slug,
                    status=e.status_code
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
            "$top": 1000,  # API max
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
            except (JSONDecodeError, ValueError):
                text = await response.text()
                events = self._parse_xml_events(text)

        # Defensive: Validate response is a list (API may return error dict)
        if not isinstance(events, list):
            raise VendorParsingError(
                f"Expected list from Legistar API at {url}, got {type(events).__name__}",
                vendor=self.vendor,
                city_slug=self.slug
            )

        # CRITICAL: Filter client-side because some APIs (Nashville) ignore server filters
        filtered_events = []
        for event in events:
            event_date_str = event.get("EventDate")
            if event_date_str:
                try:
                    event_date = datetime.fromisoformat(event_date_str.replace("Z", "+00:00"))
                    # Only include events within our date range
                    if start_date_dt <= event_date <= end_date_dt:
                        filtered_events.append(event)
                except (ValueError, TypeError):
                    # Include events with unparseable dates (let validation handle them)
                    filtered_events.append(event)
            else:
                filtered_events.append(event)

        logger.info(
            "legistar client-side filtered events",
            slug=self.slug,
            total=len(events),
            filtered=len(filtered_events)
        )

        # Process events
        meetings = []
        for event in filtered_events:
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
            event_name = event.get("EventBodyName", "Unknown Body")
            event_location = event.get("EventLocation")
            event_agenda_status = event.get("EventAgendaStatusName", "")

            if not event_id:
                return None

            # Parse date
            event_date_str = event.get("EventDate")
            event_time_str = event.get("EventTime")

            start_datetime = None
            if event_date_str:
                start_datetime = combine_date_time(event_date_str, event_time_str)

            # Parse meeting status from title and agenda status
            meeting_status = self._parse_meeting_status(event_name, event_agenda_status)

            # Build meeting dictionary
            meeting = {
                "meeting_id": str(event_id),
                "title": event_name,
                "start": start_datetime,
            }

            if event_location:
                meeting["location"] = event_location

            if meeting_status:
                meeting["meeting_status"] = meeting_status

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
                except (AttributeError, IndexError, VendorHTTPError, aiohttp.ClientError):
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

        except (AttributeError, ValueError, TypeError) as e:
            logger.warning("failed to process API event", error=str(e), error_type=type(e).__name__)
            return None

    async def _fetch_event_items_api(self, event_id: int) -> List[Dict[str, Any]]:
        """Fetch agenda items for an event from API with full metadata"""
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

            # Process items concurrently (each may fetch matter metadata/attachments)
            item_tasks = []
            for item_data in event_items:
                item_tasks.append(self._process_api_item(item_data))

            processed_items = await asyncio.gather(*item_tasks, return_exceptions=True)

            # Filter out errors and procedural items
            items = []
            for idx, item in enumerate(processed_items):
                if isinstance(item, Exception):
                    logger.warning("item processing failed", event_id=event_id, item_index=idx, error=str(item))
                elif isinstance(item, dict) and not should_skip_procedural_item(item.get("title", "")):
                    items.append(item)

            return items

        except (VendorHTTPError, aiohttp.ClientError, VendorParsingError) as e:
            logger.warning("failed to fetch event items from API", event_id=event_id, error=str(e))
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

    async def _process_api_item(self, item_data: Dict) -> Optional[Dict[str, Any]]:
        """Process API item into standardized format with full metadata"""
        try:
            item_id = item_data.get("EventItemId")
            if not item_id:
                return None

            # Get matter ID (for deduplication)
            matter_id = item_data.get("EventItemMatterId")
            matter_file = item_data.get("EventItemMatterFile")
            agenda_number = item_data.get("EventItemAgendaNumber")

            # Get title
            title = item_data.get("EventItemTitle") or item_data.get("EventItemMatterName") or "Untitled Item"

            # Get sequence
            sequence = item_data.get("EventItemAgendaSequence")
            if sequence:
                try:
                    sequence = int(sequence)
                except (ValueError, TypeError):
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
            if agenda_number:
                item["agenda_number"] = agenda_number

            # Fetch matter metadata, attachments, and votes concurrently
            # Votes keyed by event_item_id, metadata/attachments by matter_id
            votes_task = asyncio.create_task(self._fetch_event_item_votes_api(int(item_id)))

            if matter_id:
                # Fetch metadata and attachments concurrently
                metadata_task = asyncio.create_task(self._fetch_matter_metadata_async(matter_id))
                attachments_task = asyncio.create_task(self._fetch_matter_attachments_async(matter_id))

                votes, metadata, attachments = await asyncio.gather(
                    votes_task, metadata_task, attachments_task, return_exceptions=True
                )

                # Handle metadata
                if isinstance(metadata, dict):
                    if metadata.get("matter_type"):
                        item["matter_type"] = metadata["matter_type"]
                    if metadata.get("sponsors"):
                        item["sponsors"] = metadata["sponsors"]

                # Handle attachments
                if isinstance(attachments, list) and attachments:
                    item["attachments"] = attachments
            else:
                # No matter_id - still fetch votes
                votes = await votes_task

            # Handle votes (keyed by event_item_id, not matter_id)
            if isinstance(votes, list) and votes:
                item["votes"] = votes

            return item

        except (AttributeError, ValueError, TypeError) as e:
            logger.warning("failed to process API item", error=str(e), error_type=type(e).__name__)
            return None

    async def _fetch_matter_metadata_async(self, matter_id: int) -> Dict[str, Any]:
        """
        Fetch matter metadata (type, sponsors) from API.

        Args:
            matter_id: Legistar matter ID

        Returns:
            Dict with matter_type and sponsors
        """
        metadata = {"matter_type": None, "sponsors": []}

        try:
            # Fetch matter details for type
            matter_url = f"{self.base_url}/matters/{matter_id}"
            params = {"token": self.api_token} if self.api_token else {}
            response = await self._get(matter_url, params=params)

            content_type = response.headers.get('content-type', '').lower()
            if 'json' in content_type:
                matter_data = await response.json()
                if matter_data:
                    metadata["matter_type"] = matter_data.get("MatterTypeName")
            else:
                # XML fallback - NYC returns XML from Legistar API
                text = await response.text()
                matter_data = self._parse_xml_matter(text)
                if matter_data:
                    metadata["matter_type"] = matter_data.get("MatterTypeName")

            # Fetch sponsors
            sponsors_url = f"{self.base_url}/matters/{matter_id}/sponsors"
            response = await self._get(sponsors_url, params=params)

            content_type = response.headers.get('content-type', '').lower()
            if 'json' in content_type:
                sponsors_data = await response.json()
            else:
                # XML fallback - NYC returns XML from Legistar API
                text = await response.text()
                sponsors_data = self._parse_xml_sponsors(text)

            if sponsors_data:
                # Extract sponsor names, sorted by sequence
                metadata["sponsors"] = [
                    s.get("MatterSponsorName")
                    for s in sorted(sponsors_data, key=lambda x: x.get("MatterSponsorSequence", 999))
                    if s.get("MatterSponsorName")
                ]

        except (VendorHTTPError, aiohttp.ClientError, JSONDecodeError, ValueError) as e:
            logger.debug("could not fetch matter metadata", matter_id=matter_id, error=str(e))

        return metadata

    async def _fetch_event_item_votes_api(self, event_item_id: int) -> List[Dict[str, Any]]:
        """
        Fetch votes for a specific event item from API.

        Args:
            event_item_id: Legistar EventItemId

        Returns:
            List of votes: [{'name': str, 'vote': str, 'sequence': int, 'person_id': int}]
        """
        try:
            votes_url = f"{self.base_url}/EventItems/{event_item_id}/Votes"
            params = {"token": self.api_token} if self.api_token else {}

            response = await self._get(votes_url, params=params)

            content_type = response.headers.get('content-type', '').lower()
            if 'json' in content_type:
                raw_votes = await response.json()
            else:
                # XML fallback - NYC returns XML from Legistar API
                text = await response.text()
                raw_votes = self._parse_xml_votes(text)

            votes = []
            for vote in raw_votes:
                name = vote.get("VotePersonName", "").strip()
                vote_value = vote.get("VoteValueName", "").strip()
                person_id = vote.get("VotePersonId")
                sequence = vote.get("VoteSort", 0)

                if not name or not vote_value:
                    continue

                # Normalize vote value to our standard format
                vote_normalized = self._normalize_vote_value(vote_value)

                votes.append({
                    "name": name,
                    "vote": vote_normalized,
                    "sequence": sequence,
                    "person_id": person_id,
                })

            return votes

        except (VendorHTTPError, aiohttp.ClientError, JSONDecodeError, ValueError) as e:
            logger.debug("could not fetch event item votes", event_item_id=event_item_id, error=str(e))
            return []

    def _normalize_vote_value(self, value: str) -> str:
        """Normalize Legistar vote value to standard format"""
        value_lower = value.lower()
        vote_map = {
            "affirmative": "yes",
            "aye": "yes",
            "yea": "yes",
            "yes": "yes",
            "negative": "no",
            "nay": "no",
            "no": "no",
            "absent": "absent",
            "excused": "absent",
            "not present": "absent",
            "abstain": "abstain",
            "abstained": "abstain",
            "present": "present",
            "recused": "recused",
            "recuse": "recused",
            "conflict": "recused",
        }
        return vote_map.get(value_lower, "not_voting")

    async def _fetch_matter_attachments_async(self, matter_id: int) -> List[Dict[str, Any]]:
        """
        Fetch attachments for a specific matter from API.

        Args:
            matter_id: Legistar matter ID

        Returns:
            List of attachments: [{'name': str, 'url': str, 'type': str}]
        """
        try:
            attachments_url = f"{self.base_url}/matters/{matter_id}/attachments"
            params = {"token": self.api_token} if self.api_token else {}

            response = await self._get(attachments_url, params=params)

            # Parse response (JSON or XML)
            content_type = response.headers.get('content-type', '').lower()
            if 'json' in content_type:
                raw_attachments = await response.json()
            else:
                text = await response.text()
                raw_attachments = self._parse_xml_attachments(text)

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
                    file_type = "unknown"

                attachments.append({"name": name, "url": url, "type": file_type})

            return attachments

        except (VendorHTTPError, aiohttp.ClientError, VendorParsingError) as e:
            logger.debug("failed to fetch matter attachments", matter_id=matter_id, error=str(e))
            return []

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
            logger.error("XML parsing error for attachments", error=str(e))
            raise

    def _parse_xml_votes(self, xml_text: str) -> List[Dict[str, Any]]:
        """
        Parse Legistar XML response for event item votes.
        NYC and some other cities return XML instead of JSON from the API.

        Args:
            xml_text: Raw XML response text

        Returns:
            List of vote dictionaries matching JSON structure:
            [{'VotePersonName': str, 'VoteValueName': str, 'VotePersonId': int, 'VoteSort': int}]
        """
        votes = []

        try:
            root = ET.fromstring(xml_text)

            # Handle Legistar namespace
            ns = {'ns': 'http://schemas.datacontract.org/2004/07/LegistarWebAPI.Models.v1'}

            # Find all GranicusEventItemVote elements (may also be EventItemVote)
            vote_elements = root.findall('.//ns:GranicusEventItemVote', ns)
            if not vote_elements:
                vote_elements = root.findall('.//ns:EventItemVote', ns)

            for vote_elem in vote_elements:
                vote = {}

                # Map XML fields to JSON field names
                field_map = {
                    'VotePersonName': 'VotePersonName',
                    'VoteValueName': 'VoteValueName',
                    'VotePersonId': 'VotePersonId',
                    'VoteSort': 'VoteSort',
                }

                for xml_field, json_field in field_map.items():
                    elem = vote_elem.find(f'ns:{xml_field}', ns)
                    if elem is not None and elem.text:
                        # Convert numeric fields
                        if xml_field in ('VotePersonId', 'VoteSort'):
                            try:
                                vote[json_field] = int(elem.text)
                            except ValueError:
                                vote[json_field] = 0
                        else:
                            vote[json_field] = elem.text

                # Only add votes that have person name and vote value
                if vote.get('VotePersonName') and vote.get('VoteValueName'):
                    votes.append(vote)

            logger.debug("parsed xml votes", count=len(votes))
            return votes

        except ET.ParseError as e:
            logger.warning("XML parsing error for votes", error=str(e))
            return []

    def _parse_xml_matter(self, xml_text: str) -> Dict[str, Any]:
        """
        Parse Legistar XML response for single matter details.
        NYC returns XML instead of JSON from the API.

        Args:
            xml_text: Raw XML response text

        Returns:
            Dict with matter fields matching JSON structure
        """
        try:
            root = ET.fromstring(xml_text)

            # Handle Legistar namespace
            ns = {'ns': 'http://schemas.datacontract.org/2004/07/LegistarWebAPI.Models.v1'}

            # Find matter element (may be GranicusMatter or Matter)
            matter_elem = root.find('.//ns:GranicusMatter', ns)
            if matter_elem is None:
                matter_elem = root.find('.//ns:Matter', ns)
            if matter_elem is None:
                return {}

            matter = {}
            field_map = {
                'MatterTypeName': 'MatterTypeName',
                'MatterName': 'MatterName',
                'MatterFile': 'MatterFile',
                'MatterId': 'MatterId',
            }

            for xml_field, json_field in field_map.items():
                elem = matter_elem.find(f'ns:{xml_field}', ns)
                if elem is not None and elem.text:
                    matter[json_field] = elem.text

            return matter

        except ET.ParseError as e:
            logger.warning("XML parsing error for matter", error=str(e))
            return {}

    def _parse_xml_sponsors(self, xml_text: str) -> List[Dict[str, Any]]:
        """
        Parse Legistar XML response for matter sponsors.
        NYC returns XML instead of JSON from the API.

        Args:
            xml_text: Raw XML response text

        Returns:
            List of sponsor dictionaries matching JSON structure
        """
        sponsors = []

        try:
            root = ET.fromstring(xml_text)

            # Handle Legistar namespace
            ns = {'ns': 'http://schemas.datacontract.org/2004/07/LegistarWebAPI.Models.v1'}

            # Find all sponsor elements
            sponsor_elements = root.findall('.//ns:GranicusMatterSponsor', ns)
            if not sponsor_elements:
                sponsor_elements = root.findall('.//ns:MatterSponsor', ns)

            for sponsor_elem in sponsor_elements:
                sponsor = {}

                field_map = {
                    'MatterSponsorName': 'MatterSponsorName',
                    'MatterSponsorSequence': 'MatterSponsorSequence',
                }

                for xml_field, json_field in field_map.items():
                    elem = sponsor_elem.find(f'ns:{xml_field}', ns)
                    if elem is not None and elem.text:
                        if xml_field == 'MatterSponsorSequence':
                            try:
                                sponsor[json_field] = int(elem.text)
                            except ValueError:
                                sponsor[json_field] = 999
                        else:
                            sponsor[json_field] = elem.text

                if sponsor.get('MatterSponsorName'):
                    sponsors.append(sponsor)

            logger.debug("parsed xml sponsors", count=len(sponsors))
            return sponsors

        except ET.ParseError as e:
            logger.warning("XML parsing error for sponsors", error=str(e))
            return []

    async def _fetch_meetings_html(self, days_back: int = 7, days_forward: int = 14) -> List[Dict[str, Any]]:
        """
        Fetch meetings by scraping HTML calendar (fallback when API fails).

        Args:
            days_back: Days to look backward (default 7)
            days_forward: Days to look forward (default 14)

        Returns:
            List of meeting dictionaries with meeting_id, title, start, items
        """
        # Try common Legistar calendar URL patterns
        calendar_urls = [
            f"https://{self.slug}.legistar.com/Calendar.aspx",
            f"https://webapi.legistar.com/{self.slug}/Calendar.aspx",
        ]

        soup = None
        calendar_url = None
        for url in calendar_urls:
            try:
                response = await self._get(url)
                html = await response.text()
                # Parse HTML in thread pool (BeautifulSoup is CPU-bound)
                soup = await asyncio.to_thread(self._parse_html, html)
                calendar_url = url
                logger.info("legistar found HTML calendar", slug=self.slug, url=url)
                break
            except (VendorHTTPError, aiohttp.ClientError, VendorParsingError) as e:
                logger.debug("calendar not found", slug=self.slug, url=url, error=str(e))
                continue

        if not soup or not calendar_url:
            logger.error("could not find HTML calendar at any known URL", slug=self.slug)
            return []

        # Extract base URL for building absolute URLs
        html_base_url = calendar_url.rsplit('/', 1)[0]

        # Date range filter
        today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        start_date = today - timedelta(days=days_back)
        end_date = today + timedelta(days=days_forward)

        # Find meeting rows in RadGrid calendar table
        meeting_rows = soup.find_all("tr", class_=["rgRow", "rgAltRow"])

        if not meeting_rows:
            logger.warning("no meeting rows found in HTML calendar", slug=self.slug)
            return []

        logger.info(
            "legistar found meetings in HTML",
            slug=self.slug,
            count=len(meeting_rows)
        )

        # Process meetings concurrently
        meeting_tasks = []
        for row in meeting_rows:
            meeting_tasks.append(
                self._process_html_meeting_row(row, html_base_url, start_date, end_date)
            )

        processed_meetings = await asyncio.gather(*meeting_tasks, return_exceptions=True)

        # Filter out None and errors
        meetings = []
        for meeting in processed_meetings:
            if isinstance(meeting, dict):
                meetings.append(meeting)

        logger.info("legistar yielded meetings from HTML", slug=self.slug, count=len(meetings))

        return meetings

    async def _process_html_meeting_row(
        self,
        row,
        html_base_url: str,
        start_date: datetime,
        end_date: datetime
    ) -> Optional[Dict[str, Any]]:
        """Process a single HTML meeting row"""
        try:
            cells = row.find_all("td")
            if len(cells) < 6:
                return None

            # Extract meeting detail link
            detail_link = row.find("a", href=lambda x: x and "MeetingDetail.aspx" in x)
            if not detail_link:
                return None

            # Extract full detail URL (includes GUID)
            detail_url = urljoin(html_base_url, detail_link["href"])
            meeting_id_match = re.search(r"ID=(\d+)", detail_url)
            if not meeting_id_match:
                return None

            meeting_id = meeting_id_match.group(1)

            # Skip video clip IDs
            if meeting_id.startswith('clip_'):
                return None

            # Extract title - try multiple strategies
            title = None
            title_link = row.find("a", id=lambda x: x and "hypBody" in x)
            if title_link:
                title = title_link.get_text(strip=True)
            elif cells:
                first_link = cells[0].find("a")
                if first_link:
                    title = first_link.get_text(strip=True)

            if not title:
                title = detail_link.get_text(strip=True)
            if not title or title == "Details":
                title = "Meeting"

            # Skip video clip durations (pattern: "01h 49m")
            if re.match(r'^\d+h\s+\d+m\s*$', title):
                return None

            # Extract date
            meeting_dt = None
            sorted_cell = row.find("td", class_="rgSorted")
            if sorted_cell:
                parsed_date = self._parse_date(sorted_cell.get_text(strip=True))
                if parsed_date:
                    meeting_dt = parsed_date

            if not meeting_dt:
                for cell in cells:
                    cell_text = cell.get_text(strip=True)
                    parsed_date = self._parse_date(cell_text)
                    if parsed_date:
                        meeting_dt = parsed_date
                        break

            if not meeting_dt:
                return None

            # Filter by date range
            if not (start_date <= meeting_dt <= end_date):
                return None

            # Extract agenda PDF from calendar row
            packet_url = None
            agenda_link = row.find("a", href=lambda x: x and "View.ashx" in x and ("M=A" in x or "agenda" in x.lower()))
            if agenda_link:
                packet_url = urljoin(html_base_url, agenda_link["href"])

            # Fetch meeting detail page for items
            meeting_data = await self._fetch_meeting_detail_html_async(
                meeting_id, meeting_dt, title, detail_url, packet_url
            )

            return meeting_data

        except (AttributeError, IndexError, ValueError, TypeError) as e:
            logger.warning("error parsing meeting row", error=str(e))
            return None

    async def _fetch_meeting_detail_html_async(
        self,
        meeting_id: str,
        meeting_dt: datetime,
        title: str,
        detail_url: str,
        calendar_packet_url: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Fetch and parse meeting detail page for agenda items (async).

        Args:
            meeting_id: Meeting ID from calendar
            meeting_dt: Meeting datetime
            title: Meeting title from calendar
            detail_url: Full URL to MeetingDetail.aspx
            calendar_packet_url: Optional packet URL from calendar page

        Returns:
            Meeting dictionary with items array
        """
        items = []
        packet_url = calendar_packet_url

        # Extract base URL from detail_url
        parsed = urlparse(detail_url)
        base_url = f"{parsed.scheme}://{parsed.netloc}"

        # Try to fetch detail page
        try:
            response = await self._get(detail_url)
            html = await response.text()
            soup = await asyncio.to_thread(self._parse_html, html)

            # Parse agenda items from detail page using dedicated parser
            items = await asyncio.to_thread(self._parse_html_agenda_items, soup, meeting_id, base_url)

            # Filter and fetch attachments (only for non-procedural items)
            items_filtered = 0
            substantive_items = []

            for item in items:
                item_title = item.get('title', '')
                item_type = item.get('item_type', '')

                # Skip procedural items
                if should_skip_procedural_item(item_title, item_type):
                    items_filtered += 1
                    continue

                substantive_items.append(item)

            # Fetch attachments for substantive items concurrently
            if substantive_items:
                attachment_tasks = [
                    self._fetch_item_attachments_async(item, base_url)
                    for item in substantive_items
                ]
                attachment_results = await asyncio.gather(*attachment_tasks, return_exceptions=True)

                for item, attachments in zip(substantive_items, attachment_results):
                    if isinstance(attachments, list) and attachments:
                        item['attachments'] = attachments

            items = substantive_items

            # Look for agenda PDF link if not provided from calendar
            if not packet_url:
                agenda_links = soup.find_all("a", href=lambda x: x and ".pdf" in x.lower() if x else False)
                for link in agenda_links:
                    link_text = link.get_text(strip=True).lower()
                    if "agenda" in link_text or "packet" in link_text:
                        packet_url = urljoin(base_url, link["href"])
                        break

        except (VendorHTTPError, aiohttp.ClientError, VendorParsingError) as e:
            logger.debug("detail page unavailable", slug=self.slug, meeting_id=meeting_id, error=str(e))

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
        elif packet_url:
            meeting_data["packet_url"] = packet_url
        else:
            # No items and no packet - skip this meeting
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
        # Convert soup back to HTML string for the parser
        html = str(soup)

        # Use dedicated Legistar HTML parser
        parsed_data = parse_html_agenda(html, meeting_id, base_url)
        items = parsed_data.get('items', [])

        return items

    @staticmethod
    def _parse_html(html: str):
        """
        Parse HTML string to BeautifulSoup object.

        Static method for use with asyncio.to_thread() to avoid blocking.

        Args:
            html: HTML string to parse

        Returns:
            BeautifulSoup object
        """
        from bs4 import BeautifulSoup
        return BeautifulSoup(html, "html.parser")

    def _parse_meeting_status(
        self, title: str, date_str: Optional[str] = None
    ) -> Optional[str]:
        """
        Parse meeting title and date/time for status keywords.

        Common patterns:
        - [CANCELLED] - City Council Meeting
        - (POSTPONED) Regular Meeting
        - City Council - REVISED
        - RESCHEDULED: Planning Commission
        - Date field: "POSTPONED - TBD"

        Args:
            title: Meeting title to parse
            date_str: Optional date/time string to check

        Returns:
            Status string (cancelled, postponed, revised, rescheduled, deferred) or None
        """
        status_keywords = [
            ("CANCEL", "cancelled"),
            ("POSTPONE", "postponed"),
            ("DEFER", "deferred"),
            ("RESCHEDULE", "rescheduled"),
            ("REVISED", "revised"),
            ("AMENDMENT", "revised"),
            ("UPDATED", "revised"),
        ]
        current_status = None

        title_upper = title.upper() if title else ""
        date_upper = date_str.upper() if date_str else ""

        for keyword, status_value in status_keywords:
            if keyword in title_upper or keyword in date_upper:
                current_status = status_value
                break

        return current_status

    async def _fetch_item_attachments_async(
        self, item: Dict[str, Any], base_url: str
    ) -> List[Dict[str, Any]]:
        """
        Fetch attachments for a single item from its LegislationDetail page (async).

        Args:
            item: Item dictionary with legislation_url
            base_url: Base URL for building absolute URLs

        Returns:
            List of attachment dictionaries
        """
        legislation_url = item.get('legislation_url')
        if not legislation_url:
            return []

        try:
            response = await self._get(legislation_url)
            html = await response.text()

            # Parse attachments in thread pool
            attachments = await asyncio.to_thread(
                parse_legislation_attachments, html, base_url
            )

            # Filter to include at most one Leg Ver attachment
            attachments = self._filter_leg_ver_attachments(attachments)

            return attachments

        except (VendorHTTPError, aiohttp.ClientError, VendorParsingError) as e:
            logger.warning("failed to fetch item attachments", slug=self.slug, item_id=item.get('item_id'), error=str(e))
            return []

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
