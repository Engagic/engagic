"""Repository helper functions for consistent object construction and topic fetching.

Eliminates duplication across matters.py, meetings.py, items.py repositories.
Following the pattern established in cities.py with _build_city().

Usage:
    from database.repositories_async.helpers import (
        # JSONB deserialization helpers
        deserialize_attachments,
        deserialize_metadata,
        deserialize_participation,
        deserialize_city_participation,
        # Topic fetching
        fetch_topics_for_ids,
        # Object builders
        build_matter,
        build_meeting,
        build_agenda_item,
    )
"""

from collections import defaultdict
from typing import Any, Dict, List, Optional

from database.models import (
    AgendaItem,
    AttachmentInfo,
    CityParticipation,
    Matter,
    MatterMetadata,
    Meeting,
    ParticipationInfo,
)


def deserialize_attachments(data: Any) -> List[AttachmentInfo]:
    """Deserialize JSONB attachments array to typed AttachmentInfo list.

    Args:
        data: Raw JSONB data (list of dicts) or None

    Returns:
        List of AttachmentInfo objects, empty list if data is None/empty
    """
    if not data:
        return []
    return [AttachmentInfo(**a) for a in data]


def deserialize_metadata(data: Any) -> Optional[MatterMetadata]:
    """Deserialize JSONB metadata object to typed MatterMetadata.

    Args:
        data: Raw JSONB data (dict) or None

    Returns:
        MatterMetadata object or None
    """
    if not data:
        return None
    return MatterMetadata(**data)


def deserialize_participation(data: Any) -> Optional[ParticipationInfo]:
    """Deserialize JSONB participation object to typed ParticipationInfo.

    Args:
        data: Raw JSONB data (dict) or None

    Returns:
        ParticipationInfo object or None
    """
    if not data:
        return None
    return ParticipationInfo(**data)


def deserialize_city_participation(data: Any) -> Optional[CityParticipation]:
    """Deserialize JSONB city participation object to typed CityParticipation.

    Args:
        data: Raw JSONB data (dict) or None

    Returns:
        CityParticipation object or None
    """
    if not data:
        return None
    return CityParticipation(**data)


async def fetch_topics_for_ids(
    conn,
    table: str,
    id_column: str,
    ids: List[str],
) -> Dict[str, List[str]]:
    """Batch fetch topics from a topic table, return dict mapping id -> [topics].

    Eliminates N+1 queries by fetching all topics in a single query.
    This pattern was duplicated 8+ times across repositories.

    Args:
        conn: asyncpg connection (from pool.acquire() or transaction())
        table: Topic table name ("matter_topics", "meeting_topics", "item_topics")
        id_column: Foreign key column ("matter_id", "meeting_id", "item_id")
        ids: List of entity IDs to fetch topics for

    Returns:
        Dict mapping entity_id -> list of topic strings.
        Missing IDs are simply absent from the dict (use .get(id, [])).

    Example:
        topics_map = await fetch_topics_for_ids(
            conn, "meeting_topics", "meeting_id", meeting_ids
        )
        meeting_topics = topics_map.get(meeting.id, [])
    """
    if not ids:
        return {}

    rows = await conn.fetch(
        f"SELECT {id_column}, topic FROM {table} WHERE {id_column} = ANY($1::text[])",
        list(set(ids)),  # Deduplicate
    )

    result: Dict[str, List[str]] = defaultdict(list)
    for row in rows:
        result[row[id_column]].append(row["topic"])

    return dict(result)


def build_matter(row: Any, topics: Optional[List[str]] = None) -> Matter:
    """Construct Matter from database row with JSONB deserialization.

    Centralizes the Matter construction pattern that was duplicated 3+ times.

    Args:
        row: asyncpg Record with matter columns from city_matters table
        topics: Pre-fetched topics from matter_topics table.
                If None, falls back to row["canonical_topics"].

    Returns:
        Fully constructed Matter object
    """
    # Topics: prefer pre-fetched from matter_topics, fallback to canonical_topics
    resolved_topics = topics if topics is not None else (row["canonical_topics"] or [])

    return Matter(
        id=row["id"],
        banana=row["banana"],
        matter_id=row["matter_id"],
        matter_file=row["matter_file"],
        matter_type=row["matter_type"],
        title=row["title"],
        sponsors=row["sponsors"],
        canonical_summary=row["canonical_summary"],
        canonical_topics=resolved_topics,
        attachments=deserialize_attachments(row["attachments"]),
        metadata=deserialize_metadata(row["metadata"]),
        first_seen=row["first_seen"],
        last_seen=row["last_seen"],
        appearance_count=row["appearance_count"],
        status=row["status"],
    )


def build_meeting(row: Any, topics: Optional[List[str]] = None) -> Meeting:
    """Construct Meeting from database row with JSONB deserialization.

    Centralizes the Meeting construction pattern that was duplicated 5+ times.

    Args:
        row: asyncpg Record with meeting columns from meetings table
        topics: Pre-fetched topics from meeting_topics table.
                Defaults to empty list if None.

    Returns:
        Fully constructed Meeting object
    """
    participation = deserialize_participation(row["participation"])

    return Meeting(
        id=row["id"],
        banana=row["banana"],
        title=row["title"],
        date=row["date"],
        agenda_url=row["agenda_url"],
        packet_url=row["packet_url"],
        summary=row["summary"],
        participation=participation,
        status=row["status"],
        processing_status=row["processing_status"],
        processing_method=row["processing_method"],
        processing_time=row["processing_time"],
        topics=topics or [],
    )


def build_agenda_item(row: Any, topics: Optional[List[str]] = None) -> AgendaItem:
    """Construct AgendaItem from database row with JSONB deserialization.

    Centralizes the AgendaItem construction pattern that was duplicated 4+ times.

    Args:
        row: asyncpg Record with item columns from items table
        topics: Pre-fetched topics from item_topics table.
                Defaults to empty list if None.

    Returns:
        Fully constructed AgendaItem object
    """
    attachments = deserialize_attachments(row["attachments"])
    sponsors = row["sponsors"] or []

    return AgendaItem(
        id=row["id"],
        meeting_id=row["meeting_id"],
        title=row["title"],
        sequence=row["sequence"],
        attachments=attachments,
        attachment_hash=row["attachment_hash"],
        matter_id=row["matter_id"],
        matter_file=row["matter_file"],
        matter_type=row["matter_type"],
        agenda_number=row["agenda_number"],
        sponsors=sponsors,
        summary=row["summary"],
        topics=topics or [],
    )
