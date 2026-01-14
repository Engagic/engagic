"""
Async CivicPlus Adapter - Discovery and scraping for CivicPlus sites

CivicPlus cities use varied hosting:
- *.civicplus.com (standard)
- *.gov / *.org (custom domains like cityofithacany.gov)

This adapter auto-discovers the working domain by trying candidates in order:
1. {slug}.civicplus.com
2. www.{slug}.gov
3. {slug}.gov
4. www.{slug}.org
5. {slug}.org

Use clean slugs (e.g., "cityofithacany" not "www.cityofithacany.gov").
"""

import re
import asyncio
import hashlib
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
from urllib.parse import urlparse, urljoin, parse_qs

import aiohttp
from bs4 import BeautifulSoup

from vendors.adapters.base_adapter_async import AsyncBaseAdapter, logger
from pipeline.protocols import MetricsCollector
from exceptions import VendorHTTPError


class AsyncCivicPlusAdapter(AsyncBaseAdapter):
    """Async adapter for cities using CivicPlus CMS (often with external agenda systems)"""

    def __init__(self, city_slug: str, metrics: Optional[MetricsCollector] = None):
        """city_slug is clean city identifier (e.g., "cityofithacany")"""
        super().__init__(city_slug, vendor="civicplus", metrics=metrics)
        self.base_url = None  # Discovered during fetch

    def _get_candidate_base_urls(self) -> List[str]:
        """Return candidate base URLs to try, in priority order."""
        slug = self.slug
        candidates = [
            f"https://{slug}.civicplus.com",
            f"https://www.{slug}.gov",
            f"https://{slug}.gov",
            f"https://www.{slug}.org",
            f"https://{slug}.org",
        ]
        # If slug already has a dot, it's a full domain - try it directly first
        if "." in slug:
            candidates.insert(0, f"https://{slug}")
        return candidates

    async def _find_agenda_url(self) -> Optional[str]:
        """Discover agenda page URL from common CivicPlus patterns across candidate domains."""
        patterns = [
            "/AgendaCenter",
            "/Calendar.aspx",
            "/calendar",
            "/meetings",
            "/agendas",
        ]

        for base_url in self._get_candidate_base_urls():
            for pattern in patterns:
                test_url = f"{base_url}{pattern}"
                try:
                    response = await self._get(test_url)
                    html = await response.text()
                    if response.status == 200 and (
                        "agenda" in html.lower()
                        or "meeting" in html.lower()
                    ):
                        self.base_url = base_url  # Store discovered base URL
                        logger.info("found agenda page", vendor="civicplus", slug=self.slug, base_url=base_url, pattern=pattern)
                        return test_url
                except VendorHTTPError:
                    continue

        logger.warning("could not find agenda page", vendor="civicplus", slug=self.slug)
        return None

    async def _fetch_meetings_impl(self, days_back: int = 7, days_forward: int = 14) -> List[Dict[str, Any]]:
        """Scrape AgendaCenter HTML and filter meetings by date range."""
        today = datetime.now()
        start_date = today - timedelta(days=days_back)
        end_date = today + timedelta(days=days_forward)

        agenda_url = await self._find_agenda_url()

        if not agenda_url:
            logger.error(
                "no agenda page found - cannot fetch meetings",
                vendor="civicplus",
                slug=self.slug
            )
            return []

        try:
            response = await self._get(agenda_url)
            html = await response.text()
            soup = await asyncio.to_thread(BeautifulSoup, html, 'html.parser')
            meeting_links = self._extract_meeting_links(soup, agenda_url)

            logger.info(
                "found meeting links",
                vendor="civicplus",
                slug=self.slug,
                count=len(meeting_links)
            )

            results = []
            for link_data in meeting_links:
                if '/ViewFile/Agenda/' in link_data['url']:
                    meeting = self._create_meeting_from_viewfile_link(link_data)
                    if meeting and self._is_meeting_in_range(meeting, start_date, end_date):
                        results.append(meeting)
                else:
                    meeting = await self._scrape_meeting_page(
                        link_data["url"], link_data["title"]
                    )
                    if meeting and self._is_meeting_in_range(meeting, start_date, end_date):
                        results.append(meeting)

            # Dedupe by date - keep the last one (packet is typically uploaded after agenda)
            deduped = self._dedupe_by_date(results)

            logger.info(
                "filtered meetings in date range",
                vendor="civicplus",
                slug=self.slug,
                count=len(deduped),
                before_dedupe=len(results),
                start_date=str(start_date.date()),
                end_date=str(end_date.date())
            )

            return deduped

        except (aiohttp.ClientError, asyncio.TimeoutError) as e:
            logger.error("failed to fetch meetings", vendor="civicplus", slug=self.slug, error=str(e))
            return []

    def _is_meeting_in_range(
        self, meeting: Dict[str, Any], start_date: datetime, end_date: datetime
    ) -> bool:
        """Check if meeting date is within range. Includes meetings with unparseable dates."""
        meeting_start = meeting.get("start")
        if not meeting_start:
            return True

        try:
            meeting_date = datetime.fromisoformat(meeting_start)
            return start_date <= meeting_date <= end_date
        except (ValueError, AttributeError):
            return True

    def _dedupe_by_date(self, meetings: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Dedupe meetings by date, keeping the last one (packet uploaded after agenda)."""
        by_date: Dict[str, Dict[str, Any]] = {}
        for meeting in meetings:
            date_key = meeting.get("start", "unknown")
            # Later entries overwrite earlier ones (packet overwrites agenda)
            by_date[date_key] = meeting
        return list(by_date.values())

    def _extract_meeting_links(
        self, soup: BeautifulSoup, base_url: str
    ) -> List[Dict[str, str]]:
        """Extract meeting detail page links from agenda listing."""
        links = []

        # Look for links that either:
        # 1. Point to /ViewFile/Agenda/ (direct meeting links)
        # 2. Have date patterns in text (e.g., "June 25, 2025" or "06/25/2025")
        for link in soup.find_all("a", href=True):
            text = link.get_text(strip=True)
            href = link["href"]

            # Skip navigation links and page headers
            skip_patterns = [
                "<<<", "◄", "Back to", "back to",
                "Agendas & Minutes", "agendas & minutes",
                "Calendar", "All Agendas", "all agendas",
            ]
            if any(text.startswith(p) or text == p for p in skip_patterns):
                continue
            # Also skip if text is too short (likely a nav element)
            if len(text) < 5:
                continue

            # Check if it's a ViewFile link (direct meeting link)
            is_viewfile = "/ViewFile/Agenda/" in href or "/ViewFile/Item/" in href

            # Check if text has date patterns
            has_date = bool(re.search(r'\b(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]* \d{1,2},? \d{4}\b', text, re.I))
            has_numeric_date = bool(re.search(r'\b\d{1,2}/\d{1,2}/\d{4}\b', text))

            if is_viewfile or has_date or has_numeric_date:
                absolute_url = urljoin(base_url, href)
                links.append({"url": absolute_url, "title": text})

        return links

    def _extract_date_from_url(self, url: str) -> Optional[datetime]:
        """Extract date from CivicPlus ViewFile URL pattern _MMDDYYYY-ID."""
        # Pattern: /ViewFile/Agenda/_12042025-786 = December 4, 2025
        match = re.search(r'_(\d{2})(\d{2})(\d{4})-\d+', url)
        if match:
            month, day, year = match.groups()
            try:
                return datetime(int(year), int(month), int(day))
            except ValueError:
                return None
        return None

    def _create_meeting_from_viewfile_link(self, link_data: Dict[str, str]) -> Optional[Dict[str, Any]]:
        """Create meeting dict directly from ViewFile link without scraping."""
        url = link_data["url"]
        title = link_data["title"]

        # Try to extract date from URL first (more reliable for CivicPlus)
        parsed_date = self._extract_date_from_url(url)
        if not parsed_date:
            date_text = self._extract_date_from_title(title)
            parsed_date = self._parse_date(date_text) if date_text else None

        meeting_id = self._extract_meeting_id(url)

        # Build better title if we have a date
        if parsed_date and title in ["Agenda", "View Meeting Agenda", "View Agenda Packet"]:
            title = f"Meeting - {parsed_date.strftime('%B %d, %Y')}"

        meeting_status = self._parse_meeting_status(title, None)

        result = {
            "vendor_id": meeting_id,
            "title": title,
            "start": parsed_date.isoformat() if parsed_date else None,
            "packet_url": url,
        }

        if meeting_status:
            result["meeting_status"] = meeting_status

        return result

    async def _scrape_meeting_page(self, url: str, title: str) -> Optional[Dict[str, Any]]:
        """Scrape individual meeting page for metadata and PDF links."""
        try:
            response = await self._get(url)
            html = await response.text()
            soup = await asyncio.to_thread(BeautifulSoup, html, 'html.parser')

            date_text = self._extract_date_from_page(soup)
            if not date_text:
                date_text = self._extract_date_from_title(title)
            parsed_date = self._parse_date(date_text) if date_text else None

            pdfs = await self._discover_pdfs_async(url, soup)
            meeting_id = self._extract_meeting_id(url)
            meeting_status = self._parse_meeting_status(title, date_text)

            if not pdfs:
                logger.debug("no PDFs found for meeting", vendor="civicplus", slug=self.slug, title=title)

            result = {
                "vendor_id": meeting_id,
                "title": title,
                "start": parsed_date.isoformat() if parsed_date else None,
                "packet_url": pdfs[0] if pdfs else None,
            }

            if meeting_status:
                result["meeting_status"] = meeting_status

            return result

        except (aiohttp.ClientError, asyncio.TimeoutError) as e:
            logger.warning("failed to scrape meeting page", vendor="civicplus", slug=self.slug, url=url, error=str(e))
            return None

    async def _discover_pdfs_async(
        self, url: str, soup: BeautifulSoup, keywords: Optional[List[str]] = None
    ) -> List[str]:
        """Discover PDF links on a page, optionally filtering by keywords."""
        if keywords is None:
            keywords = ["agenda", "packet"]

        pdfs = []

        for link in soup.find_all("a", href=True):
            href = link["href"]
            text = link.get_text().lower()
            is_pdf = (
                ".pdf" in href.lower()
                or "pdf" in link.get("type", "").lower()
                or any(kw in text for kw in keywords)
            )

            if is_pdf:
                pdfs.append(urljoin(url, href))

        logger.debug("found PDFs", vendor="civicplus", slug=self.slug, pdf_count=len(pdfs), url=url[:100])
        return pdfs

    def _extract_date_from_page(self, soup: BeautifulSoup) -> Optional[str]:
        """Extract meeting date from page using common patterns."""
        date_patterns = [
            r"\b\d{1,2}/\d{1,2}/\d{4}\s+\d{1,2}:\d{2}\s*[APap][Mm]\b",  # MM/DD/YYYY HH:MM AM/PM
            r"\b\d{1,2}/\d{1,2}/\d{4}\b",  # MM/DD/YYYY
            r"\b[A-Z][a-z]+ \d{1,2}, \d{4}\s+\d{1,2}:\d{2}\s*[APap][Mm]\b",  # Month DD, YYYY HH:MM AM/PM
            r"\b[A-Z][a-z]+ \d{1,2}, \d{4}\b",  # Month DD, YYYY
        ]

        text = soup.get_text()
        for pattern in date_patterns:
            match = re.search(pattern, text)
            if match:
                return match.group(0)

        return None

    def _extract_date_from_title(self, title: str) -> Optional[str]:
        """Extract date from meeting title like 'October 22, 2025 Regular Meeting'"""
        date_patterns = [
            r"\b([A-Z][a-z]+)\s+(\d{1,2}),?\s+(\d{4})\b",  # Month DD, YYYY or Month DD YYYY
            r"\b(\d{1,2})/(\d{1,2})/(\d{4})\b",  # MM/DD/YYYY
        ]

        for pattern in date_patterns:
            match = re.search(pattern, title)
            if match:
                return match.group(0)

        return None

    def _extract_meeting_id(self, url: str) -> str:
        """Extract meeting ID from URL or generate hash fallback.

        Confidence: 8/10 - Normalized URL hash is stable across syncs.
        Strips tracking params (session, utm_*) before hashing.
        """
        parsed = urlparse(url)

        # Prefer explicit id parameter
        if "id=" in parsed.query.lower():
            match = re.search(r"id=(\d+)", parsed.query, re.IGNORECASE)
            if match:
                return f"civic_{match.group(1)}"

        # Fallback: Hash normalized URL (strip tracking params for stability)
        # Keep only path and meaningful params, ignore session/tracking
        tracking_params = {'session', 'sessionid', 'sid', 'utm_source', 'utm_medium',
                          'utm_campaign', 'utm_content', 'utm_term', 'fbclid', 'gclid'}

        query_params = parse_qs(parsed.query)
        stable_params = {k: v for k, v in query_params.items()
                        if k.lower() not in tracking_params}

        # Build canonical URL for hashing
        canonical = f"{parsed.netloc}{parsed.path}"
        if stable_params:
            sorted_params = sorted(stable_params.items())
            canonical += "?" + "&".join(f"{k}={v[0]}" for k, v in sorted_params)

        return f"civic_{hashlib.md5(canonical.encode()).hexdigest()[:8]}"
