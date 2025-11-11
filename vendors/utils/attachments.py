"""
Attachment utilities - version deduplication and filtering

Many vendors (especially Legistar) provide multiple versions of the same document:
- "Leg Ver1", "Leg Ver2" (Legistar legislative versions)
- "Draft", "Final Draft", "Revised" (general patterns)

This module provides generic version filtering to avoid showing duplicates.

Confidence: 7/10
Extracted from Legistar, generalized for other vendors
"""

from typing import List, Dict, Any, Optional


def filter_version_attachments(
    attachments: List[Dict[str, Any]],
    version_patterns: Optional[List[str]] = None,
    name_key: str = 'name'
) -> List[Dict[str, Any]]:
    """
    Filter attachments to include at most one version of versioned documents.

    Prefers higher version numbers (Ver2 > Ver1) when multiple versions exist.

    Args:
        attachments: List of attachment dictionaries
        version_patterns: List of version identifiers to detect (default: Legistar patterns)
        name_key: Dictionary key containing the attachment name (default: 'name')

    Returns:
        Filtered list of attachments with at most one version per document

    Examples:
        >>> atts = [
        ...     {'name': 'Staff Report Leg Ver1', 'url': '...'},
        ...     {'name': 'Staff Report Leg Ver2', 'url': '...'},
        ...     {'name': 'Exhibit A', 'url': '...'},
        ... ]
        >>> filtered = filter_version_attachments(atts)
        >>> len(filtered)
        2  # Leg Ver2 + Exhibit A (Ver1 removed)
    """
    if version_patterns is None:
        # Default: Legistar patterns
        version_patterns = ['leg ver', 'legislative version']

    version_attachments = []
    other_attachments = []

    # Separate versioned from non-versioned attachments
    for att in attachments:
        name = att.get(name_key, '').lower()
        is_versioned = any(pattern in name for pattern in version_patterns)

        if is_versioned:
            version_attachments.append(att)
        else:
            other_attachments.append(att)

    # Select best version (highest version number)
    selected_version = None
    if version_attachments:
        selected_version = _select_highest_version(version_attachments, name_key)

    # Combine: at most one version + all other attachments
    filtered = other_attachments
    if selected_version:
        filtered.insert(0, selected_version)

    return filtered


def _select_highest_version(
    version_attachments: List[Dict[str, Any]],
    name_key: str = 'name'
) -> Optional[Dict[str, Any]]:
    """
    Select the highest version number from a list of versioned attachments.

    Checks for explicit version numbers (Ver2, Ver 2, v2, etc.)
    Falls back to first attachment if no version number detected.

    Args:
        version_attachments: List of versioned attachment dictionaries
        name_key: Dictionary key containing the attachment name

    Returns:
        Attachment with highest version number, or first if none detected
    """
    import re

    if not version_attachments:
        return None

    # Try to find explicit version numbers
    for target_version in [10, 9, 8, 7, 6, 5, 4, 3, 2]:  # Check high to low
        pattern = rf'ver\s*{target_version}|v\s*{target_version}|\bversion\s*{target_version}'
        for att in version_attachments:
            name = att.get(name_key, '').lower()
            if re.search(pattern, name, re.IGNORECASE):
                return att

    # Check for Ver1/v1/version 1 explicitly
    for att in version_attachments:
        name = att.get(name_key, '').lower()
        if re.search(r'ver\s*1|v\s*1|\bversion\s*1', name, re.IGNORECASE):
            return att

    # No version number detected, just return the first one
    return version_attachments[0]


def normalize_attachment_metadata(
    attachment: Dict[str, Any],
    vendor: str
) -> Dict[str, Any]:
    """
    Normalize attachment metadata to a consistent format across vendors.

    Different vendors use different field names:
    - Legistar: MatterAttachmentName, MatterAttachmentHyperlink
    - PrimeGov: name, url, history_id
    - Granicus: varies by HTML structure

    Args:
        attachment: Raw attachment dictionary from vendor
        vendor: Vendor name (legistar, primegov, granicus, etc.)

    Returns:
        Normalized attachment with consistent fields: name, url, metadata
    """
    normalized = {}

    if vendor == 'legistar':
        normalized['name'] = attachment.get('MatterAttachmentName', attachment.get('name', ''))
        normalized['url'] = attachment.get('MatterAttachmentHyperlink', attachment.get('url', ''))
        normalized['metadata'] = {
            'vendor': 'legistar',
            'raw': attachment
        }

    elif vendor == 'primegov':
        normalized['name'] = attachment.get('name', '')
        normalized['url'] = attachment.get('url', '')
        normalized['metadata'] = {
            'vendor': 'primegov',
            'history_id': attachment.get('history_id'),
            'raw': attachment
        }

    else:
        # Generic fallback
        normalized['name'] = attachment.get('name', attachment.get('title', ''))
        normalized['url'] = attachment.get('url', attachment.get('href', ''))
        normalized['metadata'] = {
            'vendor': vendor,
            'raw': attachment
        }

    return normalized
