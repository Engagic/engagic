"""
Chicago City Council Adapter - REST API integration

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

Processing approach:
- Fetch meetings in date range (7 days back, 14 days forward)
- For each meeting, fetch full detail to get agenda structure
- Extract items from nested groups structure
- For items with matterId, fetch matter attachments
- Return item-level structure (agenda_url + items)

Confidence: 9/10 - Well-documented API, clear structure, proven pattern
"""

import logging
from typing import Dict, Any, List, Iterator, Optional
from datetime import datetime, timedelta
from urllib.parse import urljoin

from vendors.adapters.base_adapter import BaseAdapter

logger = logging.getLogger("engagic")


class ChicagoAdapter(BaseAdapter):
    """Chicago City Council - REST API adapter"""

    def __init__(self, city_slug: str):
        super().__init__(city_slug, "chicago")
        self.base_url = "https://api.chicityclerkelms.chicago.gov"

    def fetch_meetings(self, days_back: int = 7, days_forward: int = 14) -> Iterator[Dict[str, Any]]:
        """
        Fetch meetings in moving window from Chicago's API.

        Args:
            days_back: Days to look backward (default 7, captures recent votes)
            days_forward: Days to look forward (default 14, captures upcoming meetings)

        Yields:
            {
                'meeting_id': str,
                'title': str,
                'start': datetime,
                'location': str,
                'agenda_url': str,  # PDF/file URL (source document)
                'items': [...]      # Extracted agenda items
            }
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
        logger.info(f"[chicago:{self.slug}] Fetching meetings from {api_url}")

        try:
            response = self._get(api_url, params=params)
            response_data = response.json()
        except Exception as e:
            logger.error(f"[chicago:{self.slug}] Failed to fetch meetings: {e}")
            return

        # Extract meetings from response
        meetings = response_data.get("data", [])
        logger.info(f"[chicago:{self.slug}] Retrieved {len(meetings)} meetings")

        for meeting in meetings:
            try:
                # Extract basic meeting data
                meeting_id = meeting.get("meetingId")
                body = meeting.get("body", "")
                date_str = meeting.get("date")
                location = meeting.get("location")

                if not meeting_id or not date_str:
                    logger.warning(f"[chicago:{self.slug}] Meeting missing ID or date, skipping")
                    continue

                # Parse date
                meeting_date = self._parse_iso_date(date_str)
                if not meeting_date:
                    logger.warning(f"[chicago:{self.slug}] Could not parse date: {date_str}")
                    continue

                # Fetch full meeting detail to get agenda structure
                meeting_detail = self._fetch_meeting_detail(meeting_id)
                if not meeting_detail:
                    logger.warning(f"[chicago:{self.slug}] Could not fetch detail for meeting {meeting_id}")
                    continue

                # Extract agenda items from meeting detail
                items = self._extract_agenda_items(meeting_detail)

                # Get agenda file URL (prefer 'Agenda' type, fallback to first file)
                agenda_url = None
                files = meeting_detail.get("files", [])
                for file in files:
                    if file.get("attachmentType") == "Agenda":
                        agenda_url = file.get("path")
                        break
                # Fallback to first file if no Agenda type found
                if not agenda_url and files:
                    agenda_url = files[0].get("path")

                # Build meeting data
                result = {
                    "meeting_id": str(meeting_id),
                    "title": body or "City Council Meeting",
                    "start": meeting_date.isoformat() if meeting_date else None,
                }

                if location:
                    result["location"] = location

                # Architecture: items extracted → agenda_url, no items → packet_url
                if items:
                    if agenda_url:
                        result["agenda_url"] = agenda_url  # Source document
                    result["items"] = items
                    logger.info(
                        f"[chicago:{self.slug}] Meeting {meeting_id} ({body}): "
                        f"extracted {len(items)} items"
                    )
                elif agenda_url:
                    result["packet_url"] = agenda_url  # Fallback for monolithic processing
                    logger.info(
                        f"[chicago:{self.slug}] Meeting {meeting_id} ({body}): "
                        f"no items, using packet URL"
                    )
                else:
                    logger.debug(
                        f"[chicago:{self.slug}] Meeting {meeting_id} ({body}): "
                        f"no items or agenda file, skipping"
                    )
                    continue

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

                yield result

            except Exception as e:
                logger.error(
                    f"[chicago:{self.slug}] Error processing meeting {meeting.get('meetingId')}: {e}"
                )
                continue

    def _fetch_meeting_detail(self, meeting_id: str) -> Optional[Dict[str, Any]]:
        """
        Fetch full meeting detail including agenda structure.

        Args:
            meeting_id: Chicago meeting ID

        Returns:
            Meeting detail dictionary with agenda.groups[].items[] structure
        """
        detail_url = f"{self.base_url}/meeting-agenda/{meeting_id}"
        logger.debug(f"[chicago:{self.slug}] Fetching meeting detail: {detail_url}")

        try:
            response = self._get(detail_url)
            return response.json()
        except Exception as e:
            logger.warning(f"[chicago:{self.slug}] Failed to fetch meeting detail {meeting_id}: {e}")
            return None

    def _extract_agenda_items(self, meeting_detail: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Extract agenda items from meeting detail's nested structure.

        Chicago structure:
        meeting_detail.agenda.groups[] -> array of groups
          group.title -> section name
          group.items[] -> array of items in this section
            item.matterId -> link to matter
            item.matterTitle -> item title
            item.sort -> sequence number
            item.recordNumber -> bill number
            item.actionName -> action taken

        Args:
            meeting_detail: Full meeting detail from API

        Returns:
            List of agenda item dictionaries with structure:
            [{
                'item_id': str,
                'title': str,
                'sequence': int,
                'matter_id': str | None,
                'matter_file': str | None,
                'matter_type': str | None,
                'action_name': str | None,
                'attachments': [{'name': str, 'url': str, 'type': str}]
            }]
        """
        items = []

        # Get agenda structure
        agenda = meeting_detail.get("agenda", {})
        groups = agenda.get("groups", [])

        if not groups:
            logger.debug(f"[chicago:{self.slug}] No agenda groups found in meeting detail")
            return items

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

                # Use matterId or commentId as item_id
                item_id = matter_id or comment_id
                if not item_id:
                    logger.debug(f"[chicago:{self.slug}] Item missing ID, skipping: {title[:60]}")
                    continue

                # Fetch matter attachments if matterId exists
                attachments = []
                if matter_id:
                    attachments = self._fetch_matter_attachments(matter_id)

                item_data = {
                    "item_id": str(item_id),
                    "title": title,
                    "sequence": sequence,
                    "attachments": attachments,
                }

                # Add optional fields
                if matter_id:
                    item_data["matter_id"] = str(matter_id)
                if record_number:
                    item_data["matter_file"] = record_number
                if matter_type:
                    item_data["matter_type"] = matter_type
                if action_name:
                    item_data["action_name"] = action_name
                if group_title:
                    item_data["section"] = group_title

                items.append(item_data)

        logger.debug(f"[chicago:{self.slug}] Extracted {len(items)} items from agenda")
        return items

    def _fetch_matter_attachments(self, matter_id: str) -> List[Dict[str, Any]]:
        """
        Fetch attachments for a specific matter.

        Args:
            matter_id: Chicago matter ID

        Returns:
            List of attachments: [{'name': str, 'url': str, 'type': str}]
        """
        matter_url = f"{self.base_url}/matter/{matter_id}"

        try:
            response = self._get(matter_url)
            matter_data = response.json()
        except Exception as e:
            logger.debug(f"[chicago:{self.slug}] Failed to fetch matter {matter_id}: {e}")
            return []

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

        logger.debug(f"[chicago:{self.slug}] Matter {matter_id}: found {len(attachments)} attachments")
        return attachments

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
            logger.warning(f"[chicago:{self.slug}] Could not parse date '{date_str}': {e}")
            return None


# Confidence: 9/10 - Well-documented API, clear structure, proven pattern from Legistar
# TODO: Test with real Chicago data to verify assumptions
# TODO: Consider adding vote fetching if needed (endpoint available)
# TODO: May need to handle pagination if >500 meetings in range
