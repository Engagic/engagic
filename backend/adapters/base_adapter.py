"""
Base Adapter - Shared logic for all vendor adapters

Extracts common patterns:
- HTTP session with retry logic
- Date parsing across vendor formats
- PDF discovery from HTML
- Error handling and logging
"""

import logging
import requests
from typing import Optional, List, Dict, Any, Iterator
from datetime import datetime
from urllib.parse import urljoin
from bs4 import BeautifulSoup
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

logger = logging.getLogger("engagic")

# Polite scraping headers
DEFAULT_HEADERS = {
    "User-Agent": "Engagic/2.0 (Civic Engagement Bot; +https://engagic.org)",
    "Accept": "application/json, text/html, application/xhtml+xml, application/xml;q=0.9, */*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
    "Accept-Encoding": "gzip, deflate",
    "Connection": "keep-alive",
}


class BaseAdapter:
    """
    Base adapter with shared HTTP session, date parsing, and PDF discovery.

    Vendor-specific adapters extend this and implement fetch_meetings().
    """

    def __init__(self, city_slug: str, vendor: str):
        """
        Initialize adapter with city slug and vendor name.

        Args:
            city_slug: Vendor-specific city identifier (e.g., "cityofpaloalto")
            vendor: Vendor name for logging (e.g., "primegov")
        """
        if not city_slug:
            raise ValueError(f"city_slug required for {vendor}")

        self.slug = city_slug
        self.vendor = vendor
        self.session = self._create_session()

        logger.info(f"Initialized {vendor} adapter for {city_slug}")

    def _create_session(self) -> requests.Session:
        """
        Create HTTP session with retry logic and proper headers.

        Retry strategy:
        - 3 total retries
        - Exponential backoff (1s, 2s, 4s)
        - Retry on 429, 500, 502, 503, 504
        """
        session = requests.Session()
        session.headers.update(DEFAULT_HEADERS)

        retry_strategy = Retry(
            total=3,
            backoff_factor=1,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["GET", "POST", "HEAD"]
        )

        adapter = HTTPAdapter(max_retries=retry_strategy)
        session.mount("http://", adapter)
        session.mount("https://", adapter)

        return session

    def _get(self, url: str, **kwargs) -> requests.Response:
        """
        Make GET request with error handling and logging.

        Args:
            url: URL to fetch
            **kwargs: Additional arguments for requests.get

        Returns:
            Response object

        Raises:
            requests.RequestException on failure
        """
        kwargs.setdefault('timeout', 30)

        try:
            logger.debug(f"[{self.vendor}:{self.slug}] GET {url}")
            response = self.session.get(url, **kwargs)
            response.raise_for_status()
            return response
        except requests.Timeout:
            logger.error(f"[{self.vendor}:{self.slug}] Timeout fetching {url}")
            raise
        except requests.HTTPError as e:
            logger.error(f"[{self.vendor}:{self.slug}] HTTP {e.response.status_code} for {url}")
            raise
        except requests.RequestException as e:
            logger.error(f"[{self.vendor}:{self.slug}] Request failed for {url}: {e}")
            raise

    def _post(self, url: str, **kwargs) -> requests.Response:
        """Make POST request with error handling"""
        kwargs.setdefault('timeout', 30)

        try:
            logger.debug(f"[{self.vendor}:{self.slug}] POST {url}")
            response = self.session.post(url, **kwargs)
            response.raise_for_status()
            return response
        except requests.RequestException as e:
            logger.error(f"[{self.vendor}:{self.slug}] POST failed for {url}: {e}")
            raise

    def _parse_date(self, date_str: str) -> Optional[datetime]:
        """
        Parse date string from various vendor formats.

        Supports common municipal calendar formats:
        - ISO 8601: "2025-01-22T18:00:00Z"
        - US formats: "Jan 22, 2025 6:00 PM", "01/22/2025 6:00 PM"
        - Verbose: "January 22, 2025 at 6:00 PM"

        Args:
            date_str: Date string in various formats

        Returns:
            datetime object or None if parsing fails
        """
        if not date_str:
            return None

        # Common formats used by municipal calendar systems
        formats = [
            # ISO formats
            "%Y-%m-%dT%H:%M:%S.%fZ",
            "%Y-%m-%dT%H:%M:%SZ",
            "%Y-%m-%dT%H:%M:%S",
            "%Y-%m-%d %H:%M:%S",
            "%Y-%m-%d",

            # US formats with 12-hour time
            "%b %d, %Y %I:%M %p",      # Jul 22, 2025 6:30 PM
            "%B %d, %Y %I:%M %p",      # July 22, 2025 6:30 PM
            "%m/%d/%Y %I:%M %p",       # 07/22/2025 6:30 PM
            "%m/%d/%Y %I:%M:%S %p",    # 07/22/2025 6:30:00 PM

            # US formats with 24-hour time
            "%b %d, %Y %H:%M",         # Jul 22, 2025 18:30
            "%B %d, %Y %H:%M",         # July 22, 2025 18:30
            "%m/%d/%Y %H:%M",          # 07/22/2025 18:30

            # Date only formats
            "%b %d, %Y",               # Jul 22, 2025
            "%B %d, %Y",               # July 22, 2025
            "%m/%d/%Y",                # 07/22/2025
        ]

        # Try each format
        for fmt in formats:
            try:
                return datetime.strptime(date_str.strip(), fmt)
            except ValueError:
                continue

        # Fallback: Use dateutil parser for fuzzy parsing
        try:
            from dateutil import parser
            return parser.parse(date_str, fuzzy=True)
        except Exception:
            logger.warning(f"[{self.vendor}:{self.slug}] Could not parse date: {date_str}")
            return None

    def _fetch_html(self, url: str) -> BeautifulSoup:
        """
        Fetch URL and return BeautifulSoup object.

        Args:
            url: URL to fetch

        Returns:
            BeautifulSoup object
        """
        response = self._get(url)
        return BeautifulSoup(response.text, 'html.parser')

    def _discover_pdfs(self, url: str, keywords: List[str] = None) -> List[str]:
        """
        Discover PDF links on a page, optionally filtering by keywords.

        Args:
            url: URL to scrape for PDFs
            keywords: Optional list of keywords to filter PDF links (e.g., ["agenda", "packet"])

        Returns:
            List of absolute PDF URLs
        """
        if keywords is None:
            keywords = ["agenda", "packet"]

        try:
            soup = self._fetch_html(url)
            pdfs = []

            for link in soup.find_all('a', href=True):
                href = link['href']
                text = link.get_text().lower()

                # Check if link points to PDF
                is_pdf = (
                    '.pdf' in href.lower() or
                    'pdf' in link.get('type', '').lower() or
                    any(kw in text for kw in keywords)
                )

                if is_pdf:
                    # Convert to absolute URL
                    absolute_url = urljoin(url, href)
                    pdfs.append(absolute_url)

            logger.debug(f"[{self.vendor}:{self.slug}] Found {len(pdfs)} PDFs at {url}")
            return pdfs

        except Exception as e:
            logger.warning(f"[{self.vendor}:{self.slug}] PDF discovery failed for {url}: {e}")
            return []

    def _extract_text(self, soup: BeautifulSoup, selector: str) -> str:
        """
        Extract text from soup using CSS selector, handling missing elements.

        Args:
            soup: BeautifulSoup object
            selector: CSS selector

        Returns:
            Extracted text or empty string
        """
        element = soup.select_one(selector)
        return element.get_text(strip=True) if element else ""

    def _parse_meeting_status(self, title: str) -> Optional[str]:
        """
        Parse meeting title for status keywords.

        Common patterns:
        - [CANCELLED] - City Council Meeting
        - (POSTPONED) Regular Meeting
        - City Council - REVISED
        - RESCHEDULED: Planning Commission

        Args:
            title: Meeting title to parse

        Returns:
            Status string (cancelled, postponed, revised, rescheduled) or None
        """
        if not title:
            return None

        title_upper = title.upper()

        # Status keywords in priority order
        status_keywords = [
            ('CANCEL', 'cancelled'),
            ('POSTPONE', 'postponed'),
            ('RESCHEDULE', 'rescheduled'),
            ('REVISED', 'revised'),
            ('AMENDMENT', 'revised'),
            ('UPDATED', 'revised'),
        ]

        for keyword, status in status_keywords:
            if keyword in title_upper:
                logger.debug(f"[{self.vendor}:{self.slug}] Detected '{status}' status in title: {title}")
                return status

        return None

    def fetch_meetings(self) -> Iterator[Dict[str, Any]]:
        """
        Fetch meetings from vendor API/website.

        Must be implemented by subclass.

        Returns:
            Iterator of meeting dictionaries with keys:
                - meeting_id: str
                - title: str
                - start: str (ISO datetime)
                - packet_url: Optional[str]
                - meeting_status: Optional[str] (cancelled, postponed, revised, rescheduled)
        """
        raise NotImplementedError(f"{self.__class__.__name__} must implement fetch_meetings()")
