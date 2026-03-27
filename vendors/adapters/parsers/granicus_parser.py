"""
Granicus HTML Parser - Extract agenda items from Granicus pages

Supports multiple HTML formats:
1. ViewPublisher.php - Meeting listing page (parse_viewpublisher_listing)
2. AgendaOnline/ViewAgenda - HTML agenda with items (parse_agendaonline_html)
3. AgendaViewer.php - Original Granicus format (parse_agendaviewer_html)
4. S3-hosted grid HTML - Native Granicus format (parse_granicus_s3_html)
   Used by sites like Bozeman where AgendaViewer redirects to S3/CloudFront HTML
5. Questys HTML - Word-exported agenda from Questys DMS (parse_questys_html)
   Used by Anaheim and others that redirect to external Questys servers
"""

import re
from datetime import datetime
from typing import Dict, Any, List, Optional
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from config import get_logger
from vendors.utils.attachments import classify_attachment_type
from parsing.participation import parse_participation_info

logger = get_logger(__name__).bind(component="vendor")


def parse_viewpublisher_listing(html: str, base_url: str) -> List[Dict[str, Any]]:
    """Parse ViewPublisher.php listing to extract meetings with event_id, title, start, agenda_viewer_url."""
    soup = BeautifulSoup(html, 'html.parser')
    meetings = []
    # Some Granicus sites use 'odd'/'even', others use 'listingRow'
    rows = soup.find_all('tr', class_=['odd', 'even', 'listingRow'])

    for row in rows:
        cells = row.find_all('td', class_='listItem')
        if len(cells) < 2:
            continue

        title = cells[0].get_text(strip=True)
        date_cell = cells[1]

        # Parse human-readable date text (in meeting's local timezone)
        # Avoid hidden Unix timestamps - they require timezone conversion
        date_text = date_cell.get_text(strip=True)
        start = _parse_granicus_date(date_text)

        # Some Granicus sites (e.g. Oakley) have swapped columns:
        # date in title cell, "Agenda" in date cell. Detect and correct.
        if not start:
            swapped = _parse_granicus_date(title)
            if swapped:
                start = swapped
                title = date_text if date_text.lower() != "agenda" else ""

        agenda_link = row.find('a', href=lambda x: x and 'AgendaViewer' in x if x else False)
        if not agenda_link:
            continue

        href = agenda_link['href']
        if href.startswith('//'):
            href = 'https:' + href
        elif not href.startswith('http'):
            href = urljoin(base_url, href)

        # Granicus uses event_id or clip_id depending on the site
        id_match = re.search(r'(?:event_id|clip_id)=(\d+)', href)
        event_id = id_match.group(1) if id_match else None

        if not event_id:
            continue

        meetings.append({
            'event_id': event_id,
            'title': title,
            'start': start,
            'agenda_viewer_url': href,
        })

    logger.debug(
        "parsed viewpublisher listing",
        vendor="granicus",
        meeting_count=len(meetings)
    )

    return meetings


def _parse_granicus_date(date_text: str) -> Optional[str]:
    """Parse Granicus date formats like 'December 22, 2025 - 06:00 PM'.

    Handles hidden Unix timestamp prefix (e.g., '1768204800Jan 12, 2026')
    and falls back to Unix timestamp if plain text parsing fails.
    """
    date_text = date_text.replace('\xa0', ' ').strip()

    # Extract Unix timestamp prefix if present (hidden span gets concatenated).
    # Timestamps are exactly 10 digits (2001-2286). Greedy \d{10,} would
    # swallow the leading digits of the date string (e.g., "177489360003/30/26"
    # -> captures 12 digits instead of 10, yielding year 7594).
    unix_timestamp = None
    if date_text and date_text[0].isdigit():
        match = re.match(r'^(\d{10})', date_text)
        if match:
            unix_timestamp = int(match.group(1))
            date_text = date_text[10:].strip()

    # Collapse internal whitespace (date and time may be split across lines)
    date_text = " ".join(date_text.split())

    formats = [
        "%B %d, %Y - %I:%M %p",  # December 22, 2025 - 06:00 PM
        "%B %d, %Y %I:%M %p",    # December 22, 2025 06:00 PM
        "%B %d, %Y",             # December 22, 2025
        "%b %d, %Y - %I:%M %p",  # Dec 22, 2025 - 06:00 PM
        "%b %d, %Y %I:%M %p",    # Dec 22, 2025 06:00 PM
        "%b %d, %Y",             # Dec 22, 2025
        "%m/%d/%Y - %I:%M %p",   # 12/22/2025 - 06:00 PM
        "%m/%d/%Y %I:%M %p",     # 12/22/2025 06:00 PM
        "%m/%d/%Y",              # 12/22/2025
        "%m/%d/%y - %I:%M %p",   # 03/30/26 - 11:00 AM (2-digit year)
        "%m/%d/%y %I:%M %p",     # 03/30/26 11:00 AM
        "%m/%d/%y",              # 03/30/26
    ]

    for fmt in formats:
        try:
            dt = datetime.strptime(date_text, fmt)
            return dt.isoformat()
        except ValueError:
            continue

    # Fallback: use Unix timestamp if plain text parsing failed
    if unix_timestamp:
        try:
            dt = datetime.fromtimestamp(unix_timestamp)
            return dt.isoformat()
        except (ValueError, OSError):
            pass

    return None


def parse_agendaonline_html(html: str, base_url: str) -> Dict[str, Any]:
    """Parse AgendaOnline HTML for items and participation. Returns {participation: {...}, items: [...]}."""
    soup = BeautifulSoup(html, 'html.parser')
    items = []
    seen_ids = set()

    # Extract participation info (contact details, zoom links, etc.)
    page_text = soup.get_text(separator=' ', strip=True)
    participation_info = parse_participation_info(page_text)
    participation = participation_info.model_dump() if participation_info else {}

    # Extract council members from header
    members = _extract_council_members(soup)
    if members:
        participation['members'] = members

    # Parse accessible view format (ViewMeetingAgenda)
    sequence_counter = 0
    for item_div in soup.find_all('div', class_='accessible-item'):
        link = item_div.find('a', onclick=lambda x: x and 'loadAgendaItem' in x if x else False)
        if not link:
            continue
        if not (id_match := re.search(r'loadAgendaItem\((\d+)\)', link.get('onclick', ''))):
            continue
        item_id = id_match.group(1)
        if item_id in seen_ids:
            continue
        seen_ids.add(item_id)

        link_text = link.get_text(strip=True)
        title_span = link.find('span', class_='accessible-item-text')
        if title_span:
            title = title_span.get_text(strip=True)
            agenda_number = link_text.replace(title, '').strip()
        elif num_match := re.match(r'^(\d+\.?[A-Z]?\.?)\s+(.+)$', link_text):
            agenda_number, title = num_match.group(1), num_match.group(2)
        else:
            agenda_number, title = '', link_text

        if not title:
            continue

        sequence_counter += 1
        items.append({
            'vendor_item_id': item_id,
            'title': title,
            'sequence': sequence_counter,
            'agenda_number': agenda_number,
            'attachments': [],
        })

    if items:
        logger.debug("parsed agendaonline accessible html", vendor="granicus", item_count=len(items), members=len(participation.get('members', [])))
        return {'participation': participation, 'items': items}

    # Strategy 2: Fallback to table-based parsing (older format)
    all_tables = soup.find_all('table', style=lambda x: x and 'border-collapse' in x.lower() if x else False)
    sequence_counter = 0

    for table in all_tables:
        rows = table.find_all('tr')
        for row in rows:
            cells = row.find_all('td')
            if len(cells) < 2:
                continue

            number_cell = cells[0]
            number_span = number_cell.find('span', style=lambda x: x and 'font-weight:bold' in x.lower() if x else False)

            if not number_span:
                bold = number_cell.find('b') or number_cell.find('strong')
                if bold:
                    agenda_number = bold.get_text(strip=True)
                else:
                    continue
            else:
                agenda_number = number_span.get_text(strip=True)

            if not agenda_number or not re.match(r'^\d+\.?[A-Z]?\.?$', agenda_number):
                continue

            sequence_counter += 1
            content_cell = cells[1]
            item_id = None

            anchor = content_cell.find('a', attrs={'name': True})
            if anchor:
                name = anchor.get('name', '')
                if name.startswith(('S', 'I')):
                    item_id = name[1:]
                elif name:
                    item_id = name

            if not item_id:
                load_link = content_cell.find('a', href=lambda x: x and 'loadAgendaItem' in x if x else False)
                if load_link:
                    match = re.search(r'loadAgendaItem\((\d+)', load_link.get('href', ''))
                    if match:
                        item_id = match.group(1)

            title_link = content_cell.find('a', href=True)
            if title_link:
                title = title_link.get_text(strip=True)
            else:
                title = content_cell.get_text(strip=True)

            if not title or not item_id:
                continue
            if item_id in seen_ids:
                continue
            seen_ids.add(item_id)

            recommendation = None
            rec_match = content_cell.find(string=re.compile(r'Recommendation:', re.I))
            if rec_match:
                rec_parent = rec_match.find_parent('p') or rec_match.find_parent('td')
                if rec_parent:
                    rec_text = rec_parent.get_text(strip=True)
                    if 'Recommendation:' in rec_text:
                        recommendation = rec_text.split('Recommendation:', 1)[1].strip()

            item_dict = {
                'vendor_item_id': item_id,
                'title': title,
                'sequence': sequence_counter,
                'agenda_number': agenda_number,
                'attachments': [],
            }

            if recommendation:
                item_dict['recommendation'] = recommendation

            items.append(item_dict)

    # Strategy 3: Fallback to extracting all loadAgendaItem links (Durham-style)
    if not items:
        seen_ids = set()
        sequence_counter = 0
        for link in soup.find_all('a', href=lambda x: x and 'loadAgendaItem' in x if x else False):
            href = link.get('href', '')
            match = re.search(r'loadAgendaItem\((\d+)', href)
            if not match:
                continue

            item_id = match.group(1)
            if item_id in seen_ids:
                continue
            seen_ids.add(item_id)

            title = link.get_text(strip=True)
            if not title:
                continue

            # Skip section headers (usually short generic titles)
            if title.lower() in ('call to order', 'roll call', 'adjournment'):
                continue

            sequence_counter += 1
            items.append({
                'vendor_item_id': item_id,
                'title': title,
                'sequence': sequence_counter,
                'attachments': [],
            })

        if items:
            logger.debug("parsed agendaonline via loadAgendaItem links", vendor="granicus", item_count=len(items))

    logger.debug(
        "parsed agendaonline html",
        vendor="granicus",
        item_count=len(items),
        members=len(participation.get('members', []))
    )

    return {
        'participation': participation,
        'items': items,
    }


def _extract_council_members(soup: BeautifulSoup) -> List[str]:
    """Extract council member names from header spans (typically blue-styled text)."""
    members = []
    seen = set()

    # Look for spans with blue color styling (common in Granicus agendas)
    blue_spans = soup.find_all('span', style=lambda x: x and '#0070c2' in x.lower() if x else False)

    current_name = []
    for span in blue_spans:
        text = span.get_text(strip=True)
        if not text or text == ',':
            continue

        # Role indicators suggest end of a name
        role_keywords = ['mayor', 'vice mayor', 'council member', 'councilmember', 'president', 'vice president']
        text_lower = text.lower()

        is_role = any(kw in text_lower for kw in role_keywords)

        if is_role:
            # Append role to current name if we have one
            if current_name:
                full_name = ' '.join(current_name)
                if text_lower not in full_name.lower():
                    full_name = f"{full_name}, {text}"
                if full_name not in seen:
                    members.append(full_name)
                    seen.add(full_name)
                current_name = []
        else:
            # Accumulate name parts
            current_name.append(text)

    # Flush remaining name
    if current_name:
        full_name = ' '.join(current_name)
        if full_name not in seen:
            members.append(full_name)

    return members



def parse_agendaviewer_html(html: str) -> Dict[str, Any]:
    """Parse original Granicus AgendaViewer HTML for items with File IDs and MetaViewer attachments."""
    soup = BeautifulSoup(html, 'html.parser')
    items = []
    tables = soup.find_all('table', {'style': lambda x: x and 'BORDER-COLLAPSE: collapse' in x})
    sequence_counter = 0

    for table in tables:
        rows = table.find_all('tr')
        if not rows:
            continue

        first_row = rows[0]
        cells = first_row.find_all('td')
        if len(cells) < 2:
            continue

        number_text = cells[0].get_text(strip=True)
        if not number_text or not number_text.replace('.', '').isdigit():
            continue

        sequence_counter += 1
        title_full = cells[1].get_text(strip=True)

        if 'File ID:' in title_full:
            parts = title_full.split('File ID:')
            title = parts[0].strip()
            item_id = parts[1].strip() if len(parts) > 1 else None
        else:
            title = title_full
            item_id = str(sequence_counter)

        attachments = []
        parent = table.find_parent('div')
        if parent:
            next_blockquote = parent.find_next_sibling('blockquote')
            if next_blockquote:
                meta_links = next_blockquote.find_all('a', href=lambda x: x and 'MetaViewer' in x)
                for link in meta_links:
                    href = link['href']
                    link_text = link.get_text(strip=True)
                    meta_id_match = re.search(r'meta_id=(\d+)', href)
                    meta_id = meta_id_match.group(1) if meta_id_match else None

                    attachments.append({
                        'name': link_text or f"Attachment {sequence_counter}",
                        'url': href,
                        'meta_id': meta_id,
                        'type': 'pdf',
                    })

        item_dict = {
            'vendor_item_id': item_id,
            'title': title,
            'sequence': sequence_counter,
            'attachments': attachments,
        }

        if item_id and re.match(r'^\d{4}-\d+$', item_id):
            item_dict['matter_file'] = item_id

        items.append(item_dict)

    logger.debug("parsed agendaviewer html", vendor="granicus", item_count=len(items))

    return {'participation': {}, 'items': items}


def parse_granicus_s3_html(html: str) -> Dict[str, Any]:
    """Parse S3-hosted Granicus HTML agenda (grid layout with h2 sections and h3 items).

    This format is used by "native" Granicus sites (e.g. Bozeman) where AgendaViewer.php
    redirects to an S3/CloudFront-hosted HTML page with a CSS grid layout.

    Structure:
    - <h2> with letter prefix (A., B., G.) = section headers
    - <h3> with letter.number prefix (D.1, G.1) = agenda items, with PDF attachment links
    - Staff name in parens after the link: <a href="...pdf">Title</a>(StaffName)
    - Description/motion text in sibling <div> elements
    """
    soup = BeautifulSoup(html, 'html.parser')

    # Verify this is the right format: grid container with h2/h3 elements
    container = soup.find('div', class_='container')
    if not container:
        logger.debug("no grid container found, not S3 format", vendor="granicus")
        return {'participation': {}, 'items': []}

    # Extract participation info from page text
    page_text = soup.get_text(separator=' ', strip=True)
    participation_info = parse_participation_info(page_text)
    participation = participation_info.model_dump() if participation_info else {}

    items = []
    current_section = None
    sequence_counter = 0

    # Walk all grid-row divs (direct children of container with grid-column styles)
    for grid_cell in container.find_all('div', style=lambda x: x and 'grid-column-start' in x if x else False, recursive=False):
        inner = grid_cell.find('div', recursive=False)
        if not inner:
            continue

        h2 = inner.find('h2', recursive=False)
        h3 = inner.find('h3', recursive=False)

        if h2:
            # Section header: extract letter prefix
            spans = h2.find_all('span', style=lambda x: x and 'float' in x if x else False)
            if spans:
                letter_span = spans[0]
                letter_text = letter_span.get_text(strip=True).rstrip('.\xa0 ')
                title_span = spans[1] if len(spans) > 1 else None
                section_title = title_span.get_text(strip=True) if title_span else h2.get_text(strip=True)
                current_section = letter_text
            else:
                section_title = h2.get_text(strip=True)

        elif h3:
            # Agenda item: extract letter.number prefix, title, staff, attachment
            spans = h3.find_all('span', style=lambda x: x and 'float' in x if x else False)
            if not spans:
                continue

            # First span: agenda number (e.g. "D.1", "G.15")
            number_span = spans[0]
            agenda_number = number_span.get_text(strip=True).rstrip('\xa0 ')

            # Second span: title link + staff name
            content_span = spans[1] if len(spans) > 1 else None

            # Ames variant: single float span in h3 (number only),
            # title/link lives in a sibling div with float:left
            if not content_span:
                content_div = None
                for sibling in inner.find_all('div', recursive=False):
                    if sibling.find('h3') or sibling.find('h2'):
                        continue
                    style = sibling.get('style', '')
                    if 'float' in style and sibling.find('a', href=True):
                        content_div = sibling
                        break
                if not content_div:
                    continue
                content_span = content_div

            link = content_span.find('a', href=True)
            if link:
                title = link.get_text(strip=True)
                attachment_url = link.get('href', '')

                # Staff name comes after the link as bare text: <a>Title</a>(StaffName)
                # Get all text in the span, remove the link text, extract parens
                full_text = content_span.get_text(strip=True)
                after_title = full_text[len(title):].strip() if len(full_text) > len(title) else ''
                staff_match = re.match(r'^\(([^)]+)\)', after_title)
                staff_name = staff_match.group(1).strip() if staff_match else None
            else:
                # No link in the span — title is inline text (Carson City style)
                title = content_span.get_text(separator=' ', strip=True)
                attachment_url = None
                staff_name = None

            if not title:
                continue

            sequence_counter += 1

            # Collect description text and additional attachment links from sibling divs
            description_parts = []
            extra_attachments = []
            for sibling_div in inner.find_all('div', recursive=False):
                # Skip the h3-containing div and clear divs
                if sibling_div.find('h3') or sibling_div.find('h2'):
                    continue
                # Check for attachment links in sibling divs (Carson City style: "Click Here for Staff Report")
                for sibling_link in sibling_div.find_all('a', href=True):
                    href = sibling_link.get('href', '')
                    if href and ('cloudfront.net' in href or 's3.amazonaws.com' in href or '.pdf' in href.lower()):
                        link_text = sibling_link.get_text(strip=True)
                        extra_attachments.append({
                            'name': link_text or 'Staff Report',
                            'url': href,
                            'type': classify_attachment_type(href),
                        })
                text = sibling_div.get_text(strip=True)
                if text and text != '\xa0' and len(text) > 5:
                    description_parts.append(text)
            description = '\n'.join(description_parts) if description_parts else None

            item_dict = {
                'vendor_item_id': agenda_number,
                'title': title,
                'sequence': sequence_counter,
                'agenda_number': agenda_number,
                'attachments': [],
            }

            if attachment_url:
                att_type = classify_attachment_type(attachment_url)
                if att_type == 'unknown':
                    url_lower = attachment_url.lower()
                    if '.html' in url_lower or '.htm' in url_lower:
                        att_type = 'html'
                item_dict['attachments'].append({
                    'name': title,
                    'url': attachment_url,
                    'type': att_type,
                })

            # Add attachments found in sibling divs
            item_dict['attachments'].extend(extra_attachments)

            # Extract matter file from bold prefix (Carson City style: "LU-2026-0023 For Possible Action...")
            matter_match = re.match(r'^([A-Z]{1,4}-\d{4}-\d{3,6})\s+', title)
            if matter_match:
                item_dict['matter_file'] = matter_match.group(1)

            if staff_name:
                item_dict['staff'] = staff_name
            if description:
                item_dict['description'] = description
            if current_section:
                item_dict['section'] = current_section

            items.append(item_dict)

    # Fallback: flat-div variant (Yakima style) — no h2/h3, items are plain
    # grid-column divs with text like "A.Title" and embedded CloudFront links
    if not items:
        sequence_counter = 0
        current_section = None
        procedural = {'roll call', 'pledge of allegiance', 'adjournment', 'adjourn',
                      'interpreter services', 'council reports'}

        for grid_cell in container.find_all('div', style=lambda x: x and 'grid-column-start' in x if x else False, recursive=False):
            text = grid_cell.get_text(strip=True)
            if not text:
                continue

            # Detect numbered section headers: "1.Roll Call", "7.Consent Agenda..."
            num_match = re.match(r'^(\d+)\.\s*(.+)', text)
            # Detect lettered items: "A.Approval of minutes..."
            letter_match = re.match(r'^([A-Z])\.\s*(.+)', text)

            if num_match:
                section_title = num_match.group(2).split('\n')[0].strip()
                # Check if procedural
                if section_title.lower().rstrip(':') in procedural:
                    continue
                current_section = section_title
                # Numbered items with links are substantive too
                link = grid_cell.find('a', href=True)
                if link:
                    href = link.get('href', '')
                    sequence_counter += 1
                    items.append({
                        'vendor_item_id': num_match.group(1),
                        'title': section_title,
                        'sequence': sequence_counter,
                        'agenda_number': num_match.group(1),
                        'attachments': [{
                            'name': section_title[:60],
                            'url': href,
                            'type': classify_attachment_type(href),
                        }] if href else [],
                    })
            elif letter_match:
                title = letter_match.group(2).split('\n')[0].strip()
                link = grid_cell.find('a', href=True)
                href = link.get('href', '') if link else ''

                sequence_counter += 1
                item_dict = {
                    'vendor_item_id': letter_match.group(1),
                    'title': title,
                    'sequence': sequence_counter,
                    'agenda_number': letter_match.group(1),
                    'attachments': [{
                        'name': title[:60],
                        'url': href,
                        'type': classify_attachment_type(href),
                    }] if href else [],
                }
                if current_section:
                    item_dict['metadata'] = {'section': current_section}
                items.append(item_dict)

        if items:
            logger.debug("parsed granicus s3 flat-div html", vendor="granicus", item_count=len(items))

    logger.debug(
        "parsed granicus s3 html",
        vendor="granicus",
        item_count=len(items),
        sections_found=bool(current_section),
    )

    return {
        'participation': participation,
        'items': items,
    }


def parse_generated_agendaviewer_html(html: str) -> Dict[str, Any]:
    """Parse GeneratedAgendaViewer.php HTML — table-based layout with MetaViewer attachments.

    Structure: each item is a <table> with <td width=40> (number) + <td> (title).
    MetaViewer attachment links follow in sibling <blockquote> elements.
    Section headers (PUBLIC HEARINGS, CONSENT CALENDAR, BUSINESS) have sub-items (a, b, c)
    nested inside their blockquote.

    Supports three body-level layouts:
    - Div-wrapped: item tables inside <div> elements (original format)
    - Bare tables: item <table> elements directly at body level (e.g. Vacaville)
    - Section-div: <div> with <strong> section header, items in sibling <blockquote> (e.g. Irvine)
    """
    soup = BeautifulSoup(html, 'html.parser')
    items = []
    sequence_counter = 0

    # Procedural items to skip
    procedural = {
        'call meeting to order', 'call to order', 'call roll', 'roll call',
        'pledge of allegiance', 'adjourn', 'adjournment', 'other business',
    }

    def _extract_attachments(blockquote) -> List[Dict[str, Any]]:
        """Extract MetaViewer attachment links from a blockquote element."""
        attachments = []
        if not blockquote:
            return attachments
        for link in blockquote.find_all('a', href=lambda x: x and 'MetaViewer' in x if x else False):
            href = link['href']
            name = link.get_text(strip=True) or 'Supporting Document'
            meta_id_match = re.search(r'meta_id=(\d+)', href)
            attachments.append({
                'name': name,
                'url': href,
                'type': 'pdf',
                'meta_id': meta_id_match.group(1) if meta_id_match else None,
            })
        return attachments

    def _process_item_table(table, parent_section: str = "") -> Optional[Dict[str, Any]]:
        """Extract item number and title from a table with <td width=40>."""
        row = table.find('tr')
        if not row:
            return None
        cells = row.find_all('td')
        if len(cells) < 2:
            return None

        number_text = cells[0].get_text(strip=True).rstrip('.')
        if not number_text or len(number_text) > 5:
            return None

        # Get full content text (may span multiple rows for ACTION lines)
        content_parts = []
        for r in table.find_all('tr'):
            tds = r.find_all('td')
            if len(tds) >= 2:
                content_parts.append(tds[1].get_text(strip=True))
            elif len(tds) == 1 and tds[0].get('colspan'):
                # ACTION row
                action_text = tds[0].get_text(strip=True)
                if action_text and action_text != 'ACTION:':
                    content_parts.append(action_text)

        title_full = content_parts[0] if content_parts else ""

        # Strip [CA] prefix
        title_clean = re.sub(r'^\[CA\]\s*', '', title_full).strip()

        # Split title from ACTION text
        if 'ACTION:' in title_clean:
            title_clean = title_clean.split('ACTION:')[0].strip()

        return {
            'number': number_text,
            'title': title_clean,
            'section': parent_section,
        }

    # Walk body-level elements: <div> or bare <table>, followed by <blockquote> (attachments)
    # Two layouts exist:
    # - Div-wrapped: each item <table> inside a <div> at body level
    # - Bare: item <table> elements directly at body level (e.g. Vacaville)
    body = soup.find('body') or soup
    current_section = ""

    for elem in body.children:
        if not hasattr(elem, 'name') or not elem.name:
            continue

        # Get the item table - either the element itself or nested in a div
        table = None
        if elem.name == 'table':
            table = elem
        elif elem.name == 'div':
            table = elem.find('table', recursive=False)

        if not table:
            # Section-div layout: <div> has no table, just a <strong> section
            # header. Items live in the sibling <blockquote> that follows.
            if elem.name == 'div':
                strong = elem.find('strong')
                if strong:
                    header_text = strong.get_text(strip=True)
                    if header_text and header_text.rstrip('.').lower() not in procedural:
                        current_section = re.sub(r'\s*\(.*\)\s*$', '', header_text).strip()
                        current_section = re.sub(r'[\s.:,\-\u2013\u2014]+$', '', current_section).strip()
                        next_bq = elem.find_next_sibling('blockquote')
                        if next_bq:
                            for sub_table in next_bq.find_all('table', recursive=True):
                                sub_data = _process_item_table(sub_table, parent_section=current_section)
                                if not sub_data or not sub_data['title']:
                                    continue
                                att_bq = sub_table.find_next_sibling('blockquote')
                                if not att_bq:
                                    parent_div = sub_table.find_parent('div')
                                    if parent_div:
                                        att_bq = parent_div.find_next_sibling('blockquote')
                                sub_attachments = _extract_attachments(att_bq)
                                sequence_counter += 1
                                items.append({
                                    'vendor_item_id': sub_data['number'],
                                    'title': sub_data['title'],
                                    'sequence': sequence_counter,
                                    'agenda_number': sub_data['number'],
                                    'attachments': sub_attachments,
                                    'metadata': {'section': current_section} if current_section else {},
                                })
            continue

        item_data = _process_item_table(table)
        if not item_data:
            continue

        number = item_data['number']
        title = item_data['title']

        # Section headers: end with colon/dash, are empty, or are known section names
        # Strip trailing punctuation and dashes (en dash, em dash, hyphen) for keyword match
        title_stripped = re.sub(r'\s*\(.*\)\s*$', '', title).strip()
        title_stripped = re.sub(r'[\s.:,\-\u2013\u2014]+$', '', title_stripped).strip()
        title_upper = title_stripped.upper()
        section_keywords = {
            'CONSENT AGENDA', 'CONSENT CALENDAR', 'PUBLIC HEARINGS',
            'LEASES/CONTRACTS/LEGAL', 'CONTRACT MODIFICATIONS',
            'CONSIDERATION OF BIDS/PURCHASES/REQUESTS FOR PROPOSALS',
            'ANNOUNCEMENTS/REPORTS/MOTIONS', 'OTHER BUSINESS', 'OLD BUSINESS',
            'NEW BUSINESS', 'UNFINISHED BUSINESS', 'BUSINESS',
        }
        is_section = (
            title.rstrip('.').endswith(':')
            or re.search(r'\s[\-\u2013\u2014]\s*$', title)
            or not title
            or title_upper in section_keywords
        )

        # Find the blockquote that follows this element at body level
        next_bq = elem.find_next_sibling('blockquote')

        if is_section:
            section_name = title_stripped
            current_section = section_name

            # Sub-items are in the blockquote
            if next_bq:
                for sub_table in next_bq.find_all('table', recursive=True):
                    sub_data = _process_item_table(sub_table, parent_section=section_name)
                    if not sub_data or not sub_data['title']:
                        continue

                    sub_number = f"{number}.{sub_data['number']}"

                    # Find attachment blockquote: try table's next sibling (bare layout),
                    # then parent div's next sibling (div-wrapped layout)
                    att_bq = sub_table.find_next_sibling('blockquote')
                    if not att_bq:
                        parent_div = sub_table.find_parent('div')
                        if parent_div:
                            att_bq = parent_div.find_next_sibling('blockquote')
                    sub_attachments = _extract_attachments(att_bq)

                    sequence_counter += 1
                    items.append({
                        'vendor_item_id': sub_number,
                        'title': sub_data['title'],
                        'sequence': sequence_counter,
                        'agenda_number': sub_number,
                        'attachments': sub_attachments,
                        'metadata': {'section': section_name} if section_name else {},
                    })
            continue

        # Skip procedural items
        if title.rstrip('.').lower() in procedural:
            continue

        # Regular item
        attachments = _extract_attachments(next_bq)

        sequence_counter += 1
        item_dict = {
            'vendor_item_id': number,
            'title': title,
            'sequence': sequence_counter,
            'agenda_number': number,
            'attachments': attachments,
        }
        if current_section:
            item_dict['metadata'] = {'section': current_section}

        items.append(item_dict)

    logger.debug(
        "parsed generated agendaviewer html",
        vendor="granicus",
        item_count=len(items),
    )

    return {'participation': {}, 'items': items}


# ---------------------------------------------------------------------------
# Questys HTML (Word-exported agendas from Questys DMS)
# ---------------------------------------------------------------------------

# Item number at start of paragraph text: "9.", "10.", "22."
_QUESTYS_ITEM_NUM_RE = re.compile(r'^(\d+)\.\s*')

# Questys item anchor: <a name="AI{id}_NAME">
_QUESTYS_AI_RE = re.compile(r'^AI(\d+)_NAME$')

# Section header patterns in Questys agendas
_QUESTYS_SECTION_KEYWORDS = {
    'CONSENT CALENDAR', 'CONSENT AGENDA', 'BUSINESS CALENDAR',
    'PUBLIC HEARINGS', 'PUBLIC HEARING', 'CLOSED SESSION',
}


def parse_questys_html(html: str, base_url: str) -> Dict[str, Any]:
    """Parse Questys DMS Word-exported HTML agenda.

    Structure: items are numbered <p> tags with hanging indent.  Each has an
    <a name="AI{id}_NAME"> anchor and an <a href="...Documents.htm" target=fraDocuments>
    link containing the item title and pointing to the attachments page.
    Section headers are bold text ending with colon (CONSENT CALENDAR:).
    """
    soup = BeautifulSoup(html, 'html.parser')
    items = []
    sequence_counter = 0
    current_section = ""

    procedural = {
        'call to order', 'roll call', 'pledge of allegiance',
        'flag salute', 'invocation', 'adjournment', 'adjourn',
        'recess', 'reconvene',
    }

    # Walk all paragraphs -- Questys uses <p class=MsoNormal> for everything
    for p in soup.find_all('p', class_='MsoNormal'):
        text = p.get_text(strip=True)
        if not text:
            continue

        # Section headers: bold text ending with colon, no numbering
        bold = p.find('b')
        if bold:
            bold_text = bold.get_text(strip=True).rstrip(':').strip()
            bold_upper = bold_text.upper()
            # Check if this is a section header (not a numbered item)
            num_match = _QUESTYS_ITEM_NUM_RE.match(text)
            if not num_match and any(kw in bold_upper for kw in _QUESTYS_SECTION_KEYWORDS):
                current_section = bold_text
                continue

        # Numbered items: start with "9.", "10.", etc.
        num_match = _QUESTYS_ITEM_NUM_RE.match(text)
        if not num_match:
            continue

        item_number = num_match.group(1)

        # Extract vendor item ID from AI anchor
        vendor_item_id = item_number
        for anchor in p.find_all('a', attrs={'name': True}):
            ai_match = _QUESTYS_AI_RE.match(anchor.get('name', ''))
            if ai_match:
                vendor_item_id = ai_match.group(1)
                break

        # Get title from the Documents.htm link
        doc_link = p.find('a', attrs={'target': 'fraDocuments'})
        if not doc_link:
            continue

        title = doc_link.get_text(strip=True)
        if not title:
            continue

        # Skip procedural
        title_lower = title.lower()
        if any(title_lower.startswith(proc) for proc in procedural):
            continue

        # Build attachment URL from relative Documents.htm path
        href = doc_link.get('href', '')
        attachments = []
        if href:
            doc_url = urljoin(base_url, href)
            attachments.append({
                'name': 'Staff Report',
                'url': doc_url,
                'type': 'html',
            })

        sequence_counter += 1
        item_dict = {
            'vendor_item_id': vendor_item_id,
            'title': title,
            'sequence': sequence_counter,
            'agenda_number': item_number,
            'attachments': attachments,
        }
        if current_section:
            item_dict['metadata'] = {'section': current_section}
        items.append(item_dict)

    logger.debug(
        "parsed questys html",
        vendor="granicus",
        item_count=len(items),
    )

    return {'participation': {}, 'items': items}


# Alias for backward compatibility
parse_html_agenda = parse_agendaviewer_html
