"""
Meeting service layer

Handles meeting retrieval with items attached
"""

from typing import Dict, Any, List
from database.db import UnifiedDatabase, Meeting


def get_meeting_with_items(meeting: Meeting, db: UnifiedDatabase) -> Dict[str, Any]:
    """Convert meeting to dict with items attached

    This pattern is used in 5+ places throughout the API,
    consolidating into a single service function.
    """
    meeting_dict = meeting.to_dict()
    items = db.get_agenda_items(meeting.id)
    if items:
        meeting_dict["items"] = [item.to_dict() for item in items]
        meeting_dict["has_items"] = True
    else:
        meeting_dict["has_items"] = False
    return meeting_dict


def get_meetings_with_items(
    meetings: List[Meeting], db: UnifiedDatabase
) -> List[Dict[str, Any]]:
    """Batch version of get_meeting_with_items"""
    return [get_meeting_with_items(m, db) for m in meetings]
