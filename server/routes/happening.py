"""Happening This Week API routes.

Serves Claude Code's analysis of important upcoming agenda items.
Items are ranked by importance and include participation info for civic action.
"""

from fastapi import APIRouter, Depends
from server.dependencies import get_db
from database.db_postgres import Database

from config import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/api")


@router.get("/city/{banana}/happening")
async def get_happening_items(banana: str, limit: int = 10, db: Database = Depends(get_db)):
    """Get important upcoming items for a city.

    Returns Claude-analyzed ranked items with:
    - Item details (title, summary, matter_file)
    - Meeting context (title, datetime)
    - Participation info (email, phone, virtual meeting URL)
    - Reason why this item matters

    Items are ordered by rank (most important first).
    Only returns non-expired items (meeting hasn't passed yet).
    """
    items = await db.happening.get_happening_items(banana, limit=limit)

    return {
        "success": True,
        "banana": banana,
        "count": len(items),
        "items": [
            {
                "item_id": item.item_id,
                "meeting_id": item.meeting_id,
                "meeting_date": item.meeting_date.isoformat() if item.meeting_date else None,
                "meeting_title": item.meeting_title,
                "rank": item.rank,
                "reason": item.reason,
                "item_title": item.item_title,
                "item_summary": item.item_summary[:500] if item.item_summary else None,
                "matter_file": item.matter_file,
                "participation": item.participation,
                "expires_at": item.expires_at.isoformat() if item.expires_at else None,
            }
            for item in items
        ]
    }


@router.get("/happening/active")
async def get_all_happening(limit: int = 50, db: Database = Depends(get_db)):
    """Get all active happening items across all cities.

    Useful for monitoring and debugging the Claude analysis pipeline.
    Returns items ordered by meeting date (soonest first).
    """
    items = await db.happening.get_all_active(limit=limit)
    cities = await db.happening.get_cities_with_happening()

    return {
        "success": True,
        "cities_count": len(cities),
        "cities": cities,
        "items_count": len(items),
        "items": [
            {
                "banana": item.banana,
                "item_id": item.item_id,
                "meeting_id": item.meeting_id,
                "meeting_date": item.meeting_date.isoformat() if item.meeting_date else None,
                "meeting_title": item.meeting_title,
                "rank": item.rank,
                "reason": item.reason,
                "item_title": item.item_title,
                "created_at": item.created_at.isoformat() if item.created_at else None,
            }
            for item in items
        ]
    }
