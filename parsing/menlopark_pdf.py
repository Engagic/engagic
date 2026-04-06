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
from typing import Dict, Any, List


def _is_valid_agenda_item_title(title: str) -> bool:
    """
    Validate if a title looks like a real agenda item vs form field garbage.

    Form field patterns to reject:
    - Too short (< 10 chars): "CA", "ZIP CODE"
    - All caps + short (< 40 chars): "FACILITY ID #", "BUSINESS SITE ADDRESS"
    - Common form field keywords

    Confidence: 7/10 - May need tuning based on edge cases
    """
    if not title or len(title) < 10:
        return False

    # Reject all-caps short titles (form field labels)
    if title.isupper() and len(title) < 40:
        return False

    # Reject common form field keywords
    form_field_keywords = [
        'FACILITY ID', 'CERS ID', 'ZIP CODE', 'SITE ADDRESS',
        'BUSINESS NAME', 'PHONE NUMBER', 'CONTACT NAME',
        'OTHER (Specify)', 'EXAMPLE', 'LOCATION', 'CAPABILITY'
    ]

    for keyword in form_field_keywords:
        if keyword in title.upper():
            return False

    return True


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

    # Pattern to match item IDs: A1., B1., H1., I1., J1., K1., etc.
    # Items appear inline with their title: "H1.    Proclamation: Autism Acceptance Month"
    # Also match section headers: "H.    Presentations and Proclamations"
    item_id_pattern = re.compile(r'^([A-Z]\d+)\.\s+', re.MULTILINE)
    section_pattern = re.compile(r'^[A-Z]\.\s+', re.MULTILINE)

    # Find all items across all pages
    for page_idx, page_text in enumerate(page_texts):
        if page_idx == 0:
            # First split is before any page marker
            continue

        # Find all item IDs on this page
        for match in item_id_pattern.finditer(page_text):
            item_id = match.group(1)
            start_pos = match.end()

            # Find the next item or section marker to determine end
            next_item = item_id_pattern.search(page_text, start_pos)
            next_section = section_pattern.search(page_text, start_pos)

            # Determine end position
            if next_item and next_section:
                end_pos = min(next_item.start(), next_section.start())
            elif next_item:
                end_pos = next_item.start()
            elif next_section:
                end_pos = next_section.start()
            else:
                end_pos = len(page_text)

            # Extract text block for this item (title is on the same line as item ID)
            item_text = page_text[start_pos:end_pos].strip()

            # Parse title (first line, cleaned up)
            title_lines = item_text.split('\n', 1)
            title = title_lines[0].strip() if title_lines else ""

            # Skip form field garbage (validate title)
            if not _is_valid_agenda_item_title(title):
                continue

            # Parse sequence from item_id (e.g., "H1" -> 1, "J5" -> 5)
            sequence_match = re.search(r'(\d+)$', item_id)
            sequence = int(sequence_match.group(1)) if sequence_match else 0

            # Find links on the same page (attachments)
            attachments = _find_attachments_for_item(item_id, links)

            item_data = {
                'item_id': item_id,
                'title': title,
                'sequence': sequence,
                'attachments': attachments,
            }

            items.append(item_data)

    return {'items': items}


def _filename_to_label(filename: str, item_id_lower: str) -> str:
    """Derive a readable label from a Menlo Park attachment filename.

    Examples:
      "j1-20260324-cc-general-plan-apr-2025.pdf"  -> "General Plan Apr 2025"
      "k1-aquatics-study-session.pdf"             -> "Aquatics Study Session"
      "j1-20260324-cc-general-plan-apr-2025_es.pdf" -> "General Plan Apr 2025 Es"
    """
    # Strip extension and item-id prefix
    stem = re.sub(r'\.\w+$', '', filename)  # remove .pdf/.doc
    stem = stem[len(item_id_lower):].lstrip('-')  # remove "j1-"

    # Strip date-body prefix if present (e.g. "20260324-cc-")
    stem = re.sub(r'^\d{8}-[a-z]{2,4}-', '', stem)

    # Convert hyphens/underscores to spaces and title-case
    label = stem.replace('-', ' ').replace('_', ' ').strip()
    return label.title() if label else "Attachment"


def _find_attachments_for_item(
    item_id: str,
    all_links: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """Find attachment links for a specific item by matching filename prefixes.

    Menlo Park encodes item IDs in filenames (e.g. h1-20260324-cc-autism-acceptance.pdf),
    so we match all document links whose filename starts with the item ID.
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

            # Derive a readable name from the filename
            # e.g. "j1-20260324-cc-general-plan-apr-2025.pdf" -> "General Plan Apr 2025"
            name = _filename_to_label(filename, item_id_lower)

            attachments.append({
                'name': name,
                'url': url,
                'type': attachment_type,
            })

    return attachments
