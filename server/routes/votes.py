"""Vote API routes - handles vote records, tallies, and council member voting history."""

from fastapi import APIRouter, HTTPException, Depends

from config import get_logger
from database.db_postgres import Database
from server.dependencies import get_db
from server.metrics import metrics

logger = get_logger(__name__)

router = APIRouter(prefix="/api")


@router.get("/matters/{matter_id}/votes")
async def get_matter_votes(matter_id: str, db: Database = Depends(get_db)):
    """Get all votes on a matter across all meetings

    Returns individual votes and aggregate tally.
    """
    try:
        # Verify matter exists
        matter = await db.get_matter(matter_id)
        if not matter:
            raise HTTPException(status_code=404, detail="Matter not found")

        # Get votes
        votes = await db.council_members.get_votes_for_matter(matter_id)
        tally = await db.council_members.get_vote_tally_for_matter(matter_id)

        # Get vote outcomes from matter_appearances
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

    except HTTPException:
        raise
    except Exception as e:
        logger.error("error fetching matter votes", matter_id=matter_id, error=str(e))
        raise HTTPException(status_code=500, detail="Error retrieving matter votes")


@router.get("/meetings/{meeting_id}/votes")
async def get_meeting_votes(meeting_id: str, db: Database = Depends(get_db)):
    """Get all votes cast in a meeting

    Returns votes grouped by matter.
    """
    try:
        # Verify meeting exists
        meeting = await db.meetings.get_meeting(meeting_id)
        if not meeting:
            raise HTTPException(status_code=404, detail="Meeting not found")

        # Get all votes for this meeting
        votes = await db.council_members.get_votes_for_meeting(meeting_id)

        # Group votes by matter
        votes_by_matter = {}
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

            # Compute tally for this matter in this meeting
            tally = {"yes": 0, "no": 0, "abstain": 0, "absent": 0}
            for v in matter_votes:
                vote_value = v.get("vote", "absent")
                if vote_value in tally:
                    tally[vote_value] += 1
                else:
                    tally["absent"] += 1

            # Determine outcome
            if tally["yes"] > tally["no"]:
                outcome = "passed"
            elif tally["no"] > tally["yes"]:
                outcome = "failed"
            elif tally["yes"] == 0 and tally["no"] == 0:
                outcome = "no_vote"
            else:
                outcome = "tabled"

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

    except HTTPException:
        raise
    except Exception as e:
        logger.error("error fetching meeting votes", meeting_id=meeting_id, error=str(e))
        raise HTTPException(status_code=500, detail="Error retrieving meeting votes")


@router.get("/council-members/{member_id}/votes")
async def get_member_votes(
    member_id: str,
    limit: int = 100,
    db: Database = Depends(get_db)
):
    """Get voting record for a council member

    Returns recent votes with matter context.
    """
    try:
        # Get member info
        member = await db.council_members.get_member_by_id(member_id)
        if not member:
            raise HTTPException(status_code=404, detail="Council member not found")

        # Get voting record (already includes matter info)
        voting_record = await db.council_members.get_member_voting_record(member_id, limit=limit)

        # Compute voting statistics
        vote_counts = {"yes": 0, "no": 0, "abstain": 0, "absent": 0}
        for v in voting_record:
            vote_value = v.get("vote", "absent")
            if vote_value in vote_counts:
                vote_counts[vote_value] += 1
            else:
                vote_counts["absent"] += 1

        return {
            "success": True,
            "member": member.to_dict(),
            "voting_record": voting_record,
            "total_votes": len(voting_record),
            "statistics": vote_counts
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error("error fetching member votes", member_id=member_id, error=str(e))
        raise HTTPException(status_code=500, detail="Error retrieving member voting record")


@router.get("/city/{banana}/council-members")
async def get_city_council(banana: str, db: Database = Depends(get_db)):
    """Get city council roster with vote counts

    Returns all council members for a city.
    """
    try:
        # Verify city exists
        city = await db.get_city(banana=banana)
        if not city:
            raise HTTPException(status_code=404, detail="City not found")

        # Get council members
        members = await db.council_members.get_members_by_city(banana)

        return {
            "success": True,
            "city_name": city.name,
            "state": city.state,
            "banana": banana,
            "council_members": [m.to_dict() for m in members],
            "total_members": len(members)
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error("error fetching city council", banana=banana, error=str(e))
        raise HTTPException(status_code=500, detail="Error retrieving city council")
