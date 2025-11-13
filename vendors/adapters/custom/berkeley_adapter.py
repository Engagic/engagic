"""
Berkeley City Council Adapter - Custom Drupal CMS

URL patterns:
- Meetings list: https://berkeleyca.gov/your-government/city-council/city-council-agendas
- HTML agenda: https://berkeleyca.gov/city-council-regular-meeting-eagenda-november-10-2025
- PDF packet: https://berkeleyca.gov/sites/default/files/city-council-meetings/2025-11-10%20Agenda%20Packet...pdf

HTML structure (verified Nov 2025):
- Drupal views table with 7 columns: Meeting | Date | Agenda | Agenda Packet | Annotated | Video | Download
- Date in cell 1 with <time> tag
- HTML agenda link in cell 2
- PDF packet link in cell 3
- Agenda items: <strong>1.</strong><a href="...pdf">Title</a> format
- Item metadata: From, Recommendation, Financial Implications, Contact
- Participation: Zoom, phone, email in intro paragraph

Confidence: 9/10 - Verified working with item-level extraction
"""

import logging
import re
from typing import Dict, Any, List, Iterator, Optional
from datetime import datetime, timedelta
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from vendors.adapters.base_adapter import BaseAdapter

logger = logging.getLogger("engagic")


class BerkeleyAdapter(BaseAdapter):
    """Berkeley City Council - Custom Drupal CMS adapter"""

    def __init__(self, city_slug: str):
        super().__init__(city_slug, "berkeley")
        self.base_url = "https://berkeleyca.gov"

    def fetch_meetings(self, max_meetings: int = 10) -> Iterator[Dict[str, Any]]:
        """
        Fetch meetings from Berkeley's Drupal-based website.

        Args:
            max_meetings: Maximum number of meetings to fetch (default 10)

        Yields:
            {
                'meeting_id': str,
                'date': datetime,
                'time': str,
                'title': str,
                'agenda_url': str,     # HTML agenda (preferred)
                'packet_url': str,     # PDF packet (fallback)
                'participation': {...},
                'items': [...]
            }
        """
        # Date range: today to 2 weeks from now
        today = datetime.now().date()
        two_weeks_from_now = today + timedelta(days=14)

        meetings_url = f"{self.base_url}/your-government/city-council/city-council-agendas"

        logger.info(f"[berkeley:{self.slug}] Fetching meetings from {meetings_url}")

        try:
            response = self.session.get(meetings_url, timeout=30)
            response.raise_for_status()
        except Exception as e:
            logger.error(f"[berkeley:{self.slug}] Failed to fetch meetings list: {e}")
            return

        soup = BeautifulSoup(response.text, 'html.parser')

        # Find table rows with meeting data
        # Structure: <tr> with <td> for date, agenda link, minutes, video
        rows = soup.find_all('tr')

        meetings_found = 0
        for row in rows:
            if meetings_found >= max_meetings:
                break

            cells = row.find_all('td')
            if len(cells) < 2:
                continue

            # New structure (as of Nov 2025):
            # Cell 0: Meeting name/title
            # Cell 1: Date (with <time> tag)
            # Cell 2: Agenda (HTML link)
            # Cell 3: Agenda Packet (PDF link)
            # Cell 4: Annotated Agenda
            # Cell 5: Video
            # Cell 6: Download

            if len(cells) < 4:  # Need at least title, date, and agenda columns
                continue

            # Cell 1: Date (with <time> tag)
            time_tag = cells[1].find('time')
            if not time_tag:
                # Try parsing raw text
                date_text = cells[1].get_text(strip=True)
            else:
                date_text = time_tag.get('datetime') or time_tag.get_text(strip=True)

            if not date_text:
                continue

            # Parse date
            meeting_date = self._parse_date(date_text)
            if not meeting_date:
                logger.debug(f"[berkeley:{self.slug}] Could not parse date: {date_text}")
                continue

            # Filter to meetings from date range (calculated at method start)
            meeting_date_only = meeting_date.date()

            if meeting_date_only < today or meeting_date_only > two_weeks_from_now:
                logger.debug(f"[berkeley:{self.slug}] Skipping meeting {date_text} - outside 2-week window")
                continue

            # Cell 2: HTML Agenda link (Berkeley always has HTML agendas)
            html_link = None
            html_cell = cells[2]
            html_a = html_cell.find('a', href=True)
            if html_a:
                html_link = urljoin(self.base_url, html_a.get('href', ''))

            # Skip if no HTML agenda (Berkeley should always have one)
            if not html_link:
                logger.debug(f"[berkeley:{self.slug}] No HTML agenda link for {date_text}")
                continue

            # Generate meeting ID from date
            meeting_id = f"berkeley_{meeting_date.strftime('%Y%m%d')}"

            # Extract time from date string (e.g., "11/10/2025 - 6:00 pm")
            time_match = re.search(r'(\d{1,2}:\d{2}\s*[ap]m)', date_text, re.IGNORECASE)
            meeting_time = time_match.group(1) if time_match else None

            meeting_data = {
                'meeting_id': meeting_id,
                'date': meeting_date,
                'time': meeting_time,
                'title': "City Council Meeting",  # Berkeley doesn't include titles in table
                'agenda_url': html_link,
            }

            # Fetch HTML agenda detail to extract items (Berkeley always has HTML agendas)
            try:
                logger.info(f"[berkeley:{self.slug}] GET {html_link}")
                detail = self._fetch_meeting_detail(html_link)
                if detail:
                    if detail.get('participation'):
                        meeting_data['participation'] = detail['participation']
                    if detail.get('items'):
                        meeting_data['items'] = detail['items']
                        logger.info(f"[berkeley:{self.slug}] Extracted {len(detail['items'])} items from HTML agenda")
                    if detail.get('title'):
                        meeting_data['title'] = detail['title']
            except Exception as e:
                logger.warning(f"[berkeley:{self.slug}] Failed to fetch detail for {meeting_id}: {e}")
                # Continue anyway - we have basic meeting data even without items

            item_count = len(meeting_data.get('items', []))
            attachment_count = sum(len(item.get('attachments', [])) for item in meeting_data.get('items', []))
            logger.info(
                f"[berkeley:{self.slug}] Found {item_count} items, {attachment_count} attachments for "
                f"{meeting_date.strftime('%Y-%m-%d')}"
            )

            yield meeting_data
            meetings_found += 1

    def _fetch_meeting_detail(self, agenda_url: str) -> Dict[str, Any]:
        """
        Fetch and parse HTML agenda detail page.

        Args:
            agenda_url: URL to HTML agenda page

        Returns:
            {
                'title': str,
                'participation': {...},
                'items': [...]
            }
        """
        logger.debug(f"[berkeley:{self.slug}] Fetching detail: {agenda_url}")

        response = self.session.get(agenda_url, timeout=30)
        response.raise_for_status()

        soup = BeautifulSoup(response.text, 'html.parser')

        # Extract title from header
        title = None
        title_tag = soup.find('strong', string=re.compile(r'BERKELEY CITY COUNCIL', re.IGNORECASE))
        if title_tag:
            title = title_tag.get_text(strip=True)

        # Extract participation info
        participation = self._extract_participation(soup)

        # Extract agenda items
        items = self._extract_items(soup)

        return {
            'title': title,
            'participation': participation,
            'items': items,
        }

    def _extract_participation(self, soup: BeautifulSoup) -> Dict[str, Any]:
        """
        Extract participation info from intro paragraphs.

        Args:
            soup: BeautifulSoup object of agenda page

        Returns:
            Participation dictionary with email, virtual_url, meeting_id, phone, is_hybrid
        """
        participation = {}

        # Get all text from page
        page_text = soup.get_text()

        # Email pattern
        email_match = re.search(r'council@berkeleyca\.gov', page_text, re.IGNORECASE)
        if email_match:
            participation['email'] = 'council@berkeleyca.gov'

        # Zoom URL
        zoom_match = re.search(r'https://cityofberkeley-info\.zoomgov\.com/j/(\d+)', page_text)
        if zoom_match:
            participation['virtual_url'] = zoom_match.group(0)
            participation['meeting_id'] = zoom_match.group(1)

        # Phone (look for pattern like "1-669-254-5252")
        phone_match = re.search(r'1-(\d{3})-(\d{3})-(\d{4})', page_text)
        if phone_match:
            participation['phone'] = f"+1{phone_match.group(1)}{phone_match.group(2)}{phone_match.group(3)}"

        # Meeting is hybrid if both Zoom and in-person mentioned
        if participation.get('virtual_url') and 'hybrid' in page_text.lower():
            participation['is_hybrid'] = True

        return participation

    def _extract_items(self, soup: BeautifulSoup) -> List[Dict[str, Any]]:
        """
        Extract agenda items from HTML content.

        Berkeley format:
        <strong>1.</strong><a href="/sites/default/files/documents/...pdf">Title</a>
        <strong>From: ...</strong>
        <strong>Recommendation: ...</strong>

        Args:
            soup: BeautifulSoup object of agenda page

        Returns:
            List of agenda item dictionaries with structure:
            [{
                'item_id': str,
                'title': str,
                'sequence': int,
                'attachments': [{'name': str, 'url': str, 'type': str}],
                'sponsor': str (optional),
                'recommendation': str (optional)
            }]
        """
        items = []

        # Find all <strong> tags that contain item numbers (1., 2., etc.)
        # These mark the start of each item
        strong_tags = soup.find_all('strong')

        for strong in strong_tags:
            text = strong.get_text(strip=True)

            # Match item numbers: "1.", "2.", etc. (not "H1.", "I1." - those are sections)
            if not re.match(r'^\d+\.$', text):
                continue

            item_number = int(text.rstrip('.'))

            # Find the link following this number
            next_link = strong.find_next('a', href=True)
            if not next_link:
                continue

            title = next_link.get_text(strip=True)
            # Remove leading dash if present
            title = title.lstrip('-').strip()

            href = next_link.get('href', '')
            attachment_url = urljoin(self.base_url, href) if href else None

            # Find "From:" line
            from_line = strong.find_next('strong', string=re.compile(r'^From:', re.IGNORECASE))
            sponsor = None
            if from_line:
                sponsor_text = from_line.get_text(strip=True)
                sponsor = sponsor_text.replace('From:', '').strip()

            # Find "Recommendation:" line
            rec_line = strong.find_next('strong', string=re.compile(r'^Recommendation:', re.IGNORECASE))
            recommendation = None
            if rec_line:
                # Get text between "Recommendation:" and next <strong> tag
                rec_text = []
                current = rec_line.next_sibling
                while current and current.name != 'strong':
                    if isinstance(current, str):
                        rec_text.append(current.strip())
                    elif current.name == 'br':
                        break
                    current = current.next_sibling if hasattr(current, 'next_sibling') else None
                recommendation = ' '.join(rec_text).strip()

            attachments = []
            if attachment_url and attachment_url.endswith('.pdf'):
                attachments.append({
                    'name': title,
                    'url': attachment_url,
                    'type': 'pdf',
                })

            item_data = {
                'item_id': str(item_number),
                'title': title,
                'sequence': item_number,
                'attachments': attachments,
            }

            if sponsor:
                item_data['sponsor'] = sponsor
            if recommendation:
                item_data['recommendation'] = recommendation

            items.append(item_data)

        logger.debug(f"[berkeley:{self.slug}] Extracted {len(items)} items")
        return items

    def _parse_date(self, date_str: str) -> Optional[datetime]:
        """
        Parse Berkeley date formats:
        - ISO 8601: "2025-11-11T02:00:00Z"
        - US format: "11/10/2025 - 6:00 pm"
        """
        date_str = date_str.strip()

        # Try ISO 8601 first
        if 'T' in date_str:
            try:
                return datetime.fromisoformat(date_str.replace('Z', '+00:00'))
            except Exception:
                pass

        # Try US format (MM/DD/YYYY)
        match = re.search(r'(\d{1,2})/(\d{1,2})/(\d{4})', date_str)
        if match:
            month, day, year = match.groups()
            try:
                return datetime(int(year), int(month), int(day))
            except Exception:
                pass

        return None


# Confidence: 7/10
# HTML structure parsed from provided example. Need to verify:
# - Meetings list URL pattern
# - Item extraction reliability across different meeting types
# - Edge cases for special meetings vs regular meetings
