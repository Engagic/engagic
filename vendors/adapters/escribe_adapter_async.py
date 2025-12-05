"""
Async Escribe Adapter - HTML scraping for Escribe meeting management systems

Escribe (eScribe) is used by cities for agenda/meeting management.
Example: Beaumont, CA uses pub-beaumont.escribemeetings.com

Async version with:
- aiohttp for async HTTP requests
- asyncio.to_thread for CPU-bound BeautifulSoup parsing
- Non-blocking I/O for concurrent city fetching
"""

import re
import hashlib
import asyncio
from typing import Dict, Any, Optional, List
from datetime import datetime, timedelta
from urllib.parse import urljoin

from bs4 import BeautifulSoup, Tag

from vendors.adapters.base_adapter_async import AsyncBaseAdapter, logger
from pipeline.protocols import MetricsCollector


class AsyncEscribeAdapter(AsyncBaseAdapter):
    """Async adapter for cities using Escribe meeting management system"""

    def __init__(self, city_slug: str, metrics: Optional[MetricsCollector] = None):
        """city_slug is the Escribe subdomain (e.g., "pub-beaumont")"""
        super().__init__(city_slug, vendor="escribe", metrics=metrics)
        self.base_url = f"https://{self.slug}.escribemeetings.com"

    async def _fetch_meetings_impl(self, days_back: int = 7, days_forward: int = 14) -> List[Dict[str, Any]]:
        """Scrape meetings from Escribe HTML with date filtering."""
        today = datetime.now()
        start_date = today - timedelta(days=days_back)
        end_date = today + timedelta(days=days_forward)

        current_year = datetime.now().year
        list_url = f"{self.base_url}/?Year={current_year}"

        logger.info("fetching meetings", vendor="escribe", slug=self.slug, url=list_url)

        response = await self._get(list_url)
        html = await response.text()
        soup = await asyncio.to_thread(BeautifulSoup, html, 'html.parser')

        meeting_containers = []
        upcoming_section = soup.find(
            "div", {"role": "region", "aria-label": "List of Upcoming Meetings"}
        )
        if upcoming_section:
            upcoming_containers = upcoming_section.find_all(
                "div", class_="upcoming-meeting-container"
            )
            meeting_containers.extend(upcoming_containers)
            logger.info(
                "found upcoming meetings",
                vendor="escribe",
                slug=self.slug,
                count=len(upcoming_containers)
            )

        previous_section = soup.find(
            "div", {"role": "region", "aria-label": "List of Previous Meetings"}
        )
        if previous_section:
            previous_containers = previous_section.find_all(
                "div", class_="previous-meeting-container"
            )
            meeting_containers.extend(previous_containers)
            logger.info(
                "found previous meetings",
                vendor="escribe",
                slug=self.slug,
                count=len(previous_containers)
            )

        if not meeting_containers:
            logger.warning("no meeting sections found", vendor="escribe", slug=self.slug)
            return []

        results = []
        for container in meeting_containers:
            meeting = self._parse_meeting_container(container)
            if meeting:
                meeting_start = meeting.get("start")
                if meeting_start:
                    try:
                        if isinstance(meeting_start, str):
                            meeting_dt = datetime.strptime(meeting_start[:10], "%Y-%m-%d")
                        else:
                            meeting_dt = meeting_start
                        if not (start_date <= meeting_dt <= end_date):
                            logger.debug(
                                "skipping meeting outside date range",
                                vendor="escribe",
                                slug=self.slug,
                                title=meeting.get("title"),
                                date=meeting_start
                            )
                            continue
                    except (ValueError, TypeError):
                        pass
                results.append(meeting)

        return results

    def _parse_meeting_container(self, container: Tag) -> Optional[Dict[str, Any]]:
        """Parse a single meeting container to extract meeting details."""
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

        date_elem = container.find("div", class_="meeting-date")
        date_text = date_elem.get_text(strip=True) if date_elem else ""
        parsed_date = self._parse_date(date_text) if date_text else None

        pdf_links = []
        for link in container.find_all(
            "a", href=re.compile(r"FileStream\.ashx\?DocumentId=")
        ):
            aria_label = link.get("aria-label", "").lower()
            if "pdf" in aria_label and "agenda" in aria_label:
                pdf_url = link.get("href", "")
                if pdf_url:
                    if not pdf_url.startswith("http"):
                        pdf_url = urljoin(self.base_url, pdf_url)
                    pdf_links.append(pdf_url)

        meeting_id = self._extract_meeting_id(meeting_url, title, date_text)
        packet_url = pdf_links[0] if pdf_links else None
        meeting_status = self._parse_meeting_status(title, date_text)

        result = {
            "vendor_id": meeting_id,
            "title": title,
            "start": parsed_date.isoformat() if parsed_date else date_text,
            "packet_url": packet_url,
        }

        if meeting_status:
            result["meeting_status"] = meeting_status

        logger.debug("parsed meeting", vendor="escribe", slug=self.slug, title=title, date=date_text)

        return result

    def _extract_meeting_id(self, url: str, title: str, date: str) -> str:
        """Extract meeting ID from URL or generate hash from title+date."""
        match = re.search(r"Id=([a-f0-9-]+)", url)
        if match:
            return f"escribe_{match.group(1)}"
        id_string = f"{title}_{date}"
        return f"escribe_{hashlib.md5(id_string.encode()).hexdigest()[:8]}"
