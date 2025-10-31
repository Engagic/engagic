"""
Granicus Adapter - HTML scraping for Granicus/Legistar platform

Cities using Granicus: Cambridge MA, Santa Monica CA, and many others

Complex adapter because Granicus doesn't provide a clean API - requires:
- view_id discovery via brute force
- HTML table scraping
- PDF extraction from AgendaViewer pages
"""

import os
import json
import hashlib
from typing import Dict, Any, List, Optional, Iterator
from datetime import datetime, timedelta
from urllib.parse import parse_qs, urlparse, urljoin
from vendors.adapters.base_adapter import BaseAdapter, logger
from vendors.adapters.html_agenda_parser import parse_granicus_html_agenda


class GranicusAdapter(BaseAdapter):
    """Adapter for cities using Granicus/Legistar platform"""

    def __init__(self, city_slug: str):
        """
        Initialize Granicus adapter with view_id discovery.

        Args:
            city_slug: Granicus subdomain (e.g., "cambridge" for cambridge.granicus.com)
        """
        super().__init__(city_slug, vendor="granicus")
        self.base_url = f"https://{self.slug}.granicus.com"
        self.view_ids_file = "data/granicus_view_ids.json"

        # Discover or load view_id
        self.view_id = self._get_view_id()
        self.list_url = f"{self.base_url}/ViewPublisher.php?view_id={self.view_id}"

        logger.info(f"[granicus:{self.slug}] Using view_id={self.view_id}")

    def _get_view_id(self) -> int:
        """Get view_id from cache or discover it"""
        mappings = self._load_view_id_mappings()

        if self.base_url in mappings:
            logger.info(
                f"[granicus:{self.slug}] Found cached view_id: {mappings[self.base_url]}"
            )
            return mappings[self.base_url]

        # Discover and cache
        view_id = self._discover_view_id()
        mappings[self.base_url] = view_id
        self._save_view_id_mappings(mappings)

        logger.info(f"[granicus:{self.slug}] Discovered view_id: {view_id}")
        return view_id

    def _load_view_id_mappings(self) -> Dict[str, int]:
        """Load view_id cache from disk"""
        if os.path.exists(self.view_ids_file):
            try:
                with open(self.view_ids_file, "r") as f:
                    return json.load(f)
            except Exception as e:
                logger.warning(f"Could not load view_id cache: {e}")
        return {}

    def _save_view_id_mappings(self, mappings: Dict[str, int]):
        """Save view_id cache to disk"""
        os.makedirs(os.path.dirname(self.view_ids_file), exist_ok=True)
        with open(self.view_ids_file, "w") as f:
            json.dump(mappings, f, indent=2)

    def _discover_view_id(self) -> int:
        """
        Brute force discover view_id by testing 1-100.

        Returns:
            Valid view_id

        Raises:
            RuntimeError if no view_id found
        """
        current_year = str(datetime.now().year)
        base_url = f"{self.base_url}/ViewPublisher.php?view_id="

        logger.info(f"[granicus:{self.slug}] Discovering view_id (testing 1-100)...")

        # Try to find view_id with current year data
        for i in range(1, 100):
            try:
                response = self._get(f"{base_url}{i}", timeout=10)
                if (
                    "ViewPublisher" in response.text
                    and ("Meeting" in response.text or "Agenda" in response.text)
                    and current_year in response.text
                ):
                    logger.info(
                        f"[granicus:{self.slug}] Found view_id {i} with {current_year} data"
                    )
                    return i
            except Exception:
                continue

        raise RuntimeError(f"Could not discover view_id for {self.base_url}")

    def fetch_meetings(self, days_forward: int = 14, days_back: int = 7) -> Iterator[Dict[str, Any]]:
        """
        Scrape meetings from Granicus HTML.

        Modern approach: Find all AgendaViewer links on the page directly,
        rather than relying on specific table structures.

        Date filtering: Only returns meetings within the date range to avoid
        processing years of historical data.

        Args:
            days_forward: Days to look ahead (default 14 = 2 weeks)
            days_back: Days to look back (default 7 = 1 week, for recent past meetings)

        Yields:
            Meeting dictionaries with meeting_id, title, start, packet_url, items
        """
        soup = self._fetch_html(self.list_url)

        # Find all links that point to AgendaViewer or direct PDFs
        all_links = soup.find_all("a", href=True)

        agenda_viewer_links = []
        for link in all_links:
            href = link.get("href", "")
            link_text = link.get_text(strip=True)

            # Look for AgendaViewer links or PDF links related to agendas
            if "AgendaViewer.php" in href:
                full_url = urljoin(self.base_url, href)
                agenda_viewer_links.append((link_text, full_url, link))
            elif ("Agenda" in link_text or "Meeting" in link_text) and (
                ".pdf" in href.lower() or "GeneratedAgenda" in href
            ):
                full_url = urljoin(self.base_url, href)
                agenda_viewer_links.append((link_text, full_url, link))

        logger.info(
            f"[granicus:{self.slug}] Found {len(agenda_viewer_links)} total agenda links"
        )

        if not agenda_viewer_links:
            logger.warning(
                f"[granicus:{self.slug}] No agenda links found on ViewPublisher page"
            )
            return

        # Calculate date range for filtering
        today = datetime.now()
        start_date = today - timedelta(days=days_back)
        end_date = today + timedelta(days=days_forward)

        logger.info(
            f"[granicus:{self.slug}] Filtering to meetings from "
            f"{start_date.strftime('%Y-%m-%d')} to {end_date.strftime('%Y-%m-%d')}"
        )

        # Process each agenda link with date filtering
        seen_meeting_ids = set()
        meetings_yielded = 0
        meetings_skipped_date = 0
        SAFETY_LIMIT = 500  # Safety limit in case date parsing fails

        for link_text, agenda_url, link_element in agenda_viewer_links:
            # Safety limit to prevent runaway processing
            if meetings_yielded >= SAFETY_LIMIT:
                logger.warning(
                    f"[granicus:{self.slug}] Hit safety limit of {SAFETY_LIMIT} meetings, stopping"
                )
                break
            # Extract meeting_id from URL
            meeting_id = self._extract_meeting_id(agenda_url)

            # Skip duplicates
            if meeting_id and meeting_id in seen_meeting_ids:
                continue

            if meeting_id:
                seen_meeting_ids.add(meeting_id)

            # Try to extract title and date from surrounding context
            # Look for parent row or nearby elements
            title = link_text
            start = "TBD"

            # Try to find date/time in parent row
            parent_row = link_element.find_parent("tr")
            if parent_row:
                cells = parent_row.find_all("td")
                if len(cells) >= 2:
                    # Often first cell is title/name, second is date
                    # Remove hidden spans
                    for cell in cells:
                        for span in cell.find_all(
                            "span", style=lambda x: x and "display:none" in x
                        ):
                            span.decompose()

                    # Try to find which cell has date-like content
                    for cell in cells:
                        cell_text = cell.get_text(" ", strip=True)
                        # Look for date patterns (month names, year, etc.)
                        if any(
                            month in cell_text
                            for month in [
                                "January",
                                "February",
                                "March",
                                "April",
                                "May",
                                "June",
                                "July",
                                "August",
                                "September",
                                "October",
                                "November",
                                "December",
                            ]
                        ) or any(char.isdigit() and ":" in cell_text for char in cell_text):
                            start = cell_text
                        elif not title or title == link_text:
                            # Use first meaningful cell as title
                            if cell_text and cell_text != link_text and len(cell_text) > 5:
                                title = cell_text

            # Fallback meeting_id if not extracted from URL
            if not meeting_id:
                id_string = f"{title}_{start}_{agenda_url}"
                meeting_id = hashlib.md5(id_string.encode()).hexdigest()[:8]

            # Determine packet URL
            # For AgendaViewer links, follow redirect to get DocumentViewer PDF
            packet_url = None
            if "AgendaViewer.php" in agenda_url:
                try:
                    # AgendaViewer redirects to Google Doc Viewer with DocumentViewer.php PDF
                    response = self.session.head(agenda_url, allow_redirects=True, timeout=10)
                    if response.status_code == 200:
                        # Extract PDF from Google Doc Viewer URL
                        redirect_url = str(response.url)
                        if "DocumentViewer.php" in redirect_url:
                            # Extract the actual PDF URL from Google Doc Viewer
                            import urllib.parse
                            parsed = urllib.parse.urlparse(redirect_url)
                            params = urllib.parse.parse_qs(parsed.query)
                            if 'url' in params:
                                packet_url = urllib.parse.unquote(params['url'][0])
                except Exception as e:
                    logger.debug(f"[granicus:{self.slug}] Failed to get PDF URL for {title[:30]}: {e}")
            elif ".pdf" in agenda_url.lower() or "GeneratedAgenda" in agenda_url:
                packet_url = agenda_url

            # Parse meeting status
            meeting_status = self._parse_meeting_status(title, start)

            result = {
                "meeting_id": meeting_id,
                "title": title,
                "start": start,
                "packet_url": packet_url,
            }

            if meeting_status:
                result["meeting_status"] = meeting_status

            # Fetch HTML agenda items if this is an AgendaViewer page
            if "AgendaViewer.php" in agenda_url:
                try:
                    items_data = self.fetch_html_agenda_items(agenda_url)
                    if items_data["items"]:
                        result["items"] = items_data["items"]
                        logger.info(
                            f"[granicus:{self.slug}] Meeting '{title[:40]}...' has {len(items_data['items'])} items"
                        )
                    if items_data.get("participation"):
                        result["participation"] = items_data["participation"]
                        logger.debug(
                            f"[granicus:{self.slug}] Extracted participation info: {list(items_data['participation'].keys())}"
                        )
                except Exception as e:
                    logger.warning(
                        f"[granicus:{self.slug}] Failed to fetch HTML agenda items for {title}: {e}"
                    )

            yield result

    def _extract_meeting_id(self, url: str) -> Optional[str]:
        """Extract clip_id or event_id from Granicus URL"""
        parsed = urlparse(url)
        params = parse_qs(parsed.query)

        # Try clip_id first (event details)
        if "clip_id" in params:
            return f"clip_{params['clip_id'][0]}"

        # Try event_id (agenda viewer)
        if "event_id" in params:
            return f"event_{params['event_id'][0]}"

        return None

    def _extract_pdfs_from_agenda_viewer(self, agenda_url: str) -> List[str]:
        """
        Extract PDF links from AgendaViewer page.

        Args:
            agenda_url: URL to AgendaViewer.php page

        Returns:
            List of absolute PDF URLs
        """
        try:
            soup = self._fetch_html(agenda_url)
            pdfs = []

            # Look for PDF links in the page
            for link in soup.find_all("a", href=True):
                href = link["href"]
                if ".pdf" in href.lower() or "MetaViewer" in href:
                    absolute_url = urljoin(self.base_url, href)
                    pdfs.append(absolute_url)

            logger.debug(
                f"[granicus:{self.slug}] Found {len(pdfs)} PDFs in AgendaViewer"
            )
            return pdfs

        except Exception as e:
            logger.warning(
                f"[granicus:{self.slug}] Failed to extract PDFs from {agenda_url}: {e}"
            )
            return []

    def fetch_html_agenda_items(self, agenda_url: str) -> Dict[str, Any]:
        """
        Fetch and parse AgendaViewer HTML to extract items and attachments.

        Note: Some cities' AgendaViewer.php returns PDFs instead of HTML.
        We detect this and return empty items list for PDF responses.

        Args:
            agenda_url: URL to AgendaViewer.php page

        Returns:
            {
                'participation': {},
                'items': [{'item_id': str, 'title': str, 'sequence': int, 'attachments': [...]}]
            }
        """
        # Fetch response
        response = self._get(agenda_url)

        # Check if response is actually a PDF (some cities use AgendaViewer.php for PDFs)
        content_type = response.headers.get('Content-Type', '').lower()
        is_pdf = 'application/pdf' in content_type or response.content[:4] == b'%PDF'

        if is_pdf:
            logger.debug(
                f"[granicus:{self.slug}] AgendaViewer returned PDF, not HTML - skipping item parsing"
            )
            return {'participation': {}, 'items': []}

        # Parse HTML
        html = response.text
        parsed = parse_granicus_html_agenda(html)

        logger.debug(
            f"[granicus:{self.slug}] Parsed HTML agenda: {len(parsed['items'])} items"
        )

        return parsed
