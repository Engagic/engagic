"""Meeting Metadata Builder - Participation and topic aggregation"""

from collections import Counter
from typing import List, Dict, Any, Optional, TYPE_CHECKING

from config import get_logger
from parsing.participation import parse_participation_info

if TYPE_CHECKING:
    from analysis.analyzer_async import AsyncAnalyzer
    from database.models import Meeting, ParticipationInfo

logger = get_logger(__name__).bind(component="meeting_metadata")


class MeetingMetadataBuilder:
    """Builds meeting-level metadata from items and documents"""

    def __init__(self, analyzer: Optional["AsyncAnalyzer"] = None):
        self.analyzer = analyzer

    async def extract_participation_info(self, meeting: "Meeting") -> Dict[str, Any]:
        """Extract participation info from meeting agenda PDF"""
        if not self.analyzer or not meeting.agenda_url:
            return {}

        agenda_url = meeting.agenda_url
        if isinstance(agenda_url, list):
            agenda_url = agenda_url[0] if agenda_url else None

        if not agenda_url or not agenda_url.lower().endswith('.pdf'):
            if meeting.participation:
                return self._participation_to_dict(meeting.participation)
            return {}

        try:
            extraction_result = await self.analyzer.extract_pdf_async(agenda_url)
            text = extraction_result.get("text", "")[:5000]
            if text:
                participation_data = parse_participation_info(text)
                if participation_data:
                    return self._participation_to_dict(participation_data)
        except Exception as e:
            logger.warning("failed to extract participation info", meeting_id=meeting.id, error=str(e))

        return {}

    def aggregate_topics(self, processed_items: List[Dict[str, Any]]) -> List[str]:
        """Aggregate topics across items, sorted by frequency"""
        topic_counts: Counter = Counter()
        for item in processed_items:
            topics = item.get("topics", [])
            if topics:
                topic_counts.update(topics)
        return [topic for topic, _ in topic_counts.most_common()]

    def merge_participation_data(
        self,
        item_participation: List[Dict[str, Any]],
        existing: Optional["ParticipationInfo"] = None
    ) -> Optional[Dict[str, Any]]:
        """Merge participation data from multiple sources (first non-empty wins)"""
        result: Dict[str, Any] = {}
        if existing:
            result = self._participation_to_dict(existing)

        for data in item_participation:
            for key, value in data.items():
                if value and key not in result:
                    result[key] = value

        return result if result else None

    def _participation_to_dict(self, participation: "ParticipationInfo") -> Dict[str, Any]:
        """Convert ParticipationInfo model to dict"""
        if hasattr(participation, 'model_dump'):
            return participation.model_dump(exclude_none=True)
        elif hasattr(participation, 'dict'):
            return participation.dict(exclude_none=True)
        return dict(participation)
