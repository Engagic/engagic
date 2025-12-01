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

logger = get_logger(__name__)


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

    async def submit_rating(
        self,
        user_id: Optional[str],
        session_id: Optional[str],
        entity_type: str,
        entity_id: str,
        rating: int,
    ) -> bool:
        """Submit or update a rating.

        Args:
            user_id: User ID (None for anonymous)
            session_id: Session ID for anonymous rating
            entity_type: Type of entity (item, meeting, matter)
            entity_id: Entity identifier
            rating: Rating value (1-5)

        Returns:
            True if rating was created/updated
        """
        if not user_id and not session_id:
            logger.warning("rating rejected - no user or session")
            return False

        if rating < 1 or rating > 5:
            logger.warning("rating rejected - invalid value", rating=rating)
            return False

        try:
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
                # Anonymous rating - just insert (no upsert for session-based)
                await self._execute(
                    """
                    INSERT INTO userland.ratings (user_id, session_id, entity_type, entity_id, rating)
                    VALUES ($1, $2, $3, $4, $5)
                    """,
                    None,
                    session_id,
                    entity_type,
                    entity_id,
                    rating,
                )

            # Update denormalized quality score
            await self._update_quality_score(entity_type, entity_id)

            logger.info(
                "rating submitted",
                entity_type=entity_type,
                entity_id=entity_id,
                rating=rating,
                authenticated=user_id is not None,
            )
            return True

        except Exception as e:
            logger.error("failed to submit rating", error=str(e))
            return False

    async def _update_quality_score(self, entity_type: str, entity_id: str) -> None:
        """Recalculate quality score from ratings.

        Updates denormalized score on entity table for efficient queries.
        """
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
        """Get rating statistics for an entity.

        Args:
            entity_type: Type of entity
            entity_id: Entity identifier

        Returns:
            RatingStats with average, count, and distribution
        """
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
        """Get user's rating for an entity.

        Args:
            user_id: User ID
            entity_type: Type of entity
            entity_id: Entity identifier

        Returns:
            Rating value (1-5) or None if not rated
        """
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
        """Report an issue with a summary.

        Args:
            user_id: User ID (None for anonymous)
            session_id: Session ID for anonymous reporting
            entity_type: Type of entity
            entity_id: Entity identifier
            issue_type: Type of issue (inaccurate, incomplete, misleading, offensive, other)
            description: User description of the issue

        Returns:
            Issue ID or None if failed
        """
        if not user_id and not session_id:
            logger.warning("issue rejected - no user or session")
            return None

        valid_types = {"inaccurate", "incomplete", "misleading", "offensive", "other"}
        if issue_type not in valid_types:
            logger.warning("issue rejected - invalid type", issue_type=issue_type)
            return None

        try:
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
            issue_id = row["id"]

            logger.info(
                "issue reported",
                issue_id=issue_id,
                entity_type=entity_type,
                entity_id=entity_id,
                issue_type=issue_type,
            )
            return issue_id

        except Exception as e:
            logger.error("failed to report issue", error=str(e))
            return None

    async def get_open_issues(self, limit: int = 100) -> list[Issue]:
        """Get unresolved issues for admin review.

        Args:
            limit: Max issues to return

        Returns:
            List of open Issue objects
        """
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
        return [
            Issue(
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
            for row in rows
        ]

    async def get_entity_issues(
        self,
        entity_type: str,
        entity_id: str,
        status: Optional[str] = None,
    ) -> list[Issue]:
        """Get issues for a specific entity.

        Args:
            entity_type: Type of entity
            entity_id: Entity identifier
            status: Optional filter by status

        Returns:
            List of Issue objects
        """
        if status:
            rows = await self._fetch(
                """
                SELECT id, user_id, session_id, entity_type, entity_id,
                       issue_type, description, status, admin_notes,
                       created_at, resolved_at
                FROM userland.issues
                WHERE entity_type = $1 AND entity_id = $2 AND status = $3
                ORDER BY created_at DESC
                """,
                entity_type,
                entity_id,
                status,
            )
        else:
            rows = await self._fetch(
                """
                SELECT id, user_id, session_id, entity_type, entity_id,
                       issue_type, description, status, admin_notes,
                       created_at, resolved_at
                FROM userland.issues
                WHERE entity_type = $1 AND entity_id = $2
                ORDER BY created_at DESC
                """,
                entity_type,
                entity_id,
            )

        return [
            Issue(
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
            for row in rows
        ]

    async def resolve_issue(
        self,
        issue_id: int,
        status: str,
        admin_notes: Optional[str] = None,
    ) -> bool:
        """Mark issue as resolved or dismissed.

        Args:
            issue_id: Issue ID
            status: New status (resolved or dismissed)
            admin_notes: Optional notes about resolution

        Returns:
            True if issue was updated
        """
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
        """Get entities with low ratings for reprocessing consideration.

        Args:
            threshold: Maximum average rating to include
            min_ratings: Minimum number of ratings required

        Returns:
            List of (entity_type, entity_id) tuples
        """
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
        """Get count of open issues for an entity.

        Args:
            entity_type: Type of entity
            entity_id: Entity identifier

        Returns:
            Number of open issues
        """
        row = await self._fetchrow(
            """
            SELECT COUNT(*) as count FROM userland.issues
            WHERE entity_type = $1 AND entity_id = $2 AND status = 'open'
            """,
            entity_type,
            entity_id,
        )
        return row["count"] if row else 0
