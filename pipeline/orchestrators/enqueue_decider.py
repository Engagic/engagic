"""Enqueue Decider - Determines if meetings need processing"""

from datetime import datetime
from typing import Optional, List, TYPE_CHECKING

if TYPE_CHECKING:
    from database.models import Meeting, AgendaItem

QUEUE_PRIORITY_BASE_SCORE = 150


class EnqueueDecider:
    """Decides if meetings should be enqueued for processing"""

    def should_enqueue(
        self,
        meeting: "Meeting",
        agenda_items: List["AgendaItem"],
        has_items: bool
    ) -> tuple[bool, Optional[str]]:
        """Determine if meeting should be enqueued for processing

        Returns (should_enqueue, skip_reason) tuple.
        """
        # Check for item-level summaries (golden path)
        if has_items and agenda_items:
            items_with_summaries = [item for item in agenda_items if item.summary]
            if items_with_summaries and len(items_with_summaries) == len(agenda_items):
                return False, f"all {len(agenda_items)} items already have summaries"

        # Check for monolithic summary (fallback path)
        if meeting.summary:
            return False, "meeting already has summary (monolithic)"

        return True, None

    def calculate_priority(self, meeting_date: Optional[datetime]) -> int:
        """Calculate queue priority based on meeting date proximity (0-150)"""
        if meeting_date:
            now = datetime.now(meeting_date.tzinfo) if meeting_date.tzinfo else datetime.now()
            days_distance = abs((meeting_date - now).days)
        else:
            days_distance = 999
        return max(0, QUEUE_PRIORITY_BASE_SCORE - days_distance)
