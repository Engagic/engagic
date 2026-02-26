"""
Async NovusAgenda Adapter - HTML scraping for NovusAgenda platform

Cities using NovusAgenda: Hagerstown MD, Houston TX, and others
"""

import asyncio
import re
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
import aiohttp
from vendors.adapters.base_adapter_async import AsyncBaseAdapter, logger
from vendors.adapters.parsers.novusagenda_parser import parse_html_agenda
from pipeline.filters import should_skip_item
from pipeline.protocols import MetricsCollector
from bs4 import BeautifulSoup


class AsyncNovusAgendaAdapter(AsyncBaseAdapter):
    """Async adapter for cities using NovusAgenda platform."""

    def __init__(self, city_slug: str, metrics: Optional[MetricsCollector] = None):
        super().__init__(city_slug, vendor="novusagenda", metrics=metrics)
        self.base_url = f"https://{self.slug}.novusagenda.com"

    async def _fetch_meetings_impl(self, days_back: int = 7, days_forward: int = 14) -> List[Dict[str, Any]]:
        """Scrape meetings from NovusAgenda /agendapublic page."""
        # Fetch agendapublic page
        response = await self._get(f"{self.base_url}/agendapublic")
        html = await response.text()
        soup = BeautifulSoup(html, 'html.parser')

        # Date range filter
        today = datetime.now()
        start_date = today - timedelta(days=days_back)
        end_date = today + timedelta(days=days_forward)

        # Find meeting rows (rgRow and rgAltRow classes)
        meeting_rows = soup.find_all("tr", class_=["rgRow", "rgAltRow"])
        logger.info("found meeting rows", vendor="novusagenda", slug=self.slug, count=len(meeting_rows))

        meetings = []

        for row in meeting_rows:
            cells = row.find_all("td")
            if len(cells) < 5:
                continue

            # Extract meeting data
            date_str = cells[0].get_text(strip=True)
            meeting_type = cells[1].get_text(strip=True)

            try:
                meeting_date = datetime.strptime(date_str, "%m/%d/%y")
                if meeting_date < start_date or meeting_date > end_date:
                    logger.debug("skipping meeting outside date range", vendor="novusagenda", slug=self.slug, meeting_type=meeting_type, date=date_str)
                    continue
            except ValueError:
                logger.warning("could not parse date", vendor="novusagenda", slug=self.slug, date=date_str, meeting_type=meeting_type)
                continue

            time_field = cells[3].get_text(strip=True) if len(cells) > 3 else ""
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

            # Prioritize parsable HTML agendas over summaries
            best_agenda_link = None
            best_score = 0

            for link in all_agenda_links:
                link_text = link.get_text(strip=True).lower()
                img = link.find("img")
                if img:
                    alt_text = img.get("alt", "").lower()
                    link_text = f"{link_text} {alt_text}".strip()

                score = 0
                if "html agenda" in link_text or "online agenda" in link_text:
                    score = 3
                elif ("view agenda" in link_text or "agenda" in link_text) and "summary" not in link_text:
                    score = 2

                if score > best_score:
                    best_score = score
                    best_agenda_link = link

            if best_agenda_link:
                onclick = best_agenda_link.get("onclick", "")
                url_match = re.search(r"MeetingView\.aspx\?[^'\"]+", onclick)
                if url_match:
                    agenda_relative_url = url_match.group(0)
                    agenda_url = f"{self.base_url}/agendapublic/{agenda_relative_url}"

                    if not meeting_id:
                        meeting_id_match = re.search(r"MeetingID=(\d+)", agenda_relative_url)
                        if meeting_id_match:
                            meeting_id = meeting_id_match.group(1)

            if not meeting_id:
                meeting_id = self._generate_fallback_vendor_id(
                    title=meeting_type,
                    date=meeting_date
                )

            if not packet_url and not agenda_url:
                logger.debug(
                    "no packet or agenda found",
                    vendor="novusagenda",
                    slug=self.slug,
                    meeting_type=meeting_type,
                    date=date_str
                )

            items = []
            if agenda_url:
                try:
                    response = await self._get(agenda_url)
                    agenda_html = await response.text()
                    parsed = parse_html_agenda(agenda_html)
                    items = parsed.get('items', [])
                    items_before = len(items)
                    items = [
                        item for item in items
                        if not should_skip_item(item.get('title', ''))
                    ]
                    items_filtered = items_before - len(items)
                    if items_filtered > 0:
                        logger.info(
                            "filtered procedural items",
                            vendor="novusagenda",
                            slug=self.slug,
                            filtered_count=items_filtered
                        )

                    # Fetch attachments from CoverSheet detail pages
                    if items:
                        items = await self._fetch_coversheet_attachments(items, meeting_id)

                    logger.info(
                        "extracted items from HTML agenda",
                        vendor="novusagenda",
                        slug=self.slug,
                        meeting_id=meeting_id,
                        item_count=len(items),
                        items_with_attachments=sum(1 for i in items if i.get("attachments"))
                    )
                except (aiohttp.ClientError, asyncio.TimeoutError) as e:
                    logger.warning(
                        "failed to fetch HTML agenda",
                        vendor="novusagenda",
                        slug=self.slug,
                        meeting_id=meeting_id,
                        error=str(e)
                    )
                except (ValueError, KeyError, AttributeError) as e:
                    logger.warning(
                        "failed to parse HTML agenda",
                        vendor="novusagenda",
                        slug=self.slug,
                        meeting_id=meeting_id,
                        error=str(e)
                    )

            result = {
                "vendor_id": meeting_id,
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

            meetings.append(result)

        logger.info(
            "collected meetings in date range",
            vendor="novusagenda",
            slug=self.slug,
            count=len(meetings)
        )

        return meetings

    async def _fetch_coversheet_attachments(
        self, items: List[Dict[str, Any]], meeting_id: str
    ) -> List[Dict[str, Any]]:
        """Fetch attachments from CoverSheet.aspx detail pages for each item.

        NovusAgenda hosts item documents behind CoverSheet pages. Each page
        contains AttachmentViewer.ashx links pointing to the actual PDFs.
        """
        sem = asyncio.Semaphore(5)

        async def fetch_one(item: Dict[str, Any]) -> Dict[str, Any]:
            item_id = item.get("vendor_item_id")
            if not item_id:
                return item
            url = f"{self.base_url}/agendapublic/CoverSheet.aspx?ItemID={item_id}&MeetingID={meeting_id}"
            async with sem:
                try:
                    response = await self._get(url)
                    html = await response.text()
                    attachments = self._parse_coversheet_attachments(html)
                    if attachments:
                        item["attachments"] = attachments
                except Exception as e:
                    logger.debug(
                        "failed to fetch coversheet",
                        vendor="novusagenda",
                        slug=self.slug,
                        item_id=item_id,
                        error=str(e)
                    )
            return item

        return list(await asyncio.gather(*[fetch_one(item) for item in items]))

    def _parse_coversheet_attachments(self, html: str) -> List[Dict[str, str]]:
        """Extract attachment links from a CoverSheet.aspx page.

        Looks for AttachmentViewer.ashx links which are the standard
        NovusAgenda pattern for hosted documents.
        """
        soup = BeautifulSoup(html, "html.parser")
        attachments = []
        seen_ids = set()

        for link in soup.find_all("a", href=re.compile(r"AttachmentViewer\.ashx", re.IGNORECASE)):
            href = link.get("href", "")
            att_id_match = re.search(r"AttachmentID=(\d+)", href)
            if not att_id_match:
                continue
            att_id = att_id_match.group(1)
            if att_id in seen_ids:
                continue
            seen_ids.add(att_id)

            name = link.get_text(strip=True)
            if not name:
                parent = link.find_parent("td") or link.find_parent("div")
                if parent:
                    name = parent.get_text(strip=True)
            if not name:
                name = f"Attachment {att_id}"

            full_url = href if href.startswith("http") else f"{self.base_url}/agendapublic/{href}"
            file_type = "pdf" if ".pdf" in name.lower() or ".pdf" in href.lower() else "document"

            attachments.append({"name": name, "url": full_url, "type": file_type})

        return attachments
