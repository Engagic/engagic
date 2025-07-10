import re
import requests
import logging
import json
import os
from urllib.parse import urlencode, urljoin, urlparse, parse_qs
from bs4 import BeautifulSoup
from datetime import datetime

logger = logging.getLogger("engagic")

# Polite scraping headers
DEFAULT_HEADERS = {
    'User-Agent': 'Engagic/1.0 (Civic Engagement Bot; Engagic Is For The People)',
    'Accept': 'application/json, text/html, application/xhtml+xml, application/xml;q=0.9, */*;q=0.8',
    'Accept-Language': 'en-US,en;q=0.5',
    'Accept-Encoding': 'gzip, deflate',
    'Connection': 'keep-alive',
    'Upgrade-Insecure-Requests': '1'
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
                timeout=30
            )
            resp.raise_for_status()
            meetings = resp.json()
            logger.info(f"Retrieved {len(meetings)} meetings from PrimeGov for {self.slug}")
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
            response = requests.get(f"{self.base}/v1/Events", params=params, headers=DEFAULT_HEADERS, timeout=30)
            response.raise_for_status()
            data = response.json()
            meetings = data.get("value", [])
            logger.info(f"Retrieved {len(meetings)} meetings from CivicClerk for {self.slug}")
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
        logger.info(f"{self.slug}: using view_id={self.view_id}  list_url={self.list_url}")

    def upcoming_packets(self):
        soup = self._fetch_dom(self.list_url)
        
        # Find the "Upcoming Events" section
        upcoming_header = soup.find("h2", string="Upcoming Events")
        if not upcoming_header:
            logger.warning(f"No 'Upcoming Events' section found for {self.slug}")
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
        
        # Only process agenda links within the upcoming events table
        for a in upcoming_table.select("a"):
            if a.string and "Agenda" in a.string:      # human-visible "Agenda"
                href = a.get("href", "")
                if not href:
                    continue
                    
                agenda_url = self._absolute(href)
                
                row = a.find_parent("tr")
                if not row:
                    continue
                cells = row.find_all("td")
                if len(cells) < 2:
                    continue
                title = cells[0].get_text(" ", strip=True)
                start = cells[1].get_text(" ", strip=True)
                
                # Check if this is a direct PDF link
                if ".pdf" in agenda_url.lower() or "GeneratedAgenda.ashx" in agenda_url:
                    # Direct PDF link
                    logger.debug(f"Found direct PDF link for {title}: {agenda_url}")
                    yield {
                        "meeting_id": self._clip_or_event_id(agenda_url),
                        "title": title,
                        "start": self._normalize_date(start),
                        "packet_url": agenda_url,  # Single PDF
                    }
                elif "AgendaViewer.php" in agenda_url:
                    # AgendaViewer page - need to extract PDFs
                    try:
                        pdf_urls = self._extract_pdfs_from_agenda(agenda_url)
                        if pdf_urls:
                            logger.info(f"Found {len(pdf_urls)} PDFs for meeting: {title}")
                            yield {
                                "meeting_id": self._clip_or_event_id(agenda_url),
                                "title": title,
                                "start": self._normalize_date(start),
                                "packet_url": pdf_urls,  # List of PDFs
                            }
                        else:
                            logger.debug(f"No PDFs found for meeting: {title}, skipping")
                    except Exception as e:
                        logger.debug(f"Could not extract PDFs for {title}, moving on: {e}")
                        continue
                else:
                    logger.debug(f"Skipping non-PDF/non-AgendaViewer link: {agenda_url}")

    def _discover_view_id(self, url):
        """Brute force discover the view_id by testing a range of IDs"""
        tentative = f"{url}/ViewPublisher.php?view_id="
        logger.info(f"Discovering view_id for {url}")
        
        current_year = str(datetime.now().year)
        
        # Test an expanded range up to 100!
        for i in range(1, 101):
            try:
                response = requests.get(f"{tentative}{i}", headers=DEFAULT_HEADERS, timeout=30)
                if response.status_code == 200:
                    # Check if the response contains actual meeting data AND current year
                    if ("ViewPublisher" in response.text and 
                        ("Meeting" in response.text or "Agenda" in response.text) and
                        current_year in response.text):
                        logger.info(f"Found valid view_id {i} for {url} (contains {current_year} data)")
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
                with open(self.view_ids_file, 'r') as f:
                    return json.load(f)
            except Exception as e:
                logger.warning(f"Failed to load view_id mappings: {e}")
        return {}
    
    def _save_view_id_mappings(self, mappings):
        """Save view_id mappings to JSON file"""
        try:
            with open(self.view_ids_file, 'w') as f:
                json.dump(mappings, f, indent=2)
        except Exception as e:
            logger.error(f"Failed to save view_id mappings: {e}")

    @staticmethod
    def _clip_or_event_id(url: str) -> str:
        qs = parse_qs(urlparse(url).query)
        return qs.get("clip_id", qs.get("event_id", [""]))[0]

    def _fetch_dom(self, url: str) -> BeautifulSoup:
        logger.debug(f"GET {url}")
        r = requests.get(url, headers=DEFAULT_HEADERS, timeout=30)
        r.raise_for_status()
        return BeautifulSoup(r.text, "lxml")

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
        
        try:
            # First, get the AgendaViewer page
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
                    resp = requests.head(pdf_url, headers=DEFAULT_HEADERS, timeout=10, allow_redirects=True)
                    if resp.status_code != 200:
                        logger.debug(f"PDF URL returned {resp.status_code}, skipping: {pdf_url}")
                        continue
                except Exception as e:
                    logger.debug(f"Failed to check PDF URL {pdf_url}: {e}")
                    continue
                
                logger.debug(f"Found valid PDF: {pdf_url}")
                
                # Now parse this PDF for embedded links
                try:
                    embedded_pdfs = self._extract_embedded_pdfs(pdf_url)
                    if embedded_pdfs:
                        logger.info(f"Found {len(embedded_pdfs)} embedded PDFs in {pdf_url}")
                        pdf_urls.extend(embedded_pdfs)
                    else:
                        # If no embedded PDFs, include the main PDF
                        logger.debug(f"No embedded PDFs found, using main PDF: {pdf_url}")
                        pdf_urls.append(pdf_url)
                except Exception as e:
                    logger.debug(f"Could not extract embedded PDFs from {pdf_url}: {e}")
                    # Still include the main PDF even if we couldn't parse it
                    pdf_urls.append(pdf_url)
        
        return pdf_urls
    
    def _extract_embedded_pdfs(self, pdf_url):
        """Download PDF and extract embedded PDF links from it"""
        try:
            import tempfile
            import fitz  # PyMuPDF
            
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
                                    if text_near_link and "minute" in text_near_link.lower():
                                        logger.debug(f"Skipping minutes PDF based on link text: {uri}")
                                        continue
                                
                                logger.debug(f"Found embedded PDF on page {page_num + 1}: {uri}")
                                embedded_urls.append(uri)
                
                doc.close()
                
                logger.info(f"Extracted {len(embedded_urls)} embedded PDFs from {pdf_url}")
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
        resp = requests.get(f"{self.base}/Calendar.aspx", headers=DEFAULT_HEADERS, timeout=30)
        
        # Parse that deeply nested Legistar table from hell
        soup = BeautifulSoup(resp.text, 'html.parser')
        
        # Find ALL meeting rows
        all_rows = soup.find_all('tr')
        meetings_found = []
        
        logger.info(f"Scanning {len(all_rows)} table rows for all meetings...")
        
        for row in all_rows:
            # Skip empty or header rows
            if not row.find_all('td'):
                continue
                
            meeting_data = self._extract_meeting_from_row(row)
            if meeting_data:
                meetings_found.append(meeting_data)
                yield meeting_data
        
        logger.info(f"Found {len(meetings_found)} total meetings")
    
    def upcoming_packets(self):
        """Get only meetings with packets (for backward compatibility)"""
        # Get all meetings and filter for ones with packets
        for meeting in self.all_meetings():
            if meeting.get('packet_url'):
                yield meeting
    
    def _extract_meeting_from_row(self, row):
        """Extract meeting data from a table row, return None if not a meeting row"""
        try:
            # Look for meeting title link (various patterns Legistar uses)
            title_link = row.find('a', id=re.compile(r'(hypBody|hypMeeting|hypTitle|hypName)'))
            if not title_link:
                return None
                
            title = title_link.text.strip()
            if not title or title in ['Meeting', 'Event']:
                return None
            
            # Extract meeting ID from title link if possible
            meeting_id = None
            meeting_detail_url = None
            title_href = title_link.get('href', '')
            if title_href:
                params = dict(re.findall(r'(\w+)=([^&]+)', title_href))
                meeting_id = params.get('ID')
                
                # Store the MeetingDetail.aspx URL for deep scraping
                if 'MeetingDetail.aspx' in title_href:
                    if title_href.startswith('MeetingDetail.aspx'):
                        meeting_detail_url = f"{self.base}/{title_href}"
                    else:
                        meeting_detail_url = title_href
            
            # ALSO look for "Meeting details" links in the same row (SOLDIER DISCOVERY!)
            if not meeting_detail_url:
                detail_links = row.find_all('a', href=re.compile(r'MeetingDetail\.aspx'))
                for detail_link in detail_links:
                    detail_href = detail_link.get('href', '')
                    if detail_href:
                        # Extract meeting ID from detail link (more reliable)
                        detail_params = dict(re.findall(r'(\w+)=([^&]+)', detail_href))
                        if detail_params.get('ID'):
                            meeting_id = detail_params.get('ID')
                        
                        # Store detail URL
                        if detail_href.startswith('MeetingDetail.aspx'):
                            meeting_detail_url = f"{self.base}/{detail_href}"
                        else:
                            meeting_detail_url = detail_href
                        break
            
            # Look for date in the row
            date = None
            date_cells = row.find_all('td')
            for cell in date_cells:
                cell_text = cell.text.strip()
                # Look for date patterns
                if re.search(r'\d{1,2}/\d{1,2}/\d{4}', cell_text):
                    date = cell_text
                    break
            
            # Check for agenda packet link in this row
            packet_url = None
            packet_link = row.find('a', id=re.compile(r'hypAgendaPacket'))
            
            if packet_link and packet_link.get('href') and 'Not available' not in packet_link.text:
                packet_href = packet_link['href']
                
                # Extract IDs from packet URL for more reliable meeting_id
                packet_params = dict(re.findall(r'(\w+)=([^&]+)', packet_href))
                if packet_params.get('ID'):
                    meeting_id = packet_params.get('ID')
                
                # Construct full packet URL
                if packet_href.startswith('View.ashx'):
                    packet_url = f"{self.base}/{packet_href}"
                else:
                    packet_url = packet_href
            
            # If no direct packet but we have a meeting detail URL, perform deep scraping immediately
            if not packet_url and meeting_detail_url:
                logger.debug(f"Meeting {title} has detail URL - performing deep scrape immediately")
                pdf_urls = self._deep_scrape_meeting_attachments(meeting_detail_url)
                if pdf_urls:
                    # Return the list of PDF URLs directly
                    packet_url = pdf_urls
                    logger.debug(f"Deep scrape found {len(pdf_urls)} PDFs for meeting {title}")
                else:
                    logger.debug(f"Deep scrape found no PDFs for meeting {title}")
            
            # Generate a meeting_id if we don't have one
            if not meeting_id:
                # Use a hash of title + date as fallback ID
                import hashlib
                id_string = f"{title}_{date or 'no_date'}"
                meeting_id = hashlib.md5(id_string.encode()).hexdigest()[:8]
            
            return {
                'meeting_id': meeting_id,
                'title': title,
                'start': date,
                'packet_url': packet_url,  # Will be None, string URL, or list of URLs
                'meeting_detail_url': meeting_detail_url,  # For debugging
                'has_packet': packet_url is not None
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
            
            soup = BeautifulSoup(resp.text, 'html.parser')
            
            # FIRST: Check for direct View.ashx PDFs on the meeting detail page
            direct_view_links = soup.find_all('a', href=re.compile(r'View\.ashx'))
            for view_link in direct_view_links:
                view_href = view_link.get('href')
                if not view_href:
                    continue
                
                # Construct full PDF URL
                if view_href.startswith('View.ashx'):
                    pdf_url = f"{self.base}/{view_href}"
                else:
                    pdf_url = view_href
                
                pdf_urls.append(pdf_url)
                logger.debug(f"Found direct PDF on meeting page: {pdf_url}")
            
            # SECOND: Find all LegislationDetail.aspx links and scrape them too
            legislation_links = soup.find_all('a', href=re.compile(r'LegislationDetail\.aspx'))
            
            logger.debug(f"Found {len(direct_view_links)} direct PDFs and {len(legislation_links)} legislation detail links")
            
            for leg_link in legislation_links:
                leg_href = leg_link.get('href')
                if not leg_href:
                    continue
                    
                # Construct full URL
                if leg_href.startswith('LegislationDetail.aspx'):
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
            logger.error(f"Failed to deep scrape meeting detail {meeting_detail_url}: {e}")
            return []
    
    def _scrape_legislation_pdfs(self, legislation_url):
        """Scrape PDF links from a single legislation detail page"""
        pdf_urls = []
        
        try:
            resp = requests.get(legislation_url, headers=DEFAULT_HEADERS, timeout=30)
            resp.raise_for_status()
            
            soup = BeautifulSoup(resp.text, 'html.parser')
            
            # Find all View.ashx links (these are the PDFs we want)
            view_links = soup.find_all('a', href=re.compile(r'View\.ashx'))
            
            for view_link in view_links:
                view_href = view_link.get('href')
                if not view_href:
                    continue
                
                # Construct full PDF URL
                if view_href.startswith('View.ashx'):
                    pdf_url = f"{self.base}/{view_href}"
                else:
                    pdf_url = view_href
                
                pdf_urls.append(pdf_url)
                logger.debug(f"Found PDF: {pdf_url}")
            
            return pdf_urls
            
        except Exception as e:
            logger.warning(f"Failed to scrape PDFs from {legislation_url}: {e}")
            return []
    
        
class NovusAgendaAdapter():
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
            resp = requests.get(f"{self.base}/agendapublic", headers=DEFAULT_HEADERS, timeout=30)
            resp.raise_for_status()
            
            # Parse the HTML
            soup = BeautifulSoup(resp.text, 'html.parser')
            
            # Find all meeting rows (rgRow and rgAltRow classes)
            meeting_rows = soup.find_all('tr', class_=['rgRow', 'rgAltRow'])
            
            logger.info(f"Found {len(meeting_rows)} meeting rows from NovusAgenda for {self.slug}")
            
            for row in meeting_rows:
                # Extract cells
                cells = row.find_all('td')
                if len(cells) < 5:
                    continue
                
                # Extract meeting data from table cells
                date = cells[0].get_text(strip=True)
                meeting_type = cells[1].get_text(strip=True)
                location = cells[2].get_text(strip=True)
                
                # Find the PDF link (DisplayAgendaPDF.ashx)
                pdf_link = row.find('a', href=re.compile(r'DisplayAgendaPDF\.ashx'))
                if not pdf_link:
                    continue
                
                # Extract meeting ID from the PDF link
                pdf_href = pdf_link.get('href', '')
                meeting_id_match = re.search(r'MeetingID=(\d+)', pdf_href)
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
                    "packet_url": packet_url
                }
                
        except Exception as e:
            logger.error(f"Failed to fetch NovusAgenda meetings for {self.slug}: {e}")
            raise