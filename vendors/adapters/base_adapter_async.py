"""Async Base Adapter - Shared HTTP, date parsing, PDF discovery for vendor adapters."""

import asyncio
import hashlib
import time
from typing import Optional, List, Dict, Any
from datetime import datetime
from urllib.parse import urljoin
from bs4 import BeautifulSoup
import aiohttp

from config import get_logger
from pipeline.protocols import MetricsCollector, NullMetrics
from vendors.session_manager_async import AsyncSessionManager
from exceptions import VendorHTTPError

logger = get_logger(__name__).bind(component="vendor")


class AsyncBaseAdapter:
    """Async base adapter. Subclasses implement _fetch_meetings_impl().

    Contract: config errors raise in __init__, runtime errors return [] from fetch_meetings().
    """

    def __init__(
        self,
        city_slug: str,
        vendor: str,
        metrics: Optional[MetricsCollector] = None
    ):
        if not city_slug:
            raise ValueError(f"city_slug required for {vendor}")

        self.slug = city_slug
        self.vendor = vendor
        self.metrics = metrics or NullMetrics()

        logger.info("initialized async adapter", vendor=vendor, city_slug=city_slug)

    async def _get_session(self) -> aiohttp.ClientSession:
        return await AsyncSessionManager.get_session(self.vendor)

    async def _request(self, method: str, url: str, **kwargs) -> aiohttp.ClientResponse:
        """Make async HTTP request with error handling. Raises VendorHTTPError on failure."""
        session = await self._get_session()

        if "timeout" not in kwargs:
            kwargs["timeout"] = aiohttp.ClientTimeout(total=30)

        # Legistar API: prefer JSON over XML
        if 'webapi.legistar.com' in url:
            headers = kwargs.get('headers', {})
            if 'Accept' not in headers:
                headers = headers.copy() if headers else {}
                headers['Accept'] = 'application/json, application/xml;q=0.9, */*;q=0.8'
                kwargs['headers'] = headers

        # Granicus has SSL cert issues on S3 redirects (confidence: 8/10)
        if self.vendor == "granicus" or "granicus.com" in url or "granicus_production_attachments" in url:
            kwargs["ssl"] = False

        start_time = time.time()

        try:
            logger.debug("vendor request", vendor=self.vendor, slug=self.slug, method=method, url=url[:100])
            response = await session.request(method, url, **kwargs)
            duration = time.time() - start_time

            logger.debug(
                "vendor response",
                vendor=self.vendor,
                slug=self.slug,
                status_code=response.status,
                content_length=response.headers.get('content-length', 'unknown'),
                content_type=response.headers.get('content-type', 'unknown'),
                duration_seconds=round(duration, 2)
            )

            if response.status >= 400:
                error_body = await response.text()
                self.metrics.vendor_requests.labels(vendor=self.vendor, status=f"http_{response.status}").inc()
                err = VendorHTTPError(
                    f"HTTP {response.status} error",
                    vendor=self.vendor,
                    status_code=response.status,
                    url=url,
                    city_slug=self.slug
                )
                self.metrics.record_error(component="vendor", error=err)
                logger.error(
                    "vendor http error",
                    vendor=self.vendor,
                    slug=self.slug,
                    status_code=response.status,
                    url=url[:100],
                    error_body=error_body[:500] if error_body else None,
                    duration_seconds=round(duration, 2)
                )
                raise err

            self.metrics.vendor_requests.labels(vendor=self.vendor, status="success").inc()
            self.metrics.vendor_request_duration.labels(vendor=self.vendor).observe(duration)
            return response

        except asyncio.TimeoutError as e:
            duration = time.time() - start_time
            self.metrics.vendor_requests.labels(vendor=self.vendor, status="timeout").inc()
            self.metrics.record_error(component="vendor", error=e)
            logger.error("vendor request timeout", vendor=self.vendor, slug=self.slug, url=url[:100], duration_seconds=round(duration, 2))
            raise VendorHTTPError(f"Request timeout after {duration:.1f}s", vendor=self.vendor, url=url, city_slug=self.slug) from e

        except aiohttp.ClientError as e:
            duration = time.time() - start_time
            self.metrics.vendor_requests.labels(vendor=self.vendor, status="error").inc()
            self.metrics.record_error(component="vendor", error=e)
            logger.error("vendor request failed", vendor=self.vendor, slug=self.slug, url=url[:100], error=str(e), error_type=type(e).__name__, duration_seconds=round(duration, 2))
            raise VendorHTTPError(f"Request failed: {e}", vendor=self.vendor, url=url, city_slug=self.slug) from e

    async def _get(self, url: str, **kwargs) -> aiohttp.ClientResponse:
        """GET request. Raises VendorHTTPError on failure."""
        return await self._request("GET", url, **kwargs)

    async def _post(self, url: str, **kwargs) -> aiohttp.ClientResponse:
        """POST request. Raises VendorHTTPError on failure."""
        return await self._request("POST", url, **kwargs)

    async def _get_json(self, url: str, **kwargs) -> Any:
        """GET request, parse JSON. Raises VendorHTTPError on failure."""
        response = await self._get(url, **kwargs)
        try:
            return await response.json()
        except aiohttp.ContentTypeError as e:
            text = await response.text()
            logger.error("vendor json parse failed", vendor=self.vendor, slug=self.slug, url=url[:100], content_type=response.headers.get('content-type', 'unknown'), body_preview=text[:200] if text else None)
            raise VendorHTTPError(f"Expected JSON but got {response.headers.get('content-type', 'unknown')}", vendor=self.vendor, url=url, city_slug=self.slug) from e
        except ValueError as e:
            try:
                text = await response.text()
            except aiohttp.ClientError:
                text = "(unable to read body)"
            logger.error("vendor json parse failed", vendor=self.vendor, slug=self.slug, url=url[:100], error=str(e), body_preview=text[:200] if text else None)
            raise VendorHTTPError(f"JSON parse failed: {e}", vendor=self.vendor, url=url, city_slug=self.slug) from e

    def _parse_date(self, date_str: str) -> Optional[datetime]:
        """Parse vendor date formats. Returns naive datetime or None."""
        if not date_str:
            return None

        date_str = date_str.strip()

        # ISO 8601 first
        if 'T' in date_str or date_str.count('-') >= 2:
            try:
                dt = datetime.fromisoformat(date_str.replace('Z', '+00:00'))
                return dt.replace(tzinfo=None)
            except ValueError:
                pass

        formats = [
            "%b %d, %Y %I:%M %p", "%B %d, %Y %I:%M %p", "%m/%d/%Y %I:%M %p", "%m/%d/%Y %I:%M:%S %p",
            "%b %d, %Y %H:%M", "%B %d, %Y %H:%M", "%m/%d/%Y %H:%M",
            "%Y-%m-%d", "%b %d, %Y", "%B %d, %Y", "%m/%d/%Y",
            "%B %d, %Y at %I:%M %p", "%A, %B %d, %Y @ %I:%M %p",
        ]

        for fmt in formats:
            try:
                return datetime.strptime(date_str, fmt)
            except (ValueError, AttributeError):
                continue

        logger.warning("failed to parse date", date_str=date_str, vendor=self.vendor)
        return None

    def _find_pdf_in_html(self, html: str, base_url: str) -> Optional[str]:
        """Find first PDF link in HTML, return absolute URL or None."""
        soup = BeautifulSoup(html, 'html.parser')
        for link in soup.find_all('a', href=True):
            href = link['href']  # type: ignore[index]
            if '.pdf' in href.lower():  # type: ignore[union-attr]
                return urljoin(base_url, href)  # type: ignore[arg-type]
        return None

    def _generate_fallback_vendor_id(self, title: str, date: Optional[datetime], meeting_type: Optional[str] = None) -> str:
        """Generate stable 8-char hash for vendors without native meeting IDs."""
        date_str = date.strftime("%Y%m%d") if date else "nodate"
        type_str = f"_{meeting_type}" if meeting_type else ""
        id_string = f"{self.slug}_{date_str}_{title}{type_str}"
        return hashlib.md5(id_string.encode()).hexdigest()[:8]

    def _parse_meeting_status(self, title: str, date_str: Optional[str] = None) -> Optional[str]:
        """Detect cancelled/postponed/revised status from title or date string."""
        status_keywords = [
            ("CANCEL", "cancelled"), ("POSTPONE", "postponed"), ("DEFER", "deferred"),
            ("RESCHEDULE", "rescheduled"), ("REVISED", "revised"), ("AMENDMENT", "revised"), ("UPDATED", "revised"),
        ]
        status = None
        for text in [title, date_str]:
            if not text:
                continue
            text_upper = str(text).upper()
            for keyword, label in status_keywords:
                if keyword in text_upper:
                    status = label
        return status

    def _validate_meeting(self, meeting: Dict[str, Any]) -> bool:
        """Check meeting has meeting_id, title, start. Returns False if missing."""
        required = {"meeting_id", "title", "start"}
        missing = required - set(meeting.keys())
        if missing:
            logger.warning("meeting missing required fields", vendor=self.vendor, slug=self.slug, missing=list(missing), title=str(meeting.get("title", "unknown"))[:50])
            return False
        return True

    async def fetch_meetings(self, days_back: int = 7, days_forward: int = 14) -> List[Dict[str, Any]]:
        """Fetch meetings, validate, return list. Returns [] on failure (never raises)."""
        try:
            meetings = await self._fetch_meetings_impl(days_back, days_forward)
            valid = [m for m in meetings if self._validate_meeting(m)]
            if len(valid) < len(meetings):
                logger.warning("filtered invalid meetings", vendor=self.vendor, slug=self.slug, total=len(meetings), valid=len(valid))
            return valid
        except NotImplementedError:
            raise
        except Exception as e:
            logger.error("fetch_meetings failed", vendor=self.vendor, slug=self.slug, error=str(e), error_type=type(e).__name__)
            return []

    async def _fetch_meetings_impl(self, days_back: int, days_forward: int) -> List[Dict[str, Any]]:
        """Subclass must implement. Return raw meeting dicts."""
        raise NotImplementedError(f"{self.__class__.__name__} must implement _fetch_meetings_impl()")
