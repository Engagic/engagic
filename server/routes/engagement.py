"""Engagement API - watches, activity tracking, trending.

User engagement endpoints for the closed loop architecture:
- Watch/unwatch entities (matters, meetings, topics, cities, council members)
- Get user's watch list
- Get trending matters
- Social proof (watch counts)
"""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, Cookie

from database.db_postgres import Database
from server.dependencies import get_current_user, get_db, get_optional_user
from userland.database.models import User

router = APIRouter(prefix="/api", tags=["engagement"])

VALID_ENTITY_TYPES = {"matter", "meeting", "topic", "city", "council_member"}


@router.post("/watch/{entity_type}/{entity_id}")
async def watch_entity(
    entity_type: str,
    entity_id: str,
    user: User = Depends(get_current_user),
    db: Database = Depends(get_db),
):
    """Add entity to user's watch list.

    Requires authentication.
    """
    if entity_type not in VALID_ENTITY_TYPES:
        raise HTTPException(status_code=400, detail=f"Invalid entity type. Must be one of: {VALID_ENTITY_TYPES}")

    success = await db.engagement.watch(user.id, entity_type, entity_id)
    return {"success": success, "status": "watching"}


@router.delete("/watch/{entity_type}/{entity_id}")
async def unwatch_entity(
    entity_type: str,
    entity_id: str,
    user: User = Depends(get_current_user),
    db: Database = Depends(get_db),
):
    """Remove entity from user's watch list.

    Requires authentication.
    """
    if entity_type not in VALID_ENTITY_TYPES:
        raise HTTPException(status_code=400, detail=f"Invalid entity type. Must be one of: {VALID_ENTITY_TYPES}")

    success = await db.engagement.unwatch(user.id, entity_type, entity_id)
    return {"success": success, "status": "unwatched"}


@router.get("/me/watching")
async def get_user_watches(
    entity_type: Optional[str] = None,
    user: User = Depends(get_current_user),
    db: Database = Depends(get_db),
):
    """Get user's watched entities.

    Requires authentication.
    Optional filter by entity_type.
    """
    if entity_type and entity_type not in VALID_ENTITY_TYPES:
        raise HTTPException(status_code=400, detail=f"Invalid entity type. Must be one of: {VALID_ENTITY_TYPES}")

    watches = await db.engagement.get_user_watches(user.id, entity_type)
    return {
        "success": True,
        "watches": [
            {
                "id": w.id,
                "entity_type": w.entity_type,
                "entity_id": w.entity_id,
                "created_at": w.created_at.isoformat(),
            }
            for w in watches
        ],
        "total": len(watches),
    }


@router.get("/trending/matters")
async def get_trending_matters(
    limit: int = 20,
    db: Database = Depends(get_db),
):
    """Get trending matters based on engagement.

    Public endpoint - no auth required.
    """
    if limit < 1 or limit > 100:
        limit = 20

    trending = await db.engagement.get_trending_matters(limit)

    # Batch fetch matter details (single query instead of N)
    matter_ids = [item.matter_id for item in trending]
    matters = await db.matters.get_matters_batch(matter_ids) if matter_ids else {}

    result = [
        {
            "matter_id": item.matter_id,
            "engagement": item.engagement,
            "unique_users": item.unique_users,
            "title": matters[item.matter_id].title if item.matter_id in matters else None,
            "status": matters[item.matter_id].status if item.matter_id in matters else None,
        }
        for item in trending
    ]

    return {"success": True, "trending": result}


@router.get("/matters/{matter_id}/engagement")
async def get_matter_engagement(
    matter_id: str,
    request: Request,
    db: Database = Depends(get_db),
):
    """Get engagement stats for a matter.

    Returns watch count and (if authenticated) whether user is watching.
    """
    user = await get_optional_user(request)

    watch_count = await db.engagement.get_watch_count("matter", matter_id)

    is_watching = False
    if user:
        is_watching = await db.engagement.is_watching(user.id, "matter", matter_id)

    return {
        "success": True,
        "matter_id": matter_id,
        "watch_count": watch_count,
        "is_watching": is_watching,
    }


@router.get("/meetings/{meeting_id}/engagement")
async def get_meeting_engagement(
    meeting_id: str,
    request: Request,
    db: Database = Depends(get_db),
):
    """Get engagement stats for a meeting.

    Returns watch count and (if authenticated) whether user is watching.
    """
    user = await get_optional_user(request)

    watch_count = await db.engagement.get_watch_count("meeting", meeting_id)

    is_watching = False
    if user:
        is_watching = await db.engagement.is_watching(user.id, "meeting", meeting_id)

    return {
        "success": True,
        "meeting_id": meeting_id,
        "watch_count": watch_count,
        "is_watching": is_watching,
    }


@router.post("/activity/view/{entity_type}/{entity_id}")
async def log_view(
    entity_type: str,
    entity_id: str,
    request: Request,
    session_id: Optional[str] = Cookie(default=None),
    db: Database = Depends(get_db),
):
    """Log a page view for analytics.

    Works for both authenticated and anonymous users.
    """
    if entity_type not in VALID_ENTITY_TYPES:
        raise HTTPException(status_code=400, detail=f"Invalid entity type. Must be one of: {VALID_ENTITY_TYPES}")

    user = await get_optional_user(request)
    user_id = user.id if user else None

    await db.engagement.log_activity(
        user_id=user_id,
        session_id=session_id,
        action="view",
        entity_type=entity_type,
        entity_id=entity_id,
    )

    return {"success": True}


@router.post("/activity/search")
async def log_search(
    request: Request,
    query: str,
    session_id: Optional[str] = Cookie(default=None),
    db: Database = Depends(get_db),
):
    """Log a search query for analytics.

    Works for both authenticated and anonymous users.
    """
    user = await get_optional_user(request)
    user_id = user.id if user else None

    await db.engagement.log_activity(
        user_id=user_id,
        session_id=session_id,
        action="search",
        entity_type="search",
        entity_id=None,
        metadata={"query": query},
    )

    return {"success": True}
