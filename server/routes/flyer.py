"""
Flyer generation API routes

Enables civic action through printable flyers
"""

from fastapi import APIRouter, HTTPException, Depends
from fastapi.responses import HTMLResponse
from server.models.requests import FlyerRequest
from server.services.flyer import generate_meeting_flyer
from server.dependencies import get_db
from database.db_postgres import Database

from config import get_logger

logger = get_logger(__name__)


router = APIRouter(prefix="/api")


@router.post("/flyer/generate")
async def generate_flyer(
    request: FlyerRequest,
    db: Database = Depends(get_db)
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
        meeting = await db.get_meeting(str(request.meeting_id))
        if not meeting:
            raise HTTPException(status_code=404, detail="Meeting not found")

        # Fetch item if specified
        item = None
        if request.item_id:
            items = await db.get_agenda_items(str(request.meeting_id))
            item = next((i for i in items if i.id == request.item_id), None)
            if not item:
                raise HTTPException(status_code=404, detail="Agenda item not found")

        # Generate flyer HTML
        html = await generate_meeting_flyer(
            meeting=meeting,
            item=item,
            position=request.position,
            custom_message=request.custom_message,
            user_name=request.user_name,
            db=db,
            dark_mode=request.dark_mode,
        )

        logger.info(
            "generated flyer",
            meeting_id=request.meeting_id,
            item_id=request.item_id,
            position=request.position
        )

        return HTMLResponse(content=html)

    except HTTPException:
        raise
    except Exception as e:
        import traceback
        logger.error("error generating flyer", error=str(e), traceback=traceback.format_exc())
        raise HTTPException(status_code=500, detail="Error generating flyer")
