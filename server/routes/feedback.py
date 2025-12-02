"""Feedback API - ratings, issue reports, quality signals.

User feedback endpoints for the closed loop architecture:
- Rate summaries (1-5 stars)
- Report issues (inaccurate, incomplete, misleading)
- Get quality stats
- Admin: review and resolve issues
"""

from typing import Optional

from fastapi import APIRouter, Cookie, Depends, HTTPException, Request
from pydantic import BaseModel

from database.db_postgres import Database
from server.dependencies import get_db, get_optional_user
from server.routes.auth import get_current_user
from userland.database.models import User

router = APIRouter(prefix="/api", tags=["feedback"])

VALID_ENTITY_TYPES = {"item", "meeting", "matter"}
VALID_ISSUE_TYPES = {"inaccurate", "incomplete", "misleading", "offensive", "other"}


class RatingRequest(BaseModel):
    """Rating submission request."""
    rating: int


class IssueRequest(BaseModel):
    """Issue report request."""
    issue_type: str
    description: str


class IssueResolutionRequest(BaseModel):
    """Admin issue resolution request."""
    status: str  # resolved or dismissed
    admin_notes: Optional[str] = None


@router.post("/rate/{entity_type}/{entity_id}")
async def rate_entity(
    entity_type: str,
    entity_id: str,
    body: RatingRequest,
    request: Request,
    session_id: Optional[str] = Cookie(default=None),
    db: Database = Depends(get_db),
):
    """Submit rating for an entity (item, meeting, matter).

    Works for both authenticated and anonymous users.
    Anonymous users must have a session_id cookie.
    """
    if entity_type not in VALID_ENTITY_TYPES:
        raise HTTPException(status_code=400, detail=f"Invalid entity type. Must be one of: {VALID_ENTITY_TYPES}")

    if body.rating < 1 or body.rating > 5:
        raise HTTPException(status_code=400, detail="Rating must be between 1 and 5")

    user = await get_optional_user(request)
    user_id = user.id if user else None

    if not user_id and not session_id:
        raise HTTPException(status_code=400, detail="Authentication or session_id cookie required")

    success = await db.feedback.submit_rating(
        user_id=user_id,
        session_id=session_id,
        entity_type=entity_type,
        entity_id=entity_id,
        rating=body.rating,
    )

    if not success:
        raise HTTPException(status_code=500, detail="Failed to submit rating")

    return {"success": True, "status": "rated"}


@router.post("/report/{entity_type}/{entity_id}")
async def report_issue(
    entity_type: str,
    entity_id: str,
    body: IssueRequest,
    request: Request,
    session_id: Optional[str] = Cookie(default=None),
    db: Database = Depends(get_db),
):
    """Report an issue with a summary.

    Works for both authenticated and anonymous users.
    Anonymous users must have a session_id cookie.
    """
    if entity_type not in VALID_ENTITY_TYPES:
        raise HTTPException(status_code=400, detail=f"Invalid entity type. Must be one of: {VALID_ENTITY_TYPES}")

    if body.issue_type not in VALID_ISSUE_TYPES:
        raise HTTPException(status_code=400, detail=f"Invalid issue type. Must be one of: {VALID_ISSUE_TYPES}")

    if not body.description or len(body.description) < 10:
        raise HTTPException(status_code=400, detail="Description must be at least 10 characters")

    if len(body.description) > 2000:
        raise HTTPException(status_code=400, detail="Description must be less than 2000 characters")

    user = await get_optional_user(request)
    user_id = user.id if user else None

    if not user_id and not session_id:
        raise HTTPException(status_code=400, detail="Authentication or session_id cookie required")

    issue_id = await db.feedback.report_issue(
        user_id=user_id,
        session_id=session_id,
        entity_type=entity_type,
        entity_id=entity_id,
        issue_type=body.issue_type,
        description=body.description,
    )

    if issue_id is None:
        raise HTTPException(status_code=500, detail="Failed to report issue")

    # Log activity for engagement tracking
    await db.engagement.log_activity(
        user_id=user_id,
        session_id=session_id,
        action="report",
        entity_type=entity_type,
        entity_id=entity_id,
        metadata={"issue_id": issue_id, "issue_type": body.issue_type},
    )

    return {"success": True, "issue_id": issue_id}


@router.get("/{entity_type}/{entity_id}/rating")
async def get_entity_rating(
    entity_type: str,
    entity_id: str,
    request: Request,
    db: Database = Depends(get_db),
):
    """Get rating statistics for an entity.

    Public endpoint - no auth required.
    If authenticated, includes user's own rating.
    """
    if entity_type not in VALID_ENTITY_TYPES:
        raise HTTPException(status_code=400, detail=f"Invalid entity type. Must be one of: {VALID_ENTITY_TYPES}")

    stats = await db.feedback.get_entity_rating(entity_type, entity_id)

    result = {
        "success": True,
        "entity_type": entity_type,
        "entity_id": entity_id,
        "avg_rating": stats.avg_rating,
        "rating_count": stats.rating_count,
        "distribution": stats.distribution,
    }

    # Include user's rating if authenticated
    user = await get_optional_user(request)
    if user:
        user_rating = await db.feedback.get_user_rating(user.id, entity_type, entity_id)
        result["user_rating"] = user_rating

    return result


@router.get("/{entity_type}/{entity_id}/issues")
async def get_entity_issues(
    entity_type: str,
    entity_id: str,
    status: Optional[str] = None,
    db: Database = Depends(get_db),
):
    """Get issues reported for an entity.

    Public endpoint for transparency.
    """
    issues = await db.feedback.get_entity_issues(entity_type, entity_id, status)
    issue_count = await db.feedback.get_issue_count_by_entity(entity_type, entity_id)

    return {
        "success": True,
        "entity_type": entity_type,
        "entity_id": entity_id,
        "open_issue_count": issue_count,
        "issues": [
            {
                "id": i.id,
                "issue_type": i.issue_type,
                "description": i.description,
                "status": i.status,
                "created_at": i.created_at.isoformat(),
                "resolved_at": i.resolved_at.isoformat() if i.resolved_at else None,
            }
            for i in issues
        ],
    }


@router.get("/admin/issues")
async def get_open_issues(
    limit: int = 100,
    user: User = Depends(get_current_user),
    db: Database = Depends(get_db),
):
    """Get unresolved issues for admin review.

    Requires authentication. Admin role enforcement deferred to userland.
    """
    issues = await db.feedback.get_open_issues(limit)

    return {
        "success": True,
        "issues": [
            {
                "id": i.id,
                "entity_type": i.entity_type,
                "entity_id": i.entity_id,
                "issue_type": i.issue_type,
                "description": i.description,
                "status": i.status,
                "created_at": i.created_at.isoformat(),
                "user_id": i.user_id,
            }
            for i in issues
        ],
        "total": len(issues),
    }


@router.post("/admin/issues/{issue_id}/resolve")
async def resolve_issue(
    issue_id: int,
    body: IssueResolutionRequest,
    user: User = Depends(get_current_user),
    db: Database = Depends(get_db),
):
    """Mark issue as resolved or dismissed.

    Requires authentication. Admin role enforcement deferred to userland.
    """
    if body.status not in {"resolved", "dismissed"}:
        raise HTTPException(status_code=400, detail="Status must be 'resolved' or 'dismissed'")

    success = await db.feedback.resolve_issue(
        issue_id=issue_id,
        status=body.status,
        admin_notes=body.admin_notes,
    )

    if not success:
        raise HTTPException(status_code=404, detail="Issue not found")

    return {"success": True, "status": body.status}


@router.get("/admin/low-rated")
async def get_low_rated_entities(
    threshold: float = 2.5,
    min_ratings: int = 3,
    user: User = Depends(get_current_user),
    db: Database = Depends(get_db),
):
    """Get entities with low ratings for reprocessing consideration.

    Requires authentication. Admin role enforcement deferred to userland.
    """
    entities = await db.feedback.get_low_rated_entities(threshold, min_ratings)

    return {
        "success": True,
        "threshold": threshold,
        "min_ratings": min_ratings,
        "entities": [
            {"entity_type": e[0], "entity_id": e[1]}
            for e in entities
        ],
        "total": len(entities),
    }
