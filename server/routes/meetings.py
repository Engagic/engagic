"""
Meeting API routes
"""

import sys
import os
from fastapi import APIRouter, HTTPException, Depends, Request
from server.models.requests import ProcessRequest
from server.services.meeting import get_meeting_with_items
from server.metrics import metrics
from database.db import UnifiedDatabase

from config import get_logger

logger = get_logger(__name__).bind(component="api")


router = APIRouter(prefix="/api")


def get_db(request: Request) -> UnifiedDatabase:
    """Dependency to get shared database instance from app state"""
    return request.app.state.db


@router.get("/meeting/{meeting_id}")
async def get_meeting(meeting_id: str, db: UnifiedDatabase = Depends(get_db)):
    """Get a single meeting by ID - optimized endpoint to avoid fetching all city meetings"""
    try:
        # Fetch the specific meeting using db method
        meeting = db.get_meeting(meeting_id)

        if not meeting:
            raise HTTPException(status_code=404, detail="Meeting not found")

        # Track meeting page view
        metrics.page_views.labels(page_type='meeting').inc()

        # Build response with meeting data
        meeting_dict = get_meeting_with_items(meeting, db)

        # Get city info for context
        city = db.get_city(banana=meeting.banana)

        return {
            "success": True,
            "meeting": meeting_dict,
            "city_name": city.name if city else None,
            "state": city.state if city else None,
            "banana": meeting.banana,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching meeting {meeting_id}: {str(e)}")
        raise HTTPException(status_code=500, detail="Error retrieving meeting")


@router.post("/process-agenda")
async def process_agenda(request: ProcessRequest, db: UnifiedDatabase = Depends(get_db)):
    """Get cached agenda summary - no longer processes on-demand"""
    try:
        # Check for cached summary
        cached_summary = db.get_cached_summary(request.packet_url)

        if cached_summary:
            return {
                "success": True,
                "summary": cached_summary.summary,
                "processing_time_seconds": cached_summary.processing_time or 0,
                "cached": True,
                "meeting_data": cached_summary.to_dict(),
            }

        # No cached summary available
        return {
            "success": False,
            "message": "Summary not yet available - processing in background",
            "cached": False,
            "packet_url": request.packet_url,
            "estimated_wait_minutes": 10,  # Rough estimate
        }

    except Exception as e:
        logger.error(f"Error retrieving agenda for {request.packet_url}: {str(e)}")
        raise HTTPException(
            status_code=500, detail="We humbly thank you for your patience"
        )


@router.get("/random-best-meeting")
async def get_random_best_meeting():
    """Get a random high-quality meeting summary for showcasing"""
    try:
        # Import the quality checker
        sys.path.insert(
            0,
            os.path.dirname(
                os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            ),
        )
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
        logger.error(f"Error getting random best meeting: {str(e)}")
        raise HTTPException(status_code=500, detail="Error retrieving meeting summary")


@router.get("/random-meeting-with-items")
async def get_random_meeting_with_items(db: UnifiedDatabase = Depends(get_db)):
    """Get a random meeting that has high-quality item-level summaries"""
    try:
        result = db.get_random_meeting_with_items()

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
        logger.error(f"Error getting random meeting with items: {str(e)}")
        raise HTTPException(status_code=500, detail="Error retrieving meeting")
