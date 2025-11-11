"""
Database Models for Engagic

Dataclasses representing core entities in the unified database.
"""

import logging
import sqlite3
import json
from typing import Optional, List, Dict, Any
from datetime import datetime
from dataclasses import dataclass, asdict

logger = logging.getLogger("engagic")


class DatabaseConnectionError(Exception):
    """Raised when database connection is not established"""

    pass


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
                logger.warning(f"Failed to deserialize packet_url JSON: {packet_url}")
                pass  # Keep as string if JSON parsing fails

        # Deserialize participation if it's JSON
        participation = row_dict.get("participation")
        if participation:
            try:
                participation = json.loads(participation)
            except json.JSONDecodeError:
                logger.warning(f"Failed to deserialize participation JSON: {participation}")
                participation = None

        # Deserialize topics if it's JSON
        topics = row_dict.get("topics")
        if topics:
            try:
                topics = json.loads(topics)
            except json.JSONDecodeError:
                logger.warning(f"Failed to deserialize topics JSON: {topics}")
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
class AgendaItem:
    """Agenda item entity - individual items within a meeting

    Matter Tracking (Nov 2025):
    Unified schema across all vendors (Legistar, PrimeGov, Granicus, etc.):
    - matter_id: Backend unique identifier (UUID, numeric ID, etc.)
    - matter_file: Official public-facing identifier (BL2025-1005, 25-1209, etc.)
    - matter_type: Flexible metadata (Ordinance, Resolution, CD 12, etc.)
    - agenda_number: Position on THIS specific agenda (1, K. 87, etc.)
    - sponsors: List of sponsor names (when available)

    Not all vendors provide all fields - that's expected and fine.
    """

    id: str  # Vendor-specific item ID
    meeting_id: str  # Foreign key to Meeting
    title: str
    sequence: int  # Order in agenda
    attachments: List[
        Any
    ]  # Attachment metadata as JSON (flexible: URLs, dicts with name/url/type, page ranges, etc.)
    matter_id: Optional[str] = None  # Backend unique identifier
    matter_file: Optional[str] = None  # Official public identifier (BL2025-1005, 25-1209)
    matter_type: Optional[str] = None  # Flexible metadata (Ordinance, CD 12, etc.)
    agenda_number: Optional[str] = None  # Position on this agenda
    sponsors: Optional[List[str]] = None  # Sponsor names
    summary: Optional[str] = None
    topics: Optional[List[str]] = None  # Extracted topics
    created_at: Optional[datetime] = None

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization"""
        data = asdict(self)
        if self.created_at:
            data["created_at"] = self.created_at.isoformat()
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
                logger.warning(f"Failed to deserialize attachments JSON: {attachments}")
                attachments = []
        else:
            attachments = []

        topics = row_dict.get("topics")
        if topics:
            try:
                topics = json.loads(topics)
            except json.JSONDecodeError:
                logger.warning(f"Failed to deserialize topics JSON: {topics}")
                topics = None
        else:
            topics = None

        sponsors = row_dict.get("sponsors")
        if sponsors:
            try:
                sponsors = json.loads(sponsors)
            except json.JSONDecodeError:
                logger.warning(f"Failed to deserialize sponsors JSON: {sponsors}")
                sponsors = None
        else:
            sponsors = None

        return cls(
            id=row_dict["id"],
            meeting_id=row_dict["meeting_id"],
            title=row_dict["title"],
            sequence=row_dict["sequence"],
            attachments=attachments,
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
