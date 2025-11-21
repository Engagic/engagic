"""
Pydantic schemas for adapter outputs - runtime validation at boundaries.

These schemas validate data from vendor adapters before it enters the database.
Catches type errors early instead of failing at SQLite INSERT time.
"""

from typing import Optional, List, Dict, Any
from datetime import datetime
from pydantic import BaseModel, field_validator, ConfigDict


class AttachmentSchema(BaseModel):
    """Attachment metadata from adapter"""
    model_config = ConfigDict(extra="forbid")

    name: str
    url: str
    type: str  # pdf, doc, spreadsheet, unknown

    @field_validator("url")
    @classmethod
    def validate_url(cls, v: str) -> str:
        """Ensure URL is non-empty string"""
        if not v or not v.strip():
            raise ValueError("Attachment URL cannot be empty")
        return v.strip()


class AgendaItemSchema(BaseModel):
    """Agenda item from adapter - validates before DB storage"""
    model_config = ConfigDict(extra="allow")  # Allow adapter-specific extras

    item_id: str
    title: str
    sequence: int  # MUST be int, not string
    attachments: List[AttachmentSchema] = []
    matter_id: Optional[str] = None
    matter_file: Optional[str] = None
    matter_type: Optional[str] = None
    agenda_number: Optional[str] = None
    sponsors: Optional[List[str]] = None
    metadata: Optional[Dict[str, Any]] = None  # Vendor-specific metadata (action_name, section, etc.)

    @field_validator("sequence")
    @classmethod
    def validate_sequence(cls, v: Any) -> int:
        """Ensure sequence is integer (catches string "0" from APIs)"""
        if isinstance(v, str):
            try:
                return int(v)
            except ValueError:
                raise ValueError(f"Sequence must be integer, got string: {v}")
        return int(v)

    @field_validator("item_id", "title")
    @classmethod
    def validate_non_empty(cls, v: str) -> str:
        """Ensure required strings are non-empty"""
        if not v or not v.strip():
            raise ValueError("Field cannot be empty")
        return v.strip()


class MeetingSchema(BaseModel):
    """Meeting from adapter - validates before DB storage"""
    model_config = ConfigDict(extra="allow")  # Allow adapter-specific extras

    meeting_id: str
    title: str
    start: str  # ISO format string, NOT datetime object
    location: Optional[str] = None
    agenda_url: Optional[str] = None
    packet_url: Optional[str] = None
    items: Optional[List[AgendaItemSchema]] = None
    participation: Optional[Dict[str, Any]] = None
    meeting_status: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None

    @field_validator("start")
    @classmethod
    def validate_start_is_string(cls, v: Any) -> str:
        """Ensure start is ISO string, not datetime object"""
        if isinstance(v, datetime):
            raise ValueError(
                "Meeting 'start' must be ISO string, not datetime object. "
                "Use meeting_date.isoformat() in adapter."
            )
        if not isinstance(v, str):
            raise ValueError(f"Meeting 'start' must be string, got {type(v)}")
        # Validate it's parseable as ISO datetime
        try:
            datetime.fromisoformat(v.replace("Z", "+00:00"))
        except ValueError as e:
            raise ValueError(f"Invalid ISO datetime string: {v}") from e
        return v

    @field_validator("meeting_id", "title")
    @classmethod
    def validate_non_empty(cls, v: str) -> str:
        """Ensure required strings are non-empty"""
        if not v or not v.strip():
            raise ValueError("Field cannot be empty")
        return v.strip()

    @field_validator("items")
    @classmethod
    def validate_items(cls, v: Optional[List[AgendaItemSchema]]) -> Optional[List[AgendaItemSchema]]:
        """Validate items list if present"""
        if v is not None and not isinstance(v, list):
            raise ValueError("Items must be a list")
        return v


def validate_meeting_output(meeting_dict: Dict[str, Any]) -> MeetingSchema:
    """
    Validate adapter meeting output against schema.

    Args:
        meeting_dict: Raw meeting dict from adapter

    Returns:
        Validated MeetingSchema

    Raises:
        ValidationError: If data doesn't match schema
    """
    return MeetingSchema(**meeting_dict)


def validate_item_output(item_dict: Dict[str, Any]) -> AgendaItemSchema:
    """
    Validate adapter item output against schema.

    Args:
        item_dict: Raw item dict from adapter

    Returns:
        Validated AgendaItemSchema

    Raises:
        ValidationError: If data doesn't match schema
    """
    return AgendaItemSchema(**item_dict)
