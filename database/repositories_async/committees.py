"""Async CommitteeRepository for committee and membership operations

Handles CRUD operations for committees (legislative bodies):
- Find or create committees from meeting titles
- Track committee membership (which council members serve on which committees)
- Historical tracking for time-aware queries
- Committee-level vote analysis support

Design:
- Normalizes committee names for matching across vendor variations
- ID includes city_banana to prevent cross-city collisions
- Historical tracking via joined_at/left_at enables time-aware queries
"""

from typing import Dict, List, Optional
from datetime import datetime

from database.repositories_async.base import BaseRepository
from database.models import Committee
from database.id_generation import (
    generate_committee_id,
    normalize_committee_name,
)
from config import get_logger

logger = get_logger(__name__).bind(component="committee_repository")


class CommitteeRepository(BaseRepository):
    """Repository for committee and membership operations

    Provides:
    - Find or create committees by name
    - Add/remove members from committees
    - Get committee roster (current and historical)
    - Get committees by city
    """

    async def find_or_create_committee(
        self,
        banana: str,
        name: str,
        description: Optional[str] = None,
    ) -> Committee:
        """Find existing committee or create new one

        Uses normalized name for matching. Creates new committee if not found.

        Args:
            banana: City identifier
            name: Committee name (will be normalized for matching)
            description: Optional committee description

        Returns:
            Committee object (existing or newly created)
        """
        normalized = normalize_committee_name(name)
        committee_id = generate_committee_id(banana, name)

        async with self.transaction() as conn:
            # Try to find existing committee
            row = await conn.fetchrow(
                """
                SELECT id, banana, name, normalized_name, description, status,
                       created_at, updated_at
                FROM committees
                WHERE id = $1
                """,
                committee_id,
            )

            if row:
                return Committee(
                    id=row["id"],
                    banana=row["banana"],
                    name=row["name"],
                    normalized_name=row["normalized_name"],
                    description=row["description"],
                    status=row["status"],
                    created_at=row["created_at"],
                    updated_at=row["updated_at"],
                )

            # Create new committee
            await conn.execute(
                """
                INSERT INTO committees (id, banana, name, normalized_name, description, status)
                VALUES ($1, $2, $3, $4, $5, 'active')
                """,
                committee_id,
                banana,
                name,
                normalized,
                description,
            )

            logger.info("created committee", committee_id=committee_id, name=name, banana=banana)

            return Committee(
                id=committee_id,
                banana=banana,
                name=name,
                normalized_name=normalized,
                description=description,
                status="active",
            )

    async def get_committee_by_id(self, committee_id: str) -> Optional[Committee]:
        """Get committee by ID

        Args:
            committee_id: Committee ID

        Returns:
            Committee object or None
        """
        row = await self._fetchrow(
            """
            SELECT id, banana, name, normalized_name, description, status,
                   created_at, updated_at
            FROM committees
            WHERE id = $1
            """,
            committee_id,
        )

        if not row:
            return None

        return Committee(
            id=row["id"],
            banana=row["banana"],
            name=row["name"],
            normalized_name=row["normalized_name"],
            description=row["description"],
            status=row["status"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    async def get_committees_by_city(
        self,
        banana: str,
        status: Optional[str] = None,
        limit: int = 100,
    ) -> List[Committee]:
        """Get all committees for a city

        Args:
            banana: City identifier
            status: Filter by status (active, inactive, unknown)
            limit: Maximum results

        Returns:
            List of Committee objects sorted by name
        """
        if status:
            rows = await self._fetch(
                """
                SELECT id, banana, name, normalized_name, description, status,
                       created_at, updated_at
                FROM committees
                WHERE banana = $1 AND status = $2
                ORDER BY name
                LIMIT $3
                """,
                banana,
                status,
                limit,
            )
        else:
            rows = await self._fetch(
                """
                SELECT id, banana, name, normalized_name, description, status,
                       created_at, updated_at
                FROM committees
                WHERE banana = $1
                ORDER BY name
                LIMIT $2
                """,
                banana,
                limit,
            )

        return [
            Committee(
                id=row["id"],
                banana=row["banana"],
                name=row["name"],
                normalized_name=row["normalized_name"],
                description=row["description"],
                status=row["status"],
                created_at=row["created_at"],
                updated_at=row["updated_at"],
            )
            for row in rows
        ]

    # ==================
    # MEMBERSHIP METHODS
    # ==================

    async def add_member_to_committee(
        self,
        committee_id: str,
        council_member_id: str,
        role: Optional[str] = None,
        joined_at: Optional[datetime] = None,
    ) -> bool:
        """Add a council member to a committee

        Uses UPSERT with RETURNING to detect if insert succeeded.

        Args:
            committee_id: Committee ID
            council_member_id: Council member ID
            role: Role on committee (Chair, Vice-Chair, Member)
            joined_at: Date joined (defaults to now)

        Returns:
            True if new membership created, False if already exists
        """
        if joined_at is None:
            joined_at = datetime.now()

        async with self.transaction() as conn:
            result = await conn.fetchval(
                """
                INSERT INTO committee_members (committee_id, council_member_id, role, joined_at)
                VALUES ($1, $2, $3, $4)
                ON CONFLICT (committee_id, council_member_id, joined_at) DO NOTHING
                RETURNING id
                """,
                committee_id,
                council_member_id,
                role,
                joined_at,
            )

            if not result:
                return False

            logger.debug(
                "added member to committee",
                committee_id=committee_id,
                council_member_id=council_member_id,
                role=role,
            )

            return True

    async def remove_member_from_committee(
        self,
        committee_id: str,
        council_member_id: str,
        left_at: Optional[datetime] = None,
    ) -> bool:
        """Remove a council member from a committee

        Sets left_at on the most recent active membership.

        Args:
            committee_id: Committee ID
            council_member_id: Council member ID
            left_at: Date left (defaults to now)

        Returns:
            True if membership was updated, False if no active membership found
        """
        if left_at is None:
            left_at = datetime.now()

        async with self.transaction() as conn:
            result = await conn.execute(
                """
                UPDATE committee_members
                SET left_at = $3
                WHERE committee_id = $1
                  AND council_member_id = $2
                  AND left_at IS NULL
                """,
                committee_id,
                council_member_id,
                left_at,
            )

            if result == "UPDATE 0":
                return False

            logger.debug(
                "removed member from committee",
                committee_id=committee_id,
                council_member_id=council_member_id,
            )

            return True

    async def get_committee_members(
        self,
        committee_id: str,
        active_only: bool = True,
        as_of: Optional[datetime] = None,
    ) -> List[Dict]:
        """Get members of a committee

        Args:
            committee_id: Committee ID
            active_only: Only return currently serving members
            as_of: Get members as of specific date (for historical queries)

        Returns:
            List of member dicts with council_member info and role
        """
        if as_of:
            # Historical query: members who were active on as_of date
            rows = await self._fetch(
                """
                SELECT cm.id, cm.committee_id, cm.council_member_id, cm.role,
                       cm.joined_at, cm.left_at, cm.created_at,
                       c.name as member_name, c.title, c.district
                FROM committee_members cm
                JOIN council_members c ON cm.council_member_id = c.id
                WHERE cm.committee_id = $1
                  AND cm.joined_at <= $2
                  AND (cm.left_at IS NULL OR cm.left_at > $2)
                ORDER BY cm.role, c.name
                """,
                committee_id,
                as_of,
            )
        elif active_only:
            rows = await self._fetch(
                """
                SELECT cm.id, cm.committee_id, cm.council_member_id, cm.role,
                       cm.joined_at, cm.left_at, cm.created_at,
                       c.name as member_name, c.title, c.district
                FROM committee_members cm
                JOIN council_members c ON cm.council_member_id = c.id
                WHERE cm.committee_id = $1
                  AND cm.left_at IS NULL
                ORDER BY cm.role, c.name
                """,
                committee_id,
            )
        else:
            rows = await self._fetch(
                """
                SELECT cm.id, cm.committee_id, cm.council_member_id, cm.role,
                       cm.joined_at, cm.left_at, cm.created_at,
                       c.name as member_name, c.title, c.district
                FROM committee_members cm
                JOIN council_members c ON cm.council_member_id = c.id
                WHERE cm.committee_id = $1
                ORDER BY cm.role, c.name, cm.joined_at DESC
                """,
                committee_id,
            )

        return [
            {
                "id": row["id"],
                "committee_id": row["committee_id"],
                "council_member_id": row["council_member_id"],
                "role": row["role"],
                "joined_at": row["joined_at"].isoformat() if row["joined_at"] else None,
                "left_at": row["left_at"].isoformat() if row["left_at"] else None,
                "member_name": row["member_name"],
                "title": row["title"],
                "district": row["district"],
            }
            for row in rows
        ]

    async def get_member_committees(
        self,
        council_member_id: str,
        active_only: bool = True,
    ) -> List[Dict]:
        """Get committees a council member serves on

        Args:
            council_member_id: Council member ID
            active_only: Only return current committee assignments

        Returns:
            List of committee dicts with role and dates
        """
        if active_only:
            rows = await self._fetch(
                """
                SELECT cm.id, cm.committee_id, cm.role, cm.joined_at, cm.left_at,
                       c.name as committee_name, c.status as committee_status
                FROM committee_members cm
                JOIN committees c ON cm.committee_id = c.id
                WHERE cm.council_member_id = $1
                  AND cm.left_at IS NULL
                ORDER BY c.name
                """,
                council_member_id,
            )
        else:
            rows = await self._fetch(
                """
                SELECT cm.id, cm.committee_id, cm.role, cm.joined_at, cm.left_at,
                       c.name as committee_name, c.status as committee_status
                FROM committee_members cm
                JOIN committees c ON cm.committee_id = c.id
                WHERE cm.council_member_id = $1
                ORDER BY cm.left_at IS NULL DESC, cm.joined_at DESC
                """,
                council_member_id,
            )

        return [
            {
                "id": row["id"],
                "committee_id": row["committee_id"],
                "committee_name": row["committee_name"],
                "committee_status": row["committee_status"],
                "role": row["role"],
                "joined_at": row["joined_at"].isoformat() if row["joined_at"] else None,
                "left_at": row["left_at"].isoformat() if row["left_at"] else None,
            }
            for row in rows
        ]

    # ==================
    # VOTE OUTCOME METHODS
    # ==================

    async def update_matter_appearance_outcome(
        self,
        matter_id: str,
        meeting_id: str,
        item_id: str,
        committee_id: Optional[str] = None,
        vote_outcome: Optional[str] = None,
        vote_tally: Optional[Dict] = None,
    ) -> bool:
        """Update vote outcome and tally for a matter appearance

        Args:
            matter_id: Matter ID
            meeting_id: Meeting ID
            item_id: Item ID
            committee_id: Committee ID (optional)
            vote_outcome: Vote result (passed, failed, tabled, etc.)
            vote_tally: Vote counts {"yes": N, "no": N, ...}

        Returns:
            True if updated, False if appearance not found
        """
        import json

        async with self.transaction() as conn:
            result = await conn.execute(
                """
                UPDATE matter_appearances
                SET committee_id = COALESCE($4, committee_id),
                    vote_outcome = COALESCE($5, vote_outcome),
                    vote_tally = COALESCE($6, vote_tally)
                WHERE matter_id = $1 AND meeting_id = $2 AND item_id = $3
                """,
                matter_id,
                meeting_id,
                item_id,
                committee_id,
                vote_outcome,
                json.dumps(vote_tally) if vote_tally else None,
            )

            return result != "UPDATE 0"

    async def get_committee_vote_history(
        self,
        committee_id: str,
        limit: int = 50,
    ) -> List[Dict]:
        """Get voting history for a committee

        Args:
            committee_id: Committee ID
            limit: Maximum results

        Returns:
            List of matter appearances with vote outcomes
        """
        rows = await self._fetch(
            """
            SELECT ma.matter_id, ma.meeting_id, ma.item_id, ma.appeared_at,
                   ma.vote_outcome, ma.vote_tally,
                   m.matter_file, m.title as matter_title
            FROM matter_appearances ma
            JOIN city_matters m ON ma.matter_id = m.id
            WHERE ma.committee_id = $1
              AND ma.vote_outcome IS NOT NULL
            ORDER BY ma.appeared_at DESC
            LIMIT $2
            """,
            committee_id,
            limit,
        )

        return [
            {
                "matter_id": row["matter_id"],
                "meeting_id": row["meeting_id"],
                "item_id": row["item_id"],
                "appeared_at": row["appeared_at"].isoformat() if row["appeared_at"] else None,
                "vote_outcome": row["vote_outcome"],
                "vote_tally": row["vote_tally"],
                "matter_file": row["matter_file"],
                "matter_title": row["matter_title"],
            }
            for row in rows
        ]
