"""
Base Adapter - Shared logic for all vendor adapters

Extracts common patterns:
- HTTP session with retry logic
- Date parsing across vendor formats
- PDF discovery from HTML
- Error handling and logging
"""

import time
import requests
from typing import Optional, List, Dict, Any, Iterator
from datetime import datetime
from urllib.parse import urljoin
from bs4 import BeautifulSoup
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from config import get_logger
from server.metrics import metrics

logger = get_logger(__name__).bind(component="vendor")

# Browser-like headers to avoid bot detection
DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-User": "?1",
    "Cache-Control": "max-age=0",
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

    def __enter__(self):
        """Context manager entry - returns self for 'with' statement"""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit - cleanup session on exit"""
        if hasattr(self, "session"):
            self.session.close()
        return False

    def close(self):
        """Explicit cleanup method for non-context-manager usage"""
        if hasattr(self, "session"):
            self.session.close()

    def _create_session(self) -> requests.Session:
        """
        Create HTTP session with retry logic and proper headers.

        Retry strategy:
        - 3 total retries
        - Exponential backoff (1s, 2s, 4s)
        - Retry on 500, 502, 503, 504 (server errors only)
        - NOT 429: Rate limiting prevents this, if we hit it our delays are wrong
        """
        session = requests.Session()
        session.headers.update(DEFAULT_HEADERS)

        # Retry only on server errors, not rate limits (we prevent those)
        retry_strategy = Retry(
            total=3,
            backoff_factor=1,
            status_forcelist=[500, 502, 503, 504],
            allowed_methods=["GET", "POST", "HEAD"],
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
        kwargs.setdefault("timeout", 30)

        # For Legistar API endpoints, prefer JSON over XML
        # Default Accept header requests XML before JSON, causing APIs to return XML
        if 'webapi.legistar.com' in url:
            headers = kwargs.get('headers', {})
            if 'Accept' not in headers:
                headers = headers.copy() if headers else {}
                headers['Accept'] = 'application/json, application/xml;q=0.9, */*;q=0.8'
                kwargs['headers'] = headers

        # Disable SSL verification for Granicus domains (known S3 redirect issue)
        # Confidence: 8/10 - Safe for public civic data, Granicus infra issue
        # Granicus redirects to S3 with mismatched SSL certs, causing verification failures
        if (
            self.vendor == "granicus"
            or "granicus.com" in url
            or "granicus_production_attachments.s3.amazonaws.com" in url
        ):
            kwargs["verify"] = False
            import urllib3

            urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

        # Track request duration
        start_time = time.time()

        try:
            logger.debug("vendor request", vendor=self.vendor, slug=self.slug, method="GET", url=url[:100])
            response = self.session.get(url, **kwargs)

            # Log response details BEFORE raise_for_status so we see failures
            content_length = len(response.content)
            content_type = response.headers.get('content-type', 'unknown')
            duration = time.time() - start_time

            logger.debug(
                "vendor response",
                vendor=self.vendor,
                slug=self.slug,
                status_code=response.status_code,
                content_length=content_length,
                content_type=content_type,
                duration_seconds=round(duration, 2)
            )

            response.raise_for_status()

            # Record successful request
            metrics.vendor_requests.labels(vendor=self.vendor, status="success").inc()
            metrics.vendor_request_duration.labels(vendor=self.vendor).observe(duration)

            return response
        except requests.Timeout as e:
            duration = time.time() - start_time
            metrics.vendor_requests.labels(vendor=self.vendor, status="timeout").inc()
            metrics.record_error(component="vendor", error=e)
            logger.error("vendor request timeout", vendor=self.vendor, slug=self.slug, url=url[:100], duration_seconds=round(duration, 2))
            raise
        except requests.HTTPError as e:
            duration = time.time() - start_time
            metrics.vendor_requests.labels(vendor=self.vendor, status=f"http_{e.response.status_code}").inc()
            metrics.record_error(component="vendor", error=e)
            logger.error("vendor http error", vendor=self.vendor, slug=self.slug, status_code=e.response.status_code, url=url[:100], duration_seconds=round(duration, 2))
            raise
        except requests.RequestException as e:
            duration = time.time() - start_time
            metrics.vendor_requests.labels(vendor=self.vendor, status="error").inc()
            metrics.record_error(component="vendor", error=e)
            logger.error("vendor request failed", vendor=self.vendor, slug=self.slug, url=url[:100], error=str(e), error_type=type(e).__name__, duration_seconds=round(duration, 2))
            raise

    def _post(self, url: str, **kwargs) -> requests.Response:
        """Make POST request with error handling"""
        kwargs.setdefault("timeout", 30)

        # Track request duration
        start_time = time.time()

        try:
            logger.debug("vendor request", vendor=self.vendor, slug=self.slug, method="POST", url=url[:100])
            response = self.session.post(url, **kwargs)
            response.raise_for_status()

            # Log response summary
            content_length = len(response.content)
            content_type = response.headers.get('content-type', 'unknown')
            duration = time.time() - start_time

            logger.debug(
                "vendor response",
                vendor=self.vendor,
                slug=self.slug,
                status_code=response.status_code,
                content_length=content_length,
                content_type=content_type,
                duration_seconds=round(duration, 2)
            )

            # Record successful request
            metrics.vendor_requests.labels(vendor=self.vendor, status="success").inc()
            metrics.vendor_request_duration.labels(vendor=self.vendor).observe(duration)

            return response
        except requests.RequestException as e:
            duration = time.time() - start_time
            metrics.vendor_requests.labels(vendor=self.vendor, status="error").inc()
            metrics.record_error(component="vendor", error=e)
            logger.error("vendor POST failed", vendor=self.vendor, slug=self.slug, url=url[:100], error=str(e), error_type=type(e).__name__, duration_seconds=round(duration, 2))
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

        NOTE: Returning None for empty input is intentional - graceful handling of missing dates
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
            "%b %d, %Y %I:%M %p",  # Jul 22, 2025 6:30 PM
            "%B %d, %Y %I:%M %p",  # July 22, 2025 6:30 PM
            "%m/%d/%Y %I:%M %p",  # 07/22/2025 6:30 PM
            "%m/%d/%Y %I:%M:%S %p",  # 07/22/2025 6:30:00 PM
            # US formats with 24-hour time
            "%b %d, %Y %H:%M",  # Jul 22, 2025 18:30
            "%B %d, %Y %H:%M",  # July 22, 2025 18:30
            "%m/%d/%Y %H:%M",  # 07/22/2025 18:30
            # Date only formats
            "%b %d, %Y",  # Jul 22, 2025
            "%B %d, %Y",  # July 22, 2025
            "%m/%d/%Y",  # 07/22/2025
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
        except (ValueError, TypeError) as e:
            logger.warning(
                f"[{self.vendor}:{self.slug}] Could not parse date '{date_str}': {e}"
            )
            # NOTE: Returning None after logging warning is intentional - graceful failure for malformed dates
            return None

    def _generate_meeting_id(
        self,
        title: str,
        date: Optional[datetime],
        meeting_type: Optional[str] = None
    ) -> str:
        """Generate deterministic meeting ID when vendor doesn't provide one

        Uses MD5 hash of "{slug}_{date}_{title}_{type}" to create consistent
        8-character IDs. Ensures same meeting produces same ID across re-syncs.

        This is a FALLBACK for vendors that don't provide meeting IDs.
        Always prefer vendor-provided IDs when available.

        Args:
            title: Meeting title
            date: Meeting date (if available)
            meeting_type: Optional meeting type (for vendors that separate by type)

        Returns:
            8-character hexadecimal hash

        Example:
            >>> adapter._generate_meeting_id("City Council", datetime(2025, 1, 15))
            'a3f2c8d1'

        Confidence: 9/10 - Proven pattern from NovusAgenda adapter
        """
        import hashlib

        date_str = date.strftime("%Y%m%d") if date else "nodate"
        type_str = f"_{meeting_type}" if meeting_type else ""
        id_string = f"{self.slug}_{date_str}_{title}{type_str}"

        meeting_id = hashlib.md5(id_string.encode()).hexdigest()[:8]
        logger.debug(
            f"[{self.vendor}:{self.slug}] Generated fallback meeting_id: {meeting_id} "
            f"for '{title}' on {date_str}"
        )
        return meeting_id

    def _fetch_html(self, url: str) -> BeautifulSoup:
        """
        Fetch URL and return BeautifulSoup object.

        Args:
            url: URL to fetch

        Returns:
            BeautifulSoup object
        """
        response = self._get(url)
        return BeautifulSoup(response.text, "html.parser")

    def _discover_pdfs(
        self, url: str, keywords: Optional[List[str]] = None
    ) -> List[str]:
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

            for link in soup.find_all("a", href=True):
                href = link["href"]
                text = link.get_text().lower()

                # Check if link points to PDF
                is_pdf = (
                    ".pdf" in href.lower()
                    or "pdf" in link.get("type", "").lower()
                    or any(kw in text for kw in keywords)
                )

                if is_pdf:
                    # Convert to absolute URL
                    absolute_url = urljoin(url, href)
                    pdfs.append(absolute_url)

            logger.debug(f"[{self.vendor}:{self.slug}] Found {len(pdfs)} PDFs at {url}")
            return pdfs

        except Exception as e:
            logger.warning(
                f"[{self.vendor}:{self.slug}] PDF discovery failed for {url}: {e}"
            )
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

    def _parse_meeting_status(
        self, title: str, date_str: Optional[str] = None
    ) -> Optional[str]:
        """
        Parse meeting title and date/time for status keywords.

        Common patterns:
        - [CANCELLED] - City Council Meeting
        - (POSTPONED) Regular Meeting
        - City Council - REVISED
        - RESCHEDULED: Planning Commission
        - Date field: "POSTPONED - TBD"

        Args:
            title: Meeting title to parse
            date_str: Optional date/time string to check

        Returns:
            Status string (cancelled, postponed, revised, rescheduled, deferred) or None
        """
        # Status keywords in priority order
        status_keywords = [
            ("CANCEL", "cancelled"),
            ("POSTPONE", "postponed"),
            ("DEFER", "deferred"),
            ("RESCHEDULE", "rescheduled"),
            ("REVISED", "revised"),
            ("AMENDMENT", "revised"),
            ("UPDATED", "revised"),
        ]
        current_status = None
        # Check title
        if title:
            title_upper = title.upper()
            for keyword, status in status_keywords:
                if keyword in title_upper:
                    logger.debug(
                        f"[{self.vendor}:{self.slug}] Detected '{status}' in title: {title}"
                    )
                    current_status = status
        # Check date/time string
        if date_str:
            date_upper = str(date_str).upper()
            for keyword, status in status_keywords:
                if keyword in date_upper:
                    logger.debug(
                        f"[{self.vendor}:{self.slug}] Detected '{status}' in date: {date_str}"
                    )
                    current_status = status

        return current_status

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
        raise NotImplementedError(
            f"{self.__class__.__name__} must implement fetch_meetings()"
        )
