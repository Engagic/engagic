"""
HTML Agenda Parser - Extract agenda items and participation info from PrimeGov HTML

PrimeGov's Portal/Meeting pages have structured HTML with:
- Participation info in the page header
- <div class="agenda-item"> for each item
- <div class="item_contents"> with attachments
"""

import re
import logging
from typing import Dict, Any, List
from bs4 import BeautifulSoup

logger = logging.getLogger("engagic")


def parse_primegov_html_agenda(html: str) -> Dict[str, Any]:
    """
    Parse PrimeGov HTML agenda to extract items and participation info.

    Args:
        html: HTML content from /Portal/Meeting page

    Returns:
        {
            'participation': {...},  # Contact info (email, phone, zoom, etc.)
            'items': [               # Agenda items
                {
                    'item_id': str,
                    'title': str,
                    'sequence': int,
                    'attachments': [{'name': str, 'history_id': str, 'url': str}]
                }
            ]
        }
    """
    soup = BeautifulSoup(html, 'html.parser')

    # Extract participation info from page text (before agenda items)
    page_text = soup.get_text()
    participation = _extract_participation_info(page_text)

    # Extract agenda items
    items = _extract_agenda_items(soup)

    logger.debug(
        f"[HTMLParser] Extracted {len(items)} agenda items, "
        f"participation fields: {list(participation.keys())}"
    )

    return {
        'participation': participation,
        'items': items,
    }


def _extract_participation_info(text: str) -> Dict[str, Any]:
    """Extract participation info from page text using regex patterns"""
    info = {}

    # Email
    email_pattern = r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'
    emails = re.findall(email_pattern, text, re.IGNORECASE)
    if emails:
        valid = [e for e in emails if not any(skip in e.lower() for skip in ['example.com', 'test@', 'noreply'])]
        if valid:
            info['email'] = valid[0]

    # Phone (look for "Phone:" prefix to avoid meeting IDs)
    phone_patterns = [
        r'[Pp]hone[:\s]+(\+?1?\s*\(?\d{3}\)?[\s.-]?\d{3}[\s.-]?\d{4})',  # "Phone: 1(669)900-6833"
        r'\b1\s*\(\d{3}\)\s*\d{3}-\d{4}\b',  # 1(669)900-6833
    ]
    for pattern in phone_patterns:
        matches = re.findall(pattern, text)
        if matches:
            # Extract first match (may be tuple from capture group)
            phone_text = matches[0] if isinstance(matches[0], str) else matches[0]
            phone = re.sub(r'[^\d]', '', phone_text)
            if len(phone) == 10:
                phone = f"+1{phone}"
            elif len(phone) == 11 and phone.startswith('1'):
                phone = f"+{phone}"
            info['phone'] = phone
            break

    # Virtual meeting URLs (stop at closing paren/bracket)
    url_pattern = r'https?://[^\s<>"{}|\\^`\[\]\)\]]+'
    urls = re.findall(url_pattern, text, re.IGNORECASE)
    virtual_domains = ['zoom.us', 'meet.google.com', 'teams.microsoft.com', 'webex.com', 'gotomeeting.com']
    for url in urls:
        if any(domain in url.lower() for domain in virtual_domains):
            info['virtual_url'] = url
            break

    # Zoom meeting ID
    if 'zoom' in text.lower():
        meeting_id_pattern = r'meeting\s*id[:\s]+(\d{3}[\s-]?\d{3,4}[\s-]?\d{4})'
        meeting_ids = re.findall(meeting_id_pattern, text, re.IGNORECASE)
        if meeting_ids:
            info['meeting_id'] = meeting_ids[0].strip()

    # Hybrid/virtual detection
    text_lower = text.lower()
    hybrid_keywords = ['hybrid', 'in-person and virtual', 'attend in person or', 'zoom or in person']
    if any(kw in text_lower for kw in hybrid_keywords):
        info['is_hybrid'] = True
    elif info.get('virtual_url'):
        info['is_virtual_only'] = True

    return info


def _extract_agenda_items(soup: BeautifulSoup) -> List[Dict[str, Any]]:
    """Extract agenda items from HTML structure"""
    items = []

    # Find all agenda items
    agenda_items = soup.find_all('div', class_='agenda-item')

    for sequence, item_div in enumerate(agenda_items, 1):
        # Get item ID from div (format: "AgendaItem_12345")
        item_full_id = item_div.get('id', '')
        if not item_full_id:
            logger.warning(f"[HTMLParser] Agenda item {sequence} has no ID, skipping")
            continue

        # Extract numeric ID
        item_id = item_full_id.replace('AgendaItem_', '')

        # Get title from text content
        title = item_div.get_text(strip=True)

        # Find corresponding item_contents div
        contents_id = f"agenda_item_area_{item_id}"
        contents_div = soup.find('div', id=contents_id)

        # Extract attachments
        attachments = []
        if contents_div:
            attachments = _extract_attachments(contents_div, item_id)

        items.append({
            'item_id': item_id,
            'title': title,
            'sequence': sequence,
            'attachments': attachments,
        })

        logger.debug(
            f"[HTMLParser] Item {sequence}: '{title[:60]}...' "
            f"({len(attachments)} attachments)"
        )

    return items


def _extract_attachments(contents_div, item_id: str) -> List[Dict[str, Any]]:
    """Extract attachment links from item_contents div"""
    attachments = []

    # Find all links in the contents
    links = contents_div.find_all('a', href=True)

    for link in links:
        href = link['href']

        # Look for attachment API endpoint
        if 'historyattachment' in href.lower():
            # Extract historyId from URL
            history_id_match = re.search(r'historyId=([a-f0-9\-]+)', href, re.IGNORECASE)
            if history_id_match:
                history_id = history_id_match.group(1)

                # Get link text as attachment name
                name = link.get_text(strip=True)
                if not name:
                    name = f"Attachment {len(attachments) + 1}"

                attachments.append({
                    'name': name,
                    'history_id': history_id,
                    'url': href,  # Store relative URL
                    'type': 'pdf',  # PrimeGov attachments are PDFs
                })

    return attachments


def parse_granicus_html_agenda(html: str) -> Dict[str, Any]:
    """
    Parse Granicus AgendaViewer HTML to extract items and attachments.

    Granicus structure:
    - Items in <table> elements with item number, title, File ID
    - Attachments as MetaViewer.php links following each item
    - Items grouped by sections (Consent Calendar, Discussion Calendar, etc.)

    Args:
        html: HTML content from AgendaViewer.php page

    Returns:
        {
            'participation': {},  # Granicus doesn't have structured participation info in HTML
            'items': [
                {
                    'item_id': str,        # File ID (e.g., "2025-00111")
                    'title': str,          # Item title
                    'sequence': int,       # Item number (1, 2, 3...)
                    'attachments': [{'name': str, 'url': str, 'meta_id': str}]
                }
            ]
        }
    """
    soup = BeautifulSoup(html, 'html.parser')
    items = []

    # Find all tables (agenda items are in tables)
    tables = soup.find_all('table', {'style': lambda x: x and 'BORDER-COLLAPSE: collapse' in x})

    for table in tables:
        # Extract item number from first cell
        rows = table.find_all('tr')
        if len(rows) < 1:
            continue

        # First row has item number and title
        first_row = rows[0]
        cells = first_row.find_all('td')
        if len(cells) < 2:
            continue

        # Item number (e.g., "1.", "2.")
        number_cell = cells[0]
        number_text = number_cell.get_text(strip=True)

        # Skip if not a numbered item
        if not number_text or not number_text.replace('.', '').isdigit():
            continue

        sequence = int(number_text.replace('.', ''))

        # Title and File ID
        title_cell = cells[1]
        title_full = title_cell.get_text(strip=True)

        # Extract File ID from title (format: "Title File ID: 2025-00111")
        item_id = None
        if 'File ID:' in title_full:
            parts = title_full.split('File ID:')
            title = parts[0].strip()
            item_id = parts[1].strip() if len(parts) > 1 else None
        else:
            title = title_full
            # Fallback: use sequence as ID
            item_id = str(sequence)

        # Find attachment link for this item
        # It's usually in a blockquote following the table, with MetaViewer link
        attachments = []

        # Look for next blockquote sibling after this table's parent
        parent = table.find_parent('div')
        if parent:
            next_blockquote = parent.find_next_sibling('blockquote')
            if next_blockquote:
                # Find MetaViewer link
                meta_links = next_blockquote.find_all('a', href=lambda x: x and 'MetaViewer' in x)
                for link in meta_links:
                    href = link['href']
                    link_text = link.get_text(strip=True)

                    # Extract meta_id from URL (e.g., meta_id=845318)
                    import re
                    meta_id_match = re.search(r'meta_id=(\d+)', href)
                    meta_id = meta_id_match.group(1) if meta_id_match else None

                    attachments.append({
                        'name': link_text or f"Attachment {sequence}",
                        'url': href,
                        'meta_id': meta_id,
                        'type': 'pdf',  # MetaViewer links are PDFs - conductor needs this for extraction
                    })

        items.append({
            'item_id': item_id,
            'title': title,
            'sequence': sequence,
            'attachments': attachments,
        })

        logger.debug(
            f"[HTMLParser:Granicus] Item {sequence}: '{title[:60]}...' "
            f"({len(attachments)} attachments)"
        )

    logger.debug(
        f"[HTMLParser:Granicus] Extracted {len(items)} agenda items"
    )

    return {
        'participation': {},  # Granicus HTML doesn't have structured participation
        'items': items,
    }


def parse_legistar_legislation_attachments(html: str, base_url: str) -> List[Dict[str, Any]]:
    """
    Parse attachments from Legistar LegislationDetail.aspx page.

    Args:
        html: HTML content from LegislationDetail.aspx
        base_url: Base URL for building absolute URLs

    Returns:
        List of attachment dictionaries: [{'name': str, 'url': str, 'type': str}]
    """
    from urllib.parse import urljoin

    soup = BeautifulSoup(html, 'html.parser')
    attachments = []

    # Find the attachments table
    attachments_table = soup.find('table', id='ctl00_ContentPlaceHolder1_tblAttachments')

    if not attachments_table:
        logger.debug("[HTMLParser:Legistar] No attachments table found")
        return attachments

    # Find the span containing attachment links
    attachments_span = attachments_table.find('span', id='ctl00_ContentPlaceHolder1_lblAttachments2')

    if not attachments_span:
        logger.debug("[HTMLParser:Legistar] No attachments span found")
        return attachments

    # Find all links in the span
    links = attachments_span.find_all('a', href=True)

    for link in links:
        href = link.get('href', '')
        name = link.get_text(strip=True)

        if not href or not name:
            continue

        # Build absolute URL
        attachment_url = urljoin(base_url, href)

        # Determine file type from URL or name
        url_lower = attachment_url.lower()
        name_lower = name.lower()

        if '.pdf' in url_lower or 'pdf' in name_lower:
            file_type = 'pdf'
        elif '.doc' in url_lower or 'doc' in name_lower:
            file_type = 'doc'
        else:
            # Default to PDF for View.ashx links (most are PDFs)
            file_type = 'pdf'

        attachments.append({
            'name': name,
            'url': attachment_url,
            'type': file_type,
        })

    logger.debug(f"[HTMLParser:Legistar] Found {len(attachments)} attachments")

    return attachments


def parse_legistar_html_agenda(html: str, meeting_id: str, base_url: str) -> Dict[str, Any]:
    """
    Parse Legistar MeetingDetail HTML to extract items.

    Legistar structure:
    - Items in Telerik RadGrid (table.rgMasterTable)
    - Rows with class rgRow or rgAltRow
    - Columns: File #, Ver., Agenda #, Name, Type, Status, Title, Action, Result, Action Details, Video
    - File # links to LegislationDetail.aspx with ID parameter for potential attachment fetching

    Args:
        html: HTML content from MeetingDetail.aspx page
        meeting_id: Meeting ID for generating item IDs
        base_url: Base URL for building absolute URLs

    Returns:
        {
            'participation': {},  # Legistar HTML doesn't have structured participation in detail page
            'items': [
                {
                    'item_id': str,        # Legislation ID from File # link
                    'title': str,          # Full title from Title column
                    'sequence': int,       # Row number
                    'item_type': str,      # Type column (Ordinance, Resolution, etc.)
                    'status': str,         # Status column
                    'file_number': str,    # File # text
                    'attachments': []      # Empty for now, could fetch from LegislationDetail later
                }
            ]
        }
    """
    from urllib.parse import urljoin

    soup = BeautifulSoup(html, 'html.parser')
    items = []

    # Find the RadGrid master table
    master_table = soup.find('table', class_='rgMasterTable')

    if not master_table:
        logger.debug("[HTMLParser:Legistar] No rgMasterTable found in HTML")
        return {'participation': {}, 'items': []}

    # Find all agenda item rows (rgRow and rgAltRow)
    rows = master_table.find_all('tr', class_=['rgRow', 'rgAltRow'])

    if not rows:
        logger.debug("[HTMLParser:Legistar] No rgRow/rgAltRow rows found")
        return {'participation': {}, 'items': []}

    logger.debug(f"[HTMLParser:Legistar] Found {len(rows)} rows in RadGrid")

    for sequence, row in enumerate(rows, 1):
        try:
            cells = row.find_all('td')

            # Legistar RadGrid columns (0-indexed):
            # 0: File # (with link to LegislationDetail)
            # 1: Ver. (version)
            # 2: Agenda # (item number - often empty)
            # 3: Name (short name)
            # 4: Type (Ordinance, Resolution, Hearing, etc.)
            # 5: Status
            # 6: Title (full detailed title)
            # 7: Action
            # 8: Result
            # 9: Action Details
            # 10: Video

            if len(cells) < 7:
                logger.debug(f"[HTMLParser:Legistar] Row {sequence} has only {len(cells)} cells, skipping")
                continue

            # Extract File # and legislation ID
            file_cell = cells[0]
            file_link = file_cell.find('a', href=lambda x: x and 'LegislationDetail.aspx' in x)

            if not file_link:
                logger.debug(f"[HTMLParser:Legistar] Row {sequence} has no LegislationDetail link, skipping")
                continue

            file_number = file_link.get_text(strip=True)

            # Extract legislation ID from URL (ID=7494673)
            href = file_link.get('href', '')
            legislation_id_match = re.search(r'ID=(\d+)', href)
            legislation_id = legislation_id_match.group(1) if legislation_id_match else None

            if not legislation_id:
                logger.debug(f"[HTMLParser:Legistar] Row {sequence} has no ID in link, skipping")
                continue

            # Extract other fields
            version = cells[1].get_text(strip=True) if len(cells) > 1 else ''
            agenda_number = cells[2].get_text(strip=True) if len(cells) > 2 else ''
            name = cells[3].get_text(strip=True) if len(cells) > 3 else ''
            item_type = cells[4].get_text(strip=True) if len(cells) > 4 else ''
            status = cells[5].get_text(strip=True) if len(cells) > 5 else ''
            title = cells[6].get_text(strip=True) if len(cells) > 6 else ''

            # Use full title if available, otherwise fall back to name
            item_title = title if title else name

            if not item_title:
                logger.debug(f"[HTMLParser:Legistar] Row {sequence} has no title, skipping")
                continue

            # Build full legislation detail URL for potential future attachment fetching
            legislation_url = urljoin(base_url, href) if href else None

            item_data = {
                'item_id': legislation_id,
                'title': item_title,
                'sequence': sequence,
                'file_number': file_number,
                'item_type': item_type,
                'status': status,
                'attachments': [],  # Could fetch from LegislationDetail.aspx later
            }

            # Optional fields
            if version:
                item_data['version'] = version
            if agenda_number:
                item_data['agenda_number'] = agenda_number
            if legislation_url:
                item_data['legislation_url'] = legislation_url

            items.append(item_data)

            logger.debug(
                f"[HTMLParser:Legistar] Item {sequence}: File #{file_number} - '{item_title[:60]}...'"
            )

        except Exception as e:
            logger.warning(
                f"[HTMLParser:Legistar] Error parsing row {sequence}: {e}"
            )
            continue

    logger.info(
        f"[HTMLParser:Legistar] Extracted {len(items)} items from meeting {meeting_id}"
    )

    return {
        'participation': {},
        'items': items,
    }


# Confidence: 8/10
# Works with PrimeGov's current HTML structure.
# May need adjustments if they change class names or div IDs.
