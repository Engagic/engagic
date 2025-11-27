"""
Async Chicago City Council Adapter - REST API integration

API Base URL: https://api.chicityclerkelms.chicago.gov
API Docs: Swagger 2.0 spec available at /swagger.json

URL patterns:
- Meetings list: /meeting-agenda (with OData filtering)
- Meeting detail: /meeting-agenda/{meetingId}
- Matter details: /matter/{matterId}
- Votes: /meeting-agenda/{meetingId}/matter/{lineId}/votes

API structure (verified Nov 2025):
- OData-style filtering: filter=date gt datetime'2025-01-01T00:00:00Z'
- Pagination: top (max 500), skip
- Sorting: sort=date desc
- Meeting agenda has nested structure: agenda.groups[].items[]
- Items link to matters via matterId
- Matters have attachments array

Async version with:
- aiohttp for async HTTP requests
- Concurrent matter fetches with asyncio.gather
- Non-blocking I/O for faster processing
"""

import asyncio
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta

from vendors.adapters.base_adapter_async import AsyncBaseAdapter, logger
from vendors.utils.item_filters import should_skip_procedural_item


class AsyncChicagoAdapter(AsyncBaseAdapter):
    """Async Chicago City Council - REST API adapter"""

    def __init__(self, city_slug: str):
        super().__init__(city_slug, vendor="chicago")
        self.base_url = "https://api.chicityclerkelms.chicago.gov"

    async def fetch_meetings(self, days_back: int = 7, days_forward: int = 14) -> List[Dict[str, Any]]:
        """
        Fetch meetings in moving window from Chicago's API (async).

        Args:
            days_back: Days to look backward (default 7, captures recent votes)
            days_forward: Days to look forward (default 14, captures upcoming meetings)

        Returns:
            List of meeting dictionaries with meeting_id, title, start, location, items
        """
        # Build date range (7 days back, 14 days forward)
        today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        start_date_dt = today - timedelta(days=days_back)
        end_date_dt = today + timedelta(days=days_forward)

        # Format dates for OData filter
        start_date = start_date_dt.strftime("%Y-%m-%dT%H:%M:%SZ")
        end_date = end_date_dt.strftime("%Y-%m-%dT%H:%M:%SZ")

        # Build OData filter (no datetime wrapper needed per API docs)
        filter_str = f"date ge {start_date} and date lt {end_date}"

        # API parameters
        params = {
            "filter": filter_str,
            "sort": "date desc",
            "top": 500,  # API max
        }

        # Fetch meetings
        api_url = f"{self.base_url}/meeting-agenda"
        logger.info("fetching meetings", slug=self.slug, api_url=api_url)

        try:
            response = await self._get(api_url, params=params)
        except Exception as e:
            logger.error("network error fetching meetings", slug=self.slug, error=str(e))
            return []

        try:
            response_data = await response.json()
        except ValueError as e:
            logger.error("invalid json response", slug=self.slug, error=str(e))
            return []

        # Extract meetings from response
        meetings = response_data.get("data", [])
        logger.info("retrieved meetings", slug=self.slug, count=len(meetings))

        results = []
        for meeting in meetings:
            try:
                result = await self._process_meeting(meeting)
                if result:
                    results.append(result)
            except Exception as e:
                logger.error(
                    "error processing meeting",
                    slug=self.slug,
                    meeting_id=meeting.get('meetingId'),
                    error=str(e)
                )
                continue

        return results

    async def _process_meeting(self, meeting: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Process a single meeting, fetching detail and extracting items.

        Args:
            meeting: Meeting summary from list API

        Returns:
            Processed meeting dictionary or None
        """
        # Extract basic meeting data
        meeting_id = meeting.get("meetingId")
        body = meeting.get("body", "")
        date_str = meeting.get("date")
        location = meeting.get("location")

        if not meeting_id or not date_str:
            logger.warning("meeting missing id or date", slug=self.slug, meeting_id=meeting.get('meetingId'))
            return None

        # Parse date
        meeting_date = self._parse_iso_date(date_str)
        if not meeting_date:
            logger.warning("meeting invalid date", slug=self.slug, meeting_id=meeting_id, date_str=date_str)
            return None

        # Fetch full meeting detail to get agenda structure
        meeting_detail = await self._fetch_meeting_detail(meeting_id)
        if not meeting_detail:
            logger.warning("could not fetch meeting detail", slug=self.slug, meeting_id=meeting_id)
            return None

        # Extract agenda items from meeting detail
        items = await self._extract_agenda_items(meeting_detail)

        # Get agenda file URL (prefer 'Agenda' type, fallback to first file)
        files = meeting_detail.get("files", [])
        agenda_url = next(
            (f.get("path") for f in files if f.get("attachmentType") == "Agenda"),
            files[0].get("path") if files else None
        )

        # Build meeting data
        result = {
            "meeting_id": str(meeting_id),
            "title": body or "City Council Meeting",
            "start": meeting_date.isoformat() if meeting_date else None,
        }

        if location:
            result["location"] = location

        # Architecture: items extracted -> agenda_url, no items -> packet_url
        if items:
            if agenda_url:
                result["agenda_url"] = agenda_url
            result["items"] = items
            logger.info("meeting items extracted", slug=self.slug, meeting_id=meeting_id, item_count=len(items))
        elif agenda_url:
            result["packet_url"] = agenda_url
            logger.info("meeting fallback to packet url", slug=self.slug, meeting_id=meeting_id)
        else:
            logger.debug("meeting no data skipping", slug=self.slug, meeting_id=meeting_id)
            return None

        # Add video/transcript links if available
        video_links = meeting_detail.get("videoLink", [])
        transcript_links = meeting_detail.get("transcriptLink", [])
        if video_links or transcript_links:
            metadata = {}
            if video_links:
                metadata["video_links"] = video_links
            if transcript_links:
                metadata["transcript_links"] = transcript_links
            result["metadata"] = metadata

        return result

    async def _fetch_meeting_detail(self, meeting_id: str) -> Optional[Dict[str, Any]]:
        """
        Fetch full meeting detail including agenda structure (async).

        Args:
            meeting_id: Chicago meeting ID

        Returns:
            Meeting detail dictionary with agenda.groups[].items[] structure
        """
        detail_url = f"{self.base_url}/meeting-agenda/{meeting_id}"
        logger.debug("fetching meeting detail", slug=self.slug, detail_url=detail_url)

        try:
            response = await self._get(detail_url)
        except Exception as e:
            logger.warning("network error fetching meeting detail", slug=self.slug, meeting_id=meeting_id, error=str(e))
            return None

        try:
            return await response.json()
        except ValueError as e:
            logger.warning("invalid json in meeting detail", slug=self.slug, meeting_id=meeting_id, error=str(e))
            return None

    async def _extract_agenda_items(self, meeting_detail: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Extract agenda items from meeting detail's nested structure (async).

        Fetches matter data concurrently for all items with matterId.

        Args:
            meeting_detail: Full meeting detail from API

        Returns:
            List of agenda item dictionaries
        """
        items = []
        items_filtered = 0
        item_counter = 0

        # Get agenda structure
        agenda = meeting_detail.get("agenda", {})
        groups = agenda.get("groups", [])

        if not groups:
            logger.debug("no agenda groups found", slug=self.slug)
            return items

        # Collect items that need matter data
        items_needing_matter = []
        preliminary_items = []

        for group in groups:
            group_title = group.get("title", "")
            group_items = group.get("items", [])

            for item in group_items:
                # Extract item data
                matter_id = item.get("matterId")
                comment_id = item.get("commentId")
                title = item.get("matterTitle", "").strip()
                sequence = int(item.get("sort") or 0)
                record_number = item.get("recordNumber")
                matter_type = item.get("matterType")
                action_name = item.get("actionName")
                display_id = item.get("displayId")

                # Use matterId or commentId as item_id
                item_id = matter_id or comment_id
                if not item_id:
                    logger.debug("item missing id skipping", slug=self.slug, title_prefix=title[:60])
                    continue

                # Skip procedural items (adapter-level filtering)
                if should_skip_procedural_item(title, matter_type or ""):
                    items_filtered += 1
                    logger.debug("skipping procedural item", slug=self.slug, title_prefix=title[:60])
                    continue

                # Increment counter for non-filtered items
                item_counter += 1

                # Fallback: Use manual counter if API's sort field is 0 or missing
                if sequence == 0:
                    sequence = item_counter

                # Fallback: Generate displayId if missing
                if not display_id:
                    display_id = str(item_counter)

                preliminary_items.append({
                    "item_id": str(item_id),
                    "title": title,
                    "sequence": sequence,
                    "matter_id": matter_id,
                    "record_number": record_number,
                    "matter_type": matter_type,
                    "action_name": action_name,
                    "display_id": display_id,
                    "group_title": group_title,
                })

                if matter_id:
                    items_needing_matter.append(matter_id)

        # Fetch matter data concurrently
        matter_data_map = {}
        if items_needing_matter:
            matter_results = await asyncio.gather(
                *[self._fetch_matter_data(mid) for mid in items_needing_matter],
                return_exceptions=True
            )
            for mid, result in zip(items_needing_matter, matter_results):
                if isinstance(result, Exception):
                    logger.debug("matter fetch failed", slug=self.slug, matter_id=mid, error=str(result))
                    matter_data_map[mid] = {"attachments": [], "sponsors": []}
                else:
                    matter_data_map[mid] = result

        # Build final items
        for pitem in preliminary_items:
            matter_id = pitem["matter_id"]
            matter_data = matter_data_map.get(matter_id, {"attachments": [], "sponsors": []}) if matter_id else {"attachments": [], "sponsors": []}

            item_data = {
                "item_id": pitem["item_id"],
                "title": pitem["title"],
                "sequence": pitem["sequence"],
                "attachments": matter_data["attachments"],
            }

            # Add optional fields (following AgendaItem schema)
            if matter_id:
                item_data["matter_id"] = str(matter_id)
            if pitem["record_number"]:
                item_data["matter_file"] = pitem["record_number"]
            if pitem["matter_type"]:
                item_data["matter_type"] = pitem["matter_type"]
            if pitem["display_id"]:
                item_data["agenda_number"] = pitem["display_id"]
            if matter_data["sponsors"]:
                item_data["sponsors"] = matter_data["sponsors"]

            # Chicago-specific metadata (not in schema but useful)
            if pitem["action_name"] or pitem["group_title"]:
                item_data["metadata"] = {}
                if pitem["action_name"]:
                    item_data["metadata"]["action_name"] = pitem["action_name"]
                if pitem["group_title"]:
                    item_data["metadata"]["section"] = pitem["group_title"]

            items.append(item_data)

        if items_filtered > 0:
            logger.info("filtered procedural items", slug=self.slug, filtered_count=items_filtered)

        logger.debug("extracted substantive items", slug=self.slug, item_count=len(items))
        return items

    async def _fetch_matter_data(self, matter_id: str) -> Dict[str, Any]:
        """
        Fetch matter data including attachments and sponsors (async).

        Args:
            matter_id: Chicago matter ID

        Returns:
            Dict with 'attachments' and 'sponsors' keys
        """
        matter_url = f"{self.base_url}/matter/{matter_id}"

        try:
            response = await self._get(matter_url)
        except Exception as e:
            logger.debug("network error fetching matter", slug=self.slug, matter_id=matter_id, error=str(e))
            return {"attachments": [], "sponsors": []}

        try:
            matter_data = await response.json()
        except ValueError as e:
            logger.debug("invalid json in matter", slug=self.slug, matter_id=matter_id, error=str(e))
            return {"attachments": [], "sponsors": []}

        # Extract attachments
        raw_attachments = matter_data.get("attachments", [])
        attachments = []

        for att in raw_attachments:
            file_name = (att.get("fileName") or "").strip()
            path = (att.get("path") or "").strip()
            attachment_type = (att.get("attachmentType") or "").strip()

            if not path:
                continue

            # Determine file type from path
            path_lower = path.lower()
            if path_lower.endswith(".pdf"):
                file_type = "pdf"
            elif path_lower.endswith((".doc", ".docx")):
                file_type = "doc"
            elif path_lower.endswith((".xls", ".xlsx")):
                file_type = "spreadsheet"
            else:
                file_type = "unknown"

            attachments.append({
                "name": file_name or attachment_type or "Attachment",
                "url": path,
                "type": file_type,
            })

        # Extract sponsors
        raw_sponsors = matter_data.get("sponsors", [])
        sponsors = []
        for sponsor in raw_sponsors:
            sponsor_name = sponsor.get("sponsorName")
            if sponsor_name:
                sponsors.append(sponsor_name)

        logger.debug("matter data fetched", slug=self.slug, matter_id=matter_id, attachment_count=len(attachments), sponsor_count=len(sponsors))
        return {"attachments": attachments, "sponsors": sponsors}

    def _parse_iso_date(self, date_str: str) -> Optional[datetime]:
        """
        Parse Chicago's ISO 8601 date format.

        Args:
            date_str: ISO 8601 date string (e.g., "2025-11-20T18:00:00Z")

        Returns:
            datetime object or None if parsing fails
        """
        if not date_str:
            return None

        try:
            # Handle both Z and timezone offsets
            if date_str.endswith("Z"):
                return datetime.fromisoformat(date_str.replace("Z", "+00:00"))
            else:
                return datetime.fromisoformat(date_str)
        except Exception as e:
            logger.warning("could not parse date", slug=self.slug, date_str=date_str, error=str(e))
            return None
