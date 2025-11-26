"""
Database Models for Engagic

Pydantic dataclasses with runtime validation for core entities.
"""


from typing import Optional, List
from datetime import datetime
from pydantic import BaseModel, ConfigDict
from pydantic.dataclasses import dataclass
from dataclasses import asdict

from config import get_logger

logger = get_logger(__name__).bind(component="engagic")


# --- JSONB Pydantic Models (for typed serialization/deserialization) ---


class EmailContext(BaseModel):
    """Email with inferred purpose"""
    model_config = ConfigDict(extra="forbid")
    address: str
    purpose: str = "general contact"


class StreamingUrl(BaseModel):
    """Streaming platform URL"""
    model_config = ConfigDict(extra="forbid")
    url: Optional[str] = None
    platform: str
    channel: Optional[str] = None  # For cable TV


class ParticipationInfo(BaseModel):
    """
    Typed JSONB for meetings.participation field.

    Extracted from PDF text before AI summarization.
    Provides structured contact info for civic engagement.
    """
    model_config = ConfigDict(extra="forbid")

    email: Optional[str] = None  # Primary contact email
    emails: Optional[List[EmailContext]] = None  # All emails with context
    phone: Optional[str] = None  # Normalized phone (+1XXXXXXXXXX)
    virtual_url: Optional[str] = None  # Zoom/Teams/Meet URL
    meeting_id: Optional[str] = None  # Zoom meeting ID
    is_hybrid: Optional[bool] = None  # In-person + virtual
    is_virtual_only: Optional[bool] = None  # Virtual only
    streaming_urls: Optional[List[StreamingUrl]] = None  # YouTube, cable, etc.


class CityParticipation(BaseModel):
    """
    Typed JSONB for cities.participation field.

    City-level participation config for centralized testimony processes.
    When set, replaces meeting-level participation for testimony/contact info.
    Cities like NYC have a single testimony portal for all committees.
    """
    model_config = ConfigDict(extra="ignore")  # Allow future fields without breaking

    testimony_url: Optional[str] = None    # Portal to submit testimony (council.nyc.gov/testify/)
    testimony_email: Optional[str] = None  # Official testimony email (testimony@council.nyc.gov)
    process_url: Optional[str] = None      # Link to "how to testify" instructions


class MatterMetadata(BaseModel):
    """
    Typed JSONB for city_matters.metadata field.

    Contains attachment_hash for change detection and deduplication.
    """
    model_config = ConfigDict(extra="forbid")
    attachment_hash: Optional[str] = None


class AttachmentInfo(BaseModel):
    """
    Typed JSONB for attachments arrays (items.attachments, city_matters.attachments).

    Mirrors vendors.schemas.AttachmentSchema but used for DB fields.
    """
    model_config = ConfigDict(extra="forbid")
    name: str
    url: str
    type: str  # pdf, doc, spreadsheet, unknown
    history_id: Optional[str] = None  # PrimeGov-specific


# --- Domain Dataclasses (with runtime validation) ---


@dataclass
class City:
    """City entity - single source of truth"""

    banana: str  # Primary key: paloaltoCA (derived)
    name: str  # Palo Alto
    state: str  # CA
    vendor: str  # primegov, legistar, granicus, etc.
    slug: str  # cityofpaloalto (vendor-specific)
    county: Optional[str] = None
    status: str = "active"
    participation: Optional[CityParticipation] = None
    zipcodes: Optional[List[str]] = None  # Associated ZIP codes
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization"""
        data = asdict(self)
        if self.created_at:
            data["created_at"] = self.created_at.isoformat()
        if self.updated_at:
            data["updated_at"] = self.updated_at.isoformat()
        if self.participation:
            data["participation"] = self.participation.model_dump(exclude_none=True)
        return data



@dataclass
class Meeting:
    """Meeting entity with optional summary

    URL Architecture (ONE OR THE OTHER):
    - agenda_url: HTML page to view (item-based meetings with extracted items)
    - packet_url: PDF file to download (monolithic meetings, fallback processing)
    """

    id: str  # Unique meeting ID
    banana: str  # Foreign key to City
    title: str
    date: Optional[datetime]
    agenda_url: Optional[str] = None  # HTML agenda page (item-based, primary)
    packet_url: Optional[
        str | List[str]
    ] = None  # PDF packet (monolithic, fallback)
    summary: Optional[str] = None
    participation: Optional[ParticipationInfo] = None  # Contact info: email, phone, virtual_url, etc.
    status: Optional[str] = (
        None  # cancelled, postponed, revised, rescheduled, or None for normal
    )
    topics: Optional[List[str]] = None  # Aggregated topics from agenda items
    processing_status: str = "pending"  # pending, processing, completed, failed
    processing_method: Optional[str] = (
        None  # tier1_pypdf2_gemini, multiple_pdfs_N_combined
    )
    processing_time: Optional[float] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    def __post_init__(self):
        """Validate meeting data after initialization"""
        # Validate processing_status enum (Pydantic doesn't enforce sets automatically)
        valid_statuses = {"pending", "processing", "completed", "failed"}
        if self.processing_status not in valid_statuses:
            from exceptions import ValidationError
            raise ValidationError(
                f"Invalid processing_status: {self.processing_status}. Must be one of: {valid_statuses}",
                field="processing_status",
                value=self.processing_status
            )

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization"""
        data = asdict(self)
        if self.date:
            data["date"] = self.date.isoformat()
        if self.created_at:
            data["created_at"] = self.created_at.isoformat()
        if self.updated_at:
            data["updated_at"] = self.updated_at.isoformat()

        # Map status → meeting_status for frontend compatibility
        if "status" in data:
            data["meeting_status"] = data.pop("status")

        return data



@dataclass
class Matter:
    """Matter entity - legislative items tracked across meetings

    Matters-First Architecture (Nov 2025):
    Matters are the fundamental unit - tracked across time, committees, and meetings.
    Each matter has a canonical summary that's reused when attachments don't change.

    Identity:
    - id: Unique composite key (banana_matter_key, e.g., "nashvilleTN_25-1234")
    - matter_file: Official public ID (25-1234, BL2025-1098)
    - matter_id: Backend vendor ID (UUID, numeric, etc.)

    Deduplication:
    - canonical_summary: Deduplicated summary stored once
    - canonical_topics: Topics extracted from canonical summary
    - metadata: Contains attachment_hash for change detection
    """

    id: str  # Composite key: {banana}_{matter_key}
    banana: str  # Foreign key to City
    matter_file: Optional[str] = None  # Official public identifier (25-1234, BL2025-1098)
    matter_id: Optional[str] = None  # Backend vendor identifier (UUID, numeric)
    matter_type: Optional[str] = None  # Ordinance, Resolution, etc.
    title: Optional[str] = None  # Matter title
    sponsors: Optional[List[str]] = None  # Sponsor names
    canonical_summary: Optional[str] = None  # Deduplicated summary
    canonical_topics: Optional[List[str]] = None  # Extracted topics
    first_seen: Optional[datetime] = None  # First appearance date
    last_seen: Optional[datetime] = None  # Most recent appearance date
    appearance_count: int = 1  # Number of appearances across meetings
    status: str = "active"  # Matter status
    attachments: Optional[List[AttachmentInfo]] = None  # Attachment metadata
    metadata: Optional[MatterMetadata] = None  # attachment_hash, etc.
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    def __post_init__(self):
        """Validate matter data after initialization"""
        # Validate matter ID format (composite: banana_hash)
        from database.id_generation import validate_matter_id
        if not validate_matter_id(self.id):
            from exceptions import ValidationError
            raise ValidationError(
                f"Invalid matter ID format: {self.id}. Must use generate_matter_id()",
                field="id",
                value=self.id
            )

        # Validate banana format (lowercase alphanumeric + state uppercase)
        if not self.banana:
            from exceptions import ValidationError
            raise ValidationError(
                "Matter must have a banana (city identifier)",
                field="banana",
                value=self.banana
            )

        # Validate appearance_count is positive
        if self.appearance_count < 1:
            from exceptions import ValidationError
            raise ValidationError(
                "Matter appearance_count must be at least 1",
                field="appearance_count",
                value=self.appearance_count
            )

        # Validate at least one identifier present (matter_file, matter_id, or title)
        # Title-based matters are valid for cities without stable vendor IDs
        if not self.matter_file and not self.matter_id and not self.title:
            from exceptions import ValidationError
            raise ValidationError(
                "Matter must have at least one identifier (matter_file, matter_id, or title)",
                field="matter_file",
                value=None
            )

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization"""
        data = asdict(self)
        if self.created_at:
            data["created_at"] = self.created_at.isoformat()
        if self.updated_at:
            data["updated_at"] = self.updated_at.isoformat()
        return data

@dataclass
class AgendaItem:
    """Agenda item entity - individual items within a meeting

    Matter Tracking (Nov 2025):
    Unified schema across all vendors (Legistar, PrimeGov, Granicus, etc.):
    - matter_id: Backend unique identifier (UUID, numeric ID, etc.)
    - matter_file: Official public-facing identifier (BL2025-1005, 25-1209, etc.)
    - matter_type: Flexible metadata (Ordinance, Resolution, CD 12, etc.)
    - agenda_number: Position on THIS specific agenda (1, K. 87, etc.)
    - sponsors: List of sponsor names (when available)

    Items can point to Matter objects via matter_file/matter_id.
    When a Matter has a canonical_summary, items inherit it.

    Not all vendors provide all fields - that's expected and fine.
    """

    id: str  # Vendor-specific item ID
    meeting_id: str  # Foreign key to Meeting
    title: str
    sequence: int  # Order in agenda
    attachments: Optional[List[AttachmentInfo]] = None  # Attachment metadata (name, url, type)
    attachment_hash: Optional[str] = None  # SHA-256 hash of attachments for change detection
    matter_id: Optional[str] = None  # Backend unique identifier
    matter_file: Optional[str] = None  # Official public identifier (BL2025-1005, 25-1209)
    matter_type: Optional[str] = None  # Flexible metadata (Ordinance, CD 12, etc.)
    agenda_number: Optional[str] = None  # Position on this agenda
    sponsors: Optional[List[str]] = None  # Sponsor names
    summary: Optional[str] = None
    topics: Optional[List[str]] = None  # Extracted topics
    matter: Optional["Matter"] = None  # Linked Matter object (loaded on demand)
    created_at: Optional[datetime] = None

    def __post_init__(self):
        """Validate agenda item data after initialization"""
        # Validate matter_id format if present (composite: banana_hash)
        if self.matter_id:
            from database.id_generation import validate_matter_id
            if not validate_matter_id(self.matter_id):
                from exceptions import ValidationError
                raise ValidationError(
                    f"Invalid matter_id format: {self.matter_id}",
                    field="matter_id",
                    value=self.matter_id
                )

        # Validate sequence is non-negative
        if self.sequence < 0:
            from exceptions import ValidationError
            raise ValidationError(
                "Agenda item sequence must be non-negative",
                field="sequence",
                value=self.sequence
            )

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization"""
        data = asdict(self)
        if self.created_at:
            data["created_at"] = self.created_at.isoformat()

        # Handle matter field: include if loaded, exclude if None
        if "matter" in data and data["matter"] is not None:
            # Matter was eagerly loaded - serialize it
            data["matter"] = self.matter.to_dict() if self.matter else None
        elif "matter" in data:
            # Matter is None - exclude from response
            del data["matter"]

        return data

