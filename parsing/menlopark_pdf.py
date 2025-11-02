"""Menlo Park PDF agenda parser

Parses Menlo Park PDF agendas to extract items and attachments.

PDF structure:
- Letter-based sections: H. (Presentations), I. (Appointments), J. (Consent), K. (Regular Business), etc.
- Items: H1., I1., J1., K1. format
- Attachment markers: (Attachment), (Staff Report #XX-XXX-CC), (Presentation)
- Hyperlinks embedded in PDF for attachments

Confidence: 8/10 - Pattern is consistent across meetings
"""

import re
from typing import Dict, Any, List, Tuple


def parse_menlopark_pdf_agenda(pdf_text: str, links: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Parse Menlo Park PDF agenda to extract items and map attachments.

    Args:
        pdf_text: Full text extracted from PDF
        links: List of hyperlinks from PDF with structure:
               [{'page': int, 'url': str, 'rect': tuple}]

    Returns:
        {
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
    items = []

    # Split by pages to map items to pages
    page_texts = pdf_text.split('--- PAGE')

    # Track current page for link mapping
    current_page = 0

    # Pattern to match item IDs: H1., I1., J1., K1., etc.
    # Strategy: Find item ID, then capture text until next item or section
    item_id_pattern = re.compile(r'^([A-Z]\d+)\.\s*$', re.MULTILINE)

    # Find all items across all pages
    for page_idx, page_text in enumerate(page_texts):
        if page_idx == 0:
            # First split is before any page marker
            continue

        # Extract page number from header
        page_match = re.match(r'^\s*(\d+)\s*---', page_text)
        if page_match:
            current_page = int(page_match.group(1))

        # Find all item IDs on this page
        for match in item_id_pattern.finditer(page_text):
            item_id = match.group(1)
            start_pos = match.end()

            # Find the next item or section marker to determine end
            next_item = item_id_pattern.search(page_text, start_pos)
            next_section = re.search(r'^[A-Z]\.\s*$', page_text[start_pos:], re.MULTILINE)

            # Determine end position
            if next_item:
                end_pos = start_pos + next_item.start()
            elif next_section:
                end_pos = start_pos + next_section.start()
            else:
                end_pos = len(page_text)

            # Extract text block for this item
            item_text = page_text[start_pos:end_pos].strip()

            # Parse title (first line, cleaned up)
            title_lines = item_text.split('\n', 1)
            title = title_lines[0].strip() if title_lines else ""

            # Look for attachment marker in the full item text
            attachment_marker = None
            if '(Attachment)' in item_text:
                attachment_marker = 'Attachment'
            elif match := re.search(r'\(Staff Report #([\d-]+(?:-CC)?)\)', item_text):
                attachment_marker = f'Staff Report #{match.group(1)}'
            elif '(Presentation)' in item_text:
                attachment_marker = 'Presentation'

            # Parse sequence from item_id (e.g., "H1" -> 1, "J5" -> 5)
            sequence_match = re.search(r'(\d+)$', item_id)
            sequence = int(sequence_match.group(1)) if sequence_match else 0

            # Find links on the same page (attachments)
            attachments = _find_attachments_for_item(
                item_id, title, current_page, links, attachment_marker
            )

            item_data = {
                'item_id': item_id,
                'title': title,
                'sequence': sequence,
                'attachments': attachments,
            }

            items.append(item_data)

    return {'items': items}


def _find_attachments_for_item(
    item_id: str,
    title: str,
    page: int,
    all_links: List[Dict[str, Any]],
    attachment_marker: str = None
) -> List[Dict[str, Any]]:
    """
    Find attachment links for a specific item.

    Strategy: Filter document links from navigation/utility links.
    Problem: Multiple items share pages, and we can't reliably map links to specific items
    without position data.

    Solution: Only attach links when there's a clear marker (Attachment, Staff Report, etc.)
    indicating an attachment exists. Without position data, we can't determine which
    specific PDF link belongs to which item.

    Args:
        item_id: Item identifier (e.g., "H1")
        title: Item title
        page: Page number where item appears
        all_links: All links extracted from PDF
        attachment_marker: Type hint from text (e.g., "Attachment", "Staff Report #25-155-CC")

    Returns:
        List of attachment dictionaries
    """
    attachments = []

    # Filter ALL document links (not just from this page - items can reference docs on other pages)
    document_links = [
        link for link in all_links
        if '/files/sharedassets/' in link['url']  # Actual documents
        and not link['url'].startswith(('mailto:', 'https://zoom', 'http://www'))
    ]

    # Confidence: 9/10
    # Menlo Park encodes item IDs in filenames!
    # Examples: h1-20251021-cc-tour-de-menlo.pdf, j1-20251021-cc-minutes.pdf
    # We can parse these and match to items precisely

    item_id_lower = item_id.lower()  # "H1" -> "h1"

    for link in document_links:
        url = link['url']
        filename = url.split('/')[-1].lower()  # Get filename, lowercase it

        # Check if filename starts with item_id (e.g., "h1-", "j1-", "k1-")
        if filename.startswith(f"{item_id_lower}-"):
            # Determine attachment type
            attachment_type = 'pdf'  # Default assumption
            if url.endswith('.pdf'):
                attachment_type = 'pdf'
            elif url.endswith(('.doc', '.docx')):
                attachment_type = 'doc'

            # Determine name from marker or use filename
            if attachment_marker:
                if 'Staff Report' in attachment_marker:
                    name = attachment_marker
                elif attachment_marker == 'Presentation':
                    name = f"{item_id} - Presentation"
                elif attachment_marker == 'Attachment':
                    name = f"{item_id} - Attachment"
                else:
                    name = f"{item_id} - Document"
            else:
                # Use filename as name (cleaned up)
                name = filename.replace('.pdf', '').replace('-', ' ').title()

            attachments.append({
                'name': name,
                'url': url,
                'type': attachment_type,
            })

    return attachments
