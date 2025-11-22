"""
API Request and Response Models

Pydantic models for validation and serialization.
"""

from typing import Optional, List
from pydantic import BaseModel, EmailStr, validator, Field


class SignupRequest(BaseModel):
    """Request to create new user account"""
    email: EmailStr
    name: Optional[str] = None  # Optional: defaults to email prefix if not provided
    city_banana: Optional[str] = None  # Single city for simple signup flow
    cities: List[str] = Field(default=[], max_length=20)  # Multi-city for power users
    keywords: List[str] = Field(default=[], max_length=50)

    @validator("cities")
    def validate_cities_field(cls, v):
        # Allow empty list - user can configure later
        if not v:
            return []
        # Basic validation - just ensure they're non-empty strings
        return [city.strip() for city in v if city.strip()]

    @validator("keywords")
    def validate_keywords_field(cls, v):
        # Allow empty list - user can configure later
        if not v:
            return []
        # Basic validation - ensure they're non-empty strings
        return [kw.strip() for kw in v if kw.strip()]


class LoginRequest(BaseModel):
    """Request to send magic link to existing user"""
    email: EmailStr


class MagicLinkResponse(BaseModel):
    """Response after magic link sent"""
    status: str = "sent"
    message: str = "Check your email for a login link"


class TokenResponse(BaseModel):
    """JWT token response"""
    access_token: str
    refresh_token: str
    user: "UserResponse"
    token_type: str = "bearer"


class UserResponse(BaseModel):
    """User profile response"""
    id: str
    name: str
    email: str
    created_at: str


class AlertUpdateRequest(BaseModel):
    """Request model for updating an alert"""
    cities: Optional[List[str]] = None
    keywords: Optional[List[str]] = None
    frequency: Optional[str] = None


class ErrorResponse(BaseModel):
    """Error response"""
    error: str
    detail: Optional[str] = None
