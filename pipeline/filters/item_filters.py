"""Item filtering - two-tier: adapter level (skip entirely) vs processor level (skip LLM)"""

import re

# Adapter level: items with zero metadata value (not saved)
ADAPTER_SKIP_PATTERNS = [
    # Core procedural items - no value even as metadata
    r'roll call',
    r'invocation',
    r'pledge of allegiance',
    r'approval of (minutes|agenda)',
    r'approve the minutes',  # Austin variant ("approve the minutes of...")
    r'adopt minutes',
    r'review of minutes',
    r'^minutes of',  # Standalone minutes items
    r'adjourn',
    r'public comment',  # The period itself, not the content
    r'communications',  # Generic communications period
    r'time fixed for next',
    r'identify items (to|for)',  # Future items placeholder ("identify items to discuss")
    r'meeting schedule for',  # Calendar scheduling items
]

# Processor level: items worth saving but not LLM-processing
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

# High token cost, low value (scanned form letters, bulk documents)
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

# Massive PDFs with no policy content (property lists, parcel tables)
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

# Administrative matter types (not legislative)
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
    """Adapter level: should item be skipped entirely (not saved)?"""
    combined = f"{title} {item_type}".lower()
    return any(re.search(p, combined, re.IGNORECASE) for p in ADAPTER_SKIP_PATTERNS)


def should_skip_processing(title: str, item_type: str = "") -> bool:
    """Processor level: should item skip LLM processing (but still be saved)?"""
    combined = f"{title} {item_type}".lower()
    return any(re.search(p, combined, re.IGNORECASE) for p in PROCESSOR_SKIP_PATTERNS)


def should_skip_matter(matter_type: str) -> bool:
    """Should matter be skipped based on type (administrative/procedural)?"""
    if not matter_type:
        return False
    matter_lower = matter_type.lower()
    return any(skip.lower() in matter_lower for skip in SKIP_MATTER_TYPES)


def is_public_comment_attachment(name: str) -> bool:
    """Is attachment public comments or parcel tables (skip to save tokens)?"""
    name_lower = name.lower()
    all_patterns = PUBLIC_COMMENT_PATTERNS + PARCEL_TABLE_PATTERNS
    return any(re.search(p, name_lower, re.IGNORECASE) for p in all_patterns)
