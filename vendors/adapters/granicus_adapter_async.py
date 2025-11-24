"""
Async Granicus Adapter - Concurrent HTML scraping for Granicus/Legistar platform

Async version with:
- Async view_id discovery (concurrent testing of candidates)
- Async HTML agenda parsing
- S3 SSL workaround (handled in base adapter)

Cities using Granicus: Cambridge MA, Santa Monica CA, and many others
"""

import json
import os
import asyncio
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
from vendors.adapters.base_adapter_async import AsyncBaseAdapter, logger
from vendors.adapters.parsers.granicus_parser import parse_html_agenda
from vendors.utils.item_filters import should_skip_procedural_item


class AsyncGranicusAdapter(AsyncBaseAdapter):
    """Async adapter for cities using Granicus/Legistar platform"""

    def __init__(self, city_slug: str):
        """
        Initialize async Granicus adapter with view_id discovery.

        Args:
            city_slug: Granicus subdomain (e.g., "cambridge")
        """
        super().__init__(city_slug, vendor="granicus")
        self.base_url = f"https://{self.slug}.granicus.com"
        self.view_ids_file = "data/granicus_view_ids.json"
        self.view_id: Optional[int] = None
        self.list_url: Optional[str] = None

    async def _initialize_view_id(self):
        """Initialize view_id (async, called before fetch_meetings)"""
        if self.view_id is not None:
            return  # Already initialized

        # Discover or load view_id
        self.view_id = await self._get_view_id_async()
        self.list_url = f"{self.base_url}/ViewPublisher.php?view_id={self.view_id}"

        logger.info("granicus using view_id", slug=self.slug, view_id=self.view_id)

    async def _get_view_id_async(self) -> int:
        """Get view_id from cache or discover it (async)"""
        mappings = self._load_view_id_mappings()

        if self.base_url in mappings:
            logger.info(
                "granicus found cached view_id",
                slug=self.slug,
                view_id=mappings[self.base_url]
            )
            return mappings[self.base_url]

        # Discover and cache (async)
        view_id = await self._discover_view_id_async()
        mappings[self.base_url] = view_id
        self._save_view_id_mappings(mappings)

        logger.info("granicus discovered view_id", slug=self.slug, view_id=view_id)
        return view_id

    def _load_view_id_mappings(self) -> Dict[str, int]:
        """Load view_id cache from disk"""
        if os.path.exists(self.view_ids_file):
            try:
                with open(self.view_ids_file, "r") as f:
                    return json.load(f)
            except Exception as e:
                logger.warning("could not load view_id cache", error=str(e))
        return {}

    def _save_view_id_mappings(self, mappings: Dict[str, int]):
        """Save view_id cache to disk"""
        os.makedirs(os.path.dirname(self.view_ids_file), exist_ok=True)
        with open(self.view_ids_file, "w") as f:
            json.dump(mappings, f, indent=2)

    async def _discover_view_id_async(self) -> int:
        """
        Brute force discover view_id by testing 1-100 (async, concurrent).

        Returns:
            Valid view_id

        Raises:
            RuntimeError if no view_id found
        """
        current_year = str(datetime.now().year)
        base_url = f"{self.base_url}/ViewPublisher.php?view_id="

        logger.info("granicus discovering view_id, testing 1-100", slug=self.slug)

        # Government meeting indicators (high priority)
        gov_indicators = [
            "city council",
            "planning commission",
            "board of supervisors",
            "town council",
            "village board",
            "board of trustees",
        ]

        # Test view_ids concurrently (batches of 10)
        candidates = []
        batch_size = 10

        for batch_start in range(1, 100, batch_size):
            batch_ids = range(batch_start, min(batch_start + batch_size, 100))
            batch_tasks = [
                self._test_view_id_async(f"{base_url}{i}", i, current_year, gov_indicators)
                for i in batch_ids
            ]
            batch_results = await asyncio.gather(*batch_tasks, return_exceptions=True)

            # Collect successful candidates
            for result in batch_results:
                if isinstance(result, tuple) and result is not None:
                    candidates.append(result)

        # Sort by score (descending) and return highest
        if candidates:
            candidates.sort(key=lambda x: x[1], reverse=True)
            best_view_id, best_score = candidates[0]
            logger.info(
                "granicus selected best view_id",
                slug=self.slug,
                view_id=best_view_id,
                score=best_score,
                candidates=len(candidates)
            )
            return best_view_id

        raise RuntimeError(f"Could not discover view_id for {self.slug}.granicus.com")

    async def _test_view_id_async(
        self,
        url: str,
        view_id: int,
        current_year: str,
        gov_indicators: List[str]
    ) -> Optional[tuple[int, int]]:
        """Test a single view_id (async)"""
        try:
            response = await self._get(url)
            text = await response.text()
            text_lower = text.lower()

            # Must have "upcoming" section
            if "upcoming" not in text_lower:
                return None

            # Must have basic meeting page indicators
            if not ("ViewPublisher" in text and current_year in text):
                return None

            # Score this candidate
            score = 5  # Baseline for having "upcoming"

            # High priority: government body names
            for indicator in gov_indicators:
                if indicator in text_lower:
                    score += 10

            # Low priority: general meeting/agenda indicators
            if "agenda" in text_lower or "meeting" in text_lower:
                score += 1

            logger.debug("granicus view_id candidate", slug=self.slug, view_id=view_id, score=score)
            return (view_id, score)

        except Exception:
            return None

    async def fetch_meetings(self, days_back: int = 7, days_forward: int = 14) -> List[Dict[str, Any]]:
        """
        Fetch meetings from Granicus HTML (async).

        Args:
            days_back: Days to look backward (default 7)
            days_forward: Days to look forward (default 14)

        Returns:
            List of meeting dictionaries
        """
        # Initialize view_id if needed
        await self._initialize_view_id()

        if not self.list_url:
            raise RuntimeError("view_id not initialized")

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

            # Build meeting dictionary
            meeting = {
                "meeting_id": meeting_data.get("meeting_id", ""),
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
                    if not should_skip_procedural_item(item.get("title", ""))
                ]
                if items:
                    meeting["items"] = items

            meetings.append(meeting)

        logger.info(
            "granicus meetings fetched",
            slug=self.slug,
            count=len(meetings)
        )

        return meetings
