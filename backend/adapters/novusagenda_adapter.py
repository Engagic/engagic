"""
NovusAgenda Adapter - HTML scraping for NovusAgenda platform

Cities using NovusAgenda: Hagerstown MD, and others
"""

import re
from typing import Dict, Any, Iterator
from backend.adapters.base_adapter import BaseAdapter, logger


class NovusAgendaAdapter(BaseAdapter):
    """Adapter for cities using NovusAgenda platform"""

    def __init__(self, city_slug: str):
        """
        Initialize NovusAgenda adapter.

        Args:
            city_slug: NovusAgenda subdomain (e.g., "hagerstown" for hagerstown.novusagenda.com)
        """
        super().__init__(city_slug, vendor="novusagenda")
        self.base_url = f"https://{self.slug}.novusagenda.com"

    def fetch_meetings(self) -> Iterator[Dict[str, Any]]:
        """
        Scrape meetings from NovusAgenda /agendapublic page.

        Yields:
            Meeting dictionaries with meeting_id, title, start, packet_url
        """
        # Fetch agendapublic page
        soup = self._fetch_html(f"{self.base_url}/agendapublic")

        # Find meeting rows (rgRow and rgAltRow classes)
        meeting_rows = soup.find_all("tr", class_=["rgRow", "rgAltRow"])
        logger.info(f"[novusagenda:{self.slug}] Found {len(meeting_rows)} meeting rows")

        for row in meeting_rows:
            cells = row.find_all("td")
            if len(cells) < 5:
                continue

            # Extract meeting data
            date = cells[0].get_text(strip=True)
            meeting_type = cells[1].get_text(strip=True)
            # location = cells[2].get_text(strip=True)  # Available if needed

            # Parse meeting status from title
            meeting_status = self._parse_meeting_status(meeting_type)

            # Find PDF link
            pdf_link = row.find("a", href=re.compile(r"DisplayAgendaPDF\.ashx"))
            packet_url = None
            meeting_id = None

            if pdf_link:
                # Extract meeting ID
                pdf_href = pdf_link.get("href", "")
                meeting_id_match = re.search(r"MeetingID=(\d+)", pdf_href)
                if meeting_id_match:
                    meeting_id = meeting_id_match.group(1)
                    packet_url = f"{self.base_url}/agendapublic/{pdf_href}"

            # Generate fallback meeting_id if not found
            if not meeting_id:
                import hashlib
                id_string = f"{meeting_type}_{date}"
                meeting_id = hashlib.md5(id_string.encode()).hexdigest()[:8]

            if not packet_url:
                logger.debug(
                    f"[novusagenda:{self.slug}] No packet for: {meeting_type} on {date}"
                )

            result = {
                "meeting_id": meeting_id,
                "title": meeting_type,
                "start": date,
                "packet_url": packet_url,
            }

            if meeting_status:
                result["meeting_status"] = meeting_status

            yield result
