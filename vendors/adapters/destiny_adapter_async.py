"""
Async Destiny (AgendaQuick) Adapter - HTML scraping with structured items + staff reports

Destiny Software's AgendaQuick is a ColdFusion-based agenda management system hosted
at public.destinyhosted.com.  Cities are identified by a numeric site ID in the URL.

Three-level HTML extraction:
1. Listing page: month-based meeting table with seq IDs
2. Agenda detail: structured items with sections + PDF packet link
3. Item memos: staff report body text + per-item attachments

URL patterns:
- Listing:    /agenda_publish.cfm?id={site_id}&mt=ALL&get_month={m}&get_year={y}
- Agenda:     ...&dsp=ag&seq={meeting_seq}
- Item memo:  ...&dsp=agm&seq={item_seq}&rev=0&ag={meeting_seq}&ln={line_id}
- PDF packet: /{prefix}docs/{year}/{type}/{date}_{seq}/AGENDApacket_...pdf
- Attachment: /{prefix}docs/{year}/{type}/{date}_{seq}/{item_seq}_{name}.pdf

Slug convention: the city's numeric site ID (e.g., "63927" for Newark CA).

Confidence: 8/10 - Clean HTML structure, consistent across cities on this platform
"""

import asyncio
import re
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta
from urllib.parse import urljoin, urlparse, parse_qs

import aiohttp
from bs4 import BeautifulSoup, Tag

from vendors.adapters.base_adapter_async import AsyncBaseAdapter, logger
from pipeline.protocols import MetricsCollector


class AsyncDestinyAdapter(AsyncBaseAdapter):
    """Async Destiny/AgendaQuick - structured HTML agendas with staff report memos"""

    def __init__(self, city_slug: str, metrics: Optional[MetricsCollector] = None):
        super().__init__(city_slug, vendor="destiny", metrics=metrics)
        self.base_url = "https://public.destinyhosted.com"
        self.site_id = city_slug  # slug IS the numeric site ID

    async def _fetch_meetings_impl(self, days_back: int = 14, days_forward: int = 14) -> List[Dict[str, Any]]:
        """Fetch meetings across relevant months, extract items from agenda pages."""
        today = datetime.now().date()
        start_date = today - timedelta(days=days_back)
        end_date = today + timedelta(days=days_forward)

        # Determine which months to fetch (may span 2-3 months)
        months = set()
        d = start_date
        while d <= end_date:
            months.add((d.year, d.month))
            d += timedelta(days=28)
        months.add((end_date.year, end_date.month))

        results = []
        for year, month in sorted(months):
            meetings = await self._fetch_month(year, month, start_date, end_date)
            results.extend(meetings)

        return results

    async def _fetch_month(
        self, year: int, month: int, start_date, end_date
    ) -> List[Dict[str, Any]]:
        """Fetch the listing page for one month and process each meeting."""
        url = (
            f"{self.base_url}/agenda_publish.cfm"
            f"?id={self.site_id}&mt=ALL&get_month={month}&get_year={year}"
        )

        logger.info("fetching month listing", vendor="destiny", slug=self.slug, url=url)

        try:
            response = await self._get(url)
            html = await response.text()
        except (aiohttp.ClientError, asyncio.TimeoutError) as e:
            logger.error("failed to fetch listing", vendor="destiny", slug=self.slug, error=str(e))
            return []

        soup = await asyncio.to_thread(BeautifulSoup, html, 'html.parser')

        table = soup.find('table', id='meeting-table')
        if not table:
            return []

        tbody = table.find('tbody')
        if not tbody:
            return []

        meetings = []
        for row in tbody.find_all('tr'):
            if not isinstance(row, Tag):
                continue
            cells = row.find_all('td')
            if len(cells) < 2:
                continue

            link = cells[0].find('a', href=True)
            if not link:
                continue

            date_text = link.get_text(strip=True)
            meeting_date = self._parse_date(date_text)
            if not meeting_date:
                continue

            if meeting_date.date() < start_date or meeting_date.date() > end_date:
                continue

            # Extract seq from link href
            href = link.get('href', '')
            seq = self._extract_url_param(href, 'seq')
            if not seq:
                continue

            title = cells[1].get_text(strip=True)
            body_name = self._extract_body_name(title)

            # Fetch the agenda detail page for items + PDF packet
            agenda_data = await self._fetch_agenda_detail(year, month, seq)

            meeting_data: Dict[str, Any] = {
                'vendor_id': seq,
                'start': meeting_date.isoformat(),
                'title': title,
                'body_name': body_name,
                'agenda_url': urljoin(self.base_url, href),
            }

            if agenda_data.get('packet_url'):
                meeting_data['packet_url'] = agenda_data['packet_url']

            if agenda_data.get('items'):
                meeting_data['items'] = agenda_data['items']
                logger.info(
                    "extracted items",
                    vendor="destiny", slug=self.slug,
                    body=body_name, item_count=len(agenda_data['items']),
                    date=meeting_date.strftime('%Y-%m-%d'),
                )

            meetings.append(meeting_data)

        return meetings

    async def _fetch_agenda_detail(
        self, year: int, month: int, meeting_seq: str
    ) -> Dict[str, Any]:
        """Fetch agenda detail page: extract structured items + PDF packet URL."""
        url = (
            f"{self.base_url}/agenda_publish.cfm"
            f"?id={self.site_id}&mt=ALL&get_month={month}&get_year={year}"
            f"&dsp=ag&seq={meeting_seq}"
        )

        logger.info("fetching agenda detail", vendor="destiny", slug=self.slug, seq=meeting_seq)

        result: Dict[str, Any] = {'items': [], 'packet_url': None}

        try:
            response = await self._get(url)
            html = await response.text()
        except (aiohttp.ClientError, asyncio.TimeoutError) as e:
            logger.warning("failed to fetch agenda", vendor="destiny", slug=self.slug, seq=meeting_seq, error=str(e))
            return result

        soup = await asyncio.to_thread(BeautifulSoup, html, 'html.parser')

        # PDF packet link: <a id="pdf" href="/...pdf">
        pdf_link = soup.find('a', id='pdf')
        if pdf_link and isinstance(pdf_link, Tag):
            result['packet_url'] = urljoin(self.base_url, pdf_link.get('href', ''))

        # Parse items from the structured agenda table
        items = self._parse_agenda_items(soup)

        # Fetch memos concurrently for items that have memo links
        items_with_memos = [it for it in items if it.get('_memo_url')]
        if items_with_memos:
            coros = [self._enrich_item_from_memo(it) for it in items_with_memos]
            await self._bounded_gather(coros, max_concurrent=3)

        # Clean up internal keys
        for it in items:
            it.pop('_memo_url', None)

        result['items'] = items
        return result

    def _parse_agenda_items(self, soup: BeautifulSoup) -> List[Dict[str, Any]]:
        """Parse items from Destiny's multi-column agenda table.

        Two known column layouts:
        - [letter | item# | ... | content]  (Newark: sections use letters)
        - [anchor | section# | letter | sub# | spacer | content]  (Pacific Grove: sections use digits)

        Items: rows with a.ai_link (with href) in the content cell.
        Sections: rows with a letter or digit in an early cell + bold text in content.
        """
        items: List[Dict[str, Any]] = []
        current_section = ""
        current_section_id = ""
        sequence = 0

        for row in soup.find_all('tr', class_=lambda c: c and 'top' in c):
            if not isinstance(row, Tag):
                continue
            cells = row.find_all('td')
            if len(cells) < 2:
                continue

            content_cell = cells[-1]
            item_link = content_cell.find('a', class_='ai_link')
            if not item_link or not item_link.get('href'):
                # Not an item -- check for section header (letter/digit + bold)
                for cell in cells[:-1]:
                    t = cell.get_text(strip=True).rstrip('.')
                    if t.isdigit() or re.match(r'^[A-Z]$', t):
                        strong = content_cell.find('strong')
                        if strong:
                            current_section_id = t
                            current_section = strong.get_text(strip=True)
                        break
                continue

            title = item_link.get_text(strip=True)
            if not title:
                continue

            memo_href = item_link.get('href', '')

            # Collect numbering from cells before content
            num_parts = []
            for cell in cells[:-1]:
                t = cell.get_text(strip=True).rstrip('.')
                if not t or t == '\xa0':
                    continue
                if t.isdigit() or re.match(r'^[A-Z]$', t):
                    num_parts.append(t)

            # Prepend section ID if not already present in parts
            if current_section_id and current_section_id not in num_parts:
                num_parts.insert(0, current_section_id)

            agenda_number = '.'.join(num_parts) if num_parts else str(sequence + 1)
            sequence += 1

            item: Dict[str, Any] = {
                'vendor_item_id': agenda_number,
                'title': title,
                'sequence': sequence,
                'agenda_number': agenda_number,
            }

            if current_section:
                item['metadata'] = {'section': current_section}

            if memo_href:
                item['_memo_url'] = urljoin(self.base_url, memo_href)

            items.append(item)

        return items

    async def _enrich_item_from_memo(self, item: Dict[str, Any]) -> None:
        """Fetch an item's memo page to extract body text and attachments."""
        url = item.get('_memo_url')
        if not url:
            return

        try:
            response = await self._get(url)
            html = await response.text()
        except (aiohttp.ClientError, asyncio.TimeoutError) as e:
            logger.debug("failed to fetch memo", vendor="destiny", slug=self.slug, error=str(e))
            return

        soup = await asyncio.to_thread(BeautifulSoup, html, 'html.parser')

        # Extract header metadata (DATE, TO, FROM, SUBJECT fields)
        body_parts = []
        for strong in soup.find_all('strong'):
            label = strong.get_text(strip=True)
            if label in ('DATE', 'TO', 'FROM', 'SUBJECT'):
                cell = strong.find_parent('td')
                if not cell:
                    continue
                value_cell = cell.find_next_sibling('td')
                if value_cell:
                    value = value_cell.get_text(strip=True)
                    if value:
                        body_parts.append(f"{label}: {value}")

        # Extract all bold mediumText sections and their content
        for td in soup.find_all('td', class_=lambda c: c and 'bold' in c and 'mediumText' in c):
            section_name = td.get_text(strip=True)
            if section_name == 'Attachments':
                continue  # attachments handled separately
            parent_tr = td.find_parent('tr')
            if not parent_tr:
                continue
            next_tr = parent_tr.find_next_sibling('tr')
            if next_tr:
                text = next_tr.get_text(separator='\n', strip=True)
                if text:
                    body_parts.append(f"{section_name}\n{text}")

        if body_parts:
            item['body_text'] = '\n\n'.join(body_parts)[:8000]

        # Extract attachments from popupAttachments() onclick handlers
        attachments = []
        for link in soup.find_all('a', href='#'):
            onclick = link.get('onclick', '')
            if 'popupAttachments' not in onclick:
                continue
            match = re.search(r"popupAttachments\('([^']+)'", onclick)
            if not match:
                continue
            att_path = match.group(1)
            att_url = urljoin(self.base_url, att_path)
            att_name = link.get_text(strip=True)
            attachments.append({
                'name': att_name or 'Attachment',
                'url': att_url,
                'type': 'pdf' if att_url.lower().endswith('.pdf') else 'document',
            })

        if attachments:
            item['attachments'] = attachments

    @staticmethod
    def _extract_body_name(title: str) -> str:
        """Extract body name from meeting title.

        "City Council Regular Meeting" -> "City Council"
        "Planning Commission Special Meeting" -> "Planning Commission"
        """
        for suffix in (' Regular Meeting', ' Special Meeting', ' Meeting'):
            if title.endswith(suffix):
                return title[:-len(suffix)]
        return title

    @staticmethod
    def _extract_url_param(url: str, param: str) -> Optional[str]:
        """Extract a query parameter value from a URL."""
        parsed = urlparse(url)
        params = parse_qs(parsed.query)
        values = params.get(param, [])
        return values[0] if values else None
