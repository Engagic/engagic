"""Vote API routes - handles vote records, tallies, and council member voting history."""

from fastapi import APIRouter, Depends

from database.db_postgres import Database
from database.vote_utils import compute_vote_tally, determine_vote_outcome
from server.dependencies import get_db
from server.metrics import metrics
from server.utils.validation import (
    require_city,
    require_council_member,
    require_matter,
    require_meeting,
)

router = APIRouter(prefix="/api")


@router.get("/matters/{matter_id}/votes")
async def get_matter_votes(matter_id: str, db: Database = Depends(get_db)):
    """Get all votes on a matter across all meetings.

    Returns individual votes and aggregate tally.
    """
    matter = await require_matter(db, matter_id)

    votes = await db.council_members.get_votes_for_matter(matter_id)
    tally = await db.council_members.get_vote_tally_for_matter(matter_id)
    outcomes = await db.matters.get_matter_vote_outcomes(matter_id)

    metrics.matter_engagement.labels(action='votes').inc()

    return {
        "success": True,
        "matter_id": matter_id,
        "matter_title": matter.title,
        "votes": [v.to_dict() for v in votes],
        "tally": tally,
        "outcomes": outcomes
    }


@router.get("/meetings/{meeting_id}/votes")
async def get_meeting_votes(meeting_id: str, db: Database = Depends(get_db)):
    """Get all votes cast in a meeting.

    Returns votes grouped by matter.
    """
    meeting = await require_meeting(db, meeting_id)

    votes = await db.council_members.get_votes_for_meeting(meeting_id)

    # Group votes by matter
    votes_by_matter: dict[str, list] = {}
    for vote in votes:
        mid = vote.matter_id
        if mid not in votes_by_matter:
            votes_by_matter[mid] = []
        votes_by_matter[mid].append(vote.to_dict())

    # Get matter details using repository (batch fetch)
    matter_ids = list(votes_by_matter.keys())
    matters_batch = await db.matters.get_matters_batch(matter_ids) if matter_ids else {}
    matters_data = {
        mid: {"title": m.title, "matter_file": m.matter_file}
        for mid, m in matters_batch.items()
    }

    # Build response grouped by matter
    matters_with_votes = []
    for mid, matter_votes in votes_by_matter.items():
        matter_info = matters_data.get(mid, {})

        # Use shared vote tally and outcome functions
        tally = compute_vote_tally(matter_votes)
        outcome = determine_vote_outcome(tally)

        matters_with_votes.append({
            "matter_id": mid,
            "matter_title": matter_info.get("title"),
            "matter_file": matter_info.get("matter_file"),
            "votes": matter_votes,
            "tally": tally,
            "outcome": outcome
        })

    return {
        "success": True,
        "meeting_id": meeting_id,
        "meeting_title": meeting.title,
        "meeting_date": meeting.date.isoformat() if meeting.date else None,
        "matters_with_votes": matters_with_votes,
        "total": len(votes)
    }


@router.get("/council-members/{member_id}/votes")
async def get_member_votes(
    member_id: str,
    limit: int = 100,
    db: Database = Depends(get_db)
):
    """Get voting record for a council member.

    Returns recent votes with matter context.
    """
    member = await require_council_member(db, member_id)

    voting_record = await db.council_members.get_member_voting_record(member_id, limit=limit)

    # Compute voting statistics using shared function
    vote_counts = compute_vote_tally(voting_record)

    return {
        "success": True,
        "member": member.to_dict(),
        "voting_record": voting_record,
        "total": len(voting_record),
        "statistics": vote_counts
    }


@router.get("/city/{banana}/council-members")
async def get_city_council(banana: str, db: Database = Depends(get_db)):
    """Get city council roster with vote counts.

    Returns all council members for a city.
    """
    city = await require_city(db, banana)

    members = await db.council_members.get_members_by_city(banana)

    return {
        "success": True,
        "city_name": city.name,
        "state": city.state,
        "banana": banana,
        "council_members": [m.to_dict() for m in members],
        "total": len(members)
    }
