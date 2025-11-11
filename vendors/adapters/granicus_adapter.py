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
from vendors.adapters.base_adapter import BaseAdapter, logger
from vendors.adapters.parsers.granicus_parser import parse_html_agenda
from vendors.utils.item_filters import should_skip_procedural_item


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

        Prioritizes pages with government meeting indicators like
        "City Council", "Planning Commission", etc.

        Returns:
            Valid view_id

        Raises:
            RuntimeError if no view_id found
        """
        current_year = str(datetime.now().year)
        base_url = f"{self.base_url}/ViewPublisher.php?view_id="

        logger.info(f"[granicus:{self.slug}] Discovering view_id (testing 1-100)...")

        # Government meeting indicators (high priority)
        gov_indicators = [
            "city council",
            "planning commission",
            "board of supervisors",
            "town council",
            "village board",
            "board of trustees",
        ]

        candidates = []

        # Scan for candidates
        for i in range(1, 100):
            try:
                response = self._get(f"{base_url}{i}", timeout=10)
                text = response.text
                text_lower = text.lower()

                # CRITICAL: Must have "upcoming" section for filtering
                # Without it, we'd process all historical meetings
                if "upcoming" not in text_lower:
                    continue

                # Must have basic meeting page indicators
                if not ("ViewPublisher" in text and current_year in text):
                    continue

                # Score this candidate
                score = 0

                # Baseline: has required "upcoming" section
                score += 5

                # High priority: government body names
                for indicator in gov_indicators:
                    if indicator in text_lower:
                        score += 10
                        logger.debug(f"[granicus:{self.slug}] view_id {i} has '{indicator}' (+10)")

                # Low priority: general meeting/agenda indicators
                if "agenda" in text_lower or "meeting" in text_lower:
                    score += 1

                candidates.append((i, score))
                logger.debug(f"[granicus:{self.slug}] view_id {i} score: {score}")

            except Exception:
                continue

        # Sort by score (descending) and return highest
        if candidates:
            candidates.sort(key=lambda x: x[1], reverse=True)
            best_id, best_score = candidates[0]
            logger.info(
                f"[granicus:{self.slug}] Found view_id {best_id} "
                f"(score: {best_score}, {len(candidates)} candidates)"
            )
            return best_id

        raise RuntimeError(f"Could not discover view_id for {self.base_url}")

    def fetch_meetings(self, days_forward: int = 14, days_back: int = 7) -> Iterator[Dict[str, Any]]:
        """
        Scrape meetings from Granicus HTML.

        Strategy: Target the "Upcoming" section (Upcoming Events, Upcoming Programs, etc.)
        to avoid processing years of historical data.

        Args:
            days_forward: Days to look ahead (default 14 = 2 weeks)
            days_back: Days to look back (default 7 = 1 week, for recent past meetings)

        Yields:
            Meeting dictionaries with meeting_id, title, start, packet_url, items
        """
        soup = self._fetch_html(self.list_url)

        # CRITICAL: Only look in the "Upcoming" section
        # Variations: "Upcoming Events", "Upcoming Programs", "Upcoming Meetings", etc.
        upcoming_section = soup.find("div", {"id": "upcoming"})

        if not upcoming_section:
            # Fallback: try finding by heading text (check all heading levels)
            for tag in ["h1", "h2", "h3", "h4", "h5"]:
                upcoming_heading = soup.find(tag, string=lambda t: t and "upcoming" in t.lower())
                if upcoming_heading:
                    upcoming_section = upcoming_heading.find_parent("div")
                    if upcoming_section:
                        logger.info(f"[granicus:{self.slug}] Found upcoming section via {tag} heading")
                        break
        if not upcoming_section:
            # Check for table-based layout
            header_cell = soup.find("td", class_="listHeader", string=lambda t: t and "upcoming" in t.lower())
            if header_cell:
                # Get parent table or containing structure
                upcoming_section = header_cell.find_parent("table")
                if upcoming_section:
                    logger.info(f"[granicus:{self.slug}] Found upcoming section via table header")

        if not upcoming_section:
            # Log what we're actually seeing for debugging
            all_divs = soup.find_all("div", id=True)
            div_ids = [d.get("id") for d in all_divs[:10]]

            all_headings = soup.find_all(["h1", "h2", "h3", "h4"])
            heading_texts = [h.get_text(strip=True)[:50] for h in all_headings[:10]]

            logger.warning(
                f"[granicus:{self.slug}] No 'Upcoming' section found (tried div#upcoming, headings, table headers). "
                f"Returning 0 meetings to avoid processing historical data. "
                f"Found div IDs: {div_ids}. "
                f"Found headings: {heading_texts}"
            )
            return  # Return empty generator - do NOT process historical data
        else:
            logger.info(f"[granicus:{self.slug}] Found 'Upcoming' section")
            search_scope = upcoming_section

        # Find links within our target scope
        all_links = search_scope.find_all("a", href=True)

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
            f"[granicus:{self.slug}] Found {len(agenda_viewer_links)} upcoming agenda links"
        )

        if not agenda_viewer_links:
            logger.warning(
                f"[granicus:{self.slug}] No agenda links found in upcoming section"
            )
            return

        # Process each agenda link (no date filtering needed - section is pre-filtered)
        seen_meeting_ids = set()

        for link_text, agenda_url, link_element in agenda_viewer_links:
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

            # Parse meeting status
            meeting_status = self._parse_meeting_status(title, start)

            result = {
                "meeting_id": meeting_id,
                "title": title,
                "start": start,
            }

            if meeting_status:
                result["meeting_status"] = meeting_status

            # Architecture: items from HTML → agenda_url, PDF only → packet_url
            if "AgendaViewer.php" in agenda_url:
                # Try to fetch HTML agenda items
                try:
                    items_data = self.fetch_html_agenda_items(agenda_url)
                    if items_data["items"]:
                        # HTML agenda with items → agenda_url (item-based)
                        result["agenda_url"] = agenda_url
                        result["items"] = items_data["items"]
                        logger.info(
                            f"[granicus:{self.slug}] Meeting '{title[:40]}...' has {len(items_data['items'])} items"
                        )
                    else:
                        # AgendaViewer but no items → try to get PDF
                        try:
                            response = self.session.head(agenda_url, allow_redirects=True, timeout=10)
                            if response.status_code == 200:
                                redirect_url = str(response.url)
                                if "DocumentViewer.php" in redirect_url:
                                    import urllib.parse
                                    parsed = urllib.parse.urlparse(redirect_url)
                                    params = urllib.parse.parse_qs(parsed.query)
                                    if 'url' in params:
                                        result["packet_url"] = urllib.parse.unquote(params['url'][0])
                        except Exception as e:
                            logger.debug(f"[granicus:{self.slug}] Failed to get PDF URL for {title[:30]}: {e}")

                    if items_data.get("participation"):
                        result["participation"] = items_data["participation"]
                        logger.debug(
                            f"[granicus:{self.slug}] Extracted participation info: {list(items_data['participation'].keys())}"
                        )
                except Exception as e:
                    logger.warning(
                        f"[granicus:{self.slug}] Failed to fetch HTML agenda items for {title}: {e}"
                    )
            elif ".pdf" in agenda_url.lower() or "GeneratedAgenda" in agenda_url:
                # Direct PDF link → packet_url (monolithic)
                result["packet_url"] = agenda_url

            yield result

    def _extract_meeting_id(self, url: str) -> Optional[str]:
        """Extract clip_id or event_id from Granicus URL"""
        parsed = urlparse(url)
        params = parse_qs(parsed.query)

        # Try clip_id first (event details)
        if "clip_id" in params:
            return params['clip_id'][0]

        # Try event_id (agenda viewer)
        if "event_id" in params:
            return params['event_id'][0]

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
        parsed = parse_html_agenda(html)

        # Filter procedural items (roll call, approval of minutes, etc.)
        items_before = len(parsed['items'])
        parsed['items'] = [
            item for item in parsed['items']
            if not should_skip_procedural_item(item.get('title', ''))
        ]
        items_filtered = items_before - len(parsed['items'])
        if items_filtered > 0:
            logger.info(
                f"[granicus:{self.slug}] Filtered {items_filtered} procedural items"
            )

        # Convert relative attachment URLs to absolute URLs
        # Also ensure type field is set (defense-in-depth)
        for item in parsed['items']:
            for attachment in item.get('attachments', []):
                url = attachment.get('url', '')
                # If URL is relative, make it absolute using urljoin
                if url and not url.startswith('http'):
                    attachment['url'] = urljoin(self.base_url, url)
                # Ensure type field is set (Granicus MetaViewer links are PDFs)
                if 'type' not in attachment:
                    attachment['type'] = 'pdf'

        logger.debug(
            f"[granicus:{self.slug}] Parsed HTML agenda: {len(parsed['items'])} items"
        )

        return parsed
