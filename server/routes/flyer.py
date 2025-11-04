"""
Flyer generation API routes

Enables civic action through printable flyers
"""

import logging
from fastapi import APIRouter, HTTPException, Depends, Request
from fastapi.responses import HTMLResponse
from server.models.requests import FlyerRequest
from server.services.flyer import generate_meeting_flyer
from database.db import UnifiedDatabase

logger = logging.getLogger("engagic")

router = APIRouter(prefix="/api")


def get_db(request: Request) -> UnifiedDatabase:
    """Dependency to get shared database instance from app state"""
    return request.app.state.db


@router.post("/flyer/generate")
async def generate_flyer(
    request: FlyerRequest,
    db: UnifiedDatabase = Depends(get_db)
):
    """Generate printable civic action flyer

    Returns HTML ready for browser print-to-PDF.
    Users can customize position and add personal message.

    Args:
        meeting_id: ID of the meeting
        item_id: Optional agenda item ID (null = whole meeting)
        position: "support" | "oppose" | "more_info"
        custom_message: Optional message (max 500 chars)
        user_name: Optional name for signature

    Returns:
        HTML Response with print-ready flyer
    """
    try:
        # Fetch meeting
        meeting = db.get_meeting(str(request.meeting_id))
        if not meeting:
            raise HTTPException(status_code=404, detail="Meeting not found")

        # Fetch item if specified
        item = None
        if request.item_id:
            items = db.get_agenda_items(str(request.meeting_id))
            item = next((i for i in items if i.id == request.item_id), None)
            if not item:
                raise HTTPException(status_code=404, detail="Agenda item not found")

        # Generate flyer HTML
        html = generate_meeting_flyer(
            meeting=meeting,
            item=item,
            position=request.position,
            custom_message=request.custom_message,
            user_name=request.user_name,
            db=db,
        )

        logger.info(
            f"Generated flyer for meeting {request.meeting_id}, "
            f"item {request.item_id}, position {request.position}"
        )

        return HTMLResponse(content=html)

    except HTTPException:
        raise
    except Exception as e:
        import traceback
        logger.error(f"Error generating flyer: {str(e)}")
        logger.error(f"Traceback: {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail="Error generating flyer")
