"""
Participation Parser - Extract contact info from meeting text

Parses text BEFORE AI summarization to extract structured contact info.
"""

import re
import logging
from typing import Dict, Any, Optional
from urllib.parse import urlparse

logger = logging.getLogger("engagic")


def parse_participation_info(text: str) -> Optional[Dict[str, Any]]:
    """
    Extract participation info from meeting text.

    Args:
        text: Extracted PDF text (before AI summarization)

    Returns:
        Dict with contact info or None if nothing found
    """
    if not text:
        return None

    text_lower = text.lower()
    info = {}

    # Extract email addresses (word@domain.tld)
    email_pattern = r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'
    emails = re.findall(email_pattern, text, re.IGNORECASE)
    if emails:
        # Filter spam/placeholders
        valid = [e for e in emails if not any(skip in e.lower() for skip in ['example.com', 'test@', 'noreply'])]
        if valid:
            info['email'] = valid[0]

    # Extract phone numbers
    # Patterns: (123) 456-7890, 123-456-7890, +1-123-456-7890
    phone_patterns = [
        r'\+?1?\s*\(?\d{3}\)?[\s.-]?\d{3}[\s.-]?\d{4}',
        r'\b\d{3}-\d{3}-\d{4}\b',
    ]

    for pattern in phone_patterns:
        phones = re.findall(pattern, text)
        if phones:
            # Normalize: keep only digits
            phone = re.sub(r'[^\d]', '', phones[0])
            if len(phone) == 10:
                phone = f"+1{phone}"
            elif len(phone) == 11 and phone.startswith('1'):
                phone = f"+{phone}"
            info['phone'] = phone
            break

    # Extract virtual meeting URLs (zoom, google meet, teams, webex)
    url_pattern = r'https?://[^\s<>"{}|\\^`\[\]]+'
    urls = re.findall(url_pattern, text, re.IGNORECASE)

    virtual_domains = ['zoom.us', 'meet.google.com', 'teams.microsoft.com', 'webex.com', 'gotomeeting.com']
    for url in urls:
        parsed = urlparse(url)
        if any(domain in parsed.netloc for domain in virtual_domains):
            info['virtual_url'] = url
            break

    # Extract Zoom meeting ID (if zoom URL or "zoom" mentioned)
    if 'zoom' in text_lower:
        meeting_id_pattern = r'meeting\s*id[:\s]+(\d{3}[\s-]?\d{3,4}[\s-]?\d{4})'
        meeting_ids = re.findall(meeting_id_pattern, text, re.IGNORECASE)
        if meeting_ids:
            info['meeting_id'] = meeting_ids[0].strip()

    # Detect hybrid (in-person + virtual)
    hybrid_keywords = ['hybrid', 'in-person and virtual', 'attend in person or', 'zoom or in person']
    if any(kw in text_lower for kw in hybrid_keywords):
        info['is_hybrid'] = True
    elif info.get('virtual_url'):
        info['is_virtual_only'] = True

    # Only return if we found something
    return info if info else None


# Confidence: 7/10
# Limitations:
# - May miss international phone formats
# - Physical address extraction complex (not implemented)
# - Custom meeting platforms not in virtual_domains list
