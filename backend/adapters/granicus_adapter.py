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
from datetime import datetime
from urllib.parse import parse_qs, urlparse, urljoin
from backend.adapters.base_adapter import BaseAdapter, logger


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
            logger.info(f"[granicus:{self.slug}] Found cached view_id: {mappings[self.base_url]}")
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
                with open(self.view_ids_file, 'r') as f:
                    return json.load(f)
            except Exception as e:
                logger.warning(f"Could not load view_id cache: {e}")
        return {}

    def _save_view_id_mappings(self, mappings: Dict[str, int]):
        """Save view_id cache to disk"""
        os.makedirs(os.path.dirname(self.view_ids_file), exist_ok=True)
        with open(self.view_ids_file, 'w') as f:
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
        for i in range(1, 500):
            try:
                response = self._get(f"{base_url}{i}", timeout=10)
                if (
                    "ViewPublisher" in response.text
                    and ("Meeting" in response.text or "Agenda" in response.text)
                    and current_year in response.text
                ):
                    logger.info(f"[granicus:{self.slug}] Found view_id {i} with {current_year} data")
                    return i
            except Exception:
                continue

        # Fallback: accept view_id without current year
        logger.warning(f"[granicus:{self.slug}] No view_id with {current_year} data, trying any year...")
        raise RuntimeError(f"Could not discover view_id for {self.base_url}")

    def fetch_meetings(self) -> Iterator[Dict[str, Any]]:
        """
        Scrape meetings from Granicus HTML.

        Yields:
            Meeting dictionaries with meeting_id, title, start, packet_url
        """
        soup = self._fetch_html(self.list_url)

        # Find "Upcoming Events" or "Upcoming Meetings" section
        upcoming_header = soup.find("h2", string="Upcoming Events") or soup.find("h3", string="Upcoming Events")
        if not upcoming_header:
            upcoming_header = soup.find("h2", string="Upcoming Meetings") or soup.find("h3", string="Upcoming Meetings")

        if not upcoming_header:
            logger.warning(f"[granicus:{self.slug}] No upcoming events section found")
            return

        # Find table after header
        upcoming_table = None
        for sibling in upcoming_header.find_next_siblings():
            if sibling.name == "table":
                upcoming_table = sibling
                break
            if sibling.name == "div" and sibling.get("class") == ["archive"]:
                break

        if not upcoming_table:
            logger.warning(f"[granicus:{self.slug}] No upcoming events table found")
            return

        # Parse meeting rows
        for row in upcoming_table.find_all("tr"):
            cells = row.find_all("td")
            if len(cells) < 2:
                continue

            # Skip header rows
            if any(cell.get("class") == ["listHeader"] for cell in cells):
                continue

            # Extract title and date (remove hidden timestamp spans)
            for span in cells[0].find_all('span', style=lambda x: x and 'display:none' in x):
                span.decompose()
            for span in cells[1].find_all('span', style=lambda x: x and 'display:none' in x):
                span.decompose()

            title = cells[0].get_text(" ", strip=True)
            start = cells[1].get_text(" ", strip=True)

            # Skip rows without meaningful title
            if not title or title in ["Meeting", "Event"]:
                continue

            # Look for agenda link
            agenda_link = row.find("a", string=lambda s: s and "Agenda" in s)
            packet_url = None
            meeting_id = None

            if agenda_link:
                href = agenda_link.get("href", "")
                if href:
                    agenda_url = urljoin(self.base_url, href)
                    meeting_id = self._extract_meeting_id(agenda_url)

                    # Check if direct PDF or agenda viewer page
                    if ".pdf" in agenda_url.lower() or "GeneratedAgenda.ashx" in agenda_url:
                        packet_url = agenda_url
                    elif "AgendaViewer.php" in agenda_url:
                        # Extract PDFs from AgendaViewer page
                        pdfs = self._extract_pdfs_from_agenda_viewer(agenda_url)
                        if pdfs:
                            # TODO: Handle multiple PDFs better (store as JSON array or separate items table)
                            # For now, just take the first PDF to unblock processing
                            packet_url = pdfs[0]

            # Generate fallback meeting_id
            if not meeting_id:
                id_string = f"{title}_{start}"
                meeting_id = hashlib.md5(id_string.encode()).hexdigest()[:8]

            # Parse meeting status from title and start time
            meeting_status = self._parse_meeting_status(title, start)

            result = {
                "meeting_id": meeting_id,
                "title": title,
                "start": start,
                "packet_url": packet_url,
            }

            if meeting_status:
                result["meeting_status"] = meeting_status

            yield result

    def _extract_meeting_id(self, url: str) -> Optional[str]:
        """Extract clip_id or event_id from Granicus URL"""
        parsed = urlparse(url)
        params = parse_qs(parsed.query)

        # Try clip_id first (event details)
        if 'clip_id' in params:
            return f"clip_{params['clip_id'][0]}"

        # Try event_id (agenda viewer)
        if 'event_id' in params:
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
            for link in soup.find_all('a', href=True):
                href = link['href']
                if '.pdf' in href.lower() or 'MetaViewer' in href:
                    absolute_url = urljoin(self.base_url, href)
                    pdfs.append(absolute_url)

            logger.debug(f"[granicus:{self.slug}] Found {len(pdfs)} PDFs in AgendaViewer")
            return pdfs

        except Exception as e:
            logger.warning(f"[granicus:{self.slug}] Failed to extract PDFs from {agenda_url}: {e}")
            return []
