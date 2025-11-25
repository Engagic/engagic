"""
Item filtering utilities - skip procedural items with no civic impact

ALL adapters should use this to filter out:
- Roll call, invocations, pledges
- Approval of minutes/agenda
- Public comment periods
- Adjournments
- Appointments/confirmations without substantive discussion
- Ceremonial items (birthdays, retirements, congratulations)

Confidence: 8/10
Patterns validated against Legistar and Chicago, applicable to all vendors

Note: Ceremonial patterns updated to catch Chicago-specific items like
"Congratulations to X on retirement" and birthday recognitions.
"""

import re

# Procedural patterns to skip (no civic impact)
# Confidence: 8/10 - Validated against Legistar, Chicago, and multi-city production data
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
    r'adopt minutes',
    r'review of minutes',
    r'^minutes of',  # Standalone minutes items (e.g., "Minutes of Oct 1, 2025")
    r'adjourn',

    # Ceremonial items (ZERO civic value)
    r'proclamation',
    r'commendation',
    r'recognition',
    r'ceremonial',
    r'(?i)congratulations (to|extended to|for)',
    r'(?i)tribute to (late|the late)',
    r'(?i)\bon (his|her|their) retirement\b',
    r'(?i)retirement of',
    r'(?i)happy birthday',
    r'(?i)birthday (wishes|greetings|recognition|celebration)',

    # Low-value administrative items
    r'(?i)liquor license',
    r'(?i)beer (and|&) wine license',
    r'(?i)alcoholic beverage license',
    r'issuance of permits? for sign',
    r'signboard permit',
    r'fee waiver for',
    r'(various )?small claims?',
    r'time fixed for next',
]

# Skip public comment attachments (high token cost, low informational value)
# These are typically scanned form letters - hundreds of pages, minimal unique content
PUBLIC_COMMENT_PATTERNS = [
    r'public comment',
    r'public correspondence',
    r'comment letter',
    r'comment ltrs',  # SF abbreviation
    r'written comment',
    r'public hearing comment',
    r'citizen comment',
    r'correspondence received',
    r'public input',
    r'public testimony',
    r'letters received',
    r'petitions',  # SF "Petitions and Communications"
    r'pub corr',  # SF abbreviation
    r'pulbic corr',  # Common typo in SF data
    r'comm pkt',  # Committee packets
    r'committee packet',
]

# Skip parcel tables and property lists (massive PDFs with no civic value)
# Example: "Parcel Tables" (992 pages!) - just property IDs and addresses
PARCEL_TABLE_PATTERNS = [
    r'parcel table',
    r'parcel list',
    r'parcel map',
    r'tax parcel',
    r'property list',
    r'property table',
    r'assessor',
    r'apn list',  # Assessor Parcel Number
    r'parcel number',
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


def is_public_comment_attachment(name: str) -> bool:
    """
    Check if attachment is public comments or parcel tables (skip to save tokens).

    These attachments are typically:
    - Hundreds of pages of scanned form letters
    - Property lists with no policy content
    - High token cost, low informational value

    Args:
        name: Attachment filename or title

    Returns:
        True if attachment should be skipped

    Examples:
        >>> is_public_comment_attachment("Public Comments Received")
        True
        >>> is_public_comment_attachment("Parcel Table 2025")
        True
        >>> is_public_comment_attachment("Staff Report.pdf")
        False
    """
    name_lower = name.lower()

    for pattern in PUBLIC_COMMENT_PATTERNS:
        if re.search(pattern, name_lower, re.IGNORECASE):
            return True

    for pattern in PARCEL_TABLE_PATTERNS:
        if re.search(pattern, name_lower, re.IGNORECASE):
            return True

    return False
