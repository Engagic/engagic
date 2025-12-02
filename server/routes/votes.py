"""Vote API routes - handles vote records, tallies, and council member voting history."""

from fastapi import APIRouter, HTTPException, Depends

from database.db_postgres import Database
from database.vote_utils import compute_vote_tally, determine_vote_outcome
from server.dependencies import get_db
from server.metrics import metrics

router = APIRouter(prefix="/api")


@router.get("/matters/{matter_id}/votes")
async def get_matter_votes(matter_id: str, db: Database = Depends(get_db)):
    """Get all votes on a matter across all meetings.

    Returns individual votes and aggregate tally.
    """
    matter = await db.get_matter(matter_id)
    if not matter:
        raise HTTPException(status_code=404, detail="Matter not found")

    votes = await db.council_members.get_votes_for_matter(matter_id)
    tally = await db.council_members.get_vote_tally_for_matter(matter_id)

    async with db.pool.acquire() as conn:
        appearances = await conn.fetch(
            """
            SELECT
                ma.meeting_id,
                ma.vote_outcome,
                ma.vote_tally,
                ma.appeared_at,
                m.title as meeting_title
            FROM matter_appearances ma
            JOIN meetings m ON m.id = ma.meeting_id
            WHERE ma.matter_id = $1 AND ma.vote_outcome IS NOT NULL
            ORDER BY ma.appeared_at DESC
            """,
            matter_id
        )

    metrics.matter_engagement.labels(action='votes').inc()

    return {
        "success": True,
        "matter_id": matter_id,
        "matter_title": matter.title,
        "votes": [v.to_dict() for v in votes],
        "tally": tally,
        "outcomes": [
            {
                "meeting_id": a["meeting_id"],
                "meeting_title": a["meeting_title"],
                "date": a["appeared_at"].isoformat() if a["appeared_at"] else None,
                "outcome": a["vote_outcome"],
                "tally": a["vote_tally"],
            }
            for a in appearances
        ]
    }


@router.get("/meetings/{meeting_id}/votes")
async def get_meeting_votes(meeting_id: str, db: Database = Depends(get_db)):
    """Get all votes cast in a meeting.

    Returns votes grouped by matter.
    """
    meeting = await db.meetings.get_meeting(meeting_id)
    if not meeting:
        raise HTTPException(status_code=404, detail="Meeting not found")

    votes = await db.council_members.get_votes_for_meeting(meeting_id)

    # Group votes by matter
    votes_by_matter: dict[str, list] = {}
    for vote in votes:
        mid = vote.matter_id
        if mid not in votes_by_matter:
            votes_by_matter[mid] = []
        votes_by_matter[mid].append(vote.to_dict())

    # Get matter titles for display
    matter_ids = list(votes_by_matter.keys())
    matters_data = {}
    if matter_ids:
        async with db.pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT id, title, matter_file FROM city_matters WHERE id = ANY($1::text[])",
                matter_ids
            )
            for row in rows:
                matters_data[row["id"]] = {
                    "title": row["title"],
                    "matter_file": row["matter_file"]
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
        "total_votes": len(votes)
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
    member = await db.council_members.get_member_by_id(member_id)
    if not member:
        raise HTTPException(status_code=404, detail="Council member not found")

    voting_record = await db.council_members.get_member_voting_record(member_id, limit=limit)

    # Compute voting statistics using shared function
    vote_counts = compute_vote_tally(voting_record)

    return {
        "success": True,
        "member": member.to_dict(),
        "voting_record": voting_record,
        "total_votes": len(voting_record),
        "statistics": vote_counts
    }


@router.get("/city/{banana}/council-members")
async def get_city_council(banana: str, db: Database = Depends(get_db)):
    """Get city council roster with vote counts.

    Returns all council members for a city.
    """
    city = await db.get_city(banana=banana)
    if not city:
        raise HTTPException(status_code=404, detail="City not found")

    members = await db.council_members.get_members_by_city(banana)

    return {
        "success": True,
        "city_name": city.name,
        "state": city.state,
        "banana": banana,
        "council_members": [m.to_dict() for m in members],
        "total_members": len(members)
    }
