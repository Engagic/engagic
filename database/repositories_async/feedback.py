"""Feedback repository - ratings, issues, quality scores.

Handles user feedback for the closed loop architecture:
- Ratings: 1-5 star ratings on items, meetings, matters
- Issues: Reports of inaccurate, incomplete, misleading content
- Quality scores: Denormalized aggregates for display and reprocessing decisions
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from config import get_logger
from database.repositories_async.base import BaseRepository

logger = get_logger(__name__).bind(component="feedback_repository")


@dataclass
class RatingStats:
    """Aggregated rating statistics for an entity."""
    avg_rating: float
    rating_count: int
    distribution: dict[int, int]  # {1: 5, 2: 3, 3: 10, 4: 8, 5: 12}


@dataclass
class Issue:
    """User-reported issue."""
    id: int
    user_id: Optional[str]
    session_id: Optional[str]
    entity_type: str
    entity_id: str
    issue_type: str
    description: str
    status: str
    admin_notes: Optional[str]
    created_at: datetime
    resolved_at: Optional[datetime]


class FeedbackRepository(BaseRepository):
    """Repository for user feedback operations."""

    def _row_to_issue(self, row) -> Issue:
        """Convert database row to Issue object."""
        return Issue(
            id=row["id"],
            user_id=row["user_id"],
            session_id=row["session_id"],
            entity_type=row["entity_type"],
            entity_id=row["entity_id"],
            issue_type=row["issue_type"],
            description=row["description"],
            status=row["status"],
            admin_notes=row["admin_notes"],
            created_at=row["created_at"],
            resolved_at=row["resolved_at"],
        )

    async def submit_rating(
        self,
        user_id: Optional[str],
        session_id: Optional[str],
        entity_type: str,
        entity_id: str,
        rating: int,
    ) -> bool:
        """Submit or update a rating (1-5). Returns True if successful."""
        if not user_id and not session_id:
            logger.warning("rating rejected - no user or session")
            return False

        if rating < 1 or rating > 5:
            logger.warning("rating rejected - invalid value", rating=rating)
            return False

        # Upsert rating (use user_id if available, else session_id for unique constraint)
        if user_id:
            await self._execute(
                """
                INSERT INTO userland.ratings (user_id, session_id, entity_type, entity_id, rating)
                VALUES ($1, $2, $3, $4, $5)
                ON CONFLICT (user_id, entity_type, entity_id)
                DO UPDATE SET rating = $5, created_at = NOW()
                """,
                user_id,
                session_id,
                entity_type,
                entity_id,
                rating,
            )
        else:
            # Anonymous rating - upsert by session_id (partial unique index)
            await self._execute(
                """
                INSERT INTO userland.ratings (user_id, session_id, entity_type, entity_id, rating)
                VALUES (NULL, $1, $2, $3, $4)
                ON CONFLICT (session_id, entity_type, entity_id)
                WHERE user_id IS NULL AND session_id IS NOT NULL
                DO UPDATE SET rating = $4, created_at = NOW()
                """,
                session_id,
                entity_type,
                entity_id,
                rating,
            )

        await self._update_quality_score(entity_type, entity_id)

        logger.info(
            "rating submitted",
            entity_type=entity_type,
            entity_id=entity_id,
            rating=rating,
            authenticated=user_id is not None,
        )
        return True

    async def _update_quality_score(self, entity_type: str, entity_id: str) -> None:
        """Recalculate and update denormalized quality score on entity table."""
        stats = await self.get_entity_rating(entity_type, entity_id)

        if entity_type == "item":
            await self._execute(
                """
                UPDATE items
                SET quality_score = $1, rating_count = $2
                WHERE id = $3
                """,
                stats.avg_rating if stats.rating_count > 0 else None,
                stats.rating_count,
                entity_id,
            )
        elif entity_type == "matter":
            await self._execute(
                """
                UPDATE city_matters
                SET quality_score = $1, rating_count = $2
                WHERE id = $3
                """,
                stats.avg_rating if stats.rating_count > 0 else None,
                stats.rating_count,
                entity_id,
            )
        # Meetings don't have denormalized scores currently

    async def get_entity_rating(self, entity_type: str, entity_id: str) -> RatingStats:
        """Get rating statistics (avg, count, distribution) for an entity."""
        rows = await self._fetch(
            """
            SELECT rating, COUNT(*) as count
            FROM userland.ratings
            WHERE entity_type = $1 AND entity_id = $2
            GROUP BY rating
            """,
            entity_type,
            entity_id,
        )

        distribution = {i: 0 for i in range(1, 6)}
        total = 0
        weighted_sum = 0

        for row in rows:
            distribution[row["rating"]] = row["count"]
            total += row["count"]
            weighted_sum += row["rating"] * row["count"]

        avg = weighted_sum / total if total > 0 else 0.0

        return RatingStats(
            avg_rating=round(avg, 2),
            rating_count=total,
            distribution=distribution,
        )

    async def get_user_rating(
        self,
        user_id: str,
        entity_type: str,
        entity_id: str,
    ) -> Optional[int]:
        """Get user's rating (1-5) for an entity, or None if not rated."""
        row = await self._fetchrow(
            """
            SELECT rating FROM userland.ratings
            WHERE user_id = $1 AND entity_type = $2 AND entity_id = $3
            """,
            user_id,
            entity_type,
            entity_id,
        )
        return row["rating"] if row else None

    async def report_issue(
        self,
        user_id: Optional[str],
        session_id: Optional[str],
        entity_type: str,
        entity_id: str,
        issue_type: str,
        description: str,
    ) -> Optional[int]:
        """Report an issue with a summary. Returns issue ID or None if validation fails."""
        if not user_id and not session_id:
            logger.warning("issue rejected - no user or session")
            return None

        valid_types = {"inaccurate", "incomplete", "misleading", "offensive", "other"}
        if issue_type not in valid_types:
            logger.warning("issue rejected - invalid type", issue_type=issue_type)
            return None

        row = await self._fetchrow(
            """
            INSERT INTO userland.issues
                (user_id, session_id, entity_type, entity_id, issue_type, description)
            VALUES ($1, $2, $3, $4, $5, $6)
            RETURNING id
            """,
            user_id,
            session_id,
            entity_type,
            entity_id,
            issue_type,
            description,
        )
        if not row:
            return None
        issue_id = row["id"]

        logger.info(
            "issue reported",
            issue_id=issue_id,
            entity_type=entity_type,
            entity_id=entity_id,
            issue_type=issue_type,
        )
        return issue_id

    async def get_open_issues(self, limit: int = 100) -> list[Issue]:
        """Get unresolved issues for admin review."""
        rows = await self._fetch(
            """
            SELECT id, user_id, session_id, entity_type, entity_id,
                   issue_type, description, status, admin_notes,
                   created_at, resolved_at
            FROM userland.issues
            WHERE status = 'open'
            ORDER BY created_at DESC
            LIMIT $1
            """,
            limit,
        )
        return [self._row_to_issue(row) for row in rows]

    async def get_entity_issues(
        self,
        entity_type: str,
        entity_id: str,
        status: Optional[str] = None,
    ) -> list[Issue]:
        """Get issues for a specific entity, optionally filtered by status."""
        query = """
            SELECT id, user_id, session_id, entity_type, entity_id,
                   issue_type, description, status, admin_notes,
                   created_at, resolved_at
            FROM userland.issues
            WHERE entity_type = $1 AND entity_id = $2
        """
        params = [entity_type, entity_id]
        if status:
            query += " AND status = $3"
            params.append(status)
        query += " ORDER BY created_at DESC"

        rows = await self._fetch(query, *params)
        return [self._row_to_issue(row) for row in rows]

    async def resolve_issue(
        self,
        issue_id: int,
        status: str,
        admin_notes: Optional[str] = None,
    ) -> bool:
        """Mark issue as resolved or dismissed. Returns True if updated."""
        if status not in {"resolved", "dismissed"}:
            logger.warning("invalid issue resolution status", status=status)
            return False

        result = await self._execute(
            """
            UPDATE userland.issues
            SET status = $1, admin_notes = $2, resolved_at = NOW()
            WHERE id = $3
            """,
            status,
            admin_notes,
            issue_id,
        )
        updated = result.split()[-1] != "0"

        if updated:
            logger.info("issue resolved", issue_id=issue_id, status=status)

        return updated

    async def get_low_rated_entities(
        self,
        threshold: float = 2.5,
        min_ratings: int = 3,
    ) -> list[tuple[str, str]]:
        """Get entities with low avg rating for reprocessing consideration."""
        rows = await self._fetch(
            """
            SELECT entity_type, entity_id
            FROM userland.ratings
            GROUP BY entity_type, entity_id
            HAVING AVG(rating) <= $1 AND COUNT(*) >= $2
            ORDER BY AVG(rating) ASC
            """,
            threshold,
            min_ratings,
        )
        return [(row["entity_type"], row["entity_id"]) for row in rows]

    async def get_issue_count_by_entity(
        self,
        entity_type: str,
        entity_id: str,
    ) -> int:
        """Get count of open issues for an entity."""
        row = await self._fetchrow(
            """
            SELECT COUNT(*) as count FROM userland.issues
            WHERE entity_type = $1 AND entity_id = $2 AND status = 'open'
            """,
            entity_type,
            entity_id,
        )
        return row["count"] if row else 0
