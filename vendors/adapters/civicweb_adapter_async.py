"""
Async CivicWeb Adapter - eSCRIBE's CivicWeb Portal for municipal meetings

Cities using CivicWeb: Sonoma CA, Calistoga CA, and others on {slug}.civicweb.net.

CivicWeb is eSCRIBE's older portal product (Drupal-based, ASP.NET backend).
Different from escribemeetings.com (newer product with calendar API).

Architecture:
  /Portal/MeetingTypeList.aspx  - Lists ALL bodies and their recent meetings
                                  with IDs, dates, and titles in static HTML.
  /Portal/MeetingInformation.aspx?Id={mid}  - Meeting page with embedded
                                              packet PDF viewer.
  /document/{doc_id}/{name}.pdf?handle={hash}  - Direct PDF download.

The packet PDF is typically a compiled agenda+staff reports document with
a PDF TOC (bookmarks). The chunker handles item extraction via TOC entries.

Slug is the civicweb subdomain (e.g. 'sonomacity' for sonomacity.civicweb.net).
"""

import re
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from vendors.adapters.base_adapter_async import AsyncBaseAdapter, logger
from exceptions import VendorHTTPError
from pipeline.protocols import MetricsCollector


# Date in meeting title -- two formats across CivicWeb sites:
#   Sonoma:    "18 Mar 2026" (day month year)
#   Calistoga: "Mar 31 2026" (month day year)
_DATE_DMY_RE = re.compile(r'(\d{1,2})\s+(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+(\d{4})')
_DATE_MDY_RE = re.compile(r'(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+(\d{1,2})\s+(\d{4})')

# Document URL on meeting pages: /document/{id}/{name}.pdf?handle={hash}
_DOC_URL_RE = re.compile(r'/document/\d+/[^"\'>\s]+\.pdf\?handle=[^"\'>\s]+')


class AsyncCivicWebAdapter(AsyncBaseAdapter):
    """Async adapter for cities on the CivicWeb portal platform.

    Slug is the civicweb subdomain: 'sonomacity', 'calistoga', etc.
    """

    def __init__(self, city_slug: str, metrics: Optional[MetricsCollector] = None):
        super().__init__(city_slug, vendor="civicweb", metrics=metrics)
        self.base_url = f"https://{self.slug}.civicweb.net"

    # ------------------------------------------------------------------
    # Main fetch
    # ------------------------------------------------------------------

    async def _fetch_meetings_impl(
        self, days_back: int = 7, days_forward: int = 14
    ) -> List[Dict[str, Any]]:
        """Scrape MeetingTypeList for meetings, fetch packet PDFs."""
        today = datetime.now()
        start_date = today - timedelta(days=days_back)
        end_date = today + timedelta(days=days_forward)

        meetings = await self._scrape_meeting_type_list(start_date, end_date)

        logger.info(
            "civicweb meetings scraped",
            slug=self.slug,
            count=len(meetings),
            start_date=str(start_date.date()),
            end_date=str(end_date.date()),
        )

        # Fetch packet PDF URL for each meeting (concurrent, bounded)
        enriched = await self._bounded_gather(
            [self._enrich_meeting(m) for m in meetings],
            max_concurrent=5,
        )

        results = []
        for idx, meeting in enumerate(enriched):
            if isinstance(meeting, Exception):
                logger.warning(
                    "meeting enrichment failed",
                    vendor="civicweb",
                    slug=self.slug,
                    error=str(meeting),
                    meeting_index=idx,
                )
            elif isinstance(meeting, dict):
                results.append(meeting)

        # Parse packet PDFs for structured items
        async def _parse_pdf(meeting: Dict[str, Any]) -> None:
            packet_url = meeting.get("packet_url")
            if not packet_url:
                return
            items = await self._parse_packet_pdf(packet_url, meeting.get("vendor_id"))
            if items:
                meeting["items"] = items

        await self._bounded_gather(
            [_parse_pdf(m) for m in results],
            max_concurrent=3,
        )

        logger.info(
            "civicweb meetings with items",
            slug=self.slug,
            count=len(results),
            with_items=sum(1 for m in results if m.get("items")),
        )

        return results

    # ------------------------------------------------------------------
    # MeetingTypeList scraping
    # ------------------------------------------------------------------

    async def _scrape_meeting_type_list(
        self, start_date: datetime, end_date: datetime
    ) -> List[Dict[str, Any]]:
        """Scrape MeetingTypeList.aspx for all bodies and meetings.

        The page lists bodies as type= links, followed by their recent
        meetings as Id= links. We group by body and filter by date range.
        """
        url = f"{self.base_url}/Portal/MeetingTypeList.aspx"

        try:
            response = await self._get(url)
            html = await response.text()
        except VendorHTTPError as e:
            logger.error(
                "failed to fetch MeetingTypeList",
                vendor="civicweb",
                slug=self.slug,
                error=str(e),
            )
            return []

        soup = BeautifulSoup(html, "html.parser")

        meetings = []
        current_body: Optional[str] = None
        current_type_id: Optional[str] = None

        for link in soup.find_all("a", href=True):
            href = link.get("href", "")
            if not isinstance(href, str) or "MeetingInformation" not in href:
                continue

            text = link.get_text(strip=True)
            if not text:
                continue

            if "type=" in href:
                # Body header link
                current_body = text
                type_match = re.search(r"type=(\d+)", href)
                current_type_id = type_match.group(1) if type_match else None
                continue

            if "Id=" not in href:
                continue

            # Individual meeting link
            meeting_id_match = re.search(r"Id=(\d+)", href)
            if not meeting_id_match:
                continue

            meeting_id = meeting_id_match.group(1)

            # Parse date from title: "City Council - 18 Mar 2026"
            meeting_date = self._parse_civicweb_date(text)
            if not meeting_date:
                continue

            m_date = self._parse_date(meeting_date)
            if m_date and not (start_date <= m_date <= end_date):
                continue

            # Detect cancelled
            meeting_status = self._parse_meeting_status(text, meeting_date)

            # Clean title: strip date suffix and ***CANCELLED*** prefix
            title = re.sub(r'\*{3}CANCELLED\*{3}\s*', '', text, flags=re.IGNORECASE).strip()
            title = re.sub(r'\s*-\s*(?:\d{1,2}\s+\w{3}|\w{3}\s+\d{1,2})\s+\d{4}.*$', '', title).strip()
            title = re.sub(r'\s+Amended Agenda$', '', title).strip()
            if not title:
                title = text

            result: Dict[str, Any] = {
                "vendor_id": meeting_id,
                "title": title,
                "start": meeting_date,
            }

            if meeting_status:
                result["meeting_status"] = meeting_status

            meta: Dict[str, str] = {}
            if current_body:
                meta["body"] = current_body
            if current_type_id:
                meta["body_type_id"] = current_type_id

            meeting_page_url = urljoin(self.base_url, href)
            meta["meeting_url"] = meeting_page_url

            if meta:
                result["metadata"] = meta

            result["_meeting_page_url"] = meeting_page_url

            meetings.append(result)

        return meetings

    # ------------------------------------------------------------------
    # Meeting enrichment: fetch packet PDF URL
    # ------------------------------------------------------------------

    async def _enrich_meeting(self, meeting: Dict[str, Any]) -> Dict[str, Any]:
        """Fetch meeting page to extract the packet PDF URL."""
        page_url = meeting.pop("_meeting_page_url", "")
        if not page_url:
            return meeting

        try:
            response = await self._get(page_url)
            html = await response.text()
        except VendorHTTPError as e:
            logger.debug(
                "failed to fetch meeting page",
                vendor="civicweb",
                slug=self.slug,
                url=page_url,
                error=str(e),
            )
            return meeting

        # Extract document URL: /document/{id}/{name}.pdf?handle={hash}
        doc_match = _DOC_URL_RE.search(html)
        if doc_match:
            pdf_url = urljoin(self.base_url, doc_match.group(0))
            meeting["packet_url"] = pdf_url

        return meeting

    # ------------------------------------------------------------------
    # PDF chunker
    # ------------------------------------------------------------------

    # ------------------------------------------------------------------
    # Utilities
    # ------------------------------------------------------------------

    def _parse_civicweb_date(self, text: str) -> Optional[str]:
        """Parse CivicWeb date from meeting title to ISO.

        Handles both formats:
          '18 Mar 2026' (day-month-year, Sonoma)
          'Mar 31 2026' (month-day-year, Calistoga)
        """
        # Try day-month-year first (more common)
        match = _DATE_DMY_RE.search(text)
        if match:
            try:
                dt = datetime.strptime(f"{match.group(1)} {match.group(2)} {match.group(3)}", "%d %b %Y")
                return dt.isoformat()
            except ValueError:
                pass

        # Try month-day-year
        match = _DATE_MDY_RE.search(text)
        if match:
            try:
                dt = datetime.strptime(f"{match.group(1)} {match.group(2)} {match.group(3)}", "%b %d %Y")
                return dt.isoformat()
            except ValueError:
                pass

        return None

    def _parse_meeting_status(
        self, title: str, date_str: Optional[str] = None
    ) -> Optional[str]:
        """Detect meeting status from title."""
        status = super()._parse_meeting_status(title, date_str)
        if status:
            return status

        if not title:
            return None

        lower = title.lower()
        if "cancelled" in lower or "canceled" in lower:
            return "cancelled"
        if "***cancelled***" in lower:
            return "cancelled"

        return None
