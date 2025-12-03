"""
Pipeline Utilities - Shared helper functions

Contains utilities used across pipeline modules for matters-first processing.
"""

import hashlib
import json

import requests
from datetime import datetime
from typing import List, Dict, Any, Optional

from config import get_logger

logger = get_logger(__name__).bind(component="engagic")


def hash_attachments_fast(attachments: List[Any]) -> str:
    """
    Hash attachments using URL and name only (pure function, no I/O).

    This is the fast path for deduplication. Uses only local data
    without making network requests.

    Args:
        attachments: List of AttachmentInfo objects with 'url' and 'name' attrs

    Returns:
        SHA256 hex digest, or empty string if no attachments

    Confidence: 7/10 - Works but misses CDN rotations where URL stays same
    """
    if not attachments:
        return ""
    pairs = [(att.url or "", att.name or "") for att in attachments]
    pairs.sort()
    content = json.dumps(pairs, sort_keys=True)
    return hashlib.sha256(content.encode()).hexdigest()


def hash_attachments_with_metadata(attachments: List[Any], timeout: int = 3) -> str:
    """
    Hash attachments including HTTP metadata (makes network requests).

    This is the slow path for better change detection. Makes HEAD requests
    to fetch content-length and last-modified headers, which helps detect
    content changes even when URLs stay the same.

    Args:
        attachments: List of AttachmentInfo objects with 'url' and 'name' attrs
        timeout: Timeout for HEAD requests in seconds

    Returns:
        SHA256 hex digest, or empty string if no attachments

    Confidence: 8/10 - Better detection but adds latency
    """
    if not attachments:
        return ""

    tuples = []
    for att in attachments:
        url = att.url or ""
        name = att.name or ""

        if not url:
            tuples.append((url, name, "", ""))
            continue

        # Try to fetch metadata via HEAD request
        try:
            metadata = _fetch_attachment_metadata(url, timeout)
            tuples.append((url, name, metadata['content_length'], metadata['last_modified']))
        except requests.RequestException as e:
            # Fallback to URL-only if metadata fetch fails
            logger.warning("failed to fetch metadata", url=url, error=str(e))
            tuples.append((url, name, "", ""))

    tuples.sort()
    content = json.dumps(tuples, sort_keys=True)
    return hashlib.sha256(content.encode()).hexdigest()


def hash_attachments(
    attachments: List[Any],
    include_metadata: bool = False,
    timeout: int = 3
) -> str:
    """Wrapper for backwards compatibility. Prefer the specific functions."""
    if include_metadata:
        return hash_attachments_with_metadata(attachments, timeout)
    return hash_attachments_fast(attachments)


def _fetch_attachment_metadata(url: str, timeout: int = 3) -> Dict[str, str]:
    """
    Fetch content-length and last-modified headers via HEAD request.

    Args:
        url: Attachment URL
        timeout: Request timeout in seconds

    Returns:
        Dict with 'content_length' and 'last_modified' keys (strings)

    Raises:
        requests.RequestException: If HEAD request fails
    """
    response = requests.head(url, timeout=timeout, allow_redirects=True)
    response.raise_for_status()

    return {
        'content_length': response.headers.get('Content-Length', ''),
        'last_modified': response.headers.get('Last-Modified', '')
    }


def get_matter_key(matter_file: Optional[str], matter_id: Optional[str]) -> Optional[str]:
    """
    Get canonical matter key, preferring semantic ID over UUID.

    Args:
        matter_file: Public semantic ID (e.g., "25-1234", "BL2025-1098")
        matter_id: Backend UUID or numeric ID

    Returns:
        matter_file if present, else matter_id, else None

    Example:
        >>> get_matter_key("25-1234", "uuid-abc-123")
        '25-1234'
        >>> get_matter_key(None, "uuid-abc-123")
        'uuid-abc-123'
    """
    return matter_file or matter_id


def combine_date_time(date_str: Optional[str], time_str: Optional[str]) -> Optional[str]:
    """
    Combine separate date and time strings into ISO datetime.

    Generalizable utility for vendors that split date/time into separate fields
    (Legistar: EventDate + EventTime, etc.).

    Args:
        date_str: ISO date string (e.g., "2025-11-18T00:00:00" or "2025-11-18")
        time_str: Time string in various formats (e.g., "6:30 PM", "18:30:00", "6:30 PM EST")

    Returns:
        Combined ISO datetime string, or original date_str if time parsing fails

    Example:
        >>> combine_date_time("2025-11-18T00:00:00", "6:30 PM")
        '2025-11-18T18:30:00'
        >>> combine_date_time("2025-11-18", "18:30")
        '2025-11-18T18:30:00'
        >>> combine_date_time("2025-11-18", None)
        '2025-11-18'

    Confidence: 8/10
    - Handles common time formats (12h/24h, with/without seconds)
    - Falls back gracefully to date-only if time parsing fails
    - Timezone handling is basic (strips timezone info for consistency)
    """
    if not date_str:
        return None

    if not time_str:
        return date_str

    try:
        # Parse date (handle ISO datetime or date-only)
        if 'T' in date_str:
            date_obj = datetime.fromisoformat(date_str.replace('Z', '+00:00'))
        else:
            date_obj = datetime.fromisoformat(date_str)

        # Clean time string (remove timezone abbreviations like "EST", "PST")
        time_clean = time_str.strip()
        for tz in [' EST', ' PST', ' CST', ' MST', ' EDT', ' PDT', ' CDT', ' MDT']:
            time_clean = time_clean.replace(tz, '')

        # Try parsing time in common formats
        time_obj = None
        time_formats = [
            '%I:%M %p',        # 6:30 PM
            '%I:%M:%S %p',     # 6:30:00 PM
            '%H:%M',           # 18:30
            '%H:%M:%S',        # 18:30:00
        ]

        for fmt in time_formats:
            try:
                time_obj = datetime.strptime(time_clean, fmt)
                break
            except ValueError:
                continue

        if not time_obj:
            logger.debug("could not parse time - using date only", time_str=time_str)
            return date_str

        # Combine date and time
        combined = date_obj.replace(
            hour=time_obj.hour,
            minute=time_obj.minute,
            second=time_obj.second
        )

        # Return as ISO string (strip timezone for consistency)
        return combined.replace(tzinfo=None).isoformat()

    except Exception as e:
        logger.debug("error combining date/time", date_str=date_str, time_str=time_str, error=str(e))
        return date_str
