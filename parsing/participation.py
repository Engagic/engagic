"""
Participation Parser - Extract contact info from meeting text

Moved from: infocore/processing/participation_parser.py

Parses text BEFORE AI summarization to extract structured contact info.
"""

import re

from typing import Optional
from urllib.parse import urlparse

from config import get_logger
from database.models import ParticipationInfo, EmailContext, StreamingUrl

logger = get_logger(__name__).bind(component="engagic")


def parse_participation_info(text: str) -> Optional[ParticipationInfo]:
    """
    Extract participation info from meeting text.

    Args:
        text: Extracted PDF text (before AI summarization)

    Returns:
        ParticipationInfo model or None if nothing found
    """
    if not text:
        return None

    text_lower = text.lower()
    info: dict = {}

    # Extract ALL email addresses with context
    email_pattern = r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'
    all_emails = re.findall(email_pattern, text, re.IGNORECASE)

    if all_emails:
        # Filter spam/placeholders
        valid = [e for e in all_emails if not any(skip in e.lower() for skip in ['example.com', 'test@', 'noreply'])]

        if valid:
            # Primary email (first one)
            info['email'] = valid[0]

            # Store all unique emails with context
            emails_with_context: list[EmailContext] = []
            seen: set[str] = set()
            for email in valid:
                if email.lower() in seen:
                    continue
                seen.add(email.lower())

                # Try to infer purpose from surrounding text
                purpose = _infer_email_purpose(text, email)
                emails_with_context.append(EmailContext(
                    address=email,
                    purpose=purpose
                ))

            if len(emails_with_context) > 1:
                info['emails'] = emails_with_context

    # Extract phone numbers
    # Patterns: (123) 456-7890, 123-456-7890, +1-123-456-7890, Phone: 1-669-900-6833
    phone_patterns = [
        r'phone[:\s]+\+?1?[\s.-]?\(?\d{3}\)?[\s.-]?\d{3}[\s.-]?\d{4}',  # "Phone: 1-669-900-6833"
        r'\+?1?\s*\(?\d{3}\)?[\s.-]?\d{3}[\s.-]?\d{4}',
        r'\b\d{3}-\d{3}-\d{4}\b',
    ]

    for pattern in phone_patterns:
        phones = re.findall(pattern, text, re.IGNORECASE)
        if phones:
            # Normalize: keep only digits from first match
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
    streaming_platforms = {
        'youtube.com': 'YouTube',
        'youtu.be': 'YouTube',
        'facebook.com': 'Facebook Live',
        'granicus.com': 'Granicus',
        'midpenmedia.org': 'Midpen Media',
        'vimeo.com': 'Vimeo'
    }

    streaming_urls: list[StreamingUrl] = []

    for url in urls:
        # Clean trailing punctuation (common in agendas)
        url = url.rstrip('.,;:)')

        parsed = urlparse(url)

        # Check for virtual meeting platforms
        if any(domain in parsed.netloc for domain in virtual_domains):
            if 'virtual_url' not in info:
                info['virtual_url'] = url

        # Check for streaming platforms
        for domain, platform_name in streaming_platforms.items():
            if domain in parsed.netloc:
                streaming_urls.append(StreamingUrl(
                    url=url,
                    platform=platform_name
                ))
                break

    if streaming_urls:
        info['streaming_urls'] = streaming_urls

    # Extract Cable TV channel
    cable_pattern = r'cable\s+tv\s+channel\s+(\d+)'
    cable_matches = re.findall(cable_pattern, text, re.IGNORECASE)
    if cable_matches:
        if 'streaming_urls' not in info:
            info['streaming_urls'] = []
        info['streaming_urls'].append(StreamingUrl(
            channel=cable_matches[0],
            platform='Cable TV'
        ))

    # Extract Zoom meeting ID (handle spaces and dashes)
    if 'zoom' in text_lower or info.get('virtual_url'):
        # More flexible pattern: "Meeting ID: 362 027 238" or "362-027-238"
        meeting_id_pattern = r'meeting\s*id[:\s]+(\d{3}[\s-]?\d{3}[\s-]?\d{3,4})'
        meeting_ids = re.findall(meeting_id_pattern, text, re.IGNORECASE)
        if meeting_ids:
            # Keep spaces/dashes as found
            info['meeting_id'] = meeting_ids[0].strip()

    # Detect hybrid (in-person + virtual)
    hybrid_keywords = ['hybrid', 'in-person and virtual', 'attend in person or', 'zoom or in person']
    if any(kw in text_lower for kw in hybrid_keywords):
        info['is_hybrid'] = True
    elif info.get('virtual_url'):
        info['is_virtual_only'] = True

    # Only return if we found something
    if not info:
        return None
    return ParticipationInfo(**info)


def _infer_email_purpose(text: str, email: str) -> str:
    """
    Infer the purpose of an email address from surrounding context.

    Confidence: 6/10 - Heuristic-based, may miss nuanced contexts
    """
    # Find text around the email (100 chars before and after)
    email_index = text.lower().find(email.lower())
    if email_index == -1:
        return "general contact"

    context_start = max(0, email_index - 100)
    context_end = min(len(text), email_index + len(email) + 100)
    context = text[context_start:context_end].lower()

    # Check for purpose keywords
    if any(kw in context for kw in ['written comment', 'public comment', 'submit comment']):
        return "written comments"
    elif any(kw in context for kw in ['powerpoint', 'video', 'media', 'presentation']):
        return "media submissions"
    elif any(kw in context for kw in ['clerk', 'city clerk']):
        return "city clerk"
    elif any(kw in context for kw in ['council', 'city council']):
        return "city council"

    return "general contact"


# Confidence: 8/10
# Enhancements:
# - Captures multiple emails with inferred purpose
# - Detects streaming alternatives (YouTube, cable, etc.)
# - Handles meeting IDs with spaces/dashes
# - Strips trailing punctuation from URLs
#
# Limitations:
# - Email purpose inference is heuristic (may misclassify)
# - May miss international phone formats
# - Physical address extraction not implemented
# - Custom streaming platforms not in dictionary
