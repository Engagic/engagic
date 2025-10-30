"""
HTML Agenda Parser - Extract agenda items and participation info from PrimeGov HTML

PrimeGov's Portal/Meeting pages have structured HTML with:
- Participation info in the page header
- <div class="agenda-item"> for each item
- <div class="item_contents"> with attachments
"""

import re
import logging
from typing import Dict, Any, List, Optional
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

    logger.info(
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
                })

    return attachments


# Confidence: 8/10
# Works with PrimeGov's current HTML structure.
# May need adjustments if they change class names or div IDs.
