"""
Pydantic request models for API validation
"""

import re
from typing import Optional
from pydantic import BaseModel, validator
from config import config
from server.utils.validation import sanitize_string


class SearchRequest(BaseModel):
    query: str

    @validator("query")
    def validate_query(cls, v):
        if not v or not v.strip():
            raise ValueError("Search query cannot be empty")

        sanitized = sanitize_string(v)
        if len(sanitized) < 2:
            raise ValueError("Search query too short")
        if len(sanitized) > config.MAX_QUERY_LENGTH:
            raise ValueError(
                f"Search query too long (max {config.MAX_QUERY_LENGTH} characters)"
            )

        # Basic pattern validation
        if not re.match(r"^[a-zA-Z0-9\s,.-]+$", sanitized):
            raise ValueError("Search query contains invalid characters")

        return sanitized


class ProcessRequest(BaseModel):
    packet_url: str
    banana: str
    meeting_name: Optional[str] = None
    meeting_date: Optional[str] = None
    meeting_id: Optional[str] = None

    @validator("packet_url")
    def validate_packet_url(cls, v):
        if not v or not v.strip():
            raise ValueError("Packet URL cannot be empty")

        # Basic URL validation
        if not re.match(r"^https?://", v):
            raise ValueError("Packet URL must be a valid HTTP/HTTPS URL")

        if len(v) > 2000:
            raise ValueError("Packet URL too long")

        return v.strip()

    @validator("banana")
    def validate_banana(cls, v):
        if not v or not v.strip():
            raise ValueError("City banana cannot be empty")

        # City banana should be alphanumeric with state code
        if not re.match(r"^[a-z0-9]+[A-Z]{2}$", v):
            raise ValueError(
                "City banana must be lowercase city name + uppercase state code"
            )

        return v.strip()

    @validator("meeting_name", "meeting_date", "meeting_id", pre=True, always=True)
    def validate_optional_strings(cls, v):
        if v is None:
            return None
        return sanitize_string(str(v))


class TopicSearchRequest(BaseModel):
    topic: str
    banana: Optional[str] = None  # Filter by city
    limit: int = 50

    @validator("topic")
    def validate_topic(cls, v):
        if not v or not v.strip():
            raise ValueError("Topic cannot be empty")
        return sanitize_string(v)


class FlyerRequest(BaseModel):
    meeting_id: int
    item_id: Optional[int] = None
    position: str
    custom_message: Optional[str] = None
    user_name: Optional[str] = None

    @validator("position")
    def validate_position(cls, v):
        allowed = ["support", "oppose", "more_info"]
        if v not in allowed:
            raise ValueError(f"Position must be one of: {', '.join(allowed)}")
        return v

    @validator("custom_message")
    def validate_custom_message(cls, v):
        if v is None:
            return None
        sanitized = sanitize_string(v)
        if len(sanitized) > 500:
            raise ValueError("Custom message too long (max 500 characters)")
        return sanitized

    @validator("user_name")
    def validate_user_name(cls, v):
        if v is None:
            return None
        sanitized = sanitize_string(v)
        if len(sanitized) > 100:
            raise ValueError("User name too long (max 100 characters)")
        return sanitized
