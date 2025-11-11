"""
Pipeline Utilities - Shared helper functions

Contains utilities used across pipeline modules for matters-first processing.
"""

import hashlib
import json
import logging
import requests
from typing import List, Dict, Any, Optional

logger = logging.getLogger("engagic")


def hash_attachments(
    attachments: List[Dict[str, Any]],
    include_metadata: bool = False,
    timeout: int = 3
) -> str:
    """
    Generate stable hash of attachments for deduplication.

    Two modes:
    1. URL-only (default): Hash (url, name) tuples
    2. Metadata-enhanced: Hash (url, name, content-length, last-modified) tuples

    Metadata-enhanced mode makes HEAD requests to get content metadata,
    which better detects content changes even when URLs stay the same.
    However, it's slower due to network requests.

    Args:
        attachments: List of attachment dicts with 'url' and 'name' keys
        include_metadata: If True, fetch and include content-length and last-modified
        timeout: Timeout for HEAD requests (only used if include_metadata=True)

    Returns:
        SHA256 hex digest of attachment data

    Example:
        >>> attachments = [
        ...     {"url": "https://city.gov/doc1.pdf", "name": "Staff Report"},
        ...     {"url": "https://city.gov/doc2.pdf", "name": "Ordinance"}
        ... ]
        >>> hash_attachments(attachments)  # Fast, URL-only
        'a3b2c1d4...'
        >>> hash_attachments(attachments, include_metadata=True)  # Better detection
        'b5c6d7e8...'

    Confidence: 7/10
    - URL-only hashing works but misses CDN rotations
    - Metadata hashing is better but adds latency
    - Some servers don't provide content-length/last-modified headers
    """
    if not attachments:
        return ""

    if include_metadata:
        # Enhanced mode: Include content metadata in hash
        tuples = []
        for att in attachments:
            url = att.get("url", "")
            name = att.get("name", "")

            if not url:
                tuples.append((url, name, "", ""))
                continue

            # Try to fetch metadata via HEAD request
            try:
                metadata = _fetch_attachment_metadata(url, timeout)
                tuples.append((url, name, metadata['content_length'], metadata['last_modified']))
            except Exception as e:
                # Fallback to URL-only if metadata fetch fails
                logger.debug(f"Failed to fetch metadata for {url}: {e}")
                tuples.append((url, name, "", ""))

        tuples.sort()
        content = json.dumps(tuples, sort_keys=True)
        return hashlib.sha256(content.encode()).hexdigest()
    else:
        # Fast mode: URL-only hashing
        pairs = [(att.get("url", ""), att.get("name", "")) for att in attachments]
        pairs.sort()
        content = json.dumps(pairs, sort_keys=True)
        return hashlib.sha256(content.encode()).hexdigest()


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
