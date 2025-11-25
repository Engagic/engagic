"""
Legistar HTML Parser - Extract attachments and agenda items from Legistar HTML pages

Two main functions:
1. parse_legislation_attachments() - Extract attachments from LegislationDetail.aspx
2. parse_html_agenda() - Extract agenda items from MeetingDetail.aspx (HTML fallback)
"""

import re
from typing import Dict, Any, List
from bs4 import BeautifulSoup

from config import get_logger

logger = get_logger(__name__).bind(component="vendor")



def parse_legislation_attachments(html: str, base_url: str) -> List[Dict[str, Any]]:
    """
    Parse attachments from Legistar LegislationDetail.aspx page.

    Uses multiple fallback strategies for resilience:
    1. Primary: Exact ASP.NET control IDs (current Legistar implementation)
    2. Fallback: Structural patterns (class-based, text-based)
    3. Last resort: Any PDF/doc links on the page

    Args:
        html: HTML content from LegislationDetail.aspx
        base_url: Base URL for building absolute URLs

    Returns:
        List of attachment dictionaries: [{'name': str, 'url': str, 'type': str}]
    """
    from urllib.parse import urljoin

    soup = BeautifulSoup(html, 'html.parser')
    attachments = []
    links = None

    # Strategy 1: Primary - exact ASP.NET control IDs
    attachments_table = soup.find('table', id='ctl00_ContentPlaceHolder1_tblAttachments')
    if attachments_table:
        attachments_span = attachments_table.find('span', id='ctl00_ContentPlaceHolder1_lblAttachments2')
        if attachments_span:
            links = attachments_span.find_all('a', href=True)
            logger.debug("found attachments via primary selector", parser="legistar")

    # Strategy 2: Fallback - look for "Attachments" label and nearby View.ashx links
    if not links:
        attachments_label = soup.find(string=re.compile(r'Attachments?', re.IGNORECASE))
        if attachments_label:
            parent = attachments_label.find_parent(['td', 'div', 'span', 'tr'])
            if parent:
                container = parent.find_parent(['table', 'div'])
                if container:
                    # Only match Legistar View.ashx pattern, not arbitrary PDFs
                    links = container.find_all('a', href=re.compile(r'View\.ashx\?', re.IGNORECASE))
                    if links:
                        logger.warning("using fallback selector for attachments", parser="legistar")

    if not links:
        logger.debug("no attachments found", parser="legistar")
        return attachments

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

    logger.debug("found attachments", parser="legistar", attachment_count=len(attachments))

    return attachments


def parse_novusagenda_html_agenda(html: str) -> Dict[str, Any]:
    """
    Parse NovusAgenda MeetingView HTML to extract items and attachments.

    NovusAgenda structure:
    - Items in table grid (can vary by implementation)
    - Each item may have link to CoverSheet.aspx with ItemID
    - Attachments may be embedded or linked

    Args:
        html: HTML content from MeetingView.aspx or similar agenda page

    Returns:
        {
            'participation': {},  # NovusAgenda doesn't have structured participation
            'items': [
                {
                    'item_id': str,
                    'title': str,
                    'sequence': int,
                    'attachments': [{'name': str, 'url': str, 'type': str}]
                }
            ]
        }
    """
    soup = BeautifulSoup(html, 'html.parser')
    items = []

    # Try to find items grid (pattern varies, log what we find)
    # Look for common patterns: tables, divs with item classes, etc.

    # Log page structure for debugging
    logger.debug("parsing NovusAgenda HTML", parser="novusagenda", html_length=len(html))

    # Pattern 1: Look for links to CoverSheet.aspx (item detail pages)
    # Note: NovusAgenda uses "CoverSheet" with both C and S capitalized
    coversheet_links = soup.find_all('a', href=re.compile(r'CoverSheet\.aspx\?ItemID=', re.IGNORECASE))

    if coversheet_links:
        logger.info("found coversheet links", parser="novusagenda", link_count=len(coversheet_links))

        for sequence, link in enumerate(coversheet_links, 1):
            # Extract ItemID from href
            href = link.get('href', '')
            item_id_match = re.search(r'ItemID=(\d+)', href)
            if not item_id_match:
                continue

            item_id = item_id_match.group(1)

            # Get title from link text or parent context
            title = link.get_text(strip=True)
            if not title:
                # Try parent td or container
                parent_td = link.find_parent('td')
                if parent_td:
                    title = parent_td.get_text(strip=True)

            items.append({
                'item_id': item_id,
                'title': title,
                'sequence': sequence,
                'attachments': [],  # Will be populated if we fetch Coversheet page
            })

    # Pattern 2: Look for agenda item tables or divs
    # Try finding tables with agenda item data
    agenda_tables = soup.find_all('table', class_=re.compile(r'agenda', re.I))
    if agenda_tables:
        logger.info("found agenda tables", parser="novusagenda", table_count=len(agenda_tables))

    # Pattern 3: Look for PDF links that might be attachments
    pdf_links = soup.find_all('a', href=re.compile(r'\.pdf$|DisplayAgendaPDF', re.I))
    if pdf_links:
        logger.info("found PDF links", parser="novusagenda", pdf_count=len(pdf_links))

    # Pattern 4: Look for "Online Agenda" / "HTML Agenda" / "View Agenda" links
    agenda_view_links = soup.find_all('a', text=re.compile(r'(online|html|view).*agenda', re.I))
    if agenda_view_links:
        logger.info("found agenda view links", parser="novusagenda", link_count=len(agenda_view_links))
        for link in agenda_view_links:
            logger.debug("agenda view link", parser="novusagenda", link_action=link.get('onClick', link.get('href', 'no href')))

    # Pattern 5: Look for image-based agenda links (common pattern)
    img_links = soup.find_all('img', alt=re.compile(r'agenda|item', re.I))
    if img_links:
        logger.info("found agenda/item images", parser="novusagenda", image_count=len(img_links))
        for img in img_links[:5]:  # Log first 5
            logger.debug("image alt text", parser="novusagenda", alt_text=img.get('alt'))

    logger.info(
        f"[HTMLParser:NovusAgenda] Extracted {len(items)} items from HTML"
    )

    return {
        'participation': {},
        'items': items,
    }


def parse_html_agenda(html: str, meeting_id: str, base_url: str) -> Dict[str, Any]:
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

    # Build column map from header row (different Legistar sites have different columns)
    # Header row may have class='rgHeader' or no class (just first tr with th elements)
    header_row = master_table.find('tr', class_='rgHeader')
    if not header_row:
        # Try finding first tr with th elements
        header_row = master_table.find('tr')
        if header_row and not header_row.find_all('th'):
            header_row = None

    column_map = {}
    if header_row:
        headers = header_row.find_all('th')
        for i, th in enumerate(headers):
            # Normalize header text (remove nbsp, lowercase)
            header_text = th.get_text(strip=True).replace('\xa0', ' ').lower()
            column_map[header_text] = i
        logger.debug("column map created", parser="legistar", column_map=column_map)
    else:
        # Fallback: assume standard layout if no header found
        logger.warning("[HTMLParser:Legistar] No header row found, using default column positions")
        column_map = {
            'file #': 0, 'ver.': 1, 'agenda #': 2, 'name': 3,
            'type': 4, 'status': 5, 'title': 6, 'action': 7,
            'result': 8, 'action details': 9, 'video': 10
        }

    # Find all agenda item rows (rgRow and rgAltRow)
    rows = master_table.find_all('tr', class_=['rgRow', 'rgAltRow'])

    if not rows:
        logger.debug("[HTMLParser:Legistar] No rgRow/rgAltRow rows found")
        return {'participation': {}, 'items': []}

    logger.debug("found RadGrid rows", parser="legistar", row_count=len(rows))

    for sequence, row in enumerate(rows, 1):
        try:
            cells = row.find_all('td')

            if len(cells) < 5:
                logger.debug("row has too few cells, skipping", parser="legistar", row=sequence, cell_count=len(cells))
                continue

            # Extract File # and legislation ID (always column 0)
            file_cell = cells[0]
            file_link = file_cell.find('a', href=lambda x: x and 'LegislationDetail.aspx' in x)

            if not file_link:
                logger.debug("row has no LegislationDetail link, skipping", parser="legistar", row=sequence)
                continue

            file_number = file_link.get_text(strip=True)

            # Extract legislation ID from URL (ID=7494673)
            href = file_link.get('href', '')
            legislation_id_match = re.search(r'ID=(\d+)', href)
            legislation_id = legislation_id_match.group(1) if legislation_id_match else None

            if not legislation_id:
                logger.debug("row has no ID in link, skipping", parser="legistar", row=sequence)
                continue

            # Extract fields using column map
            def get_cell_text(col_name: str) -> str:
                idx = column_map.get(col_name.lower())
                if idx is not None and idx < len(cells):
                    return cells[idx].get_text(strip=True)
                return ''

            version = get_cell_text('ver.')
            agenda_number = get_cell_text('agenda #')
            name = get_cell_text('name')
            item_type = get_cell_text('type')
            status = get_cell_text('status')  # May not exist in all layouts (e.g., Philadelphia)
            title = get_cell_text('title')

            # Use full title if available, otherwise fall back to name
            item_title = title if title else name

            if not item_title:
                logger.debug("row has no title, skipping", parser="legistar", row=sequence)
                continue

            # Build full legislation detail URL for potential future attachment fetching
            legislation_url = urljoin(base_url, href) if href else None

            item_data = {
                'item_id': legislation_id,
                'title': item_title,
                'sequence': sequence,
                'file_number': file_number,
                'matter_file': file_number,  # For matter tracking (e.g., "251041", "BL2025-1234")
                'matter_id': legislation_id,  # Legislation ID as matter_id
                'item_type': item_type,
                'attachments': [],  # Could fetch from LegislationDetail.aspx later
            }

            # Optional fields
            if version:
                item_data['version'] = version
            if agenda_number:
                item_data['agenda_number'] = agenda_number
            if status:
                item_data['status'] = status
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
