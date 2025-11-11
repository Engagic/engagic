"""
Item filtering utilities - skip procedural items with no civic impact

ALL adapters should use this to filter out:
- Roll call, invocations, pledges
- Approval of minutes/agenda
- Public comment periods
- Adjournments
- Appointments/confirmations without substantive discussion

Confidence: 8/10
Patterns validated against Legistar, applicable to all vendors
"""

import re

# Procedural patterns to skip (no civic impact)
PROCEDURAL_PATTERNS = [
    # Core procedural items
    r'appointment',
    r'confirmation',
    r'public comment',
    r'communications',
    r'roll call',
    r'invocation',
    r'pledge of allegiance',
    r'approval of (minutes|agenda)',
    r'^minutes of',  # Standalone minutes items (e.g., "Minutes of Oct 1, 2025")
    r'adjourn',

    # Low-value administrative items (conservative filtering)
    r'(?i)liquor license',
    r'(?i)beer (and|&) wine license',
    r'(?i)alcoholic beverage license',
]

# Matter types to skip (administrative/procedural, not legislative)
SKIP_MATTER_TYPES = [
    'Minutes (Min)',
    'Introduction & Referral Calendar (IRC)',
    'Information Item (Inf)',
    # Add city-specific variants
    'Minutes',
    'Min',
    'IRC',
    'Inf',
    'Information',
    'Referral Calendar',
]


def should_skip_procedural_item(title: str, item_type: str = "") -> bool:
    """
    Check if an agenda item should be skipped (procedural, no civic impact).

    Args:
        title: Item title
        item_type: Item type (if available)

    Returns:
        True if item should be skipped

    Examples:
        >>> should_skip_procedural_item("Roll Call")
        True
        >>> should_skip_procedural_item("Approval of Minutes")
        True
        >>> should_skip_procedural_item("Housing Development at 123 Main St")
        False
    """
    combined = f"{title} {item_type}".lower()

    for pattern in PROCEDURAL_PATTERNS:
        if re.search(pattern, combined, re.IGNORECASE):
            return True

    return False


def should_skip_matter(matter_type: str) -> bool:
    """
    Check if a matter should be skipped based on its type.

    Filters out administrative/procedural matters that have no legislative impact:
    - Minutes (administrative records)
    - Information items (briefings, presentations)
    - Referral calendars (procedural agendas)

    Args:
        matter_type: Matter type string (e.g., "Minutes (Min)", "Council Bill (CB)")

    Returns:
        True if matter should be skipped from processing queue

    Examples:
        >>> should_skip_matter("Minutes (Min)")
        True
        >>> should_skip_matter("Council Bill (CB)")
        False
        >>> should_skip_matter("Information Item (Inf)")
        True
    """
    if not matter_type:
        return False

    matter_type_lower = matter_type.lower()

    # Check exact matches first
    for skip_type in SKIP_MATTER_TYPES:
        if skip_type.lower() in matter_type_lower:
            return True

    return False


def add_custom_skip_patterns(patterns: list[str]) -> None:
    """
    Add city-specific skip patterns to the global list.

    Use this for cities with unique procedural items.

    Args:
        patterns: List of regex patterns to add

    Example:
        >>> add_custom_skip_patterns([r'land acknowledgment', r'presentations'])
    """
    global PROCEDURAL_PATTERNS
    PROCEDURAL_PATTERNS.extend(patterns)
