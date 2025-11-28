"""Async CouncilMemberRepository for council member and sponsorship operations

Handles CRUD operations for council members (elected officials):
- Find or create council members from sponsor names
- Link council members to matters via sponsorships
- Retrieve sponsorship history for members and matters
- Update member statistics (sponsorship_count, last_seen)

Design:
- Normalizes sponsor names for matching across vendor variations
- ID includes city_banana to prevent cross-city collisions
- Denormalized sponsorship_count for quick stats queries
"""

from typing import Dict, List, Optional
from datetime import datetime

from database.repositories_async.base import BaseRepository
from database.models import CouncilMember, Vote
from database.id_generation import (
    generate_council_member_id,
    normalize_sponsor_name,
)
from config import get_logger

logger = get_logger(__name__).bind(component="council_member_repository")


class CouncilMemberRepository(BaseRepository):
    """Repository for council member and sponsorship operations

    Provides:
    - Find or create council members by name
    - Link members to matters via sponsorships
    - Retrieve members by city
    - Get sponsorship history
    """

    async def find_or_create_member(
        self,
        banana: str,
        name: str,
        appeared_at: Optional[datetime] = None,
    ) -> CouncilMember:
        """Find existing council member or create new one

        Uses normalized name for matching. Creates new member if not found.
        Updates last_seen if existing member found.

        Args:
            banana: City identifier
            name: Sponsor name (will be normalized for matching)
            appeared_at: Date when sponsor appeared (for first_seen/last_seen)

        Returns:
            CouncilMember object (existing or newly created)
        """
        normalized = normalize_sponsor_name(name)
        member_id = generate_council_member_id(banana, name)

        async with self.transaction() as conn:
            # Try to find existing member
            row = await conn.fetchrow(
                """
                SELECT id, banana, name, normalized_name, title, district,
                       status, first_seen, last_seen, sponsorship_count, vote_count, metadata
                FROM council_members
                WHERE id = $1
                """,
                member_id,
            )

            if row:
                # Update last_seen if newer
                if appeared_at and (not row["last_seen"] or appeared_at > row["last_seen"]):
                    await conn.execute(
                        """
                        UPDATE council_members
                        SET last_seen = $2, updated_at = CURRENT_TIMESTAMP
                        WHERE id = $1
                        """,
                        member_id,
                        appeared_at,
                    )

                return CouncilMember(
                    id=row["id"],
                    banana=row["banana"],
                    name=row["name"],
                    normalized_name=row["normalized_name"],
                    title=row["title"],
                    district=row["district"],
                    status=row["status"],
                    first_seen=row["first_seen"],
                    last_seen=appeared_at or row["last_seen"],
                    sponsorship_count=row["sponsorship_count"],
                    vote_count=row["vote_count"],
                    metadata=row["metadata"],
                )

            # Create new member
            await conn.execute(
                """
                INSERT INTO council_members (
                    id, banana, name, normalized_name, status,
                    first_seen, last_seen, sponsorship_count
                )
                VALUES ($1, $2, $3, $4, 'active', $5, $5, 0)
                """,
                member_id,
                banana,
                name,
                normalized,
                appeared_at,
            )

            logger.info("created council member", member_id=member_id, name=name, banana=banana)

            return CouncilMember(
                id=member_id,
                banana=banana,
                name=name,
                normalized_name=normalized,
                status="active",
                first_seen=appeared_at,
                last_seen=appeared_at,
                sponsorship_count=0,
                vote_count=0,
            )

    async def create_sponsorship(
        self,
        council_member_id: str,
        matter_id: str,
        is_primary: bool = False,
        sponsor_order: Optional[int] = None,
    ) -> bool:
        """Create sponsorship link between council member and matter

        Uses UPSERT with RETURNING to detect if insert succeeded.
        Only increments sponsorship_count when a new row is actually created.

        Args:
            council_member_id: Council member ID
            matter_id: Matter ID (city_matters.id)
            is_primary: True if primary sponsor, False for co-sponsor
            sponsor_order: Position in sponsor list (1 = first)

        Returns:
            True if new sponsorship created, False if already exists
        """
        async with self.transaction() as conn:
            # Use RETURNING to detect if insert succeeded (no redundant SELECT)
            result = await conn.fetchval(
                """
                INSERT INTO sponsorships (council_member_id, matter_id, is_primary, sponsor_order)
                VALUES ($1, $2, $3, $4)
                ON CONFLICT (council_member_id, matter_id) DO NOTHING
                RETURNING id
                """,
                council_member_id,
                matter_id,
                is_primary,
                sponsor_order,
            )

            if not result:
                # ON CONFLICT triggered - sponsorship already exists
                return False

            # Only increment count when INSERT actually succeeded
            await conn.execute(
                """
                UPDATE council_members
                SET sponsorship_count = sponsorship_count + 1,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = $1
                """,
                council_member_id,
            )

            logger.debug(
                "created sponsorship",
                council_member_id=council_member_id,
                matter_id=matter_id,
                is_primary=is_primary,
            )

            return True

    async def get_members_by_city(
        self,
        banana: str,
        status: Optional[str] = None,
        limit: int = 100,
    ) -> List[CouncilMember]:
        """Get all council members for a city

        Args:
            banana: City identifier
            status: Filter by status (active, former, unknown)
            limit: Maximum results

        Returns:
            List of CouncilMember objects sorted by sponsorship_count desc
        """
        if status:
            rows = await self._fetch(
                """
                SELECT id, banana, name, normalized_name, title, district,
                       status, first_seen, last_seen, sponsorship_count, vote_count, metadata
                FROM council_members
                WHERE banana = $1 AND status = $2
                ORDER BY sponsorship_count DESC
                LIMIT $3
                """,
                banana,
                status,
                limit,
            )
        else:
            rows = await self._fetch(
                """
                SELECT id, banana, name, normalized_name, title, district,
                       status, first_seen, last_seen, sponsorship_count, vote_count, metadata
                FROM council_members
                WHERE banana = $1
                ORDER BY sponsorship_count DESC
                LIMIT $2
                """,
                banana,
                limit,
            )

        return [
            CouncilMember(
                id=row["id"],
                banana=row["banana"],
                name=row["name"],
                normalized_name=row["normalized_name"],
                title=row["title"],
                district=row["district"],
                status=row["status"],
                first_seen=row["first_seen"],
                last_seen=row["last_seen"],
                sponsorship_count=row["sponsorship_count"],
                vote_count=row["vote_count"],
                metadata=row["metadata"],
            )
            for row in rows
        ]

    async def get_member_by_id(self, member_id: str) -> Optional[CouncilMember]:
        """Get council member by ID

        Args:
            member_id: Council member ID

        Returns:
            CouncilMember object or None
        """
        row = await self._fetchrow(
            """
            SELECT id, banana, name, normalized_name, title, district,
                   status, first_seen, last_seen, sponsorship_count, vote_count, metadata
            FROM council_members
            WHERE id = $1
            """,
            member_id,
        )

        if not row:
            return None

        return CouncilMember(
            id=row["id"],
            banana=row["banana"],
            name=row["name"],
            normalized_name=row["normalized_name"],
            title=row["title"],
            district=row["district"],
            status=row["status"],
            first_seen=row["first_seen"],
            last_seen=row["last_seen"],
            sponsorship_count=row["sponsorship_count"],
            vote_count=row["vote_count"],
            metadata=row["metadata"],
        )

    async def get_sponsors_for_matter(self, matter_id: str) -> List[CouncilMember]:
        """Get all sponsors for a matter

        Args:
            matter_id: Matter ID

        Returns:
            List of CouncilMember objects, ordered by sponsor_order
        """
        rows = await self._fetch(
            """
            SELECT cm.id, cm.banana, cm.name, cm.normalized_name, cm.title,
                   cm.district, cm.status, cm.first_seen, cm.last_seen,
                   cm.sponsorship_count, cm.vote_count, cm.metadata, s.is_primary, s.sponsor_order
            FROM council_members cm
            JOIN sponsorships s ON cm.id = s.council_member_id
            WHERE s.matter_id = $1
            ORDER BY s.sponsor_order ASC NULLS LAST, s.is_primary DESC
            """,
            matter_id,
        )

        return [
            CouncilMember(
                id=row["id"],
                banana=row["banana"],
                name=row["name"],
                normalized_name=row["normalized_name"],
                title=row["title"],
                district=row["district"],
                status=row["status"],
                first_seen=row["first_seen"],
                last_seen=row["last_seen"],
                sponsorship_count=row["sponsorship_count"],
                vote_count=row["vote_count"],
                metadata=row["metadata"],
            )
            for row in rows
        ]

    async def get_matters_by_sponsor(
        self,
        council_member_id: str,
        limit: int = 50,
    ) -> List[Dict]:
        """Get all matters sponsored by a council member

        Args:
            council_member_id: Council member ID
            limit: Maximum results

        Returns:
            List of matter dicts with sponsorship info
        """
        rows = await self._fetch(
            """
            SELECT m.id, m.banana, m.matter_file, m.title, m.matter_type,
                   m.canonical_summary, m.first_seen, m.last_seen,
                   s.is_primary, s.sponsor_order
            FROM city_matters m
            JOIN sponsorships s ON m.id = s.matter_id
            WHERE s.council_member_id = $1
            ORDER BY m.last_seen DESC NULLS LAST
            LIMIT $2
            """,
            council_member_id,
            limit,
        )

        return [
            {
                "id": row["id"],
                "banana": row["banana"],
                "matter_file": row["matter_file"],
                "title": row["title"],
                "matter_type": row["matter_type"],
                "canonical_summary": row["canonical_summary"],
                "first_seen": row["first_seen"].isoformat() if row["first_seen"] else None,
                "last_seen": row["last_seen"].isoformat() if row["last_seen"] else None,
                "is_primary": row["is_primary"],
                "sponsor_order": row["sponsor_order"],
            }
            for row in rows
        ]

    async def link_sponsors_to_matter(
        self,
        banana: str,
        matter_id: str,
        sponsor_names: List[str],
        appeared_at: Optional[datetime] = None,
    ) -> int:
        """Link multiple sponsors to a matter

        Convenience method for processing sponsor arrays from vendor data.
        Creates council members if they don't exist, then creates sponsorships.

        Args:
            banana: City identifier
            matter_id: Matter ID
            sponsor_names: List of sponsor names from vendor data
            appeared_at: Date when sponsors appeared

        Returns:
            Number of new sponsorships created
        """
        created_count = 0

        for order, name in enumerate(sponsor_names, start=1):
            if not name or not name.strip():
                continue

            # Find or create council member
            member = await self.find_or_create_member(banana, name, appeared_at)

            # Create sponsorship (first sponsor is primary)
            is_primary = (order == 1)
            if await self.create_sponsorship(member.id, matter_id, is_primary, order):
                created_count += 1

        if created_count > 0:
            logger.info(
                "linked sponsors to matter",
                matter_id=matter_id,
                sponsor_count=len(sponsor_names),
                new_sponsorships=created_count,
            )

        return created_count

    # ==================
    # VOTING METHODS
    # ==================

    async def record_vote(
        self,
        council_member_id: str,
        matter_id: str,
        meeting_id: str,
        vote: str,
        vote_date: Optional[datetime] = None,
        sequence: Optional[int] = None,
        metadata: Optional[dict] = None,
    ) -> bool:
        """Record a single vote for a council member on a matter in a meeting

        Uses UPSERT with RETURNING to detect if insert succeeded.
        Only increments vote_count when a new row is actually created.

        Args:
            council_member_id: Council member ID
            matter_id: Matter ID
            meeting_id: Meeting ID (critical: same matter can be voted multiple times)
            vote: Vote value (yes, no, abstain, absent, present, recused, not_voting)
            vote_date: Date of vote (usually meeting date)
            sequence: Order in roll call if available
            metadata: Vendor-specific data (motion_id, etc.)

        Returns:
            True if new vote recorded, False if already exists
        """
        async with self.transaction() as conn:
            # Use RETURNING to detect if insert succeeded (no redundant SELECT)
            result = await conn.fetchval(
                """
                INSERT INTO votes (council_member_id, matter_id, meeting_id, vote, vote_date, sequence, metadata)
                VALUES ($1, $2, $3, $4, $5, $6, $7)
                ON CONFLICT (council_member_id, matter_id, meeting_id) DO NOTHING
                RETURNING id
                """,
                council_member_id,
                matter_id,
                meeting_id,
                vote,
                vote_date,
                sequence,
                metadata,
            )

            if not result:
                # ON CONFLICT triggered - vote already exists
                return False

            # Only increment count when INSERT actually succeeded
            await conn.execute(
                """
                UPDATE council_members
                SET vote_count = vote_count + 1,
                    last_seen = GREATEST(last_seen, $2),
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = $1
                """,
                council_member_id,
                vote_date,
            )

            logger.debug(
                "recorded vote",
                council_member_id=council_member_id,
                matter_id=matter_id,
                meeting_id=meeting_id,
                vote=vote,
            )

            return True

    async def record_votes_for_matter(
        self,
        banana: str,
        matter_id: str,
        meeting_id: str,
        votes: List[Dict],
        vote_date: Optional[datetime] = None,
    ) -> int:
        """Record all votes for a matter in a meeting

        Convenience method for processing vote arrays from vendor data.
        Creates council members if they don't exist, then records votes.

        Args:
            banana: City identifier
            matter_id: Matter ID
            meeting_id: Meeting ID
            votes: List of vote dicts with keys: name, vote, sequence (optional)
            vote_date: Date of vote

        Returns:
            Number of new votes recorded
        """
        recorded_count = 0

        for vote_data in votes:
            name = vote_data.get("name")
            vote_value = vote_data.get("vote")

            if not name or not vote_value:
                continue

            # Normalize vote value
            vote_value = vote_value.lower().strip()
            valid_votes = {"yes", "no", "abstain", "absent", "present", "recused", "not_voting"}
            if vote_value not in valid_votes:
                # Map common variations
                vote_map = {
                    "aye": "yes",
                    "yea": "yes",
                    "nay": "no",
                    "abstained": "abstain",
                    "excused": "absent",
                    "not present": "absent",
                    "recuse": "recused",
                }
                vote_value = vote_map.get(vote_value, "not_voting")

            # Find or create council member
            member = await self.find_or_create_member(banana, name, vote_date)

            # Record vote
            if await self.record_vote(
                council_member_id=member.id,
                matter_id=matter_id,
                meeting_id=meeting_id,
                vote=vote_value,
                vote_date=vote_date,
                sequence=vote_data.get("sequence"),
                metadata=vote_data.get("metadata"),
            ):
                recorded_count += 1

        if recorded_count > 0:
            logger.info(
                "recorded votes for matter",
                matter_id=matter_id,
                meeting_id=meeting_id,
                vote_count=len(votes),
                new_votes=recorded_count,
            )

        return recorded_count

    async def get_votes_for_meeting(
        self,
        meeting_id: str,
    ) -> List[Vote]:
        """Get all votes cast in a meeting

        Args:
            meeting_id: Meeting ID

        Returns:
            List of Vote objects
        """
        rows = await self._fetch(
            """
            SELECT id, council_member_id, matter_id, meeting_id, vote,
                   vote_date, sequence, metadata, created_at
            FROM votes
            WHERE meeting_id = $1
            ORDER BY matter_id, sequence ASC NULLS LAST
            """,
            meeting_id,
        )

        return [
            Vote(
                id=row["id"],
                council_member_id=row["council_member_id"],
                matter_id=row["matter_id"],
                meeting_id=row["meeting_id"],
                vote=row["vote"],
                vote_date=row["vote_date"],
                sequence=row["sequence"],
                metadata=row["metadata"],
                created_at=row["created_at"],
            )
            for row in rows
        ]

    async def get_votes_for_matter(
        self,
        matter_id: str,
    ) -> List[Vote]:
        """Get all votes cast on a matter (across all meetings)

        Args:
            matter_id: Matter ID

        Returns:
            List of Vote objects ordered by vote_date
        """
        rows = await self._fetch(
            """
            SELECT id, council_member_id, matter_id, meeting_id, vote,
                   vote_date, sequence, metadata, created_at
            FROM votes
            WHERE matter_id = $1
            ORDER BY vote_date DESC NULLS LAST, sequence ASC NULLS LAST
            """,
            matter_id,
        )

        return [
            Vote(
                id=row["id"],
                council_member_id=row["council_member_id"],
                matter_id=row["matter_id"],
                meeting_id=row["meeting_id"],
                vote=row["vote"],
                vote_date=row["vote_date"],
                sequence=row["sequence"],
                metadata=row["metadata"],
                created_at=row["created_at"],
            )
            for row in rows
        ]

    async def get_member_voting_record(
        self,
        council_member_id: str,
        limit: int = 100,
    ) -> List[Dict]:
        """Get voting history for a council member

        Args:
            council_member_id: Council member ID
            limit: Maximum results

        Returns:
            List of vote dicts with matter info
        """
        rows = await self._fetch(
            """
            SELECT v.id, v.matter_id, v.meeting_id, v.vote, v.vote_date, v.sequence,
                   m.matter_file, m.title, m.matter_type
            FROM votes v
            JOIN city_matters m ON v.matter_id = m.id
            WHERE v.council_member_id = $1
            ORDER BY v.vote_date DESC NULLS LAST
            LIMIT $2
            """,
            council_member_id,
            limit,
        )

        return [
            {
                "id": row["id"],
                "matter_id": row["matter_id"],
                "meeting_id": row["meeting_id"],
                "vote": row["vote"],
                "vote_date": row["vote_date"].isoformat() if row["vote_date"] else None,
                "sequence": row["sequence"],
                "matter_file": row["matter_file"],
                "title": row["title"],
                "matter_type": row["matter_type"],
            }
            for row in rows
        ]

    async def get_vote_tally_for_matter(
        self,
        matter_id: str,
        meeting_id: Optional[str] = None,
    ) -> Dict[str, int]:
        """Get vote tally (counts) for a matter

        Args:
            matter_id: Matter ID
            meeting_id: Optional meeting ID to filter to specific vote

        Returns:
            Dict with vote counts: {yes: N, no: N, abstain: N, ...}
        """
        if meeting_id:
            rows = await self._fetch(
                """
                SELECT vote, COUNT(*) as count
                FROM votes
                WHERE matter_id = $1 AND meeting_id = $2
                GROUP BY vote
                """,
                matter_id,
                meeting_id,
            )
        else:
            # Get most recent meeting's votes
            rows = await self._fetch(
                """
                SELECT vote, COUNT(*) as count
                FROM votes
                WHERE matter_id = $1
                  AND meeting_id = (
                      SELECT meeting_id FROM votes WHERE matter_id = $1
                      ORDER BY vote_date DESC NULLS LAST LIMIT 1
                  )
                GROUP BY vote
                """,
                matter_id,
            )

        return {row["vote"]: row["count"] for row in rows}
