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
    r'appointment',
    r'confirmation',
    r'public comment',
    r'communications',
    r'roll call',
    r'invocation',
    r'pledge of allegiance',
    r'approval of (minutes|agenda)',
    r'adjourn',
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
