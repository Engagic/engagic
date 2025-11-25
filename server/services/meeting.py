"""
Meeting service layer

Handles meeting retrieval with items attached
"""

from typing import Dict, Any, List
from database.db_postgres import Database
from database.models import Meeting

from config import get_logger

logger = get_logger(__name__)


async def get_meeting_with_items(meeting: Meeting, db: Database) -> Dict[str, Any]:
    """Convert meeting to dict with items attached

    This pattern is used in 5+ places throughout the API,
    consolidating into a single service function.

    Only sets has_items=True if items have summaries, allowing
    meetings with unsummarized items to fall back to monolithic summary.

    Eagerly loads Matter objects for items so frontend can display
    matter timeline (e.g., "this bill appeared 3 times").
    """
    meeting_dict = meeting.to_dict()
    items = await db.get_agenda_items(meeting.id, load_matters=True)
    if items:
        items_with_summaries = [item for item in items if item.summary]
        if items_with_summaries:
            meeting_dict["items"] = [item.to_dict() for item in items]
            meeting_dict["has_items"] = True
        else:
            meeting_dict["has_items"] = False
    else:
        meeting_dict["has_items"] = False
    return meeting_dict


async def get_meetings_with_items(
    meetings: List[Meeting], db: Database
) -> List[Dict[str, Any]]:
    """Batch fetch items for all meetings - eliminates N+1

    Uses db.get_items_for_meetings() to fetch all items across all meetings
    in a single batch operation (4-5 queries total instead of N*M).

    Args:
        meetings: List of Meeting objects
        db: Database instance

    Returns:
        List of meeting dicts with items attached
    """
    if not meetings:
        return []

    meeting_ids = [m.id for m in meetings]

    # Single batch call for ALL items and matters (4-5 queries total)
    items_by_meeting = await db.get_items_for_meetings(meeting_ids, load_matters=True)

    results = []
    for meeting in meetings:
        meeting_dict = meeting.to_dict()
        items = items_by_meeting.get(meeting.id, [])

        if items:
            items_with_summaries = [item for item in items if item.summary]
            if items_with_summaries:
                meeting_dict["items"] = [item.to_dict() for item in items]
                meeting_dict["has_items"] = True
            else:
                meeting_dict["has_items"] = False
        else:
            meeting_dict["has_items"] = False

        results.append(meeting_dict)

    return results
