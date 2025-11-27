"""
Async Menlo Park City Council Adapter - Custom table-based website with PDF item extraction

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

Async version with:
- aiohttp for async HTTP requests
- asyncio.to_thread for CPU-bound PDF parsing
- Non-blocking I/O for concurrent fetching

Confidence: 8/10 - PDF parsing reliable, link mapping based on page proximity
"""

import asyncio
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta
from urllib.parse import urljoin

import aiohttp
from bs4 import BeautifulSoup

from vendors.adapters.base_adapter_async import AsyncBaseAdapter, logger
from parsing.pdf import PdfExtractor
from parsing.menlopark_pdf import parse_menlopark_pdf_agenda


class AsyncMenloParkAdapter(AsyncBaseAdapter):
    """Async Menlo Park City Council - PDF agenda with item extraction"""

    def __init__(self, city_slug: str):
        super().__init__(city_slug, vendor="menlopark")
        self.base_url = "https://menlopark.gov"
        self.pdf_extractor = PdfExtractor()

    async def fetch_meetings(self, max_meetings: int = 10) -> List[Dict[str, Any]]:
        """
        Fetch meetings from Menlo Park's table-based website and extract items from PDFs (async).

        Args:
            max_meetings: Maximum number of meetings to fetch (default 10)

        Returns:
            List of meeting dictionaries with meeting_id, title, start, agenda_url, items
        """
        # Date range: today to 2 weeks from now
        today = datetime.now().date()
        two_weeks_from_now = today + timedelta(days=14)

        meetings_url = f"{self.base_url}/Agendas-and-minutes"

        logger.info("fetching meetings list", adapter="menlopark", slug=self.slug, url=meetings_url)

        try:
            response = await self._get(meetings_url)
            html = await response.text()
        except (aiohttp.ClientError, asyncio.TimeoutError) as e:
            logger.error("failed to fetch meetings list", adapter="menlopark", slug=self.slug, error=str(e))
            return []

        # Parse HTML (CPU-bound, run in thread pool)
        soup = await asyncio.to_thread(BeautifulSoup, html, 'html.parser')

        # Find all table rows
        rows = soup.find_all('tr')

        results = []
        for row in rows:
            if len(results) >= max_meetings:
                break

            cells = row.find_all('td')
            if len(cells) < 2:
                continue

            # Cell 0: Date text (e.g., "Nov. 4, 2025")
            date_text = cells[0].get_text(strip=True)
            if not date_text:
                continue

            # Parse date
            meeting_date = self._parse_menlopark_date(date_text)
            if not meeting_date:
                logger.debug("could not parse date", adapter="menlopark", slug=self.slug, date_text=date_text)
                continue

            # Filter to meetings from date range
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
                'start': meeting_date.isoformat(),
                'title': "City Council Meeting",
                'agenda_url': pdf_link,  # PDF is the source document
            }

            # Extract items from PDF (sync PDF extraction wrapped in to_thread)
            try:
                logger.info("extracting items from PDF", adapter="menlopark", slug=self.slug, url=pdf_link)

                # Run sync PDF extraction in thread pool
                pdf_result = await asyncio.to_thread(
                    self.pdf_extractor.extract_from_url,
                    pdf_link,
                    extract_links=True
                )

                if pdf_result['success']:
                    # Parse PDF text (also CPU-bound)
                    parsed = await asyncio.to_thread(
                        parse_menlopark_pdf_agenda,
                        pdf_result['text'],
                        pdf_result.get('links', [])
                    )

                    if parsed['items']:
                        meeting_data['items'] = parsed['items']
                        item_count = len(parsed['items'])
                        attachment_count = sum(len(item.get('attachments', [])) for item in parsed['items'])
                        logger.info(
                            "extracted items from PDF",
                            adapter="menlopark",
                            slug=self.slug,
                            item_count=item_count,
                            attachment_count=attachment_count,
                            date=meeting_date.strftime('%Y-%m-%d')
                        )
                    else:
                        logger.warning(
                            "no items extracted from PDF",
                            adapter="menlopark",
                            slug=self.slug,
                            meeting_id=meeting_id
                        )
                else:
                    logger.error(
                        "PDF extraction failed",
                        adapter="menlopark",
                        slug=self.slug,
                        meeting_id=meeting_id,
                        error=pdf_result.get('error', 'unknown error')
                    )
                    # Continue anyway - we have basic meeting data

            except (aiohttp.ClientError, asyncio.TimeoutError, OSError) as e:
                logger.warning("failed to parse PDF items", adapter="menlopark", slug=self.slug, meeting_id=meeting_id, error=str(e))
                # Continue anyway - we have basic meeting data

            results.append(meeting_data)

        return results

    def _parse_menlopark_date(self, date_str: str) -> Optional[datetime]:
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
