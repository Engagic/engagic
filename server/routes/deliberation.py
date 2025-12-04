"""Deliberation API - opinion clustering for civic engagement

Endpoints for citizen deliberation on matters:
- Create deliberations for matters
- Submit comments with trust-based moderation
- Vote on comments (agree/disagree/pass)
- View clustering results (consensus, opinion groups)
- Moderate pending comments (owner only)
"""

from fastapi import APIRouter, Depends, HTTPException, status

from config import get_logger
from database.db_postgres import Database
from deliberation import compute_deliberation_clusters
from server.dependencies import get_current_user, get_db
from server.models.requests import (
    CommentCreateRequest,
    DeliberationCreateRequest,
    ModerateRequest,
    VoteRequest,
)
from server.routes.admin import verify_admin_token
from userland.database.models import User

logger = get_logger(__name__).bind(component="deliberation_api")

router = APIRouter(prefix="/api/v1/deliberations", tags=["deliberations"])


# -----------------------------------------------------------------------------
# Helper Functions
# -----------------------------------------------------------------------------


def _format_comment(c: dict) -> dict:
    """Format a comment dict for API response.

    Hides user_id, shows participant pseudonym and formatted timestamp.
    """
    return {
        "id": c["id"],
        "participant_number": c["participant_number"],
        "txt": c["txt"],
        "created_at": c["created_at"].isoformat() if c["created_at"] else None,
    }


# -----------------------------------------------------------------------------
# Public Endpoints
# -----------------------------------------------------------------------------


@router.get("/{deliberation_id}")
async def get_deliberation(
    deliberation_id: str,
    db: Database = Depends(get_db),
):
    """Get deliberation state and approved comments.

    Returns deliberation metadata, approved comments (with pseudonyms),
    and participation stats. Does not require authentication.
    """
    delib = await db.deliberation.get_deliberation(deliberation_id)
    if not delib:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Deliberation not found",
        )

    comments = await db.deliberation.get_comments(deliberation_id)
    stats = await db.deliberation.get_deliberation_stats(deliberation_id)

    formatted_comments = [_format_comment(c) for c in comments]

    return {
        "deliberation": {
            "id": delib["id"],
            "matter_id": delib["matter_id"],
            "topic": delib["topic"],
            "is_active": delib["is_active"],
            "created_at": delib["created_at"].isoformat() if delib.get("created_at") else None,
        },
        "comments": formatted_comments,
        "stats": stats,
    }


@router.get("/{deliberation_id}/results")
async def get_results(
    deliberation_id: str,
    db: Database = Depends(get_db),
):
    """Get clustering results for a deliberation.

    Returns cached results if available. Results include:
    - positions: 2D coordinates for each participant
    - clusters: which group each participant belongs to
    - consensus: agreement scores per comment
    - group_votes: vote tallies per cluster per comment
    """
    delib = await db.deliberation.get_deliberation(deliberation_id)
    if not delib:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Deliberation not found",
        )

    results = await db.deliberation.get_results(deliberation_id)

    if not results:
        return {"results": None, "message": "Not enough data for clustering yet"}

    return {
        "results": {
            "n_participants": results["n_participants"],
            "n_comments": results["n_comments"],
            "k": results["k"],
            "positions": results["positions"],
            "clusters": results["clusters"],
            "cluster_centers": results["cluster_centers"],
            "consensus": results["consensus"],
            "group_votes": results["group_votes"],
            "computed_at": results["computed_at"].isoformat() if results.get("computed_at") else None,
        }
    }


@router.get("/matter/{matter_id}")
async def get_deliberation_for_matter(
    matter_id: str,
    db: Database = Depends(get_db),
):
    """Get active deliberation for a matter.

    Returns the most recent active deliberation for the specified matter,
    or null if none exists.
    """
    delib = await db.deliberation.get_deliberation_for_matter(matter_id)

    if not delib:
        return {"deliberation": None}

    return {
        "deliberation": {
            "id": delib["id"],
            "matter_id": delib["matter_id"],
            "topic": delib["topic"],
            "is_active": delib["is_active"],
        }
    }


# -----------------------------------------------------------------------------
# Authenticated Endpoints
# -----------------------------------------------------------------------------


@router.post("")
async def create_deliberation(
    body: DeliberationCreateRequest,
    user: User = Depends(get_current_user),
    db: Database = Depends(get_db),
):
    """Create a new deliberation for a matter.

    Requires authentication. Only one active deliberation per matter.
    """
    # Check matter exists
    matter = await db.matters.get_matter(body.matter_id)
    if not matter:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Matter not found",
        )

    # Check for existing active deliberation
    existing = await db.deliberation.get_deliberation_for_matter(body.matter_id)
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Active deliberation already exists for this matter",
        )

    delib = await db.deliberation.create_deliberation(
        matter_id=body.matter_id,
        banana=matter.banana,
        topic=body.topic or matter.title,
    )

    logger.info(
        "created deliberation",
        deliberation_id=delib["id"],
        matter_id=body.matter_id,
        user_id=user.id,
    )

    return {"deliberation": delib}


@router.post("/{deliberation_id}/comments")
async def create_comment(
    deliberation_id: str,
    body: CommentCreateRequest,
    user: User = Depends(get_current_user),
    db: Database = Depends(get_db),
):
    """Submit a comment to a deliberation.

    Requires authentication. Comments from trusted users are auto-approved.
    First-time users have comments queued for moderation.
    """
    delib = await db.deliberation.get_deliberation(deliberation_id)
    if not delib:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Deliberation not found",
        )

    if not delib["is_active"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Deliberation is closed",
        )

    comment = await db.deliberation.create_comment(
        deliberation_id=deliberation_id,
        user_id=user.id,
        txt=body.txt,
    )

    if comment.get("error") == "duplicate":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="You already submitted this comment",
        )

    # Return status based on moderation
    is_approved = comment["mod_status"] == 1

    return {
        "comment": {
            "id": comment["id"],
            "participant_number": comment["participant_number"],
            "txt": comment["txt"],
            "is_approved": is_approved,
        },
        "message": "Comment submitted" if is_approved else "Comment pending moderation",
    }


@router.post("/{deliberation_id}/votes")
async def vote_on_comment(
    deliberation_id: str,
    body: VoteRequest,
    user: User = Depends(get_current_user),
    db: Database = Depends(get_db),
):
    """Vote on a comment.

    Requires authentication. Vote values:
    - 1: Agree
    - 0: Pass (skip/neutral)
    - -1: Disagree

    Users can change their vote by submitting again.
    """
    delib = await db.deliberation.get_deliberation(deliberation_id)
    if not delib:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Deliberation not found",
        )

    if not delib["is_active"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Deliberation is closed",
        )

    # Ensure participant is registered
    await db.deliberation.get_or_assign_participant_number(deliberation_id, user.id)

    result = await db.deliberation.record_vote(
        comment_id=body.comment_id,
        user_id=user.id,
        vote=body.vote,
    )

    if result and result.get("error") == "not_found":
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Comment not found",
        )

    return {"success": True, "vote": body.vote}


@router.get("/{deliberation_id}/my-votes")
async def get_my_votes(
    deliberation_id: str,
    user: User = Depends(get_current_user),
    db: Database = Depends(get_db),
):
    """Get current user's votes for a deliberation.

    Returns a mapping of comment_id -> vote value.
    """
    delib = await db.deliberation.get_deliberation(deliberation_id)
    if not delib:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Deliberation not found",
        )

    votes = await db.deliberation.get_user_votes(deliberation_id, user.id)

    return {"votes": votes}


# -----------------------------------------------------------------------------
# Moderation Endpoints
# -----------------------------------------------------------------------------


@router.get("/{deliberation_id}/pending")
async def get_pending_comments(
    deliberation_id: str,
    is_admin: bool = Depends(verify_admin_token),
    db: Database = Depends(get_db),
):
    """Get pending comments for moderation. Admin only."""
    delib = await db.deliberation.get_deliberation(deliberation_id)
    if not delib:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Deliberation not found",
        )

    comments = await db.deliberation.get_pending_comments(deliberation_id)

    return {"pending_comments": [_format_comment(c) for c in comments]}


@router.post("/{deliberation_id}/moderate")
async def moderate_comment(
    deliberation_id: str,
    body: ModerateRequest,
    is_admin: bool = Depends(verify_admin_token),
    db: Database = Depends(get_db),
):
    """Approve or hide a pending comment. Admin only.

    When approved, the comment becomes visible and the user is marked
    as trusted for future auto-approval.
    """
    delib = await db.deliberation.get_deliberation(deliberation_id)
    if not delib:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Deliberation not found",
        )

    success = await db.deliberation.moderate_comment(body.comment_id, body.approve)

    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Comment not found",
        )

    action = "approved" if body.approve else "hidden"
    logger.info(
        "moderated comment",
        comment_id=body.comment_id,
        action=action,
    )

    return {"success": True, "action": action}


# -----------------------------------------------------------------------------
# Clustering Trigger
# -----------------------------------------------------------------------------


@router.post("/{deliberation_id}/compute")
async def compute_clusters(
    deliberation_id: str,
    is_admin: bool = Depends(verify_admin_token),
    db: Database = Depends(get_db),
):
    """Trigger clustering computation for a deliberation. Admin only."""
    delib = await db.deliberation.get_deliberation(deliberation_id)
    if not delib:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Deliberation not found",
        )

    vote_matrix, user_ids, comment_ids = await db.deliberation.get_vote_matrix(
        deliberation_id
    )

    results = compute_deliberation_clusters(vote_matrix, user_ids, comment_ids)
    if not results:
        return {"success": False, "message": "Insufficient data for clustering"}

    # Save results
    await db.deliberation.save_results(deliberation_id, results)

    logger.info(
        "computed clusters",
        deliberation_id=deliberation_id,
        n_participants=results["n_participants"],
        n_comments=results["n_comments"],
        k=results["k"],
    )

    return {
        "success": True,
        "results": {
            "n_participants": results["n_participants"],
            "n_comments": results["n_comments"],
            "k": results["k"],
        },
    }
