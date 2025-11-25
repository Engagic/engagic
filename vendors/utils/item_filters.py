"""
Item filtering utilities - two-tier filtering for agenda items

TWO LEVELS OF FILTERING:

1. ADAPTER LEVEL (should_skip_item):
   - Items to NOT SAVE at all - zero metadata value
   - Roll call, pledge, invocation, adjournment, minutes approval
   - These never hit the database

2. PROCESSOR LEVEL (should_skip_processing):
   - Items to SAVE but NOT LLM-PROCESS
   - Proclamations, commendations, appointments - have searchable metadata
   - Stored in DB but skipped during LLM summarization to save tokens

Confidence: 8/10
Patterns validated against Legistar, Chicago, and multi-city production data
"""

import re

# =============================================================================
# ADAPTER LEVEL - Don't save these items at all (zero metadata value)
# =============================================================================
ADAPTER_SKIP_PATTERNS = [
    # Core procedural items - no value even as metadata
    r'roll call',
    r'invocation',
    r'pledge of allegiance',
    r'approval of (minutes|agenda)',
    r'adopt minutes',
    r'review of minutes',
    r'^minutes of',  # Standalone minutes items
    r'adjourn',
    r'public comment',  # The period itself, not the content
    r'communications',  # Generic communications period
    r'time fixed for next',
]

# =============================================================================
# PROCESSOR LEVEL - Save but don't LLM-process (has metadata value)
# =============================================================================
PROCESSOR_SKIP_PATTERNS = [
    # Ceremonial items - who/what is searchable, but no need to summarize
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

    # Appointments/confirmations - names matter, details don't need LLM
    r'appointment',
    r'confirmation',

    # Low-value administrative - save for record, don't process
    r'(?i)liquor license',
    r'(?i)beer (and|&) wine license',
    r'(?i)alcoholic beverage license',
    r'issuance of permits? for sign',
    r'signboard permit',
    r'fee waiver for',
    r'(various )?small claims?',
]

# Combined for backward compatibility (deprecated - use specific functions)
PROCEDURAL_PATTERNS = ADAPTER_SKIP_PATTERNS + PROCESSOR_SKIP_PATTERNS

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


def should_skip_item(title: str, item_type: str = "") -> bool:
    """
    ADAPTER LEVEL: Check if item should NOT be saved at all.

    Use this in adapters to filter out items with zero metadata value.
    These items never reach the database.

    Args:
        title: Item title
        item_type: Item type (if available)

    Returns:
        True if item should be skipped entirely (not saved)

    Examples:
        >>> should_skip_item("Roll Call")
        True
        >>> should_skip_item("Approval of Minutes")
        True
        >>> should_skip_item("Proclamation honoring Jane Doe")
        False  # Saved but not processed
    """
    combined = f"{title} {item_type}".lower()

    for pattern in ADAPTER_SKIP_PATTERNS:
        if re.search(pattern, combined, re.IGNORECASE):
            return True

    return False


def should_skip_processing(title: str, item_type: str = "") -> bool:
    """
    PROCESSOR LEVEL: Check if item should be saved but NOT LLM-processed.

    Use this in processor to skip LLM summarization for items that have
    metadata value but don't need expensive analysis.

    Args:
        title: Item title
        item_type: Item type (if available)

    Returns:
        True if item should skip LLM processing (but is still saved)

    Examples:
        >>> should_skip_processing("Proclamation honoring Jane Doe")
        True  # Save metadata, skip LLM
        >>> should_skip_processing("Housing Development at 123 Main St")
        False  # Full processing
    """
    combined = f"{title} {item_type}".lower()

    for pattern in PROCESSOR_SKIP_PATTERNS:
        if re.search(pattern, combined, re.IGNORECASE):
            return True

    return False


# Backward compatibility alias (deprecated)
def should_skip_procedural_item(title: str, item_type: str = "") -> bool:
    """DEPRECATED: Use should_skip_item() for adapters."""
    return should_skip_item(title, item_type)


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
