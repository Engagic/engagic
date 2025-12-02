"""Engagement repository - watches, activity logging, trending.

Handles user engagement tracking for the closed loop architecture:
- Watches: Users following matters, meetings, topics, cities, council members
- Activity: Anonymous and authenticated views, actions, searches
- Trending: Materialized view of hot content
"""

import asyncpg
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from config import get_logger
from database.repositories_async.base import BaseRepository

logger = get_logger(__name__)


@dataclass
class Watch:
    """User watch record."""
    id: int
    user_id: str
    entity_type: str
    entity_id: str
    created_at: datetime


@dataclass
class TrendingMatter:
    """Trending matter from materialized view."""
    matter_id: str
    engagement: int
    unique_users: int


class EngagementRepository(BaseRepository):
    """Repository for user engagement operations."""

    async def watch(self, user_id: str, entity_type: str, entity_id: str) -> bool:
        """Add entity to user's watch list. Returns True if created, False if already watching."""
        row = await self._fetchrow(
            """
            INSERT INTO userland.watches (user_id, entity_type, entity_id)
            VALUES ($1, $2, $3)
            ON CONFLICT (user_id, entity_type, entity_id) DO NOTHING
            RETURNING id
            """,
            user_id,
            entity_type,
            entity_id,
        )
        created = row is not None
        if created:
            await self.log_activity(user_id, None, "watch", entity_type, entity_id)
            logger.info("user watching entity", user_id=user_id, entity_type=entity_type, entity_id=entity_id)
        return created

    async def unwatch(self, user_id: str, entity_type: str, entity_id: str) -> bool:
        """Remove entity from user's watch list. Returns True if removed."""
        result = await self._execute(
            """
            DELETE FROM userland.watches
            WHERE user_id = $1 AND entity_type = $2 AND entity_id = $3
            """,
            user_id,
            entity_type,
            entity_id,
        )
        deleted = result.split()[-1] != "0"
        if deleted:
            await self.log_activity(user_id, None, "unwatch", entity_type, entity_id)
            logger.info("user unwatched entity", user_id=user_id, entity_type=entity_type, entity_id=entity_id)
        return deleted

    async def get_watch_count(self, entity_type: str, entity_id: str) -> int:
        """Count users watching an entity."""
        row = await self._fetchrow(
            """
            SELECT COUNT(*) as count FROM userland.watches
            WHERE entity_type = $1 AND entity_id = $2
            """,
            entity_type,
            entity_id,
        )
        return row["count"] if row else 0

    async def is_watching(self, user_id: str, entity_type: str, entity_id: str) -> bool:
        """Check if user is watching an entity."""
        row = await self._fetchrow(
            """
            SELECT 1 FROM userland.watches
            WHERE user_id = $1 AND entity_type = $2 AND entity_id = $3
            """,
            user_id,
            entity_type,
            entity_id,
        )
        return row is not None

    async def get_user_watches(self, user_id: str, entity_type: Optional[str] = None) -> list[Watch]:
        """Get all entities a user is watching, optionally filtered by type."""
        if entity_type:
            rows = await self._fetch(
                """
                SELECT id, user_id, entity_type, entity_id, created_at
                FROM userland.watches
                WHERE user_id = $1 AND entity_type = $2
                ORDER BY created_at DESC
                """,
                user_id,
                entity_type,
            )
        else:
            rows = await self._fetch(
                """
                SELECT id, user_id, entity_type, entity_id, created_at
                FROM userland.watches
                WHERE user_id = $1
                ORDER BY created_at DESC
                """,
                user_id,
            )
        return [
            Watch(
                id=row["id"],
                user_id=row["user_id"],
                entity_type=row["entity_type"],
                entity_id=row["entity_id"],
                created_at=row["created_at"],
            )
            for row in rows
        ]

    async def get_watchers(self, entity_type: str, entity_id: str, limit: int = 100) -> list[str]:
        """Get user IDs watching an entity."""
        rows = await self._fetch(
            """
            SELECT user_id FROM userland.watches
            WHERE entity_type = $1 AND entity_id = $2
            ORDER BY created_at DESC
            LIMIT $3
            """,
            entity_type,
            entity_id,
            limit,
        )
        return [row["user_id"] for row in rows]

    async def log_activity(
        self,
        user_id: Optional[str],
        session_id: Optional[str],
        action: str,
        entity_type: str,
        entity_id: Optional[str] = None,
        metadata: Optional[dict] = None,
    ) -> None:
        """Record user activity for analytics and trending."""
        await self._execute(
            """
            INSERT INTO userland.activity_log
                (user_id, session_id, action, entity_type, entity_id, metadata)
            VALUES ($1, $2, $3, $4, $5, $6)
            """,
            user_id,
            session_id,
            action,
            entity_type,
            entity_id,
            metadata,
        )

    async def get_trending_matters(self, limit: int = 20) -> list[TrendingMatter]:
        """Get trending matters from materialized view, ordered by engagement."""
        rows = await self._fetch(
            "SELECT matter_id, engagement, unique_users FROM userland.trending_matters LIMIT $1",
            limit,
        )
        return [
            TrendingMatter(
                matter_id=row["matter_id"],
                engagement=row["engagement"],
                unique_users=row["unique_users"],
            )
            for row in rows
        ]

    async def refresh_trending(self) -> None:
        """Refresh trending materialized view (called every 15 min by daemon)."""
        try:
            await self._execute("REFRESH MATERIALIZED VIEW CONCURRENTLY userland.trending_matters")
            logger.info("refreshed trending materialized view")
        except asyncpg.PostgresError as e:
            # May fail if view doesn't exist yet or no unique index
            logger.warning("failed to refresh trending view", error=str(e))
