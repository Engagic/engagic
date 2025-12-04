"""
Async Granicus Adapter - Concurrent HTML scraping for Granicus/Legistar platform

Async version with:
- Static view_id configuration (from data/granicus_view_ids.json)
- Async HTML agenda parsing
- S3 SSL workaround (handled in base adapter)

Cities using Granicus: Cambridge MA, Santa Monica CA, and many others
"""

import json
import os
import asyncio
from datetime import datetime, timedelta
from typing import Dict, Any, List
from vendors.adapters.base_adapter_async import AsyncBaseAdapter, logger
from vendors.adapters.parsers.granicus_parser import parse_html_agenda
from pipeline.filters import should_skip_item


class AsyncGranicusAdapter(AsyncBaseAdapter):
    """Async adapter for cities using Granicus/Legistar platform"""

    def __init__(self, city_slug: str):
        """
        Initialize async Granicus adapter with static view_id configuration.

        Args:
            city_slug: Granicus subdomain (e.g., "cambridge")

        Raises:
            ValueError: If view_id not configured for this city
        """
        super().__init__(city_slug, vendor="granicus")
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
        """
        Load view_id mappings from static configuration file.

        Returns:
            Dictionary mapping base URLs to view_ids

        Raises:
            FileNotFoundError: If config file doesn't exist
            ValueError: If config file is invalid JSON
        """
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
        """
        Fetch meetings from Granicus HTML (async).

        Args:
            days_back: Days to look backward (default 7)
            days_forward: Days to look forward (default 14)

        Returns:
            List of meeting dictionaries (validation in base class)
        """

        # Fetch HTML list page (async)
        response = await self._get(self.list_url)
        html = await response.text()

        # Parse HTML (sync - BeautifulSoup is CPU-bound, run in thread pool)
        parsed = await asyncio.to_thread(parse_html_agenda, html)

        # Filter by date range and process meetings
        meetings = []
        today = datetime.now()
        start_date = today - timedelta(days=days_back)
        end_date = today + timedelta(days=days_forward)

        for meeting_data in parsed.get("meetings", []):
            # Parse date
            date_str = meeting_data.get("start", "")
            if not date_str:
                continue

            try:
                meeting_date = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
                meeting_date = meeting_date.replace(tzinfo=None)

                # Filter by date range
                if not (start_date <= meeting_date <= end_date):
                    continue

            except (ValueError, AttributeError):
                # Include if date parsing fails
                pass

            meeting = {
                "vendor_id": meeting_data.get("meeting_id", ""),
                "title": meeting_data.get("title", ""),
                "start": date_str,
            }

            # Get agenda URL or packet URL
            if meeting_data.get("agenda_url"):
                meeting["agenda_url"] = meeting_data["agenda_url"]
            if meeting_data.get("packet_url"):
                meeting["packet_url"] = meeting_data["packet_url"]

            # Get items if available
            if meeting_data.get("items"):
                # Filter procedural items
                items = [
                    item for item in meeting_data["items"]
                    if not should_skip_item(item.get("title", ""))
                ]
                if items:
                    meeting["items"] = items

            meetings.append(meeting)

        logger.info(
            "meetings fetched",
            vendor="granicus",
            slug=self.slug,
            count=len(meetings)
        )

        return meetings
