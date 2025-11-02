"""
Menlo Park City Council Adapter - Custom table-based website

URL patterns:
- Meetings list: https://menlopark.gov/Government/City-Council/Agendas-and-minutes (TODO: verify)
- PDF packet: https://menlopark.gov/files/sharedassets/public/v/1/agendas-and-minutes/...pdf

HTML structure:
- Simple <table> with <tr> rows
- Columns: Date | Agenda packet (PDF) | Minutes | Video
- Date format: "Nov. 4, 2025"
- PDF link: <a href="/files/sharedassets/..." class="document ext-pdf">Agenda packet</a>

Meeting structure (from PDF text):
- Letter-based sections: H. (Presentations), I. (Consent), J. (Public Hearing), K. (Informational)
- Items: H1., I1., J1., K1. format
- Example: "J1. Waive the second reading and adopt an ordinance... (Staff Report #25-167-CC)"

Processing approach:
- Fetch PDF packet only (no HTML agenda)
- Mark as monolithic processing
- Could potentially extract items from PDF text in future enhancement

Confidence: 6/10 - Table parsing straightforward, but no item-level structure without PDF parsing
"""

import logging
from typing import Dict, Any, Iterator
from datetime import datetime
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from vendors.adapters.base_adapter import BaseAdapter

logger = logging.getLogger("engagic")


class MenloParkAdapter(BaseAdapter):
    """Menlo Park City Council - Custom simple table website"""

    def __init__(self, city_slug: str):
        super().__init__(city_slug, "custom_menlopark")
        self.base_url = "https://menlopark.gov"

    def fetch_meetings(self, max_meetings: int = 10) -> Iterator[Dict[str, Any]]:
        """
        Fetch meetings from Menlo Park's table-based website.

        Yields:
            {
                'meeting_id': str,
                'date': datetime,
                'title': str,
                'packet_url': str,  # PDF only, no HTML agenda
                'agenda_url': None,  # Menlo Park doesn't have HTML agendas
            }
        """
        # TODO: Verify actual meetings list URL
        # Possible patterns:
        # - /Government/City-Council/Agendas-and-minutes
        # - /government/city-council/meetings
        # - /city-council/agendas
        meetings_url = f"{self.base_url}/Government/City-Council/Agendas-and-minutes"

        logger.info(f"[MenloPark] Fetching meetings from {meetings_url}")

        try:
            response = self.session.get(meetings_url, timeout=30)
            response.raise_for_status()
        except Exception as e:
            logger.error(f"[MenloPark] Failed to fetch meetings list: {e}")
            return

        soup = BeautifulSoup(response.text, 'html.parser')

        # Find all table rows
        rows = soup.find_all('tr')

        meetings_found = 0
        for row in rows:
            if meetings_found >= max_meetings:
                break

            cells = row.find_all('td')
            if len(cells) < 2:
                continue

            # Cell 0: Date text (e.g., "Nov. 4, 2025")
            date_text = cells[0].get_text(strip=True)
            if not date_text:
                continue

            # Parse date
            meeting_date = self._parse_date(date_text)
            if not meeting_date:
                logger.debug(f"[MenloPark] Could not parse date: {date_text}")
                continue

            # Cell 1: Agenda packet PDF link
            pdf_link = None
            if len(cells) > 1:
                link = cells[1].find('a', href=True, class_='document')
                if link:
                    href = link.get('href', '')
                    pdf_link = urljoin(self.base_url, href)

            # Skip if no PDF packet
            if not pdf_link:
                logger.debug(f"[MenloPark] No PDF packet for {date_text}")
                continue

            # Generate meeting ID from date
            meeting_id = f"menlopark_{meeting_date.strftime('%Y%m%d')}"

            meeting_data = {
                'meeting_id': meeting_id,
                'date': meeting_date,
                'title': "City Council Meeting",  # Menlo Park doesn't include titles in table
                'packet_url': pdf_link,
                'agenda_url': None,  # No HTML agenda available
            }

            logger.info(
                f"[MenloPark] Meeting {meeting_date.strftime('%Y-%m-%d')}: "
                f"PDF packet only (monolithic processing)"
            )

            yield meeting_data
            meetings_found += 1

    def _parse_date(self, date_str: str) -> datetime:
        """
        Parse Menlo Park date formats:
        - "Nov. 4, 2025"
        - "October 21, 2025"
        """
        date_str = date_str.strip()

        # Try full month name format
        for fmt in [
            "%b. %d, %Y",   # "Nov. 4, 2025"
            "%B %d, %Y",    # "November 4, 2025"
            "%b %d, %Y",    # "Nov 4, 2025" (without period)
        ]:
            try:
                return datetime.strptime(date_str, fmt)
            except Exception:
                continue

        return None


# Enhancement opportunity: Parse PDF text to extract items
# Structure in PDF:
# - Sections: H. (Presentations), I. (Consent), J. (Public Hearing), K. (Informational)
# - Items: H1., I1., J1., K1.
# - Pattern: r'^([A-Z]\d+)\.\s+(.+?)(?:\(Staff Report #[\d-]+\))?$'
#
# Could implement _extract_items_from_pdf() in future if:
# 1. High user demand for item-level Menlo Park data
# 2. PDF text extraction proves reliable for this format
# 3. Worth the maintenance burden vs monolithic processing
#
# For now: Monolithic processing is acceptable (42% of cities use this approach)

# Confidence: 6/10
# Table parsing is straightforward from provided HTML.
# Monolithic processing limits value but reduces complexity.
# Could enhance with PDF parsing if needed.
