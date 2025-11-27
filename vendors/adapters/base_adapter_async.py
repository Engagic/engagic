"""
Async Base Adapter - Shared logic for all async vendor adapters

Async version of base_adapter.py with:
- aiohttp for async HTTP requests
- AsyncSessionManager for connection pooling
- Non-blocking I/O for concurrent city fetching
- Same error handling and logging as sync version

Extracts common patterns:
- Async HTTP session with error handling
- Date parsing across vendor formats
- PDF discovery from HTML
- Error handling and logging
"""

import asyncio
import time
from typing import Optional, List, Dict, Any
from datetime import datetime
from urllib.parse import urljoin
from bs4 import BeautifulSoup
import aiohttp

from config import get_logger
from server.metrics import metrics
from vendors.session_manager_async import AsyncSessionManager
from exceptions import VendorHTTPError

logger = get_logger(__name__).bind(component="vendor")


class AsyncBaseAdapter:
    """
    Async base adapter with shared HTTP session, date parsing, and PDF discovery.

    Vendor-specific async adapters extend this and implement fetch_meetings().
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

        logger.info("initialized async adapter", vendor=vendor, city_slug=city_slug)

    async def _get_session(self) -> aiohttp.ClientSession:
        """Get shared async session for this vendor"""
        return await AsyncSessionManager.get_session(self.vendor)

    async def _get(self, url: str, **kwargs) -> aiohttp.ClientResponse:
        """
        Make async GET request with error handling and logging.

        Args:
            url: URL to fetch
            **kwargs: Additional arguments for aiohttp.get

        Returns:
            ClientResponse object (must read with .text(), .json(), etc.)

        Raises:
            VendorHTTPError on failure
        """
        session = await self._get_session()

        # Set default timeout if not specified
        if "timeout" not in kwargs:
            kwargs["timeout"] = aiohttp.ClientTimeout(total=30)

        # For Legistar API endpoints, prefer JSON over XML
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
            kwargs["ssl"] = False

        # Track request duration
        start_time = time.time()

        try:
            logger.debug("vendor request", vendor=self.vendor, slug=self.slug, method="GET", url=url[:100])

            # Don't use context manager - return unconsumed response for caller to use
            response = await session.get(url, **kwargs)

            # Get metadata from headers (don't consume body yet)
            content_length = response.headers.get('content-length', 'unknown')
            content_type = response.headers.get('content-type', 'unknown')
            duration = time.time() - start_time

            logger.debug(
                "vendor response",
                vendor=self.vendor,
                slug=self.slug,
                status_code=response.status,
                content_length=content_length,
                content_type=content_type,
                duration_seconds=round(duration, 2)
            )

            # Check for HTTP errors
            if response.status >= 400:
                # For errors, consume body for logging then raise
                error_body = await response.text()
                metrics.vendor_requests.labels(vendor=self.vendor, status=f"http_{response.status}").inc()
                metrics.record_error(component="vendor", error=VendorHTTPError(
                    f"HTTP {response.status} error",
                    vendor=self.vendor,
                    status_code=response.status,
                    url=url,
                    city_slug=self.slug
                ))
                logger.error(
                    "vendor http error",
                    vendor=self.vendor,
                    slug=self.slug,
                    status_code=response.status,
                    url=url[:100],
                    error_body=error_body[:500] if error_body else None,
                    duration_seconds=round(duration, 2)
                )
                raise VendorHTTPError(
                    f"HTTP {response.status} error",
                    vendor=self.vendor,
                    status_code=response.status,
                    url=url,
                    city_slug=self.slug
                )

            # Record successful request
            metrics.vendor_requests.labels(vendor=self.vendor, status="success").inc()
            metrics.vendor_request_duration.labels(vendor=self.vendor).observe(duration)

            # Return unconsumed response - caller will call await response.text() or .json()
            return response

        except asyncio.TimeoutError as e:
            duration = time.time() - start_time
            metrics.vendor_requests.labels(vendor=self.vendor, status="timeout").inc()
            metrics.record_error(component="vendor", error=e)
            logger.error(
                "vendor request timeout",
                vendor=self.vendor,
                slug=self.slug,
                url=url[:100],
                duration_seconds=round(duration, 2)
            )
            raise VendorHTTPError(
                f"Request timeout after {duration:.1f}s",
                vendor=self.vendor,
                url=url,
                city_slug=self.slug
            ) from e
        except aiohttp.ClientError as e:
            duration = time.time() - start_time
            metrics.vendor_requests.labels(vendor=self.vendor, status="error").inc()
            metrics.record_error(component="vendor", error=e)
            logger.error(
                "vendor request failed",
                vendor=self.vendor,
                slug=self.slug,
                url=url[:100],
                error=str(e),
                error_type=type(e).__name__,
                duration_seconds=round(duration, 2)
            )
            raise VendorHTTPError(
                f"Request failed: {str(e)}",
                vendor=self.vendor,
                url=url,
                city_slug=self.slug
            ) from e

    async def _post(self, url: str, **kwargs) -> aiohttp.ClientResponse:
        """
        Make async POST request with error handling.

        Args:
            url: URL to post to
            **kwargs: Additional arguments for aiohttp.post

        Returns:
            ClientResponse object (must read with .text(), .json(), etc.)

        Raises:
            VendorHTTPError on failure
        """
        session = await self._get_session()

        # Set default timeout if not specified
        if "timeout" not in kwargs:
            kwargs["timeout"] = aiohttp.ClientTimeout(total=30)

        # Track request duration
        start_time = time.time()

        try:
            logger.debug("vendor request", vendor=self.vendor, slug=self.slug, method="POST", url=url[:100])

            # Don't use context manager - return unconsumed response for caller to use
            response = await session.post(url, **kwargs)

            # Get metadata from headers (don't consume body yet)
            content_length = response.headers.get('content-length', 'unknown')
            content_type = response.headers.get('content-type', 'unknown')
            duration = time.time() - start_time

            logger.debug(
                "vendor response",
                vendor=self.vendor,
                slug=self.slug,
                status_code=response.status,
                content_length=content_length,
                content_type=content_type,
                duration_seconds=round(duration, 2)
            )

            # Check for HTTP errors
            if response.status >= 400:
                # For errors, consume body for logging then raise
                error_body = await response.text()
                metrics.vendor_requests.labels(vendor=self.vendor, status=f"http_{response.status}").inc()
                metrics.record_error(component="vendor", error=VendorHTTPError(
                    f"HTTP {response.status} error",
                    vendor=self.vendor,
                    status_code=response.status,
                    url=url,
                    city_slug=self.slug
                ))
                logger.error(
                    "vendor POST failed",
                    vendor=self.vendor,
                    slug=self.slug,
                    status_code=response.status,
                    url=url[:100],
                    error_body=error_body[:500] if error_body else None,
                    duration_seconds=round(duration, 2)
                )
                raise VendorHTTPError(
                    f"HTTP {response.status} error",
                    vendor=self.vendor,
                    status_code=response.status,
                    url=url,
                    city_slug=self.slug
                )

            # Record successful request
            metrics.vendor_requests.labels(vendor=self.vendor, status="success").inc()
            metrics.vendor_request_duration.labels(vendor=self.vendor).observe(duration)

            # Return unconsumed response - caller will call await response.text() or .json()
            return response

        except asyncio.TimeoutError as e:
            duration = time.time() - start_time
            metrics.vendor_requests.labels(vendor=self.vendor, status="timeout").inc()
            metrics.record_error(component="vendor", error=e)
            logger.error(
                "vendor POST timeout",
                vendor=self.vendor,
                slug=self.slug,
                url=url[:100],
                duration_seconds=round(duration, 2)
            )
            raise VendorHTTPError(
                f"POST timeout after {duration:.1f}s",
                vendor=self.vendor,
                url=url,
                city_slug=self.slug
            ) from e
        except aiohttp.ClientError as e:
            duration = time.time() - start_time
            metrics.vendor_requests.labels(vendor=self.vendor, status="error").inc()
            metrics.record_error(component="vendor", error=e)
            logger.error(
                "vendor POST failed",
                vendor=self.vendor,
                slug=self.slug,
                url=url[:100],
                error=str(e),
                error_type=type(e).__name__,
                duration_seconds=round(duration, 2)
            )
            raise VendorHTTPError(
                f"POST request failed: {str(e)}",
                vendor=self.vendor,
                url=url,
                city_slug=self.slug
            ) from e

    async def _get_json(self, url: str, **kwargs) -> Any:
        """
        Make async GET request and parse JSON response with error handling.

        Args:
            url: URL to fetch
            **kwargs: Additional arguments for aiohttp.get

        Returns:
            Parsed JSON data (dict or list)

        Raises:
            VendorHTTPError on HTTP or JSON parsing failure
        """
        response = await self._get(url, **kwargs)
        try:
            return await response.json()
        except aiohttp.ContentTypeError as e:
            # Server returned non-JSON content type
            text = await response.text()
            logger.error(
                "vendor json parse failed",
                vendor=self.vendor,
                slug=self.slug,
                url=url[:100],
                error="unexpected content type",
                content_type=response.headers.get('content-type', 'unknown'),
                body_preview=text[:200] if text else None
            )
            raise VendorHTTPError(
                f"Expected JSON but got {response.headers.get('content-type', 'unknown')}",
                vendor=self.vendor,
                url=url,
                city_slug=self.slug
            ) from e
        except Exception as e:
            # JSONDecodeError or other parsing issues
            try:
                text = await response.text()
            except Exception:
                text = "(unable to read response body)"
            logger.error(
                "vendor json parse failed",
                vendor=self.vendor,
                slug=self.slug,
                url=url[:100],
                error=str(e),
                error_type=type(e).__name__,
                body_preview=text[:200] if text else None
            )
            raise VendorHTTPError(
                f"JSON parse failed: {str(e)}",
                vendor=self.vendor,
                url=url,
                city_slug=self.slug
            ) from e

    def _parse_date(self, date_str: str) -> Optional[datetime]:
        """
        Parse date string from various vendor formats.

        Supports common municipal calendar formats:
        - ISO 8601: "2025-01-22T18:00:00Z", "2025-01-22T18:00:00+00:00"
        - US formats: "Jan 22, 2025 6:00 PM", "01/22/2025 6:00 PM"
        - Verbose: "January 22, 2025 at 6:00 PM"

        Args:
            date_str: Date string in various formats

        Returns:
            Naive datetime object (tzinfo stripped) or None if parsing fails

        NOTE: Always returns naive datetimes for database compatibility.
        Timezone info is stripped after parsing to avoid offset-aware/naive mixing.
        """
        if not date_str:
            return None

        date_str = date_str.strip()

        # Try ISO 8601 first using fromisoformat (handles timezone properly)
        if 'T' in date_str or date_str.count('-') >= 2:
            try:
                # Handle 'Z' suffix (UTC)
                iso_str = date_str.replace('Z', '+00:00')
                dt = datetime.fromisoformat(iso_str)
                # Strip timezone for database compatibility
                return dt.replace(tzinfo=None)
            except ValueError:
                pass

        # Common formats used by municipal calendar systems
        formats = [
            # US formats with 12-hour time
            "%b %d, %Y %I:%M %p",
            "%B %d, %Y %I:%M %p",
            "%m/%d/%Y %I:%M %p",
            "%m/%d/%Y %I:%M:%S %p",
            # US formats with 24-hour time
            "%b %d, %Y %H:%M",
            "%B %d, %Y %H:%M",
            "%m/%d/%Y %H:%M",
            # Date only formats
            "%Y-%m-%d",
            "%b %d, %Y",
            "%B %d, %Y",
            "%m/%d/%Y",
            # Verbose formats
            "%B %d, %Y at %I:%M %p",
            # Escribe format: "Tuesday, December 02, 2025 @ 5:30 PM"
            "%A, %B %d, %Y @ %I:%M %p",
        ]

        for fmt in formats:
            try:
                return datetime.strptime(date_str, fmt)
            except (ValueError, AttributeError):
                continue

        logger.warning("failed to parse date", date_str=date_str, vendor=self.vendor)
        return None

    def _find_pdf_in_html(self, html: str, base_url: str) -> Optional[str]:
        """
        Find PDF link in HTML content.

        Args:
            html: HTML content
            base_url: Base URL for resolving relative links

        Returns:
            Absolute PDF URL or None
        """
        soup = BeautifulSoup(html, 'html.parser')

        # Find links with .pdf extension
        for link in soup.find_all('a', href=True):
            href = link['href']  # type: ignore[index]
            if '.pdf' in href.lower():  # type: ignore[union-attr]
                # Convert to absolute URL
                return urljoin(base_url, href)  # type: ignore[arg-type]

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
            "generated fallback meeting_id",
            vendor=self.vendor,
            slug=self.slug,
            meeting_id=meeting_id,
            title=title,
            date=date_str
        )
        return meeting_id

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
                        "detected meeting status in title",
                        vendor=self.vendor,
                        slug=self.slug,
                        status=status,
                        title=title
                    )
                    current_status = status
        # Check date/time string
        if date_str:
            date_upper = str(date_str).upper()
            for keyword, status in status_keywords:
                if keyword in date_upper:
                    logger.debug(
                        "detected meeting status in date",
                        vendor=self.vendor,
                        slug=self.slug,
                        status=status,
                        date=date_str
                    )
                    current_status = status

        return current_status

    async def fetch_meetings(self) -> List[Dict[str, Any]]:
        """
        Fetch meetings from vendor (to be implemented by subclasses).

        Returns:
            List of meeting dictionaries

        Raises:
            NotImplementedError: Subclass must implement this method
        """
        raise NotImplementedError(f"{self.__class__.__name__} must implement fetch_meetings()")
