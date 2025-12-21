"""
Async Granicus Adapter - Concurrent HTML scraping for Granicus platform

Two-step fetching:
1. ViewPublisher.php - List of meetings
2. AgendaViewer.php -> follows redirect -> actual agenda HTML

Supports multiple HTML formats:
- AgendaOnline (meetings.{city}.org) - parsed with parse_agendaonline_html
- Original Granicus format - parsed with parse_agendaviewer_html

Cities using Granicus: Cambridge MA, Santa Monica CA, Redwood City CA, and many others
"""

import json
import os
import asyncio
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from vendors.adapters.base_adapter_async import AsyncBaseAdapter, logger
from vendors.adapters.parsers.granicus_parser import (
    parse_viewpublisher_listing,
    parse_agendaonline_html,
    parse_agendaviewer_html,
)
from pipeline.filters import should_skip_item
from pipeline.protocols import MetricsCollector


class AsyncGranicusAdapter(AsyncBaseAdapter):
    """Async adapter for cities using Granicus platform."""

    def __init__(self, city_slug: str, metrics: Optional[MetricsCollector] = None):
        """city_slug is the Granicus subdomain (e.g., "redwoodcity-ca"). Raises ValueError if view_id not configured."""
        super().__init__(city_slug, vendor="granicus", metrics=metrics)
        self.base_url = f"https://{self.slug}.granicus.com"
        self.view_ids_file = "data/granicus_view_ids.json"

        # Load view_id from static configuration (fail-fast if not configured)
        mappings = self._load_static_view_id_config()
        if self.base_url not in mappings:
            raise ValueError(
                f"view_id not configured for {self.base_url}. "
                f"Add mapping to {self.view_ids_file}"
            )

        self.view_id: int = mappings[self.base_url]
        self.list_url: str = f"{self.base_url}/ViewPublisher.php?view_id={self.view_id}"

        logger.info("adapter initialized", vendor="granicus", slug=self.slug, view_id=self.view_id)

    def _load_static_view_id_config(self) -> Dict[str, int]:
        """Load view_id mappings from data/granicus_view_ids.json."""
        if not os.path.exists(self.view_ids_file):
            raise FileNotFoundError(
                f"Granicus view_id configuration not found: {self.view_ids_file}"
            )

        try:
            with open(self.view_ids_file, "r") as f:
                return json.load(f)
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON in {self.view_ids_file}: {e}")

    async def _fetch_meetings_impl(self, days_back: int = 7, days_forward: int = 14) -> List[Dict[str, Any]]:
        """Fetch meetings via two-step process: listing -> detail pages."""
        response = await self._get(self.list_url)
        html = await response.text()
        listing = await asyncio.to_thread(parse_viewpublisher_listing, html, self.base_url)

        if not listing:
            logger.warning("no meetings found in listing", vendor="granicus", slug=self.slug)
            return []

        today = datetime.now()
        start_date = today - timedelta(days=days_back)
        end_date = today + timedelta(days=days_forward)

        meetings_in_range = []
        for meeting_data in listing:
            date_str = meeting_data.get("start", "")
            if not date_str:
                # No date - include anyway (might be upcoming with no time set)
                meetings_in_range.append(meeting_data)
                continue

            try:
                meeting_date = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
                meeting_date = meeting_date.replace(tzinfo=None)
                if start_date <= meeting_date <= end_date:
                    meetings_in_range.append(meeting_data)
            except (ValueError, AttributeError):
                # Can't parse date - include anyway
                meetings_in_range.append(meeting_data)

        logger.debug(
            "filtered meetings by date",
            vendor="granicus",
            slug=self.slug,
            total=len(listing),
            in_range=len(meetings_in_range)
        )

        if not meetings_in_range:
            return []

        detail_tasks = [
            self._fetch_meeting_detail(meeting_data)
            for meeting_data in meetings_in_range
        ]

        results = await asyncio.gather(*detail_tasks, return_exceptions=True)

        meetings = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                logger.warning(
                    "failed to fetch meeting detail",
                    vendor="granicus",
                    slug=self.slug,
                    event_id=meetings_in_range[i].get("event_id"),
                    error=str(result)
                )
            elif result is not None:
                meetings.append(result)

        logger.info(
            "meetings fetched",
            vendor="granicus",
            slug=self.slug,
            count=len(meetings),
            with_items=sum(1 for m in meetings if m.get("items"))
        )

        return meetings

    async def _fetch_meeting_detail(self, meeting_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Fetch and parse individual meeting agenda, choosing parser based on redirect destination."""
        agenda_viewer_url = meeting_data.get("agenda_viewer_url")
        event_id = meeting_data.get("event_id")

        if not agenda_viewer_url:
            logger.debug(
                "no agenda viewer url",
                vendor="granicus",
                slug=self.slug,
                event_id=event_id
            )
            return None

        try:
            response = await self._get(agenda_viewer_url)
            final_url = str(response.url)
            html = await response.text()

            if "AgendaOnline" in final_url or "ViewAgenda" in final_url:
                parsed = await asyncio.to_thread(parse_agendaonline_html, html, final_url)
            else:
                parsed = await asyncio.to_thread(parse_agendaviewer_html, html)

            items = [
                item for item in parsed.get("items", [])
                if not should_skip_item(item.get("title", ""))
            ]

            meeting = {
                "vendor_id": event_id,
                "title": meeting_data.get("title", ""),
                "start": meeting_data.get("start", ""),
            }

            if items:
                meeting["items"] = items
                meeting["agenda_url"] = final_url
                logger.debug(
                    "parsed meeting with items",
                    vendor="granicus",
                    slug=self.slug,
                    event_id=event_id,
                    item_count=len(items)
                )
            else:
                packet_url = self._find_packet_url(html, final_url)
                if packet_url:
                    meeting["packet_url"] = packet_url
                    logger.debug(
                        "no items, using packet fallback",
                        vendor="granicus",
                        slug=self.slug,
                        event_id=event_id
                    )
                else:
                    logger.debug(
                        "no items or packet found",
                        vendor="granicus",
                        slug=self.slug,
                        event_id=event_id
                    )

            return meeting

        except Exception as e:
            logger.warning(
                "error fetching meeting detail",
                vendor="granicus",
                slug=self.slug,
                event_id=event_id,
                error=str(e)
            )
            return None

    def _find_packet_url(self, html: str, base_url: str) -> Optional[str]:
        """Find agenda packet PDF URL: MetaViewer > agenda/packet PDF > any PDF."""
        soup = BeautifulSoup(html, 'html.parser')

        meta_link = soup.find('a', href=lambda x: x and 'MetaViewer' in x if x else False)
        if meta_link:
            href = meta_link['href']
            if href.startswith('//'):
                return 'https:' + href
            return urljoin(base_url, href)

        for link in soup.find_all('a', href=True):
            href = link['href'].lower()
            text = link.get_text(strip=True).lower()
            if '.pdf' in href and ('agenda' in text or 'packet' in text or 'agenda' in href):
                full_href = link['href']
                if full_href.startswith('//'):
                    return 'https:' + full_href
                return urljoin(base_url, full_href)

        pdf_link = soup.find('a', href=lambda x: x and '.pdf' in x.lower() if x else False)
        if pdf_link:
            href = pdf_link['href']
            if href.startswith('//'):
                return 'https:' + href
            return urljoin(base_url, href)

        return None
