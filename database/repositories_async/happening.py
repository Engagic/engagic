"""Async HappeningRepository for "Happening This Week" feature.

Stores Claude Code's analysis of important upcoming agenda items.
Items are ranked by importance and shown prominently on city pages.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import List, Optional

from database.repositories_async.base import BaseRepository
from config import get_logger

logger = get_logger(__name__).bind(component="happening_repository")


@dataclass
class HappeningItem:
    """A ranked important upcoming item."""
    id: int
    banana: str
    item_id: str
    meeting_id: str
    meeting_date: datetime
    rank: int
    reason: str
    created_at: datetime
    expires_at: datetime
    # Joined from items table
    item_title: Optional[str] = None
    item_summary: Optional[str] = None
    matter_file: Optional[str] = None
    # Joined from meetings table
    meeting_title: Optional[str] = None
    participation: Optional[dict] = None


class HappeningRepository(BaseRepository):
    """Repository for happening items (Claude-analyzed important upcoming items)."""

    async def get_happening_items(self, banana: str, limit: int = 10) -> List[HappeningItem]:
        """Get active happening items for a city with full context.

        Joins to items and meetings tables to include all display info.
        Only returns non-expired items, ordered by rank.
        """
        rows = await self._fetch(
            """
            SELECT
                h.id, h.banana, h.item_id, h.meeting_id, h.meeting_date,
                h.rank, h.reason, h.created_at, h.expires_at,
                i.title as item_title, i.summary as item_summary, i.matter_file,
                m.title as meeting_title, m.participation
            FROM happening_items h
            LEFT JOIN items i ON i.id = h.item_id
            LEFT JOIN meetings m ON m.id = h.meeting_id
            WHERE h.banana = $1
              AND h.expires_at > NOW()
            ORDER BY h.rank ASC
            LIMIT $2
            """,
            banana, limit
        )

        return [
            HappeningItem(
                id=row['id'],
                banana=row['banana'],
                item_id=row['item_id'],
                meeting_id=row['meeting_id'],
                meeting_date=row['meeting_date'],
                rank=row['rank'],
                reason=row['reason'],
                created_at=row['created_at'],
                expires_at=row['expires_at'],
                item_title=row['item_title'],
                item_summary=row['item_summary'],
                matter_file=row['matter_file'],
                meeting_title=row['meeting_title'],
                participation=row['participation'],
            )
            for row in rows
        ]

    async def clear_expired(self) -> int:
        """Delete expired happening items. Returns count deleted."""
        result = await self._execute(
            "DELETE FROM happening_items WHERE expires_at < NOW()"
        )
        count = self._parse_row_count(result)
        if count > 0:
            logger.info("cleared expired happening items", count=count)
        return count

    async def get_all_active(self, limit: int = 100) -> List[HappeningItem]:
        """Get all active happening items across all cities.

        Useful for debugging and monitoring.
        """
        rows = await self._fetch(
            """
            SELECT
                h.id, h.banana, h.item_id, h.meeting_id, h.meeting_date,
                h.rank, h.reason, h.created_at, h.expires_at,
                i.title as item_title, i.summary as item_summary, i.matter_file,
                m.title as meeting_title, m.participation
            FROM happening_items h
            LEFT JOIN items i ON i.id = h.item_id
            LEFT JOIN meetings m ON m.id = h.meeting_id
            WHERE h.expires_at > NOW()
            ORDER BY h.meeting_date ASC, h.rank ASC
            LIMIT $1
            """,
            limit
        )

        return [
            HappeningItem(
                id=row['id'],
                banana=row['banana'],
                item_id=row['item_id'],
                meeting_id=row['meeting_id'],
                meeting_date=row['meeting_date'],
                rank=row['rank'],
                reason=row['reason'],
                created_at=row['created_at'],
                expires_at=row['expires_at'],
                item_title=row['item_title'],
                item_summary=row['item_summary'],
                matter_file=row['matter_file'],
                meeting_title=row['meeting_title'],
                participation=row['participation'],
            )
            for row in rows
        ]

    async def get_cities_with_happening(self) -> List[str]:
        """Get list of bananas that have active happening items."""
        rows = await self._fetch(
            """
            SELECT DISTINCT banana
            FROM happening_items
            WHERE expires_at > NOW()
            ORDER BY banana
            """
        )
        return [row['banana'] for row in rows]
