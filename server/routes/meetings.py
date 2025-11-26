"""
Meeting API routes
"""

from fastapi import APIRouter, HTTPException, Depends
from server.models.requests import ProcessRequest
from server.services.meeting import get_meeting_with_items
from server.metrics import metrics
from server.dependencies import get_db
from database.db_postgres import Database

from config import get_logger

logger = get_logger(__name__)


router = APIRouter(prefix="/api")


@router.get("/meeting/{meeting_id}")
async def get_meeting(meeting_id: str, db: Database = Depends(get_db)):
    """Get a single meeting by ID - optimized endpoint to avoid fetching all city meetings"""
    try:
        # Fetch the specific meeting using db method
        meeting = await db.get_meeting(meeting_id)

        if not meeting:
            raise HTTPException(status_code=404, detail="Meeting not found")

        # Track meeting page view
        metrics.page_views.labels(page_type='meeting').inc()

        # Build response with meeting data
        meeting_dict = await get_meeting_with_items(meeting, db)

        # Get city info for context
        city = await db.get_city(banana=meeting.banana)

        return {
            "success": True,
            "meeting": meeting_dict,
            "city_name": city.name if city else None,
            "state": city.state if city else None,
            "banana": meeting.banana,
            "participation": city.participation if city else None,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error("error fetching meeting", meeting_id=meeting_id, error=str(e))
        raise HTTPException(status_code=500, detail="Error retrieving meeting")


@router.post("/process-agenda")
async def process_agenda(request: ProcessRequest, db: Database = Depends(get_db)):
    """Check if agenda has been processed - no longer processes on-demand"""
    try:
        # No cache - summary not yet available
        return {
            "success": False,
            "message": "Summary not yet available - processing in background",
            "cached": False,
            "packet_url": request.packet_url,
            "estimated_wait_minutes": 10,  # Rough estimate
        }

    except Exception as e:
        logger.error("error retrieving agenda", packet_url=request.packet_url, error=str(e))
        raise HTTPException(
            status_code=500, detail="We humbly thank you for your patience"
        )


@router.get("/random-best-meeting")
async def get_random_best_meeting():
    """Get a random high-quality meeting summary for showcasing"""
    try:
        from scripts.summary_quality_checker import SummaryQualityChecker

        checker = SummaryQualityChecker()
        random_meeting = checker.get_random_best_summary()

        if not random_meeting:
            raise HTTPException(
                status_code=404,
                detail="No high-quality meeting summaries available yet",
            )

        # Format for frontend consumption
        return {
            "status": "success",
            "meeting": {
                "id": random_meeting["id"],
                "banana": random_meeting["banana"],
                "city_url": f"/city/{random_meeting['banana']}",
                "title": random_meeting["title"],
                "date": random_meeting["date"],
                "packet_url": random_meeting["packet_url"],
                "summary": random_meeting["summary"],
                "quality_score": random_meeting["quality_score"],
            },
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error("error getting random best meeting", error=str(e))
        raise HTTPException(status_code=500, detail="Error retrieving meeting summary")


@router.get("/random-meeting-with-items")
async def get_random_meeting_with_items(db: Database = Depends(get_db)):
    """Get a random meeting that has high-quality item-level summaries"""
    try:
        result = await db.get_random_meeting_with_items()

        if not result:
            raise HTTPException(
                status_code=404,
                detail="No meetings with item summaries available yet",
            )

        return {
            "success": True,
            "meeting": result,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error("error getting random meeting with items", error=str(e))
        raise HTTPException(status_code=500, detail="Error retrieving meeting")
