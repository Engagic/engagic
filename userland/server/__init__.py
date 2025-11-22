"""Userland server module - Pydantic models for auth and dashboard endpoints"""

from userland.server.models import (
    SignupRequest,
    LoginRequest,
    AlertUpdateRequest,
    MagicLinkResponse,
    TokenResponse,
    UserResponse,
    ErrorResponse,
)

__all__ = [
    "SignupRequest",
    "LoginRequest",
    "AlertUpdateRequest",
    "MagicLinkResponse",
    "TokenResponse",
    "UserResponse",
    "ErrorResponse",
]
