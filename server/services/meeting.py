"""
Meeting service layer

Handles meeting retrieval with items attached
"""

from typing import Dict, Any, List
from database.db import UnifiedDatabase, Meeting

from config import get_logger

logger = get_logger(__name__).bind(component="api")


def get_meeting_with_items(meeting: Meeting, db: UnifiedDatabase) -> Dict[str, Any]:
    """Convert meeting to dict with items attached

    This pattern is used in 5+ places throughout the API,
    consolidating into a single service function.

    Only sets has_items=True if items have summaries, allowing
    meetings with unsummarized items to fall back to monolithic summary.

    Eagerly loads Matter objects for items so frontend can display
    matter timeline (e.g., "this bill appeared 3 times").
    """
    meeting_dict = meeting.to_dict()
    items = db.get_agenda_items(meeting.id, load_matters=True)
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


def get_meetings_with_items(
    meetings: List[Meeting], db: UnifiedDatabase
) -> List[Dict[str, Any]]:
    """Batch version of get_meeting_with_items"""
    return [get_meeting_with_items(m, db) for m in meetings]
