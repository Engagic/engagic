"""
Berkeley City Council Adapter - Custom Drupal CMS

URL patterns:
- Meetings list: https://berkeleyca.gov/your-government/city-council/city-council-agendas (TODO: verify)
- HTML agenda: https://berkeleyca.gov/city-council-regular-meeting-eagenda-november-10-2025
- PDF packet: https://berkeleyca.gov/sites/default/files/city-council-meetings/2025-11-10%20Agenda%20Packet...pdf

HTML structure:
- Drupal views table with columns: Date | Agenda | Minutes | Video
- HTML agenda link: <a href="/city-council-regular-meeting-eagenda-...">HTML</a>
- PDF packet link: <a href="/sites/default/files/...pdf">PDF</a>
- Agenda items: <strong>1.</strong><a href="...">Title</a> format
- Participation: Zoom, phone, email in intro paragraph

Confidence: 7/10 - Need to verify meetings list URL and item extraction patterns
"""

import logging
import re
from typing import Dict, Any, List, Iterator
from datetime import datetime
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
        # TODO: Verify actual meetings list URL
        # Possible patterns:
        # - /your-government/city-council/city-council-agendas
        # - /government/city-council/agendas
        # - /city-council/meetings
        meetings_url = f"{self.base_url}/your-government/city-council/city-council-agendas"

        logger.info(f"[Berkeley] Fetching meetings from {meetings_url}")

        try:
            response = self.session.get(meetings_url, timeout=30)
            response.raise_for_status()
        except Exception as e:
            logger.error(f"[Berkeley] Failed to fetch meetings list: {e}")
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

            # Cell 0: Date (with <time> tag)
            time_tag = cells[0].find('time')
            if not time_tag:
                # Try parsing raw text
                date_text = cells[0].get_text(strip=True)
            else:
                date_text = time_tag.get('datetime') or time_tag.get_text(strip=True)

            if not date_text:
                continue

            # Parse date
            meeting_date = self._parse_date(date_text)
            if not meeting_date:
                logger.debug(f"[Berkeley] Could not parse date: {date_text}")
                continue

            # Cell 1: Agenda links (HTML and/or PDF)
            agenda_cell = cells[1] if len(cells) > 1 else None
            html_link = None
            pdf_link = None

            if agenda_cell:
                links = agenda_cell.find_all('a', href=True)
                for link in links:
                    href = link.get('href', '')
                    link_text = link.get_text(strip=True).lower()

                    if 'html' in link_text:
                        html_link = urljoin(self.base_url, href)
                    elif 'pdf' in link_text or '.pdf' in href.lower():
                        pdf_link = urljoin(self.base_url, href)

            # Skip if no agenda available
            if not html_link and not pdf_link:
                logger.debug(f"[Berkeley] No agenda links for {date_text}")
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
                'packet_url': pdf_link,
            }

            # If HTML agenda available, fetch detailed info
            if html_link:
                try:
                    detail = self._fetch_meeting_detail(html_link)
                    if detail:
                        meeting_data['participation'] = detail.get('participation', {})
                        meeting_data['items'] = detail.get('items', [])
                        if detail.get('title'):
                            meeting_data['title'] = detail['title']
                except Exception as e:
                    logger.warning(f"[Berkeley] Failed to fetch detail for {meeting_id}: {e}")

            logger.info(
                f"[Berkeley] Meeting {meeting_date.strftime('%Y-%m-%d')}: "
                f"{'HTML' if html_link else 'PDF only'}, "
                f"{len(meeting_data.get('items', []))} items"
            )

            yield meeting_data
            meetings_found += 1

    def _fetch_meeting_detail(self, agenda_url: str) -> Dict[str, Any]:
        """
        Fetch and parse HTML agenda detail page.

        Returns:
            {
                'title': str,
                'participation': {...},
                'items': [...]
            }
        """
        logger.debug(f"[Berkeley] Fetching detail: {agenda_url}")

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
        """Extract participation info from intro paragraphs"""
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

        logger.debug(f"[Berkeley] Extracted {len(items)} items")
        return items

    def _parse_date(self, date_str: str) -> datetime:
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
