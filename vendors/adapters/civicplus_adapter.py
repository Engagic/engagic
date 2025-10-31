"""
CivicPlus Adapter - Complex discovery and scraping for CivicPlus sites

CivicPlus cities often redirect to other platforms (Granicus, Municode, etc.)
This adapter handles:
- Homepage scraping to detect external agenda systems
- Multiple agenda URL patterns
- PDF extraction from agenda pages
"""

import re
from typing import Dict, Any, List, Optional, Iterator
from urllib.parse import urlparse, urljoin
from datetime import datetime, timedelta
from bs4 import BeautifulSoup
from vendors.adapters.base_adapter import BaseAdapter, logger


class CivicPlusAdapter(BaseAdapter):
    """Adapter for cities using CivicPlus CMS (often with external agenda systems)"""

    def __init__(self, city_slug: str):
        """
        Initialize CivicPlus adapter.

        Args:
            city_slug: CivicPlus subdomain (e.g., "cityname" for cityname.civicplus.com)
        """
        super().__init__(city_slug, vendor="civicplus")
        self.base_url = f"https://{self.slug}.civicplus.com"

        # Detect if city uses external agenda system
        self._check_for_external_system()

    def _check_for_external_system(self):
        """
        Check homepage for external agenda system links.

        Many CivicPlus cities link to Granicus, Municode, Legistar, etc.
        """
        try:
            soup = self._fetch_html(self.base_url)

            known_systems = {
                "municodemeetings.com": "municode",
                "granicus.com": "granicus",
                "legistar.com": "legistar",
                "primegov.com": "primegov",
                "civicclerk.com": "civicclerk",
                "novusagenda.com": "novusagenda",
                "iqm2.com": "granicus",
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
                                    f"[civicplus:{self.slug}] City uses {vendor} ({domain}), not CivicPlus! "
                                    f"Update city config to use {vendor} adapter"
                                )
                                break

        except Exception as e:
            logger.debug(
                f"[civicplus:{self.slug}] Could not check for external system: {e}"
            )

    def _find_agenda_url(self) -> Optional[str]:
        """
        Discover agenda page URL from common CivicPlus patterns.

        Returns:
            Agenda page URL or None
        """
        # Common CivicPlus agenda URL patterns
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
                response = self._get(test_url)
                if response.status_code == 200 and (
                    "agenda" in response.text.lower()
                    or "meeting" in response.text.lower()
                ):
                    logger.info(f"[civicplus:{self.slug}] Found agenda page: {pattern}")
                    return test_url
            except Exception:
                continue

        logger.warning(f"[civicplus:{self.slug}] Could not find agenda page")
        return None

    def fetch_meetings(self) -> Iterator[Dict[str, Any]]:
        """
        Fetch meetings from CivicPlus site with date filtering.

        Uses AgendaCenter Search endpoint to limit results to recent meetings only.
        Default: today to 2 weeks forward.

        Yields:
            Meeting dictionaries with meeting_id, title, start, packet_url
        """
        agenda_url = self._find_agenda_url()
        if not agenda_url:
            logger.error(
                f"[civicplus:{self.slug}] No agenda page found - cannot fetch meetings"
            )
            return

        try:
            # Calculate date range: today to 2 weeks from now
            today = datetime.now()
            end_date = today + timedelta(weeks=2)

            # Format dates as MM/DD/YYYY for CivicPlus
            start_str = today.strftime("%m/%d/%Y")
            end_str = end_date.strftime("%m/%d/%Y")

            # Use Search endpoint with date filters if /AgendaCenter exists
            if "/AgendaCenter" in agenda_url:
                search_url = f"{self.base_url}/AgendaCenter/Search/?term=&CIDs=all&startDate={start_str}&endDate={end_str}"
                logger.info(
                    f"[civicplus:{self.slug}] Using date-filtered search: {start_str} to {end_str}"
                )
                soup = self._fetch_html(search_url)
            else:
                soup = self._fetch_html(agenda_url)

            # Try to find meeting links
            meeting_links = self._extract_meeting_links(soup, agenda_url)

            logger.info(
                f"[civicplus:{self.slug}] Found {len(meeting_links)} potential meeting links"
            )

            for link_data in meeting_links:
                # Try to extract meeting info and PDFs
                meeting = self._scrape_meeting_page(
                    link_data["url"], link_data["title"]
                )
                if meeting:
                    yield meeting

        except Exception as e:
            logger.error(f"[civicplus:{self.slug}] Failed to fetch meetings: {e}")

    def _extract_meeting_links(
        self, soup: BeautifulSoup, base_url: str
    ) -> List[Dict[str, str]]:
        """
        Extract meeting detail page links from agenda listing.

        Args:
            soup: BeautifulSoup of agenda page
            base_url: Base URL for relative links

        Returns:
            List of dicts with 'url' and 'title'
        """
        links = []

        # Look for links with "agenda", "meeting", or specific date patterns
        for link in soup.find_all("a", href=True):
            text = link.get_text(strip=True)
            href = link["href"]

            # Check if link looks like a meeting
            if any(word in text.lower() for word in ["agenda", "meeting", "minutes"]):
                absolute_url = urljoin(base_url, href)
                links.append({"url": absolute_url, "title": text})

        return links

    def _scrape_meeting_page(self, url: str, title: str) -> Optional[Dict[str, Any]]:
        """
        Scrape individual meeting page for metadata and PDF links.

        Args:
            url: Meeting detail page URL
            title: Meeting title from listing

        Returns:
            Meeting dict or None if scraping fails
        """
        try:
            soup = self._fetch_html(url)

            # Extract date string from page or title
            date_text = self._extract_date_from_page(soup)
            if not date_text:
                # Try extracting from title (e.g., "October 22, 2025 Regular Meeting")
                date_text = self._extract_date_from_title(title)

            # Parse the date string using BaseAdapter's robust parser
            parsed_date = self._parse_date(date_text) if date_text else None

            # Find PDF links
            pdfs = self._discover_pdfs(url, keywords=["agenda", "packet", "minutes"])

            # Generate meeting ID from URL
            meeting_id = self._extract_meeting_id(url)

            # Parse meeting status from title and date
            meeting_status = self._parse_meeting_status(title, date_text)

            # Log if no PDFs (but still track the meeting)
            if not pdfs:
                logger.debug(f"[civicplus:{self.slug}] No PDFs found for: {title}")

            result = {
                "meeting_id": meeting_id,
                "title": title,
                "start": parsed_date.isoformat() if parsed_date else None,
                "packet_url": pdfs[0] if len(pdfs) == 1 else (pdfs if pdfs else None),
            }

            if meeting_status:
                result["meeting_status"] = meeting_status

            return result

        except Exception as e:
            logger.warning(f"[civicplus:{self.slug}] Failed to scrape {url}: {e}")
            return None

    def _extract_date_from_page(self, soup: BeautifulSoup) -> Optional[str]:
        """Extract meeting date from page using common patterns"""
        # Look for common date patterns in text
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
        """Extract meeting ID from URL or generate from hash"""
        # Try to extract ID from URL parameters
        import hashlib

        parsed = urlparse(url)

        # Look for common ID parameters
        if "id=" in parsed.query:
            match = re.search(r"id=(\d+)", parsed.query)
            if match:
                return f"civic_{match.group(1)}"

        # Fallback: hash the URL
        return f"civic_{hashlib.md5(url.encode()).hexdigest()[:8]}"
