"""
Menlo Park City Council Adapter - Custom table-based website with PDF item extraction

URL patterns:
- Meetings list: https://menlopark.gov/Agendas-and-minutes
- PDF packet: https://menlopark.gov/files/sharedassets/public/v/1/agendas-and-minutes/...pdf

HTML structure:
- Simple <table> with <tr> rows
- Columns: Date | Agenda packet (PDF) | Minutes | Video
- Date format: "Nov. 4, 2025"
- PDF link: <a href="/files/sharedassets/..." class="document ext-pdf">Agenda packet</a>

PDF agenda structure:
- Letter-based sections: H. (Presentations), I. (Appointments), J. (Consent), K. (Regular Business)
- Items: H1., I1., J1., K1. format
- Hyperlinked attachments: (Attachment), (Staff Report #XX-XXX-CC), (Presentation)
- Example: "J1. Waive the second reading and adopt an ordinance... (Staff Report #25-167-CC)"

Processing approach:
- Extract PDF text + hyperlinks using PyMuPDF
- Parse items from text using regex patterns
- Map hyperlinks to items based on page location
- Return item-level structure (agenda_url + items)

Confidence: 8/10 - PDF parsing reliable, link mapping based on page proximity
"""

from typing import Dict, Any, Iterator, Optional
from datetime import datetime, timedelta
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from vendors.adapters.base_adapter import BaseAdapter
from parsing.pdf import PdfExtractor
from parsing.menlopark_pdf import parse_menlopark_pdf_agenda

from config import get_logger

logger = get_logger(__name__).bind(component="vendor")



class MenloParkAdapter(BaseAdapter):
    """Menlo Park City Council - PDF agenda with item extraction"""

    def __init__(self, city_slug: str):
        super().__init__(city_slug, "menlopark")
        self.base_url = "https://menlopark.gov"
        self.pdf_extractor = PdfExtractor()

    def fetch_meetings(self, max_meetings: int = 10) -> Iterator[Dict[str, Any]]:
        """
        Fetch meetings from Menlo Park's table-based website and extract items from PDFs.

        Args:
            max_meetings: Maximum number of meetings to fetch (default 10)

        Yields:
            {
                'meeting_id': str,
                'date': datetime,
                'title': str,
                'agenda_url': str,  # PDF URL (source document)
                'items': [...]      # Extracted from PDF
            }
        """
        # Date range: today to 2 weeks from now
        today = datetime.now().date()
        two_weeks_from_now = today + timedelta(days=14)

        meetings_url = f"{self.base_url}/Agendas-and-minutes"

        logger.info("fetching meetings list", adapter="menlopark", slug=self.slug, url=meetings_url)

        try:
            response = self.session.get(meetings_url, timeout=30)
            response.raise_for_status()
        except Exception as e:
            logger.error("failed to fetch meetings list", adapter="menlopark", slug=self.slug, error=str(e))
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
                logger.debug("could not parse date", adapter="menlopark", slug=self.slug, date_text=date_text)
                continue

            # Filter to meetings from date range (calculated at method start)
            meeting_date_only = meeting_date.date()

            if meeting_date_only < today or meeting_date_only > two_weeks_from_now:
                logger.debug("skipping meeting outside 2-week window", adapter="menlopark", slug=self.slug, date=date_text)
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
                logger.debug("no PDF packet", adapter="menlopark", slug=self.slug, date=date_text)
                continue

            # Generate meeting ID from date
            meeting_id = f"menlopark_{meeting_date.strftime('%Y%m%d')}"

            meeting_data = {
                'meeting_id': meeting_id,
                'date': meeting_date,
                'title': "City Council Meeting",
                'agenda_url': pdf_link,  # PDF is the source document
            }

            # Extract items from PDF
            try:
                logger.info("extracting items from PDF", adapter="menlopark", slug=self.slug, url=pdf_link)
                pdf_result = self.pdf_extractor.extract_from_url(pdf_link, extract_links=True)

                if pdf_result['success']:
                    parsed = parse_menlopark_pdf_agenda(
                        pdf_result['text'],
                        pdf_result.get('links', [])
                    )

                    if parsed['items']:
                        meeting_data['items'] = parsed['items']
                        item_count = len(parsed['items'])
                        attachment_count = sum(len(item.get('attachments', [])) for item in parsed['items'])
                        logger.info(
                            f"[menlopark:{self.slug}] Extracted {item_count} items, "
                            f"{attachment_count} attachments for {meeting_date.strftime('%Y-%m-%d')}"
                        )
                    else:
                        logger.warning(
                            f"[menlopark:{self.slug}] No items extracted from PDF for {meeting_id}"
                        )
                else:
                    logger.error(
                        f"[menlopark:{self.slug}] PDF extraction failed for {meeting_id}: "
                        f"{pdf_result.get('error', 'unknown error')}"
                    )
                    # Continue anyway - we have basic meeting data

            except Exception as e:
                logger.warning("failed to parse PDF items", adapter="menlopark", slug=self.slug, meeting_id=meeting_id, error=str(e))
                # Continue anyway - we have basic meeting data

            yield meeting_data
            meetings_found += 1

    def _parse_date(self, date_str: str) -> Optional[datetime]:
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
            except ValueError:
                continue

        return None
