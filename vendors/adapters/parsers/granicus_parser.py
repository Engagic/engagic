"""
Granicus HTML Parser - Extract agenda items from Granicus pages

Supports multiple HTML formats:
1. ViewPublisher.php - Meeting listing page (parse_viewpublisher_listing)
2. AgendaOnline/ViewAgenda - HTML agenda with items (parse_agendaonline_html)
3. AgendaViewer.php - Original Granicus format (parse_agendaviewer_html)
"""

import re
from datetime import datetime
from typing import Dict, Any, List, Optional
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from config import get_logger
from parsing.participation import parse_participation_info

logger = get_logger(__name__).bind(component="vendor")


def parse_viewpublisher_listing(html: str, base_url: str) -> List[Dict[str, Any]]:
    """Parse ViewPublisher.php listing to extract meetings with event_id, title, start, agenda_viewer_url."""
    soup = BeautifulSoup(html, 'html.parser')
    meetings = []
    rows = soup.find_all('tr', class_=['odd', 'even'])

    for row in rows:
        cells = row.find_all('td', class_='listItem')
        if len(cells) < 2:
            continue

        title = cells[0].get_text(strip=True)
        date_cell = cells[1]
        timestamp_span = date_cell.find('span', style=lambda x: x and 'display:none' in x if x else False)
        start = None

        if timestamp_span:
            try:
                unix_ts = int(timestamp_span.get_text(strip=True))
                start_dt = datetime.fromtimestamp(unix_ts)
                start = start_dt.isoformat()
            except (ValueError, OSError):
                pass

        if not start:
            date_text = date_cell.get_text(strip=True)
            start = _parse_granicus_date(date_text)

        agenda_link = row.find('a', href=lambda x: x and 'AgendaViewer' in x if x else False)
        if not agenda_link:
            continue

        href = agenda_link['href']
        if href.startswith('//'):
            href = 'https:' + href
        elif not href.startswith('http'):
            href = urljoin(base_url, href)

        event_id_match = re.search(r'event_id=(\d+)', href)
        event_id = event_id_match.group(1) if event_id_match else None

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
    """Parse Granicus date formats like 'December 22, 2025 - 06:00 PM'."""
    date_text = date_text.replace('\xa0', ' ').strip()
    formats = [
        "%B %d, %Y - %I:%M %p",  # December 22, 2025 - 06:00 PM
        "%B %d, %Y %I:%M %p",    # December 22, 2025 06:00 PM
        "%B %d, %Y",             # December 22, 2025
        "%m/%d/%Y %I:%M %p",     # 12/22/2025 06:00 PM
        "%m/%d/%Y",              # 12/22/2025
    ]

    for fmt in formats:
        try:
            dt = datetime.strptime(date_text, fmt)
            return dt.isoformat()
        except ValueError:
            continue

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


# Alias for backward compatibility
parse_html_agenda = parse_agendaviewer_html


# Confidence: 7/10
# Works with Granicus AgendaViewer HTML structure
# MetaViewer PDF extraction requires follow-up HTTP requests
