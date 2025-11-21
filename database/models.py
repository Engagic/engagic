"""
Database Models for Engagic

Pydantic dataclasses with runtime validation for core entities.
"""


import sqlite3
import json
from typing import Optional, List, Dict, Any
from datetime import datetime
from pydantic.dataclasses import dataclass
from dataclasses import asdict

from config import get_logger

logger = get_logger(__name__).bind(component="engagic")


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
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization"""
        data = asdict(self)
        if self.created_at:
            data["created_at"] = self.created_at.isoformat()
        if self.updated_at:
            data["updated_at"] = self.updated_at.isoformat()
        return data

    @classmethod
    def from_db_row(cls, row: sqlite3.Row) -> "City":
        """Create City from database row"""
        row_dict = dict(row)
        return cls(
            banana=row_dict["banana"],
            name=row_dict["name"],
            state=row_dict["state"],
            vendor=row_dict["vendor"],
            slug=row_dict["slug"],
            county=row_dict.get("county"),
            status=row_dict.get("status", "active"),
            created_at=datetime.fromisoformat(row_dict["created_at"])
            if row_dict.get("created_at")
            else None,
            updated_at=datetime.fromisoformat(row_dict["updated_at"])
            if row_dict.get("updated_at")
            else None,
        )


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
    participation: Optional[Dict[str, Any]] = None  # Contact info: email, phone, virtual_url, etc.
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
        # Validate banana format
        if not self.banana:
            from exceptions import ValidationError
            raise ValidationError(
                "Meeting must have a banana (city identifier)",
                field="banana",
                value=self.banana
            )

        # Validate processing_status values
        valid_statuses = {"pending", "processing", "completed", "failed"}
        if self.processing_status not in valid_statuses:
            from exceptions import ValidationError
            raise ValidationError(
                f"Invalid processing_status: {self.processing_status}. Must be one of: {valid_statuses}",
                field="processing_status",
                value=self.processing_status
            )

        # Validate at least one URL present (agenda_url or packet_url)
        if not self.agenda_url and not self.packet_url:
            from exceptions import ValidationError
            raise ValidationError(
                "Meeting must have at least one URL (agenda_url or packet_url)",
                field="agenda_url",
                value=None
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

    @classmethod
    def from_db_row(cls, row: sqlite3.Row) -> "Meeting":
        """Create Meeting from database row"""
        row_dict = dict(row)

        # Deserialize packet_url if it's a JSON list
        packet_url = row_dict.get("packet_url")
        if packet_url and packet_url.startswith("["):
            try:
                packet_url = json.loads(packet_url)
            except json.JSONDecodeError:
                logger.warning("failed to deserialize packet_url JSON", packet_url=packet_url)
                pass  # Keep as string if JSON parsing fails

        # Deserialize participation if it's JSON
        participation = row_dict.get("participation")
        if participation:
            try:
                participation = json.loads(participation)
            except json.JSONDecodeError:
                logger.warning("failed to deserialize participation JSON", participation=participation)
                participation = None

        # Deserialize topics if it's JSON
        topics = row_dict.get("topics")
        if topics:
            try:
                topics = json.loads(topics)
            except json.JSONDecodeError:
                logger.warning("failed to deserialize topics JSON", topics=topics)
                topics = None
        else:
            topics = None

        return cls(
            id=row_dict["id"],
            banana=row_dict["banana"],
            title=row_dict["title"],
            date=datetime.fromisoformat(row_dict["date"])
            if row_dict.get("date")
            else None,
            agenda_url=row_dict.get("agenda_url"),
            packet_url=packet_url,
            summary=row_dict.get("summary"),
            participation=participation,
            status=row_dict.get("status"),
            topics=topics,
            processing_status=row_dict.get("processing_status", "pending"),
            processing_method=row_dict.get("processing_method"),
            processing_time=row_dict.get("processing_time"),
            created_at=datetime.fromisoformat(row_dict["created_at"])
            if row_dict.get("created_at")
            else None,
            updated_at=datetime.fromisoformat(row_dict["updated_at"])
            if row_dict.get("updated_at")
            else None,
        )


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
    attachments: Optional[List[Dict[str, Any]]] = None  # Attachment metadata
    metadata: Optional[Dict[str, Any]] = None  # attachment_hash, etc.
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

        # Validate at least one identifier present
        if not self.matter_file and not self.matter_id:
            from exceptions import ValidationError
            raise ValidationError(
                "Matter must have at least one identifier (matter_file or matter_id)",
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

    @classmethod
    def from_db_row(cls, row: sqlite3.Row) -> "Matter":
        """Create Matter from database row"""
        row_dict = dict(row)

        # Deserialize JSON fields
        sponsors = row_dict.get("sponsors")
        if sponsors:
            try:
                sponsors = json.loads(sponsors)
            except json.JSONDecodeError:
                logger.warning("failed to deserialize sponsors JSON", sponsors=sponsors)
                sponsors = None
        else:
            sponsors = None

        canonical_topics = row_dict.get("canonical_topics")
        if canonical_topics:
            try:
                canonical_topics = json.loads(canonical_topics)
            except json.JSONDecodeError:
                logger.warning("failed to deserialize canonical_topics JSON", canonical_topics=canonical_topics)
                canonical_topics = None
        else:
            canonical_topics = None

        attachments = row_dict.get("attachments")
        if attachments:
            try:
                attachments = json.loads(attachments)
            except json.JSONDecodeError:
                logger.warning("failed to deserialize attachments JSON", attachments=attachments)
                attachments = None
        else:
            attachments = None

        metadata = row_dict.get("metadata")
        if metadata:
            try:
                metadata = json.loads(metadata)
            except json.JSONDecodeError:
                logger.warning("failed to deserialize metadata JSON", metadata=metadata)
                metadata = None
        else:
            metadata = None

        return cls(
            id=row_dict["id"],
            banana=row_dict["banana"],
            matter_file=row_dict.get("matter_file"),
            matter_id=row_dict.get("matter_id"),
            matter_type=row_dict.get("matter_type"),
            title=row_dict.get("title"),
            sponsors=sponsors,
            canonical_summary=row_dict.get("canonical_summary"),
            canonical_topics=canonical_topics,
            first_seen=datetime.fromisoformat(row_dict["first_seen"])
            if row_dict.get("first_seen")
            else None,
            last_seen=datetime.fromisoformat(row_dict["last_seen"])
            if row_dict.get("last_seen")
            else None,
            appearance_count=row_dict.get("appearance_count", 1),
            status=row_dict.get("status", "active"),
            attachments=attachments,
            metadata=metadata,
            created_at=datetime.fromisoformat(row_dict["created_at"])
            if row_dict.get("created_at")
            else None,
            updated_at=datetime.fromisoformat(row_dict["updated_at"])
            if row_dict.get("updated_at")
            else None,
        )


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
    attachments: List[
        Any
    ]  # Attachment metadata as JSON (flexible: URLs, dicts with name/url/type, page ranges, etc.)
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

    @classmethod
    def from_db_row(cls, row: sqlite3.Row) -> "AgendaItem":
        """Create AgendaItem from database row"""
        row_dict = dict(row)

        # Deserialize JSON fields
        attachments = row_dict.get("attachments")
        if attachments:
            try:
                attachments = json.loads(attachments)
            except json.JSONDecodeError:
                logger.warning("failed to deserialize attachments JSON", attachments=attachments)
                attachments = []
        else:
            attachments = []

        topics = row_dict.get("topics")
        if topics:
            try:
                topics = json.loads(topics)
            except json.JSONDecodeError:
                logger.warning("failed to deserialize topics JSON", topics=topics)
                topics = None
        else:
            topics = None

        sponsors = row_dict.get("sponsors")
        if sponsors:
            try:
                sponsors = json.loads(sponsors)
            except json.JSONDecodeError:
                logger.warning("failed to deserialize sponsors JSON", sponsors=sponsors)
                sponsors = None
        else:
            sponsors = None

        return cls(
            id=row_dict["id"],
            meeting_id=row_dict["meeting_id"],
            title=row_dict["title"],
            sequence=row_dict["sequence"],
            attachments=attachments,
            attachment_hash=row_dict.get("attachment_hash"),
            matter_id=row_dict.get("matter_id"),
            matter_file=row_dict.get("matter_file"),
            matter_type=row_dict.get("matter_type"),
            agenda_number=row_dict.get("agenda_number"),
            sponsors=sponsors,
            summary=row_dict.get("summary"),
            topics=topics,
            created_at=datetime.fromisoformat(row_dict["created_at"])
            if row_dict.get("created_at")
            else None,
        )
