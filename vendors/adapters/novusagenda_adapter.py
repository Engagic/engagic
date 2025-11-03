"""
NovusAgenda Adapter - HTML scraping for NovusAgenda platform

Cities using NovusAgenda: Hagerstown MD, Houston TX, and others
"""

import re
from datetime import datetime, timedelta
from typing import Dict, Any, Iterator
from vendors.adapters.base_adapter import BaseAdapter, logger
from vendors.adapters.html_agenda_parser import parse_novusagenda_html_agenda


class NovusAgendaAdapter(BaseAdapter):
    """Adapter for cities using NovusAgenda platform"""

    def __init__(self, city_slug: str):
        """
        Initialize NovusAgenda adapter.

        Args:
            city_slug: NovusAgenda subdomain (e.g., "hagerstown" for hagerstown.novusagenda.com)
        """
        super().__init__(city_slug, vendor="novusagenda")
        self.base_url = f"https://{self.slug}.novusagenda.com"

    def fetch_meetings(self, days_forward: int = 60, days_back: int = 7) -> Iterator[Dict[str, Any]]:
        """
        Scrape meetings from NovusAgenda /agendapublic page with date filtering.

        Args:
            days_forward: Days to look ahead (default 60)
            days_back: Days to look back (default 7)

        Yields:
            Meeting dictionaries with meeting_id, title, start, packet_url, items (if available)
        """
        # Fetch agendapublic page
        soup = self._fetch_html(f"{self.base_url}/agendapublic")

        # Date range filter
        today = datetime.now()
        start_date = today - timedelta(days=days_back)
        end_date = today + timedelta(days=days_forward)

        # Find meeting rows (rgRow and rgAltRow classes)
        meeting_rows = soup.find_all("tr", class_=["rgRow", "rgAltRow"])
        logger.info(f"[novusagenda:{self.slug}] Found {len(meeting_rows)} meeting rows")

        for row in meeting_rows:
            cells = row.find_all("td")
            if len(cells) < 5:
                continue

            # Extract meeting data
            date_str = cells[0].get_text(strip=True)
            meeting_type = cells[1].get_text(strip=True)
            # location = cells[2].get_text(strip=True)  # Available if needed

            # Parse and filter by date (format: MM/DD/YY)
            try:
                meeting_date = datetime.strptime(date_str, "%m/%d/%y")
                # Skip meetings outside date range
                if meeting_date < start_date or meeting_date > end_date:
                    logger.debug(f"[novusagenda:{self.slug}] Skipping {meeting_type} on {date_str} (outside date range)")
                    continue
            except ValueError:
                # If date parsing fails, skip this meeting
                logger.warning(f"[novusagenda:{self.slug}] Could not parse date '{date_str}' for {meeting_type}")
                continue

            # Time is often in cell 3 or 4 depending on layout
            time_field = cells[3].get_text(strip=True) if len(cells) > 3 else ""

            # Parse meeting status from title and time field
            meeting_status = self._parse_meeting_status(meeting_type, time_field)

            # Find PDF link and HTML agenda link
            pdf_link = row.find("a", href=re.compile(r"DisplayAgendaPDF\.ashx"))
            all_agenda_links = row.find_all("a", onclick=re.compile(r"MeetingView\.aspx"))

            packet_url = None
            agenda_url = None
            meeting_id = None

            if pdf_link:
                # Extract meeting ID
                pdf_href = pdf_link.get("href", "")
                meeting_id_match = re.search(r"MeetingID=(\d+)", pdf_href)
                if meeting_id_match:
                    meeting_id = meeting_id_match.group(1)
                    packet_url = f"{self.base_url}/agendapublic/{pdf_href}"

            # Prioritize HTML agendas that are parsable (contain structured items)
            # Good: "HTML Agenda", "Online Agenda"
            # Skip: "Agenda Summary" (not parsable)
            best_agenda_link = None
            best_score = 0

            for link in all_agenda_links:
                # Check both link text and image alt attributes (Houston uses image-only links)
                link_text = link.get_text(strip=True).lower()

                # Also check for img alt text within the link
                img = link.find("img")
                if img:
                    alt_text = img.get("alt", "").lower()
                    link_text = f"{link_text} {alt_text}".strip()

                score = 0

                # High priority: parsable HTML agendas
                if "html agenda" in link_text or "online agenda" in link_text:
                    score = 3
                # Medium priority: generic agenda view
                elif "view agenda" in link_text or "agenda" in link_text:
                    if "summary" not in link_text:
                        score = 2
                # Skip: summaries (not useful)
                elif "summary" in link_text:
                    score = 0

                if score > best_score:
                    best_score = score
                    best_agenda_link = link

            # Extract URL from best agenda link
            if best_agenda_link:
                onclick = best_agenda_link.get("onclick", "")
                url_match = re.search(r"MeetingView\.aspx\?[^'\"]+", onclick)
                if url_match:
                    agenda_relative_url = url_match.group(0)
                    agenda_url = f"{self.base_url}/agendapublic/{agenda_relative_url}"

                    logger.debug(
                        f"[novusagenda:{self.slug}] Selected HTML agenda: {best_agenda_link.get_text(strip=True)[:40]} (score={best_score})"
                    )

                    # Extract meeting ID if not already found
                    if not meeting_id:
                        meeting_id_match = re.search(r"MeetingID=(\d+)", agenda_relative_url)
                        if meeting_id_match:
                            meeting_id = meeting_id_match.group(1)

            # Generate fallback meeting_id if not found
            if not meeting_id:
                import hashlib

                id_string = f"{meeting_type}_{date_str}"
                meeting_id = hashlib.md5(id_string.encode()).hexdigest()[:8]

            if not packet_url and not agenda_url:
                logger.debug(
                    f"[novusagenda:{self.slug}] No packet or agenda for: {meeting_type} on {date_str}"
                )

            # Try to fetch and parse HTML agenda for items
            items = []
            if agenda_url:
                try:
                    logger.info(f"[novusagenda:{self.slug}] Fetching HTML agenda: {agenda_url}")
                    # Fetch raw HTML (get response text directly)
                    response = self._get(agenda_url)
                    agenda_html = response.text

                    # Parse for items
                    parsed = parse_novusagenda_html_agenda(agenda_html)
                    items = parsed.get('items', [])

                    logger.info(
                        f"[novusagenda:{self.slug}] Meeting {meeting_id}: "
                        f"extracted {len(items)} items from HTML agenda"
                    )
                except Exception as e:
                    logger.warning(
                        f"[novusagenda:{self.slug}] Failed to parse HTML agenda for {meeting_id}: {e}"
                    )

            result = {
                "meeting_id": meeting_id,
                "title": meeting_type,
                "start": date_str,
                "packet_url": packet_url,
            }

            if agenda_url:
                result["agenda_url"] = agenda_url

            if items:
                result["items"] = items

            if meeting_status:
                result["meeting_status"] = meeting_status

            yield result
