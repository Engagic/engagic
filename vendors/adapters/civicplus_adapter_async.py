"""
Async CivicPlus Adapter - Complex discovery and scraping for CivicPlus sites

CivicPlus cities often redirect to other platforms (Granicus, Municode, etc.)
This adapter handles:
- Homepage scraping to detect external agenda systems
- Multiple agenda URL patterns
- PDF extraction from agenda pages

Async version with:
- aiohttp for async HTTP requests
- asyncio.to_thread for CPU-bound BeautifulSoup parsing
- Non-blocking I/O for concurrent city fetching
"""

import re
import asyncio
import hashlib
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
from urllib.parse import urlparse, urljoin

import aiohttp
from bs4 import BeautifulSoup

from vendors.adapters.base_adapter_async import AsyncBaseAdapter, logger
from pipeline.protocols import MetricsCollector


class AsyncCivicPlusAdapter(AsyncBaseAdapter):
    """Async adapter for cities using CivicPlus CMS (often with external agenda systems)"""

    def __init__(self, city_slug: str, metrics: Optional[MetricsCollector] = None):
        """city_slug is the CivicPlus subdomain (e.g., "cityname")"""
        super().__init__(city_slug, vendor="civicplus", metrics=metrics)
        self.base_url = f"https://{self.slug}.civicplus.com"

    async def _check_for_external_system(self) -> None:
        """Check homepage for external agenda system links (Granicus, Municode, Legistar, etc.)"""
        try:
            response = await self._get(self.base_url)
            html = await response.text()
            soup = await asyncio.to_thread(BeautifulSoup, html, 'html.parser')

            known_systems = {
                "municodemeetings.com": "municode",
                "granicus.com": "granicus",
                "legistar.com": "legistar",
                "primegov.com": "primegov",
                "civicclerk.com": "civicclerk",
                "novusagenda.com": "novusagenda",
                "iqm2.com": "iqm2",
            }

            for link in soup.find_all("a", href=True):
                link_text = link.get_text().strip().lower()
                href = link["href"]

                if any(word in link_text for word in ["agenda", "meeting", "minutes"]):
                    if href.startswith("http") and "civicplus.com" not in href:
                        domain = urlparse(href).netloc

                        for pattern, vendor in known_systems.items():
                            if pattern in domain:
                                logger.warning(
                                    "city uses external agenda system",
                                    vendor="civicplus",
                                    slug=self.slug,
                                    detected_vendor=vendor,
                                    domain=domain,
                                    action="update city config to use correct adapter"
                                )
                                break

        except (aiohttp.ClientError, asyncio.TimeoutError) as e:
            logger.debug(
                "could not check for external system",
                vendor="civicplus",
                slug=self.slug,
                error=str(e)
            )

    async def _find_agenda_url(self) -> Optional[str]:
        """Discover agenda page URL from common CivicPlus patterns."""
        patterns = [
            "/AgendaCenter",
            "/Calendar.aspx",
            "/calendar",
            "/meetings",
            "/agendas",
        ]

        for pattern in patterns:
            test_url = f"{self.base_url}{pattern}"
            try:
                response = await self._get(test_url)
                html = await response.text()
                if response.status == 200 and (
                    "agenda" in html.lower()
                    or "meeting" in html.lower()
                ):
                    logger.info("found agenda page", vendor="civicplus", slug=self.slug, pattern=pattern)
                    return test_url
            except (aiohttp.ClientError, asyncio.TimeoutError):
                continue

        logger.warning("could not find agenda page", vendor="civicplus", slug=self.slug)
        return None

    async def _fetch_meetings_impl(self, days_back: int = 7, days_forward: int = 14) -> List[Dict[str, Any]]:
        """Scrape AgendaCenter HTML and filter meetings by date range."""
        await self._check_for_external_system()

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

            logger.info(
                "filtered meetings in date range",
                vendor="civicplus",
                slug=self.slug,
                count=len(results),
                start_date=str(start_date.date()),
                end_date=str(end_date.date())
            )

            return results

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

            # Skip navigation links
            if text.startswith("<<<") or text.startswith("Back to") or text == "Agendas & Minutes":
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

    def _create_meeting_from_viewfile_link(self, link_data: Dict[str, str]) -> Optional[Dict[str, Any]]:
        """Create meeting dict directly from ViewFile link without scraping."""
        url = link_data["url"]
        title = link_data["title"]
        date_text = self._extract_date_from_title(title)
        parsed_date = self._parse_date(date_text) if date_text else None
        meeting_id = self._extract_meeting_id(url)
        meeting_status = self._parse_meeting_status(title, date_text)

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
        """Extract meeting ID from URL or generate hash fallback."""
        parsed = urlparse(url)
        if "id=" in parsed.query:
            match = re.search(r"id=(\d+)", parsed.query)
            if match:
                return f"civic_{match.group(1)}"
        return f"civic_{hashlib.md5(url.encode()).hexdigest()[:8]}"
