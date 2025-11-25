"""
Escribe Adapter - HTML scraping for Escribe meeting management systems

Escribe (eScribe) is used by cities for agenda/meeting management.
Example: Beaumont, CA uses pub-beaumont.escribemeetings.com
"""

import re
import hashlib
from typing import Dict, Any, Optional, Iterator
from datetime import datetime
from urllib.parse import urljoin
from vendors.adapters.base_adapter import BaseAdapter, logger


class EscribeAdapter(BaseAdapter):
    """Adapter for cities using Escribe meeting management system"""

    def __init__(self, city_slug: str):
        """
        Initialize Escribe adapter.

        Args:
            city_slug: Escribe subdomain (e.g., "pub-beaumont" for pub-beaumont.escribemeetings.com)
        """
        super().__init__(city_slug, vendor="escribe")
        self.base_url = f"https://{self.slug}.escribemeetings.com"

    def fetch_meetings(self) -> Iterator[Dict[str, Any]]:
        """
        Scrape meetings from Escribe HTML.

        Yields:
            Meeting dictionaries with meeting_id, title, start, packet_url
        """
        current_year = datetime.now().year
        list_url = f"{self.base_url}/?Year={current_year}"

        logger.info("fetching meetings", vendor="escribe", slug=self.slug, url=list_url)

        soup = self._fetch_html(list_url)

        # Find "Upcoming Meetings" section
        upcoming_section = soup.find(
            "div", {"role": "region", "aria-label": "List of Upcoming Meetings"}
        )

        if not upcoming_section:
            logger.warning("no upcoming meetings section found", vendor="escribe", slug=self.slug)
            return

        # Parse meeting containers
        meeting_containers = upcoming_section.find_all(
            "div", class_="upcoming-meeting-container"
        )

        logger.info(
            "found upcoming meetings",
            vendor="escribe",
            slug=self.slug,
            count=len(meeting_containers)
        )

        for container in meeting_containers:
            meeting = self._parse_meeting_container(container)
            if meeting:
                yield meeting

    def _parse_meeting_container(self, container) -> Optional[Dict[str, Any]]:
        """
        Parse a single meeting container to extract meeting details.

        Args:
            container: BeautifulSoup element for meeting container

        Returns:
            Meeting dict or None if parsing fails
        """
        # Extract title and meeting URL
        title_elem = container.find("h3", class_="meeting-title-heading")
        if not title_elem:
            return None

        title_link = title_elem.find("a")
        if not title_link:
            return None

        title = title_link.get_text(strip=True)
        meeting_url = title_link.get("href", "")
        if meeting_url and not meeting_url.startswith("http"):
            meeting_url = urljoin(self.base_url, meeting_url)

        # Extract date
        date_elem = container.find("div", class_="meeting-date")
        date_text = date_elem.get_text(strip=True) if date_elem else ""

        # Parse date using base adapter's multi-format parser
        parsed_date = self._parse_date(date_text) if date_text else None

        # Extract PDF links (look for agenda PDFs specifically)
        pdf_links = []
        for link in container.find_all(
            "a", href=re.compile(r"FileStream\.ashx\?DocumentId=")
        ):
            aria_label = link.get("aria-label", "").lower()
            # Only include PDFs labeled as "Agenda (PDF)"
            if "pdf" in aria_label and "agenda" in aria_label:
                pdf_url = link.get("href", "")
                if pdf_url:
                    if not pdf_url.startswith("http"):
                        pdf_url = urljoin(self.base_url, pdf_url)
                    pdf_links.append(pdf_url)

        # Extract meeting ID from URL (format: Meeting.aspx?Id=UUID)
        meeting_id = self._extract_meeting_id(meeting_url, title, date_text)

        # Determine packet_url
        packet_url = None
        if pdf_links:
            packet_url = pdf_links[0] if len(pdf_links) == 1 else pdf_links

        # Parse meeting status from title and date
        meeting_status = self._parse_meeting_status(title, date_text)

        result = {
            "meeting_id": meeting_id,
            "title": title,
            "start": parsed_date or date_text,
            "packet_url": packet_url,
        }

        if meeting_status:
            result["meeting_status"] = meeting_status

        logger.debug("parsed meeting", vendor="escribe", slug=self.slug, title=title, date=date_text)

        return result

    def _extract_meeting_id(self, url: str, title: str, date: str) -> str:
        """
        Extract meeting ID from URL or generate from title+date.

        Args:
            url: Meeting detail page URL
            title: Meeting title
            date: Meeting date string

        Returns:
            Meeting ID string
        """
        # Try to extract UUID from URL (format: Meeting.aspx?Id=UUID)
        match = re.search(r"Id=([a-f0-9-]+)", url)
        if match:
            return f"escribe_{match.group(1)}"

        # Fallback: hash title + date
        id_string = f"{title}_{date}"
        return f"escribe_{hashlib.md5(id_string.encode()).hexdigest()[:8]}"
