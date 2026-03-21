"""
Async CivicEngage Archive Center Adapter

CivicEngage Archive Center is a CivicPlus product used by cities on custom .gov domains.
It's a document archive system (not a meeting calendar like CivicPlus AgendaCenter).

Two listing modes (auto-detected with fallback):

  Search mode (lngArchiveMasterID):
    https://{domain}/Archive.aspx?ysnExecuteSearch=1&lngArchiveMasterID=30&dtiStartDate=...&dtiEndDate=...
    Server-side date filtering. Used by most CivicEngage sites.

  AMID mode:
    https://{domain}/Archive.aspx?AMID=100
    No server-side date filtering — returns all documents in category.
    Used by sites like Wichita where lngArchiveMasterID doesn't match AMID.
    Client-side date filtering applied after fetch.

Both modes produce pages with ADID links:
  https://{domain}/Archive.aspx?ADID=8497  (resolves directly to PDF)

The adapter tries search mode first, falls back to AMID if no results.
"""

import re
import json
import os
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from vendors.adapters.base_adapter_async import AsyncBaseAdapter, logger
from pipeline.protocols import MetricsCollector
from config import config
from exceptions import VendorHTTPError

DEFAULT_CATEGORY_ID = 30  # City Council Agendas (common across CivicEngage sites)


class AsyncCivicEngageAdapter(AsyncBaseAdapter):
    """Async adapter for CivicPlus CivicEngage Archive Center sites."""

    def __init__(self, city_slug: str, metrics: Optional[MetricsCollector] = None):
        super().__init__(city_slug, vendor="civicengage", metrics=metrics)
        self._site_config = self._load_site_config()
        self.category_id = self._site_config.get("category_id", DEFAULT_CATEGORY_ID)
        # Allow domain override for cities on civicplus.com with state prefixes etc.
        domain_override = self._site_config.get("domain")
        self.base_url: Optional[str] = f"https://{domain_override}" if domain_override else None

    def _get_candidate_base_urls(self) -> List[str]:
        """Return candidate base URLs to try, in priority order."""
        slug = self.slug
        candidates = [
            f"https://{slug}.gov",
            f"https://www.{slug}.gov",
            f"https://{slug}.org",
            f"https://www.{slug}.org",
            f"https://{slug}.civicplus.com",
        ]
        # If slug already has a dot, it's a full domain — try it directly first
        if "." in slug:
            candidates.insert(0, f"https://{slug}")
        return candidates

    async def _discover_base_url(self) -> Optional[str]:
        """Discover working base URL by probing /Archive.aspx on candidate domains."""
        for base_url in self._get_candidate_base_urls():
            test_url = f"{base_url}/Archive.aspx"
            try:
                response = await self._get(test_url)
                html = await response.text()
                if response.status == 200 and "archive" in html.lower():
                    logger.info(
                        "discovered archive page",
                        vendor="civicengage",
                        slug=self.slug,
                        base_url=base_url,
                    )
                    return base_url
            except VendorHTTPError:
                continue

        logger.warning(
            "could not find archive page",
            vendor="civicengage",
            slug=self.slug,
        )
        return None

    def _load_site_config(self) -> Dict[str, Any]:
        """Load site-specific config (category_id, domain override, etc)."""
        config_file = os.path.join(config.DB_DIR, "civicengage_sites.json")
        if os.path.exists(config_file):
            try:
                with open(config_file) as f:
                    sites = json.load(f)
                    return sites.get(self.slug, {})
            except Exception:
                pass
        return {}

    async def _fetch_meetings_impl(
        self, days_back: int = 7, days_forward: int = 14
    ) -> List[Dict[str, Any]]:
        """Fetch agendas from CivicEngage Archive Center.

        Tries search mode (lngArchiveMasterID with date filtering) first.
        Falls back to AMID mode if search returns no results.
        """
        if not self.base_url:
            self.base_url = await self._discover_base_url()
        if not self.base_url:
            logger.error(
                "no archive page found - cannot fetch meetings",
                vendor="civicengage",
                slug=self.slug,
            )
            return []

        today = datetime.now()
        start_date = today - timedelta(days=days_back)
        end_date = today + timedelta(days=days_forward)

        # Try search mode first (server-side date filtering)
        listing_html = await self._fetch_listing_search(start_date, end_date)
        meetings = self._parse_listing_html(listing_html)

        if not meetings:
            # Fall back to AMID mode (no server-side date filtering)
            logger.info(
                "search mode returned no results, trying AMID mode",
                vendor="civicengage",
                slug=self.slug,
                category_id=self.category_id,
            )
            listing_html = await self._fetch_listing_amid()
            all_meetings = self._parse_listing_html(listing_html)

            # Client-side date filtering
            for m in all_meetings:
                if m.get("start"):
                    try:
                        meeting_date = datetime.fromisoformat(m["start"])
                        if start_date <= meeting_date <= end_date:
                            meetings.append(m)
                    except ValueError:
                        meetings.append(m)
                else:
                    meetings.append(m)

            logger.info(
                "AMID mode results",
                vendor="civicengage",
                slug=self.slug,
                total=len(all_meetings),
                in_range=len(meetings),
            )

        logger.info(
            "parsed meetings from listing",
            vendor="civicengage",
            slug=self.slug,
            count=len(meetings),
        )

        return meetings

    async def _fetch_listing_search(
        self, start_date: datetime, end_date: datetime
    ) -> str:
        """Fetch Archive.aspx listing with lngArchiveMasterID search (server-side date filter)."""
        url = (
            f"{self.base_url}/Archive.aspx"
            f"?ysnExecuteSearch=1"
            f"&txtKeywords="
            f"&lngArchiveMasterID={self.category_id}"
            f"&txtDateRange="
            f"&dtiStartDate={start_date.strftime('%m/%d/%Y')}"
            f"&dtiEndDate={end_date.strftime('%m/%d/%Y')}"
        )

        response = await self._get(url)
        return await response.text()

    async def _fetch_listing_amid(self) -> str:
        """Fetch Archive.aspx listing with AMID parameter (all documents in category)."""
        url = f"{self.base_url}/Archive.aspx?AMID={self.category_id}"
        response = await self._get(url)
        return await response.text()

    def _parse_listing_html(self, html: str) -> List[Dict[str, Any]]:
        """Parse ADID links from listing page into meeting dicts.

        Each ADID link provides:
        - title: from link text (e.g., "City Council Agenda - February 24, 2026")
        - packet_url: the ADID URL itself (resolves to PDF)
        - vendor_id: ce_adid_{ADID}
        - start: parsed from the title text
        """
        soup = BeautifulSoup(html, "html.parser")
        results = []
        seen_adids = set()

        for link in soup.find_all("a", href=re.compile(r"ADID=\d+")):
            href = link.get("href", "")
            title = link.get_text(strip=True)

            adid_match = re.search(r"ADID=(\d+)", str(href))
            if not adid_match or not title:
                continue

            adid = adid_match.group(1)
            if adid in seen_adids:
                continue
            seen_adids.add(adid)

            # Extract date from title
            date_str = self._extract_date_from_title(title)
            parsed_date = self._parse_date(date_str) if date_str else None

            # Detect meeting status
            meeting_status = self._parse_meeting_status(title, date_str)

            packet_url = urljoin(
                f"{self.base_url}/", str(href)
            )

            meeting: Dict[str, Any] = {
                "vendor_id": f"ce_adid_{adid}",
                "title": title,
                "start": parsed_date.isoformat() if parsed_date else "",
                "packet_url": packet_url,
            }

            if meeting_status:
                meeting["meeting_status"] = meeting_status

            results.append(meeting)

        return results

    def _extract_date_from_title(self, title: str) -> Optional[str]:
        """Extract date from titles like 'City Council Agenda - February 24, 2026'.

        Supports formats:
        - Full month: "February 24, 2026"
        - Slash numeric: "02/24/2026"
        - Dash numeric: "03-24-2026" (Wichita style)
        """
        # Full month name: "February 24, 2026"
        month_match = re.search(
            r"\b(?:January|February|March|April|May|June|July|August|"
            r"September|October|November|December)\s+\d{1,2},?\s+\d{4}\b",
            title,
            re.IGNORECASE,
        )
        if month_match:
            return month_match.group(0)

        # Slash numeric: "02/24/2026"
        slash_match = re.search(r"\b\d{1,2}/\d{1,2}/\d{4}\b", title)
        if slash_match:
            return slash_match.group(0)

        # Dash numeric: "03-24-2026" (e.g., Wichita)
        dash_match = re.search(r"\b(\d{1,2})-(\d{1,2})-(\d{4})\b", title)
        if dash_match:
            # Normalize to slash format for _parse_date
            return f"{dash_match.group(1)}/{dash_match.group(2)}/{dash_match.group(3)}"

        return None
