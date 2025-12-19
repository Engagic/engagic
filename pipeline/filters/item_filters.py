"""Item filtering - two-tier: adapter level (skip entirely) vs processor level (skip LLM)"""

import re

# Meeting level: test/demo meetings to skip entirely
MEETING_SKIP_PATTERNS = [
    r'\bmock\b',  # "Mock Select Committee", "Mock Hearing"
    r'\btest\b',  # "Test Meeting", "Test Committee"
    r'\bdemo\b',  # "Demo Session"
    r'\btraining\b',  # "Training Session"
    r'\bpractice\b',  # "Practice Meeting"
]

# Adapter level: items with zero metadata value (not saved)
ADAPTER_SKIP_PATTERNS = [
    # Core procedural items - no value even as metadata
    r'roll call',
    r'invocation',
    r'pledge of allegiance',
    r'approval of (minutes|agenda)',
    r'approval of.*minutes',  # "Approval of Draft Raleigh Board of Adjustment Minutes"
    r'approve the minutes',  # Austin variant ("approve the minutes of...")
    r'adopt minutes',
    r'review of minutes',
    r'^minutes of',  # Standalone minutes items
    r'draft.*minutes',  # Draft minutes items
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
    r'cmte pkt',  # Committee packets (alternate abbreviation)
    r'committee packet',
    r'board pkt',  # Board packets (SF compilation format)
    r'co-?sponsor(ship)?\s*(request|ltr|letter)',  # "Co-Sponsor Request Chen 122525"
    r'sponsor(ship)?\s*request',
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

# Boilerplate vendor/contract documents (huge, not substantive to decision)
BOILERPLATE_CONTRACT_PATTERNS = [
    r'omnia partners contract',  # Cooperative purchasing agreements (100s of pages each)
    r'sourcewell contract',  # Another cooperative purchasing org
    r'naspo valuepoint',  # State purchasing cooperative
    r'u\.?s\.? communities',  # US Communities contracts
    r'hgac.?buy',  # Houston-Galveston Area Council cooperative
    r'master agreement',  # Generic master agreements (often boilerplate)
    r'terms and conditions',  # T&C documents
    r'general conditions',  # Construction general conditions
    r'insurance certificate',  # COI documents
    r'certificate of insurance',
    r'w-?9',  # Tax forms
    r'bid tabulation',  # Bid results tables (useful but huge)
]

# SF procedural boilerplate (internal routing, compliance checkboxes, no policy substance)
# The actual legislative content is in "Leg Ver*" and "PC Transmittal"
SF_PROCEDURAL_PATTERNS = [
    r'ceqa det',  # CEQA Determination - checkbox form saying "categorically exempt"
    r'ceqa determination',
    r'referral ceqa',  # Referral to CEQA review - internal routing
    r'referral fyi',  # FYI referral - just routing notification
    r'myr memo',  # Mayor's memo - cover letter, no substance
    r'mayor.?s? memo',
    r'comm rpt rqst',  # Committee Report Request Memo - internal request
    r'committee report request',
    r'referral.*pc\b',  # Referral to Planning Commission - routing form
    r'hearing notice',  # Notice that hearing will occur - no content
]

# Environmental Impact Reports - massive technical documents (200-500+ pages)
# Important for environmental review but too large for LLM summarization
EIR_PATTERNS = [
    r'\bfeir\b',  # Final EIR
    r'\bdeir\b',  # Draft EIR
    r'\bseir\b',  # Supplemental EIR
    r'\beir\b',   # Generic EIR reference
    r'environmental impact report',
    r'ceqa findings',  # CEQA findings document (different from CEQA Det form)
    r'initial study',  # CEQA initial study
    r'negative declaration',  # Mitigated Negative Declaration
    r'notice of preparation',  # NOP for EIR
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


def should_skip_meeting(title: str) -> bool:
    """Meeting level: should entire meeting be skipped (test/demo/mock)?"""
    return any(re.search(p, title, re.IGNORECASE) for p in MEETING_SKIP_PATTERNS)


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
    """Is attachment low-value for summarization (public comments, parcel tables, boilerplate, procedural, EIRs)?"""
    name_lower = name.lower()
    all_patterns = (
        PUBLIC_COMMENT_PATTERNS +
        PARCEL_TABLE_PATTERNS +
        BOILERPLATE_CONTRACT_PATTERNS +
        SF_PROCEDURAL_PATTERNS +
        EIR_PATTERNS
    )
    return any(re.search(p, name_lower, re.IGNORECASE) for p in all_patterns)
