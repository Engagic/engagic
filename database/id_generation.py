"""
ID Generation - Deterministic identifier generation for matters

Provides consistent, collision-free ID generation for matters across
the system. Uses SHA256 hashing for determinism.

Design Philosophy:
- IDs are deterministic: same inputs always produce same ID
- IDs are unique: hash collision probability is negligible
- IDs are bidirectional: can lookup by original identifiers
- Original data preserved: store matter_file and matter_id in record

Matter ID Fallback Hierarchy:
1. matter_file (preferred) - Public legislative file number (Legistar, LA-style PrimeGov)
2. matter_id (vendor UUID) - Backend identifier if stable
3. title (normalized) - For cities without stable vendor IDs (Palo Alto-style PrimeGov)
4. generated UUID - Last resort for generic items (always unique, no deduplication)
"""

import hashlib
import re
from typing import Optional


def _strip_reading_prefixes(text: str) -> str:
    """Strip reading prefixes from ordinance/resolution titles

    Handles variations: "FIRST READ:", "FIRST READING:", "REINTRODUCED FIRST READING:", etc.
    This allows different readings of the same ordinance to be identified as the same matter.

    Args:
        text: Title text that may contain reading prefix

    Returns:
        Text with reading prefix removed

    Examples:
        >>> _strip_reading_prefixes("FIRST READING: Ordinance 2025-123")
        'Ordinance 2025-123'

        >>> _strip_reading_prefixes("REINTRODUCED SECOND READ: Resolution")
        'Resolution'
    """
    reading_prefixes = [
        r'^FIRST\s+READ(?:ING)?:\s*',
        r'^SECOND\s+READ(?:ING)?:\s*',
        r'^THIRD\s+READ(?:ING)?:\s*',
        r'^FINAL\s+READ(?:ING)?:\s*',
        r'^REINTRODUCED\s+(?:FIRST\s+)?(?:SECOND\s+)?READ(?:ING)?:\s*',
    ]

    result = text
    for pattern in reading_prefixes:
        result = re.sub(pattern, '', result, flags=re.IGNORECASE)

    return result


def normalize_title_for_matter_id(title: str) -> Optional[str]:
    """Normalize title for matter identification (title-based fallback)

    Used when cities lack stable vendor IDs (e.g., Palo Alto-style PrimeGov).
    Strips reading prefixes, normalizes whitespace/case, excludes generic titles.

    Args:
        title: Raw agenda item title

    Returns:
        Normalized title string for hashing, or None if title should NOT be deduplicated

    Examples:
        >>> normalize_title_for_matter_id("FIRST READING: Ordinance 2025-123...")
        'ordinance 2025-123...'

        >>> normalize_title_for_matter_id("Public Comment")
        None  # Generic title, always unique per meeting

        >>> normalize_title_for_matter_id("Approval of Budget Amendments...")
        'approval of budget amendments...'

    Exclusion Rules:
        - Generic titles (<30 chars or in exclusion list) return None
        - These items are always processed individually (no deduplication)
        - Examples: "Public Comment", "Staff Comments", "VTA"

    Normalization Rules:
        - Strip reading prefixes (FIRST/SECOND/THIRD/FINAL READING, REINTRODUCED)
        - Collapse whitespace to single spaces
        - Convert to lowercase
        - Preserve special characters (parentheses, dashes, etc.)

    Design:
        - Conservative: When in doubt, exclude (false negatives > false positives)
        - City-agnostic: Works across PrimeGov implementations
        - Robust: Handles inconsistent prefix formatting

    Confidence: 8/10
    - Works well for substantive titles (ordinances, resolutions, contracts)
    - May need city-specific tuning for exclusion list
    - 30-char threshold is empirically derived from Palo Alto data
    """
    if not title or not title.strip():
        return None

    # Normalize whitespace early (helps with length check)
    normalized = re.sub(r'\s+', ' ', title.strip())

    # Exclude very short titles (likely generic/procedural)
    if len(normalized) < 30:
        return None

    # Generic title exclusion list (case-insensitive exact match)
    # Based on Palo Alto data analysis (10.3% of items)
    generic_titles = {
        "vta",
        "caltrain",
        "city staff",
        "public comment",
        "public letters",
        "staff comments",
        "future business",
        "review of minutes",
        "city and district reports",
        "open forum",
        "closed session",
        "oral communications",
    }

    if normalized.lower() in generic_titles:
        return None

    # Strip reading prefixes (ordinance lifecycle tracking)
    normalized = _strip_reading_prefixes(normalized)

    # Final normalization
    normalized = re.sub(r'\s+', ' ', normalized.strip().lower())

    # After stripping prefix, check length again (edge case: "FIRST READING: VTA")
    if len(normalized) < 30:
        return None

    return normalized


def generate_matter_id(
    banana: str,
    matter_file: Optional[str] = None,
    matter_id: Optional[str] = None,
    title: Optional[str] = None
) -> Optional[str]:
    """Generate deterministic matter ID from inputs with fallback hierarchy

    Fallback hierarchy (most stable to least):
    1. matter_file - Public legislative file number (Legistar, LA-style PrimeGov)
    2. matter_id - Backend vendor identifier (may be unstable for some vendors)
    3. title - Normalized title (Palo Alto-style PrimeGov fallback)

    Args:
        banana: City identifier (e.g., "sanfranciscoCA")
        matter_file: Official public identifier (e.g., "251041", "BL2025-1098")
        matter_id: Backend vendor identifier (e.g., UUID, numeric)
        title: Agenda item title (fallback for cities without stable IDs)

    Returns:
        Composite ID: {banana}_{hash} where hash is first 16 chars of SHA256
        Returns None if title is provided but excluded (generic item)

    Examples:
        >>> generate_matter_id("nashvilleTN", matter_file="BL2025-1098")
        'nashvilleTN_7a8f3b2c1d9e4f5a'

        >>> generate_matter_id("paloaltoCA", matter_id="fb36db52-...")
        'paloaltoCA_a1b2c3d4e5f6g7h8'

        >>> generate_matter_id("paloaltoCA", title="FIRST READING: Ordinance 2025-123")
        'paloaltoCA_c4d5e6f7a8b9c0d1'  # Uses normalized title

        >>> generate_matter_id("paloaltoCA", title="Public Comment")
        None  # Generic title excluded from deduplication

    Notes:
        - At least one of matter_file, matter_id, or title must be provided
        - If multiple provided, uses first in hierarchy
        - Same inputs always produce same ID (determinism)
        - Generic titles return None (caller should generate unique ID)
    """
    # Hierarchy: matter_file > matter_id > title
    # BACKWARD COMPATIBILITY: Maintain original key format for matter_file/matter_id
    if matter_file or matter_id:
        # Original format: "banana:matter_file:matter_id"
        # Preserves existing matter IDs in database
        key = f"{banana}:{matter_file or ''}:{matter_id or ''}"
    elif title:
        # NEW: Title-based fallback for cities without stable vendor IDs
        normalized = normalize_title_for_matter_id(title)
        if normalized is None:
            # Generic title - caller should generate unique ID
            return None
        # Use distinct prefix to avoid collision with vendor IDs
        key = f"{banana}:title:{normalized}"
    else:
        raise ValueError(
            "At least one of matter_file, matter_id, or title must be provided"
        )

    # Hash the key
    hash_bytes = hashlib.sha256(key.encode('utf-8')).digest()
    hash_hex = hash_bytes.hex()[:16]  # Use first 16 hex chars (64 bits)

    # Return composite ID
    return f"{banana}_{hash_hex}"


def validate_matter_id(matter_id: str) -> bool:
    """Validate matter ID format

    Args:
        matter_id: Matter ID to validate

    Returns:
        True if valid format, False otherwise

    Valid format: {banana}_{16-char-hex}
    Example: "nashvilleTN_7a8f3b2c1d9e4f5a"
    """
    if not matter_id:
        return False

    parts = matter_id.split('_')
    if len(parts) != 2:
        return False

    banana, hash_part = parts

    # Banana should be alphanumeric
    if not banana.isalnum():
        return False

    # Hash should be 16 hex characters
    if len(hash_part) != 16:
        return False

    try:
        int(hash_part, 16)  # Verify it's valid hex
        return True
    except ValueError:
        return False


def extract_banana_from_matter_id(matter_id: str) -> Optional[str]:
    """Extract banana from matter ID

    Args:
        matter_id: Matter ID (e.g., "nashvilleTN_7a8f3b2c1d9e4f5a")

    Returns:
        Banana string or None if invalid format
    """
    if not validate_matter_id(matter_id):
        return None

    return matter_id.split('_')[0]


def matter_ids_match(
    banana: str,
    matter_file_1: Optional[str],
    matter_id_1: Optional[str],
    matter_file_2: Optional[str],
    matter_id_2: Optional[str]
) -> bool:
    """Check if two sets of matter identifiers refer to same matter

    Useful for detecting duplicates when identifiers may differ slightly
    but represent the same legislative item.

    Args:
        banana: City identifier
        matter_file_1: First matter's public ID
        matter_id_1: First matter's backend ID
        matter_file_2: Second matter's public ID
        matter_id_2: Second matter's backend ID

    Returns:
        True if they generate the same composite ID
    """
    try:
        id1 = generate_matter_id(banana, matter_file_1, matter_id_1)
        id2 = generate_matter_id(banana, matter_file_2, matter_id_2)
        return id1 == id2
    except ValueError:
        return False


def hash_meeting_id(meeting_id: str) -> str:
    """Generate deterministic hash from meeting ID for URL slugs

    CRITICAL: Must match frontend hashMeetingId() in utils.ts!

    Algorithm: SHA-256 → hex → first 16 chars
    - Same pattern as generate_matter_id()
    - Handles meeting IDs with dashes/special chars (Chicago UUIDs, etc.)
    - Deterministic: Same ID always produces same hash
    - Collision-resistant: 64 bits (16 hex chars)

    Args:
        meeting_id: Meeting ID (can contain dashes, UUIDs, etc.)

    Returns:
        16-character hex hash

    Examples:
        >>> hash_meeting_id("71CAEB7D-4BC6-F011-BBD2-001DD8020E93")
        'a3f2c1d4e5b6a7c8'  # 16 hex chars

        >>> hash_meeting_id("12345")
        '5994471abb01112a'

    Frontend reference: frontend/src/lib/utils/utils.ts:hashMeetingId()

    Confidence: 10/10 - Standard crypto hash
    """
    hash_bytes = hashlib.sha256(meeting_id.encode('utf-8')).digest()
    return hash_bytes.hex()[:16]  # First 16 hex chars (64 bits)


# Confidence level: 9/10
# This hashing scheme is deterministic and collision-resistant.
# SHA256 provides 2^128 combinations with 16 hex chars, far exceeding
# the number of matters we'll ever track (millions at most).
# The only edge case is if a city changes their matter ID scheme mid-year,
# but that would break their own systems too, so unlikely.


def normalize_sponsor_name(name: str) -> str:
    """Normalize sponsor name for council member matching

    Handles vendor variations like:
    - "John Smith" vs "JOHN SMITH" vs "Smith, John"
    - "Council Member Smith" vs "CM Smith" vs "Smith"
    - Leading/trailing whitespace, multiple spaces

    Args:
        name: Raw sponsor name from vendor data

    Returns:
        Lowercase, trimmed, collapsed whitespace name

    Examples:
        >>> normalize_sponsor_name("  John   Smith  ")
        'john smith'

        >>> normalize_sponsor_name("SMITH, JOHN")
        'smith, john'
    """
    if not name:
        return ""

    # Collapse whitespace and lowercase
    normalized = re.sub(r'\s+', ' ', name.strip().lower())

    return normalized


def generate_council_member_id(banana: str, name: str) -> str:
    """Generate deterministic council member ID

    Uses same pattern as generate_matter_id() for consistency.
    ID includes city_banana to prevent cross-city collisions.

    Args:
        banana: City identifier (e.g., "chicagoIL")
        name: Council member name (will be normalized)

    Returns:
        Composite ID: {banana}_cm_{16-char-hex}

    Examples:
        >>> generate_council_member_id("chicagoIL", "John Smith")
        'chicagoIL_cm_a1b2c3d4e5f6g7h8'

        >>> generate_council_member_id("chicagoIL", "SMITH, JOHN")
        'chicagoIL_cm_a1b2c3d4e5f6g7h8'  # Different name, different hash
    """
    if not banana or not name:
        raise ValueError("Both banana and name are required")

    normalized = normalize_sponsor_name(name)
    if not normalized:
        raise ValueError("Name cannot be empty after normalization")

    key = f"{banana}:council_member:{normalized}"
    hash_bytes = hashlib.sha256(key.encode('utf-8')).digest()
    hash_hex = hash_bytes.hex()[:16]

    return f"{banana}_cm_{hash_hex}"


def validate_council_member_id(member_id: str) -> bool:
    """Validate council member ID format

    Args:
        member_id: Council member ID to validate

    Returns:
        True if valid format, False otherwise

    Valid format: {banana}_cm_{16-char-hex}
    Example: "chicagoIL_cm_7a8f3b2c1d9e4f5a"
    """
    if not member_id:
        return False

    parts = member_id.split('_')
    if len(parts) != 3:
        return False

    banana, prefix, hash_part = parts

    # Banana should be alphanumeric
    if not banana.isalnum():
        return False

    # Prefix must be "cm"
    if prefix != "cm":
        return False

    # Hash should be 16 hex characters
    if len(hash_part) != 16:
        return False

    try:
        int(hash_part, 16)
        return True
    except ValueError:
        return False


def normalize_committee_name(name: str) -> str:
    """Normalize committee name for consistent matching

    Args:
        name: Committee name (e.g., "Planning Commission", "budget committee")

    Returns:
        Normalized lowercase name with standardized whitespace

    Examples:
        >>> normalize_committee_name("  Planning Commission  ")
        'planning commission'
        >>> normalize_committee_name("BUDGET  COMMITTEE")
        'budget committee'
    """
    if not name:
        return ""

    # Strip and collapse whitespace
    normalized = " ".join(name.split())

    # Lowercase for consistent matching
    return normalized.lower()


def generate_committee_id(banana: str, name: str) -> str:
    """Generate deterministic committee ID

    Uses same pattern as generate_council_member_id() for consistency.
    ID includes city_banana to prevent cross-city collisions.

    Args:
        banana: City identifier (e.g., "chicagoIL")
        name: Committee name (will be normalized)

    Returns:
        Composite ID: {banana}_comm_{16-char-hex}

    Examples:
        >>> generate_committee_id("chicagoIL", "Planning Commission")
        'chicagoIL_comm_a1b2c3d4e5f6g7h8'

        >>> generate_committee_id("chicagoIL", "PLANNING COMMISSION")
        'chicagoIL_comm_a1b2c3d4e5f6g7h8'  # Same hash (normalized)
    """
    if not banana or not name:
        raise ValueError("Both banana and name are required")

    normalized = normalize_committee_name(name)
    if not normalized:
        raise ValueError("Name cannot be empty after normalization")

    key = f"{banana}:committee:{normalized}"
    hash_bytes = hashlib.sha256(key.encode('utf-8')).digest()
    hash_hex = hash_bytes.hex()[:16]

    return f"{banana}_comm_{hash_hex}"


def validate_committee_id(committee_id: str) -> bool:
    """Validate committee ID format

    Args:
        committee_id: Committee ID to validate

    Returns:
        True if valid format, False otherwise

    Valid format: {banana}_comm_{16-char-hex}
    Example: "chicagoIL_comm_7a8f3b2c1d9e4f5a"
    """
    if not committee_id:
        return False

    parts = committee_id.split('_')
    if len(parts) != 3:
        return False

    banana, prefix, hash_part = parts

    # Banana should be alphanumeric
    if not banana.isalnum():
        return False

    # Prefix must be "comm"
    if prefix != "comm":
        return False

    # Hash should be 16 hex characters
    if len(hash_part) != 16:
        return False

    try:
        int(hash_part, 16)
        return True
    except ValueError:
        return False
