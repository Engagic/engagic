"""
Council Member Extractor - Extract and normalize sponsor data from vendor output

Extracts sponsor information from meeting/item data returned by adapters.
Works with CouncilMemberRepository to persist extracted sponsors.

Data Flow:
1. Adapter fetches meetings with items (items may have sponsors array)
2. Extractor processes items, extracting sponsor names
3. Repository creates/updates council_members and sponsorships

Vendor Support:
- Legistar: sponsors in EventItemSponsors array
- PrimeGov (LA-style): sponsors in matter metadata
- Chicago: sponsors in matter.sponsors array
- Others: sponsors field on items if present

Design:
- Stateless: Extractor doesn't maintain state between calls
- Idempotent: Safe to process same item multiple times
- Batch-friendly: Process all items in a meeting at once
"""

from typing import Dict, List, Optional, Any
from datetime import datetime

from database.id_generation import normalize_sponsor_name
from config import get_logger

logger = get_logger(__name__).bind(component="council_member_extractor")


class CouncilMemberExtractor:
    """Extract council member/sponsor data from vendor output

    Provides methods to extract sponsor names from various vendor formats
    and normalize them for consistent matching.
    """

    @staticmethod
    def extract_sponsors_from_item(item: Dict[str, Any]) -> List[str]:
        """Extract sponsor names from an agenda item

        Handles various vendor formats:
        - item["sponsors"]: List of sponsor names (most common)
        - item["sponsor"]: Single sponsor string (Berkeley)
        - item["metadata"]["sponsors"]: Nested sponsor data

        Args:
            item: Item dict from adapter output

        Returns:
            List of sponsor names (may be empty)
        """
        sponsors = []

        # Direct sponsors array (Chicago, Legistar)
        if "sponsors" in item:
            raw_sponsors = item["sponsors"]
            if isinstance(raw_sponsors, list):
                sponsors.extend(raw_sponsors)
            elif isinstance(raw_sponsors, str) and raw_sponsors.strip():
                sponsors.append(raw_sponsors)

        # Single sponsor field (Berkeley)
        if "sponsor" in item:
            raw_sponsor = item["sponsor"]
            if isinstance(raw_sponsor, str) and raw_sponsor.strip():
                sponsors.append(raw_sponsor)

        # Nested in metadata (some PrimeGov implementations)
        if "metadata" in item and isinstance(item["metadata"], dict):
            meta_sponsors = item["metadata"].get("sponsors")
            if isinstance(meta_sponsors, list):
                sponsors.extend(meta_sponsors)
            elif isinstance(meta_sponsors, str) and meta_sponsors.strip():
                sponsors.append(meta_sponsors)

        # Filter empty strings and normalize
        return [s for s in sponsors if s and s.strip()]

    @staticmethod
    def extract_sponsors_from_matter(matter: Dict[str, Any]) -> List[str]:
        """Extract sponsor names from a matter record

        Similar to extract_sponsors_from_item but for matter data.

        Args:
            matter: Matter dict (from city_matters or adapter output)

        Returns:
            List of sponsor names (may be empty)
        """
        sponsors = []

        # Direct sponsors array (most common)
        if "sponsors" in matter:
            raw_sponsors = matter["sponsors"]
            if isinstance(raw_sponsors, list):
                sponsors.extend(raw_sponsors)
            elif isinstance(raw_sponsors, str) and raw_sponsors.strip():
                # Handle comma-separated string
                sponsors.extend([s.strip() for s in raw_sponsors.split(",")])

        return [s for s in sponsors if s and s.strip()]

    @staticmethod
    def extract_all_sponsors_from_meeting(meeting: Dict[str, Any]) -> Dict[str, List[str]]:
        """Extract all sponsors from a meeting and its items

        Returns mapping of matter_id -> sponsor names for linking.

        Args:
            meeting: Meeting dict with items array

        Returns:
            Dict mapping matter_id to list of sponsor names
            Items without matter_id are keyed by item_id
        """
        sponsors_by_matter: Dict[str, List[str]] = {}

        items = meeting.get("items", [])
        for item in items:
            sponsors = CouncilMemberExtractor.extract_sponsors_from_item(item)
            if not sponsors:
                continue

            # Use matter_id if available, else item_id
            key = item.get("matter_id") or item.get("item_id")
            if key:
                if key not in sponsors_by_matter:
                    sponsors_by_matter[key] = []
                # Extend but dedupe
                for s in sponsors:
                    if s not in sponsors_by_matter[key]:
                        sponsors_by_matter[key].append(s)

        return sponsors_by_matter

    @staticmethod
    def normalize_sponsors(sponsors: List[str]) -> List[str]:
        """Normalize sponsor names for consistent matching

        Args:
            sponsors: Raw sponsor names

        Returns:
            Normalized sponsor names (lowercase, trimmed)
        """
        normalized = []
        seen = set()

        for s in sponsors:
            norm = normalize_sponsor_name(s)
            if norm and norm not in seen:
                normalized.append(norm)
                seen.add(norm)

        return normalized

    @staticmethod
    def dedupe_sponsors(sponsors: List[str]) -> List[str]:
        """Remove duplicate sponsors preserving order

        Uses normalized comparison but returns original names.

        Args:
            sponsors: List of sponsor names (may have duplicates)

        Returns:
            Deduplicated list preserving first occurrence order
        """
        seen_normalized = set()
        result = []

        for s in sponsors:
            norm = normalize_sponsor_name(s)
            if norm and norm not in seen_normalized:
                result.append(s)  # Keep original name
                seen_normalized.add(norm)

        return result

    @staticmethod
    def get_primary_sponsor(sponsors: List[str]) -> Optional[str]:
        """Get primary sponsor (first in list)

        Convention: First listed sponsor is primary sponsor.

        Args:
            sponsors: List of sponsor names

        Returns:
            First sponsor name, or None if empty
        """
        if sponsors:
            return sponsors[0]
        return None

    @staticmethod
    def extract_sponsor_stats(meetings: List[Dict[str, Any]]) -> Dict[str, int]:
        """Extract sponsor frequency across multiple meetings

        Useful for identifying most active council members.

        Args:
            meetings: List of meeting dicts with items

        Returns:
            Dict mapping normalized sponsor name to count
        """
        counts: Dict[str, int] = {}

        for meeting in meetings:
            sponsor_map = CouncilMemberExtractor.extract_all_sponsors_from_meeting(meeting)
            for sponsors in sponsor_map.values():
                for s in sponsors:
                    norm = normalize_sponsor_name(s)
                    if norm:
                        counts[norm] = counts.get(norm, 0) + 1

        return counts


async def process_meeting_sponsors(
    meeting: Dict[str, Any],
    banana: str,
    council_member_repo,  # CouncilMemberRepository
    meeting_date: Optional[datetime] = None,
) -> int:
    """Process all sponsors in a meeting, linking to council members

    Convenience function that:
    1. Extracts sponsors from all items
    2. Creates/updates council members
    3. Creates sponsorship links

    Args:
        meeting: Meeting dict with items array
        banana: City identifier
        council_member_repo: CouncilMemberRepository instance
        meeting_date: Date of meeting (for first_seen/last_seen tracking)

    Returns:
        Total number of new sponsorships created
    """
    total_created = 0
    extractor = CouncilMemberExtractor()

    items = meeting.get("items", [])
    for item in items:
        sponsors = extractor.extract_sponsors_from_item(item)
        if not sponsors:
            continue

        matter_id = item.get("matter_id")
        if not matter_id:
            # Can't link sponsors without matter_id
            continue

        # Dedupe sponsors
        sponsors = extractor.dedupe_sponsors(sponsors)

        # Link sponsors to matter
        created = await council_member_repo.link_sponsors_to_matter(
            banana=banana,
            matter_id=matter_id,
            sponsor_names=sponsors,
            appeared_at=meeting_date,
        )
        total_created += created

    if total_created > 0:
        logger.info(
            "processed meeting sponsors",
            meeting_id=meeting.get("meeting_id"),
            banana=banana,
            new_sponsorships=total_created,
        )

    return total_created
