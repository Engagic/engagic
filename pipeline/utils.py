"""
Pipeline Utilities - Shared helper functions

Contains utilities used across pipeline modules for matters-first processing.
"""

import hashlib
import json
from typing import List, Dict, Any, Optional


def hash_attachments(attachments: List[Dict[str, Any]]) -> str:
    """
    Generate stable hash of attachment URLs for deduplication.

    Used to detect when a matter's attachments haven't changed across
    multiple meeting appearances, enabling summary reuse.

    Args:
        attachments: List of attachment dicts with 'url' and 'name' keys

    Returns:
        SHA256 hex digest of sorted (url, name) tuples

    Example:
        >>> attachments = [
        ...     {"url": "https://city.gov/doc1.pdf", "name": "Staff Report"},
        ...     {"url": "https://city.gov/doc2.pdf", "name": "Ordinance"}
        ... ]
        >>> hash_attachments(attachments)
        'a3b2c1d4...'
    """
    if not attachments:
        return ""

    # Extract (url, name) tuples and sort for stability
    # Sorting ensures same attachments in different order produce same hash
    pairs = [(att.get("url", ""), att.get("name", "")) for att in attachments]
    pairs.sort()

    # JSON encode and hash
    content = json.dumps(pairs, sort_keys=True)
    return hashlib.sha256(content.encode()).hexdigest()


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
