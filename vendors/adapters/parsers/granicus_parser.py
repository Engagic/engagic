"""
Granicus HTML Parser - Extract agenda items from AgendaViewer pages

Granicus structure:
- Items in <table> elements with item number, title, File ID
- Attachments as MetaViewer.php links following each item
- Items grouped by sections (Consent Calendar, Discussion Calendar, etc.)
"""

import re
import logging
from typing import Dict, Any
from bs4 import BeautifulSoup

logger = logging.getLogger("engagic")


def parse_html_agenda(html: str) -> Dict[str, Any]:
    """
    Parse Granicus AgendaViewer HTML to extract items and attachments.

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


# Confidence: 7/10
# Works with Granicus AgendaViewer HTML structure
# MetaViewer PDF extraction requires follow-up HTTP requests
