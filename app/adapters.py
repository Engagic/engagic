import re
import requests
import tempfile
import logging
import fitz
import json
import os
from urllib.parse import urlencode, urljoin, urlparse, parse_qs
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
from pdf_scraper_utils import deep_scrape_pdfs
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

logger = logging.getLogger("engagic")

# Polite scraping headers
DEFAULT_HEADERS = {
    "User-Agent": "Engagic/1.0 (Civic Engagement Bot; Engagic Is For The People)",
    "Accept": "application/json, text/html, application/xhtml+xml, application/xml;q=0.9, */*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
    "Accept-Encoding": "gzip, deflate",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
}


class PrimeGovAdapter:
    def __init__(self, city_slug: str):
        if not city_slug:
            raise ValueError("city_slug required, e.g. 'cityofpaloalto'")
        self.slug = city_slug
        self.base = f"https://{self.slug}.primegov.com"
        logger.info(f"Initialized PrimeGov adapter for {city_slug}")

    def _packet_url(self, doc):
        q = urlencode(
            {
                "meetingTemplateId": doc["templateId"],
                "compileOutputType": doc["compileOutputType"],
            }
        )
        return f"https://{self.slug}.primegov.com/Public/CompiledDocument?{q}"

    def upcoming_packets(self):
        try:
            logger.debug(f"Fetching upcoming meetings from PrimeGov for {self.slug}")
            resp = requests.get(
                f"{self.base}/api/v2/PublicPortal/ListUpcomingMeetings",
                headers=DEFAULT_HEADERS,
                timeout=30,
            )
            resp.raise_for_status()
            meetings = resp.json()
            logger.info(
                f"Retrieved {len(meetings)} meetings from PrimeGov for {self.slug}"
            )
        except Exception as e:
            logger.error(f"Failed to fetch PrimeGov meetings for {self.slug}: {e}")
            raise

        for mtg in meetings:
            pkt = next(
                (d for d in mtg["documentList"] if "Packet" in d["templateName"]), None
            )
            if not pkt:
                continue

            yield {
                "meeting_id": mtg["id"],
                "title": mtg.get("title", ""),
                "start": mtg.get("dateTime", ""),
                "packet_url": self._packet_url(pkt),
            }


class CivicClerkAdapter:
    def __init__(self, city_slug: str):
        if not city_slug:
            raise ValueError("city_slug required, e.g. 'montpelliervt'")
        self.slug = city_slug
        self.base = f"https://{self.slug}.api.civicclerk.com"
        logger.info(f"Initialized CivicClerk adapter for {city_slug}")

    def _packet_url(self, doc):
        return f"https://{self.slug}.api.civicclerk.com/v1/Meetings/GetMeetingFileStream(fileId={doc['fileId']},plainText=false)"

    def upcoming_packets(self):
        try:
            logger.debug(f"Fetching upcoming meetings from CivicClerk for {self.slug}")
            current_date = datetime.now().strftime("%Y-%m-%dT%H:%M:%S.%fZ")[:-3] + "Z"
            params = {
                "$filter": f"startDateTime gt {current_date}",
                "$orderby": "startDateTime asc, eventName asc",
            }
            response = requests.get(
                f"{self.base}/v1/Events",
                params=params,
                headers=DEFAULT_HEADERS,
                timeout=30,
            )
            response.raise_for_status()
            data = response.json()
            meetings = data.get("value", [])
            logger.info(
                f"Retrieved {len(meetings)} meetings from CivicClerk for {self.slug}"
            )
        except Exception as e:
            logger.error(f"Failed to fetch CivicClerk meetings for {self.slug}: {e}")
            raise

        for mtg in meetings:
            pkt = next(
                (
                    d
                    for d in mtg.get("publishedFiles", [])
                    if d.get("type") == "Agenda Packet"
                ),
                None,
            )
            if not pkt:
                continue

            yield {
                "meeting_id": mtg["id"],
                "title": mtg.get("eventName", ""),
                "start": mtg.get("startDateTime", ""),
                "packet_url": self._packet_url(pkt),
            }


class GranicusAdapter:
    def __init__(self, city_slug: str):
        self.slug = city_slug
        self.base = f"https://{self.slug}.granicus.com"
        self.view_ids_file = "granicus_view_ids.json"
        
        # Create a robust HTTP session with proper timeouts
        self.session = requests.Session()
        self.session.headers.update(DEFAULT_HEADERS)
        
        # Set aggressive connection and read timeouts
        # Configure retry strategy
        retry_strategy = Retry(
            total=2,
            backoff_factor=1,
            status_forcelist=[429, 500, 502, 503, 504],
        )
        
        adapter = HTTPAdapter(max_retries=retry_strategy)
        self.session.mount("http://", adapter)
        self.session.mount("https://", adapter)

        # Load existing view_id mappings
        view_id_mappings = self._load_view_id_mappings()

        # Check if we already have a view_id for this base URL
        if self.base in view_id_mappings:
            self.view_id = view_id_mappings[self.base]
            logger.info(f"Found cached view_id {self.view_id} for {self.base}")
        else:
            # Discover and cache the view_id
            self.view_id = self._discover_view_id(self.base)
            view_id_mappings[self.base] = self.view_id
            self._save_view_id_mappings(view_id_mappings)
            logger.info(f"Discovered and cached view_id {self.view_id} for {self.base}")

        # Build the list URL
        self.list_url = f"{self.base}/ViewPublisher.php?view_id={self.view_id}"
        logger.info(
            f"{self.slug}: using view_id={self.view_id}  list_url={self.list_url}"
        )

    def all_meetings(self):
        """Get ALL meetings (with and without packets) for display to users"""
        soup = self._fetch_dom(self.list_url)

        # Find the "Upcoming Events" or "Upcoming Meetings" section
        header_options = ["h2", "h3"]
        for header in header_options:
            upcoming_header = soup.find(header, string="Upcoming Events")
            if not upcoming_header:
                upcoming_header = soup.find(header, string="Upcoming Meetings")
            else:
                break
        
        if not upcoming_header:
            logger.warning(f"No 'Upcoming Events' or 'Upcoming Meetings' section found for {self.slug}")
            return

        # Find the table that follows the "Upcoming Events" header
        upcoming_table = None
        for sibling in upcoming_header.find_next_siblings():
            if sibling.name == "table":
                upcoming_table = sibling
                break
            # Stop if we hit the archive section
            if sibling.name == "div" and sibling.get("class") == ["archive"]:
                break

        if not upcoming_table:
            logger.warning(f"No upcoming events table found for {self.slug}")
            return

        logger.info(f"Processing upcoming events table for {self.slug}")

        meetings_found = []

        # Process ALL meeting rows, not just ones with agenda links
        for row in upcoming_table.find_all("tr"):
            # Skip empty or header rows
            cells = row.find_all("td")
            if len(cells) < 2:
                continue
            
            # Extract meeting info from cells
            # Remove hidden spans (containing timestamps) before extracting text
            for span in cells[0].find_all('span', style=lambda x: x and 'display:none' in x):
                span.decompose()
            for span in cells[1].find_all('span', style=lambda x: x and 'display:none' in x):
                span.decompose()
            
            title = cells[0].get_text(" ", strip=True)
            start = cells[1].get_text(" ", strip=True)
            
            # Skip if no meaningful title
            if not title or title in ["Meeting", "Event"]:
                logger.info(f"No Title found for {self.base}{row}")
            
            # Look for agenda link in this row
            agenda_link = row.find("a", string=lambda s: s and "Agenda" in s)
            
            packet_url = None
            meeting_id = None
            
            if agenda_link:
                href = agenda_link.get("href", "")
                if href:
                    agenda_url = self._absolute(href)
                    meeting_id = self._clip_or_event_id(agenda_url)
                    
                    # Check if this is a direct PDF link
                    if ".pdf" in agenda_url.lower() or "GeneratedAgenda.ashx" in agenda_url:
                        # Direct PDF link
                        logger.debug(f"Found direct PDF link for {title}: {agenda_url}")
                        packet_url = agenda_url
                    elif "AgendaViewer.php" in agenda_url:
                        # AgendaViewer page - need to extract PDFs
                        try:
                            pdf_urls = self._extract_pdfs_from_agenda(agenda_url)
                            if pdf_urls:
                                logger.info(
                                    f"Found {len(pdf_urls)} PDFs for meeting: {title}"
                                )
                                packet_url = pdf_urls  # List of PDFs
                            else:
                                logger.debug(
                                    f"No PDFs found for meeting: {title}"
                                )
                        except Exception as e:
                            logger.debug(
                                f"Could not extract PDFs for {title}: {e}"
                            )
            
            # Generate a meeting_id if we don't have one
            if not meeting_id:
                # Use a hash of title + date as fallback ID
                import hashlib
                id_string = f"{title}_{start}"
                meeting_id = hashlib.md5(id_string.encode()).hexdigest()[:8]
            
            # Yield the meeting regardless of packet availability
            meeting_data = {
                "meeting_id": meeting_id,
                "title": title,
                "start": self._normalize_date(start),
                "packet_url": packet_url,  # Will be None, string URL, or list of URLs
                "has_packet": packet_url is not None,
            }
            meetings_found.append(meeting_data)
            yield meeting_data
        
        logger.info(f"Found {len(meetings_found)} total meetings")

    def _discover_view_id(self, url):
        """Brute force discover the view_id by testing a range of IDs"""
        tentative = f"{url}/ViewPublisher.php?view_id="
        logger.info(f"Discovering view_id for {url}")

        current_year = str(datetime.now().year)

        # Test an expanded range up to 100!
        for i in range(1, 101):
            try:
                response = self.session.get(
                    f"{tentative}{i}", timeout=(5, 10)
                )
                if response.status_code == 200:
                    # Check if the response contains actual meeting data AND current year
                    if (
                        "ViewPublisher" in response.text
                        and ("Meeting" in response.text or "Agenda" in response.text)
                        and current_year in response.text
                    ):
                        logger.info(
                            f"Found valid view_id {i} for {url} (contains {current_year} data)"
                        )
                        return i
            except Exception as e:
                logger.debug(f"Error testing view_id {i} for {url}: {e}")
                continue

        # If we couldn't find one with current year, try again without year check
        logger.warning(
            f"No view_id found with {current_year} data, trying without year filter..."
        )
        for i in range(1, 101):
            try:
                response = self.session.get(
                    f"{tentative}{i}", timeout=(5, 10)
                )
                if response.status_code == 200:
                    if "ViewPublisher" in response.text and (
                        "Meeting" in response.text or "Agenda" in response.text
                    ):
                        logger.warning(
                            f"Found view_id {i} for {url} (but no {current_year} data - might be stale)"
                        )
                        return i
            except Exception as e:
                logger.debug(f"Error testing view_id {i} for {url}: {e}")
                continue

        # If we get here, no valid view_id was found
        raise ValueError(f"Could not discover view_id for {url} in range 1-100")

    def _load_view_id_mappings(self):
        """Load existing view_id mappings from JSON file"""
        if os.path.exists(self.view_ids_file):
            try:
                with open(self.view_ids_file, "r") as f:
                    return json.load(f)
            except Exception as e:
                logger.warning(f"Failed to load view_id mappings: {e}")
        return {}

    def _save_view_id_mappings(self, mappings):
        """Save view_id mappings to JSON file"""
        try:
            with open(self.view_ids_file, "w") as f:
                json.dump(mappings, f, indent=2)
        except Exception as e:
            logger.error(f"Failed to save view_id mappings: {e}")

    @staticmethod
    def _clip_or_event_id(url: str) -> str:
        qs = parse_qs(urlparse(url).query)
        return qs.get("clip_id", qs.get("event_id", [""]))[0]

    def _fetch_dom(self, url: str) -> BeautifulSoup:
        logger.debug(f"GET {url}")
        # Handle S3 redirects with SSL issues
        try:
            # Use session with strict timeouts: 10s connect, 20s read
            r = self.session.get(url, timeout=(10, 20), allow_redirects=False)
            
            # If it's a redirect to S3, rewrite the URL to use path-style
            if r.status_code in [301, 302] and 's3.amazonaws.com' in r.headers.get('Location', ''):
                redirect_url = r.headers['Location']
                # Convert virtual-hosted-style to path-style S3 URL
                if 'granicus_production_attachments.s3.amazonaws.com' in redirect_url:
                    redirect_url = redirect_url.replace(
                        'granicus_production_attachments.s3.amazonaws.com',
                        's3.amazonaws.com/granicus_production_attachments'
                    )
                else:
                    logger.warning(f"Unknown redirect from Granicus for {url} towards {redirect_url}")
                r = self.session.get(redirect_url, timeout=(10, 20))
            else:
                # For non-S3 redirects, follow normally
                r = self.session.get(url, timeout=(10, 20))
                
            r.raise_for_status()
            return BeautifulSoup(r.text, "lxml")
        except Exception as e:
            logger.debug(f"Error fetching {url}: {e}")
            raise

    def _absolute(self, href: str) -> str:
        if href.startswith("//"):
            return "https:" + href
        elif href.startswith("http"):
            return href
        else:
            return urljoin(self.base + "/", href)

    @staticmethod
    def _normalize_date(raw: str) -> str:
        # Leave strictly textual parsing to downstream code;
        # just collapse whitespace here.
        return re.sub(r"\s+", " ", raw).strip()

    def _extract_pdfs_from_agenda(self, agenda_viewer_url):
        """Extract PDF URLs from the AgendaViewer page AND parse embedded PDFs"""
        pdf_urls = []

        # Check if the URL redirects directly to a PDF
        try:
            r = requests.get(agenda_viewer_url, headers=DEFAULT_HEADERS, timeout=30, allow_redirects=False)
            
            # If it redirects to a PDF, just return that PDF URL
            if r.status_code in [301, 302]:
                redirect_url = r.headers.get('Location', '')
                if redirect_url and ('.pdf' in redirect_url.lower() or 's3.amazonaws.com' in redirect_url):
                    # Handle S3 URL conversion if needed
                    if 'granicus_production_attachments.s3.amazonaws.com' in redirect_url:
                        redirect_url = redirect_url.replace(
                            'granicus_production_attachments.s3.amazonaws.com',
                            's3.amazonaws.com/granicus_production_attachments'
                        )
                    logger.debug(f"AgendaViewer redirects directly to PDF: {redirect_url}")
                    return [redirect_url]
        except Exception as e:
            logger.debug(f"Error checking for PDF redirect: {e}")

        try:
            # If no direct PDF redirect, parse as HTML page
            soup = self._fetch_dom(agenda_viewer_url)
        except Exception as e:
            logger.debug(f"Could not fetch agenda viewer page {agenda_viewer_url}: {e}")
            return []

        # Look for direct PDF links on the page
        for a in soup.select("a"):
            href = a.get("href", "")
            # Look for GeneratedAgenda.ashx or similar PDF endpoints
            if "GeneratedAgenda.ashx" in href or ".pdf" in href.lower():
                pdf_url = self._absolute(href)

                # Check if the PDF URL is valid before trying to parse it
                try:
                    resp = requests.head(
                        pdf_url,
                        headers=DEFAULT_HEADERS,
                        timeout=10,
                        allow_redirects=True,
                    )
                    if resp.status_code != 200:
                        logger.debug(
                            f"PDF URL returned {resp.status_code}, skipping: {pdf_url}"
                        )
                        continue
                except Exception as e:
                    logger.debug(f"Failed to check PDF URL {pdf_url}: {e}")
                    continue

                logger.debug(f"Found valid PDF: {pdf_url}")

                # Now parse this PDF for embedded links
                try:
                    embedded_pdfs = self._extract_embedded_pdfs(pdf_url)
                    if embedded_pdfs:
                        logger.info(
                            f"Found {len(embedded_pdfs)} embedded PDFs in {pdf_url}"
                        )
                        pdf_urls.extend(embedded_pdfs)
                    else:
                        # If no embedded PDFs, include the main PDF
                        logger.debug(
                            f"No embedded PDFs found, using main PDF: {pdf_url}"
                        )
                        pdf_urls.append(pdf_url)
                except Exception as e:
                    logger.debug(f"Could not extract embedded PDFs from {pdf_url}: {e}")
                    # Still include the main PDF even if we couldn't parse it
                    pdf_urls.append(pdf_url)

        return pdf_urls

    def _extract_embedded_pdfs(self, pdf_url):
        """Download PDF and extract embedded PDF links from it"""
        try:

            logger.info(f"Downloading PDF to extract embedded links: {pdf_url}")

            # Download the PDF
            resp = requests.get(pdf_url, headers=DEFAULT_HEADERS, timeout=60)
            resp.raise_for_status()

            # Save to temp file and parse
            with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
                tmp.write(resp.content)
                tmp_path = tmp.name

            try:
                # Open with PyMuPDF
                doc = fitz.open(tmp_path)
                embedded_urls = []

                # Search all pages for clickable links
                for page_num in range(len(doc)):
                    page = doc[page_num]
                    links = page.get_links()

                    for link in links:
                        if link.get("kind") == fitz.LINK_URI:
                            uri = link.get("uri", "")

                            # Look for ANY PDF links (not just Legistar)
                            if ".pdf" in uri.lower():
                                # Get the text around this link to check if it's minutes
                                link_rect = link.get("from")
                                if link_rect:
                                    # Extract text near the link
                                    text_near_link = page.get_textbox(link_rect)
                                    if (
                                        text_near_link
                                        and "minute" in text_near_link.lower()
                                    ):
                                        logger.debug(
                                            f"Skipping minutes PDF based on link text: {uri}"
                                        )
                                        continue

                                logger.debug(
                                    f"Found embedded PDF on page {page_num + 1}: {uri}"
                                )
                                embedded_urls.append(uri)

                doc.close()

                logger.info(
                    f"Extracted {len(embedded_urls)} embedded PDFs from {pdf_url}"
                )
                return embedded_urls

            finally:
                # Clean up temp file
                import os

                if os.path.exists(tmp_path):
                    os.unlink(tmp_path)

        except ImportError:
            logger.error("PyMuPDF (fitz) not installed. Run: pip install PyMuPDF")
            return []
        except Exception as e:
            logger.error(f"Failed to extract embedded PDFs from {pdf_url}: {e}")
            return []


class LegistarAdapter:
    def __init__(self, city_slug: str):
        self.city_slug = city_slug
        self.base = f"https://{city_slug}.legistar.com"

    def all_meetings(self):
        """Get ALL meetings (with and without packets) for display to users"""
        # Get calendar HTML
        resp = requests.get(
            f"{self.base}/Calendar.aspx", headers=DEFAULT_HEADERS, timeout=30
        )

        # Parse that deeply nested Legistar table from hell
        soup = BeautifulSoup(resp.text, "html.parser")

        # Find ALL meeting rows
        all_rows = soup.find_all("tr")
        meetings_found = []

        logger.info(f"Scanning {len(all_rows)} table rows for all meetings...")

        for row in all_rows:
            # Skip empty or header rows
            if not row.find_all("td"):
                continue

            meeting_data = self._extract_meeting_from_row(row)
            if meeting_data:
                meetings_found.append(meeting_data)
                yield meeting_data

        logger.info(f"Found {len(meetings_found)} total meetings")

    def _extract_meeting_from_row(self, row):
        """Extract meeting data from a table row, return None if not a meeting row"""
        try:
            # Look for meeting title link (various patterns Legistar uses)
            title_link = row.find(
                "a", id=re.compile(r"(hypBody|hypMeeting|hypTitle|hypName)")
            )
            if not title_link:
                return None

            title = title_link.text.strip()
            if not title or title in ["Meeting", "Event"]:
                return None

            # Extract meeting ID from title link if possible
            meeting_id = None
            meeting_detail_url = None
            title_href = title_link.get("href", "")
            if title_href:
                params = dict(re.findall(r"(\w+)=([^&]+)", title_href))
                meeting_id = params.get("ID")

                # Store the MeetingDetail.aspx URL for deep scraping
                if "MeetingDetail.aspx" in title_href:
                    if title_href.startswith("MeetingDetail.aspx"):
                        meeting_detail_url = f"{self.base}/{title_href}"
                    else:
                        meeting_detail_url = title_href

            # ALSO look for "Meeting details" links in the same row (SOLDIER DISCOVERY!)
            if not meeting_detail_url:
                detail_links = row.find_all(
                    "a", href=re.compile(r"MeetingDetail\.aspx")
                )
                for detail_link in detail_links:
                    detail_href = detail_link.get("href", "")
                    if detail_href:
                        # Extract meeting ID from detail link (more reliable)
                        detail_params = dict(re.findall(r"(\w+)=([^&]+)", detail_href))
                        if detail_params.get("ID"):
                            meeting_id = detail_params.get("ID")

                        # Store detail URL
                        if detail_href.startswith("MeetingDetail.aspx"):
                            meeting_detail_url = f"{self.base}/{detail_href}"
                        else:
                            meeting_detail_url = detail_href
                        break

            # Look for date in the row
            date = None
            date_cells = row.find_all("td")
            for cell in date_cells:
                cell_text = cell.text.strip()
                # Look for date patterns
                if re.search(r"\d{1,2}/\d{1,2}/\d{4}", cell_text):
                    date = cell_text
                    break

            # Check for agenda packet link in this row
            packet_url = None
            packet_link = row.find("a", id=re.compile(r"hypAgendaPacket"))

            if (
                packet_link
                and packet_link.get("href")
                and "Not available" not in packet_link.text
            ):
                packet_href = packet_link["href"]

                # Extract IDs from packet URL for more reliable meeting_id
                packet_params = dict(re.findall(r"(\w+)=([^&]+)", packet_href))
                if packet_params.get("ID"):
                    meeting_id = packet_params.get("ID")

                # Construct full packet URL
                if packet_href.startswith("View.ashx"):
                    packet_url = f"{self.base}/{packet_href}"
                else:
                    packet_url = packet_href

            # If no direct packet but we have a meeting detail URL, perform deep scraping immediately
            if not packet_url and meeting_detail_url:
                logger.debug(
                    f"Meeting {title} has detail URL - performing deep scrape immediately"
                )
                pdf_urls = self._deep_scrape_meeting_attachments(meeting_detail_url)
                if pdf_urls:
                    # Return the list of PDF URLs directly
                    packet_url = pdf_urls
                    logger.debug(
                        f"Deep scrape found {len(pdf_urls)} PDFs for meeting {title}"
                    )
                else:
                    logger.debug(f"Deep scrape found no PDFs for meeting {title}")

            # Generate a meeting_id if we don't have one
            if not meeting_id:
                # Use a hash of title + date as fallback ID
                import hashlib

                id_string = f"{title}_{date or 'no_date'}"
                meeting_id = hashlib.md5(id_string.encode()).hexdigest()[:8]

            return {
                "meeting_id": meeting_id,
                "title": title,
                "start": date,
                "packet_url": packet_url,  # Will be None, string URL, or list of URLs
                "meeting_detail_url": meeting_detail_url,  # For debugging
                "has_packet": packet_url is not None,
            }

        except Exception as e:
            logger.debug(f"Error extracting meeting from row: {e}")
            return None

    def _deep_scrape_meeting_attachments(self, meeting_detail_url):
        """Recursively scrape all PDF attachments from a meeting detail page"""
        pdf_urls = []

        try:
            # Get the meeting detail page
            resp = requests.get(meeting_detail_url, headers=DEFAULT_HEADERS, timeout=30)
            resp.raise_for_status()

            soup = BeautifulSoup(resp.text, "html.parser")

            # FIRST: Check for direct View.ashx PDFs on the meeting detail page
            direct_view_links = soup.find_all("a", href=re.compile(r"View\.ashx"))
            for view_link in direct_view_links:
                view_href = view_link.get("href")
                if not view_href:
                    continue

                # Construct full PDF URL
                if view_href.startswith("View.ashx"):
                    pdf_url = f"{self.base}/{view_href}"
                else:
                    pdf_url = view_href

                pdf_urls.append(pdf_url)
                logger.debug(f"Found direct PDF on meeting page: {pdf_url}")

            # SECOND: Find all LegislationDetail.aspx links and scrape them too
            legislation_links = soup.find_all(
                "a", href=re.compile(r"LegislationDetail\.aspx")
            )

            logger.debug(
                f"Found {len(direct_view_links)} direct PDFs and {len(legislation_links)} legislation detail links"
            )

            for leg_link in legislation_links:
                leg_href = leg_link.get("href")
                if not leg_href:
                    continue

                # Construct full URL
                if leg_href.startswith("LegislationDetail.aspx"):
                    leg_url = f"{self.base}/{leg_href}"
                else:
                    leg_url = leg_href

                # Scrape this legislation detail page for PDFs
                try:
                    leg_pdfs = self._scrape_legislation_pdfs(leg_url)
                    pdf_urls.extend(leg_pdfs)

                    # Be polite - small delay between requests
                    import time

                    time.sleep(0.5)

                except Exception as e:
                    logger.warning(f"Failed to scrape legislation page {leg_url}: {e}")
                    continue

            logger.debug(f"Deep scrape extracted {len(pdf_urls)} total PDFs")
            return pdf_urls

        except Exception as e:
            logger.error(
                f"Failed to deep scrape meeting detail {meeting_detail_url}: {e}"
            )
            return []

    def _scrape_legislation_pdfs(self, legislation_url):
        """Scrape PDF links from a single legislation detail page"""
        pdf_urls = []

        try:
            resp = requests.get(legislation_url, headers=DEFAULT_HEADERS, timeout=30)
            resp.raise_for_status()

            soup = BeautifulSoup(resp.text, "html.parser")

            # Find all View.ashx links (these are the PDFs we want)
            view_links = soup.find_all("a", href=re.compile(r"View\.ashx"))

            for view_link in view_links:
                view_href = view_link.get("href")
                if not view_href:
                    continue

                # Construct full PDF URL
                if view_href.startswith("View.ashx"):
                    pdf_url = f"{self.base}/{view_href}"
                else:
                    pdf_url = view_href

                pdf_urls.append(pdf_url)
                logger.debug(f"Found PDF: {pdf_url}")

            return pdf_urls

        except Exception as e:
            logger.warning(f"Failed to scrape PDFs from {legislation_url}: {e}")
            return []


class NovusAgendaAdapter:
    def __init__(self, city_slug: str):
        if not city_slug:
            raise ValueError("city_slug required, e.g. 'hagerstown'")
        self.slug = city_slug
        self.base = f"https://{self.slug}.novusagenda.com"
        logger.info(f"Initialized NovusAgenda adapter for {city_slug}")

    def upcoming_packets(self):
        """Scrape upcoming meetings from NovusAgenda /agendapublic endpoint"""
        try:
            logger.debug(f"Fetching upcoming meetings from NovusAgenda for {self.slug}")

            # Hit the agendapublic endpoint
            resp = requests.get(
                f"{self.base}/agendapublic", headers=DEFAULT_HEADERS, timeout=30
            )
            resp.raise_for_status()

            # Parse the HTML
            soup = BeautifulSoup(resp.text, "html.parser")

            # Find all meeting rows (rgRow and rgAltRow classes)
            meeting_rows = soup.find_all("tr", class_=["rgRow", "rgAltRow"])

            logger.info(
                f"Found {len(meeting_rows)} meeting rows from NovusAgenda for {self.slug}"
            )

            for row in meeting_rows:
                # Extract cells
                cells = row.find_all("td")
                if len(cells) < 5:
                    continue

                # Extract meeting data from table cells
                date = cells[0].get_text(strip=True)
                meeting_type = cells[1].get_text(strip=True)
                location = cells[2].get_text(strip=True)

                # Find the PDF link (DisplayAgendaPDF.ashx)
                pdf_link = row.find("a", href=re.compile(r"DisplayAgendaPDF\.ashx"))
                if not pdf_link:
                    continue

                # Extract meeting ID from the PDF link
                pdf_href = pdf_link.get("href", "")
                meeting_id_match = re.search(r"MeetingID=(\d+)", pdf_href)
                meeting_id = meeting_id_match.group(1) if meeting_id_match else None

                if not meeting_id:
                    continue

                # Construct full packet URL
                packet_url = f"{self.base}/agendapublic/{pdf_href}"

                yield {
                    "meeting_id": meeting_id,
                    "title": meeting_type,
                    "start": date,
                    "location": location,
                    "packet_url": packet_url,
                }

        except Exception as e:
            logger.error(f"Failed to fetch NovusAgenda meetings for {self.slug}: {e}")
            raise


class CivicPlusAdapter:
    def __init__(self, city_slug: str):
        if not city_slug:
            raise ValueError("city_slug required")
        self.city_slug = city_slug
        self.base_url = f"https://{city_slug}.civicplus.com"
        self.session = requests.Session()
        self.session.headers.update(
            {"User-Agent": "Engagic/1.0 (Civic Engagement Bot)"}
        )
        logger.info(f"Initialized CivicPlus adapter for {city_slug}")

    def _find_agenda_url(self):
        """Find the agenda page URL - first check homepage for external redirects"""
        logger.info(f"Finding agenda URL for {self.city_slug}")

        # FIRST: Check homepage for external agenda links (like MunicodeMetings)
        logger.info("Checking homepage for external agenda system links")
        try:
            resp = self.session.get(self.base_url, timeout=10)
            if resp.status_code == 200:
                soup = BeautifulSoup(resp.text, "html.parser")

                # Look for links with "agenda" in text that go to external systems
                agenda_links = []
                for link in soup.find_all("a", href=True):
                    link_text = link.get_text().strip().lower()
                    href = link["href"]

                    # Check if link text contains agenda-related keywords
                    if any(
                        word in link_text for word in ["agenda", "meeting", "minutes"]
                    ):
                        # Check if it's an external link (not CivicPlus)
                        if href.startswith("http") and "civicplus.com" not in href:
                            agenda_links.append(
                                {
                                    "text": link.get_text().strip(),
                                    "url": href,
                                    "domain": urlparse(href).netloc,
                                }
                            )

                if agenda_links:
                    logger.info(
                        f"Found {len(agenda_links)} external agenda links on homepage:"
                    )
                    for link_info in agenda_links:
                        logger.info(
                            f"  - '{link_info['text']}' -> {link_info['domain']}"
                        )

                    # Check for known meeting systems
                    known_systems = {
                        "municodemeetings.com": "municode",
                        "granicus.com": "granicus",
                        "legistar.com": "legistar",
                        "primegov.com": "primegov",
                        "civicclerk.com": "civicclerk",
                        "novusagenda.com": "novusagenda",
                        "iqm2.com": "granicus",
                        "destinyhosted.com": "destiny",
                    }

                    for link_info in agenda_links:
                        for domain_pattern, vendor in known_systems.items():
                            if domain_pattern in link_info["domain"]:
                                logger.warning(
                                    f"⚠️  This city uses {vendor} ({link_info['domain']}), not CivicPlus!"
                                )
                                logger.warning(
                                    f"    Update discovered_cities.json: {self.city_slug} -> vendor: '{vendor}'"
                                )
                                # Still try to process with CivicPlus adapter as fallback
                                break

        except Exception as e:
            logger.debug(f"Failed to check homepage: {e}")

        # THEN: Try standard CivicPlus agenda URLs
        logger.info("Trying standard CivicPlus agenda URLs")
        agenda_urls = [
            f"{self.base_url}/agendacenter",
            f"{self.base_url}/AgendaCenter",
            f"{self.base_url}/Government/Agendas",
            f"{self.base_url}/Agendas",
            f"{self.base_url}/Meetings",
        ]

        for url in agenda_urls:
            try:
                logger.debug(f"Trying agenda URL: {url}")
                resp = self.session.get(url, timeout=10)
                logger.debug(f"Response status: {resp.status_code}")

                if resp.status_code == 200:
                    # Check if it's actually an agenda page
                    text_lower = resp.text.lower()
                    keywords_found = [
                        kw
                        for kw in ["agenda", "meeting", "council"]
                        if kw in text_lower
                    ]

                    if keywords_found:
                        logger.info(
                            f"✓ Found agenda page at {url} (keywords: {keywords_found})"
                        )
                        return url
                    else:
                        logger.debug(
                            f"Page exists but no agenda keywords found at {url}"
                        )
                else:
                    logger.debug(f"Non-200 response ({resp.status_code}) for {url}")
            except Exception as e:
                logger.debug(
                    f"Failed to fetch {url}: {type(e).__name__}: {str(e)[:100]}"
                )
                continue

        # If no standard URL works, search homepage for agenda links
        logger.info(
            "Standard URLs failed, searching homepage for CivicPlus agenda links"
        )
        try:
            resp = self.session.get(self.base_url, timeout=10)
            logger.debug(f"Homepage status: {resp.status_code}")
            soup = BeautifulSoup(resp.text, "html.parser")

            agenda_links_found = []
            for link in soup.find_all("a", href=True):
                href = link["href"]
                text = link.get_text().strip().lower()

                if any(word in text for word in ["agenda", "meeting", "council"]):
                    if href.startswith("http"):
                        url = href
                    else:
                        url = urljoin(self.base_url, href)

                    agenda_links_found.append((text[:50], url))

                    # Make sure it's still on CivicPlus
                    if "civicplus.com" in url:
                        logger.info(
                            f"✓ Found agenda link on homepage: '{text[:50]}' -> {url}"
                        )
                        return url

            if agenda_links_found:
                logger.debug(
                    f"Found {len(agenda_links_found)} agenda-related links but none on CivicPlus"
                )
                for text, url in agenda_links_found[:3]:
                    logger.debug(f"  - '{text}' -> {url}")
        except Exception as e:
            logger.warning(
                f"Failed to search homepage: {type(e).__name__}: {str(e)[:100]}"
            )

        # Default to agendacenter
        default_url = f"{self.base_url}/agendacenter"
        logger.warning(f"No agenda URL found, defaulting to {default_url}")
        return default_url

    def _parse_agenda_item(self, item):
        """Parse a single agenda item from CivicPlus"""
        try:
            # CivicPlus usually has structure like:
            # <div class="agenda-item">
            #   <h3>Meeting Name</h3>
            #   <div class="date">Date</div>
            #   <a href="/DocumentCenter/View/123/Agenda-PDF">Agenda</a>
            # </div>

            meeting_info = {}
            item_text = item.get_text().strip()
            logger.debug(f"Parsing agenda item: {item_text[:100]}...")

            # Try to find meeting name
            title_elem = item.find(["h3", "h4", "h5", "strong", "b"])
            if title_elem:
                meeting_info["meeting_name"] = title_elem.get_text().strip()
                logger.debug(f"  Found title: {meeting_info['meeting_name']}")
            else:
                # Fallback - use first text
                meeting_info["meeting_name"] = item_text[:100]
                logger.debug(
                    f"  No title element, using text: {meeting_info['meeting_name']}"
                )

            # Skip generic UI elements
            generic_names = [
                "tools",
                "search",
                "filter",
                "sort",
                "view",
                "options",
                "settings",
                "agenda center",
                "document center",
                "home",
                "back",
                "next",
                "previous",
            ]
            if meeting_info["meeting_name"].lower().strip() in generic_names:
                logger.debug(
                    f"  Skipping generic UI element: {meeting_info['meeting_name']}"
                )
                return None

            # Try to find date
            date_text = None
            date_elem = item.find(class_=re.compile(r"date|time|when"))
            if date_elem:
                date_text = date_elem.get_text().strip()
                logger.debug(f"  Found date element: {date_text}")
            else:
                # Search for date pattern
                date_match = re.search(
                    r"\b(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]* \d{1,2},? \d{4}\b",
                    item.get_text(),
                    re.IGNORECASE,
                )
                if date_match:
                    date_text = date_match.group()
                    logger.debug(f"  Found date pattern: {date_text}")

            if date_text:
                # Try parsing common date formats
                for fmt in ["%B %d, %Y", "%b %d, %Y", "%m/%d/%Y", "%Y-%m-%d"]:
                    try:
                        meeting_info["meeting_date"] = datetime.strptime(date_text, fmt)
                        logger.debug(f"  Parsed date: {meeting_info['meeting_date']}")
                        break
                    except:
                        continue

                if "meeting_date" not in meeting_info:
                    logger.debug(f"  Could not parse date: {date_text}")
                    meeting_info["meeting_date"] = None
            else:
                logger.debug("  No date found in item")

            # Find PDF link
            pdf_link = None
            all_links = item.find_all("a", href=True)
            logger.debug(f"  Found {len(all_links)} links in item")

            for link in all_links:
                href = link["href"]
                link_text = link.get_text().lower()

                # Skip generic DocumentCenter links
                if "/documentcenter" in href.lower() and "/view/" not in href.lower():
                    continue

                # Look for agenda/packet links
                if any(
                    word in link_text
                    for word in ["agenda", "packet", "pdf", "download"]
                ):
                    if href.startswith("http"):
                        pdf_link = href
                    else:
                        pdf_link = urljoin(self.base_url, href)
                    logger.debug(
                        f"  Found agenda link by text '{link_text[:30]}': {pdf_link}"
                    )
                    break

                # Also check href for PDF or specific document view
                if ".pdf" in href.lower() or "/documentcenter/view/" in href.lower():
                    if href.startswith("http"):
                        pdf_link = href
                    else:
                        pdf_link = urljoin(self.base_url, href)
                    logger.debug(f"  Found PDF link by URL pattern: {pdf_link}")
                    break

            if pdf_link:
                # Check if this is a direct PDF or needs deep scraping
                # CivicPlus ViewFile URLs are direct PDFs even without .pdf extension
                if ".pdf" in pdf_link.lower() or "/ViewFile/" in pdf_link:
                    meeting_info["packet_url"] = pdf_link
                    logger.info(f"  ✓ Direct PDF: {pdf_link}")
                else:
                    # This might be a detail page with nested PDFs
                    logger.info(f"  Deep scraping {pdf_link} for nested PDFs")
                    nested_pdfs = deep_scrape_pdfs(pdf_link, self.base_url, max_depth=2)
                    if nested_pdfs:
                        logger.info(f"  ✓ Found {len(nested_pdfs)} nested PDFs")
                        for i, pdf in enumerate(nested_pdfs[:3]):
                            logger.debug(f"    PDF {i + 1}: {pdf}")
                        if len(nested_pdfs) > 3:
                            logger.debug(f"    ... and {len(nested_pdfs) - 3} more")
                        meeting_info["packet_url"] = (
                            nested_pdfs  # List of PDFs like Legistar
                        )
                    else:
                        logger.warning(
                            f"  No nested PDFs found, using original link: {pdf_link}"
                        )
                        meeting_info["packet_url"] = (
                            pdf_link  # Fallback to original link
                        )

                meeting_info["meeting_id"] = self._extract_meeting_id(pdf_link)
                return meeting_info
            else:
                logger.debug("  No PDF link found in item")

        except Exception as e:
            logger.error(f"Error parsing agenda item: {e}")

        return None

    def _extract_meeting_id(self, url):
        """Extract a meeting ID from URL"""
        # Try to find numeric ID in URL
        match = re.search(r"/(\d{3,})", url)
        if match:
            return match.group(1)

        # Fallback to URL hash
        return str(hash(url))[-8:]

    def all_meetings(self):
        """Fetch all available meetings from CivicPlus"""
        meetings = []

        try:
            # Find the agenda page
            agenda_url = self._find_agenda_url()

            # Add date range parameters (today to 2 weeks from now)
            today = datetime.now()
            two_weeks = today + timedelta(days=14)

            # Format dates as MM/DD/YYYY for CivicPlus
            start_date = today.strftime("%m/%d/%Y")
            end_date = two_weeks.strftime("%m/%d/%Y")

            # Build search URL with date parameters
            search_params = f"/Search/?term=&CIDs=all&startDate={start_date}&endDate={end_date}&dateRange=&dateSelector="

            # If agenda_url ends with /agendacenter, append search params
            if agenda_url.lower().endswith("/agendacenter"):
                agenda_url_with_dates = agenda_url.rstrip("/") + search_params
            else:
                # For other URLs, try to use the base URL + agendacenter + search
                agenda_url_with_dates = f"{self.base_url}/agendacenter{search_params}"

            logger.info(f"Fetching meetings from {start_date} to {end_date}")
            logger.info(f"URL: {agenda_url_with_dates}")

            resp = self.session.get(agenda_url_with_dates, timeout=30)
            resp.raise_for_status()
            logger.info(f"Successfully loaded agenda page, status: {resp.status_code}")

            soup = BeautifulSoup(resp.text, "html.parser")

            # CivicPlus has various structures, try multiple selectors
            selectors = [
                "div.agendaItem",
                "div.agenda-item",
                "div.meeting-item",
                "div.MeetingItem",
                "tr.agendaRow",
                "div.widgetRow",
                "article.meeting",
                "li.meeting-list-item",
                # Search results specific selectors
                "div.searchResult",
                "div.result-item",
                "table.agendaTable tr",
            ]

            items = []
            for selector in selectors:
                items = soup.select(selector)
                if items:
                    logger.info(
                        f"✓ Found {len(items)} items with selector: '{selector}'"
                    )
                    break
                else:
                    logger.debug(f"No items found with selector: '{selector}'")

            if not items:
                logger.info(
                    "No items found with standard selectors, trying fallback search"
                )
                # Fallback: look for any div/tr containing both a date and "agenda"
                all_divs = soup.find_all(["div", "tr", "li", "article"])
                logger.debug(f"Scanning {len(all_divs)} elements for agenda items")

                for div in all_divs:
                    text = div.get_text().lower()
                    if "agenda" in text and any(
                        month in text
                        for month in [
                            "jan",
                            "feb",
                            "mar",
                            "apr",
                            "may",
                            "jun",
                            "jul",
                            "aug",
                            "sep",
                            "oct",
                            "nov",
                            "dec",
                        ]
                    ):
                        items.append(div)

                if items:
                    logger.info(f"✓ Found {len(items)} items using fallback search")
                else:
                    logger.warning(f"No agenda items found on page {agenda_url}")

            # If we're on a search results page, also look for direct ViewFile links
            if "/Search/" in agenda_url_with_dates:
                logger.info(
                    "Detected search results page, looking for direct ViewFile links"
                )
                viewfile_links = soup.find_all(
                    "a", href=re.compile(r"/ViewFile/Agenda/")
                )

                if viewfile_links:
                    logger.info(
                        f"Found {len(viewfile_links)} direct ViewFile agenda links"
                    )
                    valid_viewfiles = 0

                    for link in viewfile_links:
                        href = link["href"]
                        text = link.get_text().strip()

                        # Skip minutes and generic text
                        if "minutes" in text.lower():
                            continue

                        # Skip generic link text
                        generic_texts = [
                            "pdf",
                            "view",
                            "download",
                            "agenda",
                            "html",
                            "packet",
                        ]
                        if text.lower() in generic_texts:
                            # Try to find better text from parent element
                            parent = link.find_parent(["tr", "div", "li", "td"])
                            if parent:
                                parent_text = parent.get_text().strip()
                                # Look for meeting name pattern
                                lines = parent_text.split("\n")
                                for line in lines:
                                    line = line.strip()
                                    if (
                                        line
                                        and line.lower() not in generic_texts
                                        and len(line) > 10
                                    ):
                                        text = line
                                        break

                        # Skip if still generic
                        if text.lower() in generic_texts or len(text) < 5:
                            logger.debug(f"Skipping generic ViewFile link: {text}")
                            continue

                        # Create meeting info from direct link
                        meeting_info = {
                            "meeting_name": text[:100],
                            "packet_url": urljoin(self.base_url, href),
                            "meeting_id": self._extract_meeting_id(href),
                        }

                        # Try to extract date from link
                        date_match = re.search(r"_(\d{8})-", href)
                        if date_match:
                            date_str = date_match.group(1)
                            try:
                                meeting_info["meeting_date"] = datetime.strptime(
                                    date_str, "%m%d%Y"
                                )
                            except:
                                pass

                        meetings.append(meeting_info)
                        valid_viewfiles += 1
                        logger.debug(
                            f"Added direct ViewFile: {meeting_info['meeting_name']}"
                        )

                    if valid_viewfiles > 0:
                        logger.info(
                            f"Added {valid_viewfiles} valid meetings from direct ViewFile links"
                        )
                        return meetings  # Return early if we found direct links

            # Parse each item
            logger.info(f"Parsing {len(items)} potential meeting items")
            valid_meetings = 0

            for i, item in enumerate(items):
                logger.debug(f"\n--- Processing item {i + 1}/{len(items)} ---")
                meeting = self._parse_agenda_item(item)
                if meeting and "packet_url" in meeting:
                    meetings.append(meeting)
                    valid_meetings += 1
                    logger.info(
                        f"✓ Valid meeting: {meeting.get('meeting_name', 'Unknown')[:50]}"
                    )
                else:
                    logger.debug("✗ Invalid/incomplete meeting item")

            logger.info(
                f"\nSummary: Found {valid_meetings} valid meetings with packets out of {len(items)} items for {self.city_slug}"
            )

        except Exception as e:
            logger.error(
                f"Error fetching CivicPlus meetings for {self.city_slug}: {type(e).__name__}: {str(e)}"
            )
            import traceback

            logger.debug(traceback.format_exc())

        return meetings