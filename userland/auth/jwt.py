"""
JWT Authentication Utilities

Magic link generation, session token management, refresh tokens.

Note: Uses module-level state initialized once at server startup.
This is acceptable because the secret is set once and never modified.
For testing, call init_jwt() before using any token functions.
"""

import hashlib
from datetime import datetime, timedelta, timezone
from typing import Optional

from jose import JWTError, jwt

# Module-level secret (initialized once at startup via init_jwt)
_SECRET_KEY: Optional[str] = None
_ALGORITHM = "HS256"

# Token expiry times
_MAGIC_LINK_EXPIRY = timedelta(minutes=15)  # Magic links are one-time use, short expiry is fine
_ACCESS_TOKEN_EXPIRY = timedelta(hours=1)  # Extended for better UX during active sessions
_REFRESH_TOKEN_EXPIRY = timedelta(days=30)  # Long-lived for persistent sessions
_UNSUBSCRIBE_TOKEN_EXPIRY = timedelta(days=365)  # Long-lived for email links


def init_jwt(secret: str) -> None:
    """
    Initialize JWT module with secret key.

    Should be called once at server startup. Subsequent calls will
    raise ValueError to prevent accidental re-initialization.

    Args:
        secret: JWT signing secret (should be cryptographically secure)

    Raises:
        ValueError: If secret is empty or module already initialized
    """
    global _SECRET_KEY

    if not secret or not secret.strip():
        raise ValueError("JWT secret cannot be empty")

    if _SECRET_KEY is not None:
        raise ValueError("JWT module already initialized. Do not re-initialize.")

    _SECRET_KEY = secret


def _get_secret() -> str:
    """Get the initialized secret key, raising if not initialized"""
    if _SECRET_KEY is None:
        raise ValueError("JWT module not initialized. Call init_jwt() first.")
    return _SECRET_KEY


def generate_magic_link_token(user_id: str) -> str:
    """Generate short-lived magic link token for passwordless login."""
    secret = _get_secret()
    payload = {
        "user_id": user_id,
        "type": "magic_link",
        "exp": datetime.now(timezone.utc) + _MAGIC_LINK_EXPIRY,
    }
    return jwt.encode(payload, secret, algorithm=_ALGORITHM)


def generate_access_token(user_id: str) -> str:
    """Generate short-lived access token for API requests."""
    secret = _get_secret()
    payload = {
        "user_id": user_id,
        "type": "access",
        "exp": datetime.now(timezone.utc) + _ACCESS_TOKEN_EXPIRY,
    }
    return jwt.encode(payload, secret, algorithm=_ALGORITHM)


def generate_refresh_token(user_id: str) -> tuple[str, str]:
    """Generate long-lived refresh token. Returns (token, hash) for revocation support."""
    secret = _get_secret()
    payload = {
        "user_id": user_id,
        "type": "refresh",
        "exp": datetime.now(timezone.utc) + _REFRESH_TOKEN_EXPIRY,
    }
    token = jwt.encode(payload, secret, algorithm=_ALGORITHM)
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    return token, token_hash


def verify_token(token: str, expected_type: Optional[str] = None) -> Optional[dict]:
    """Verify JWT token and return payload, or None if invalid/expired."""
    secret = _get_secret()
    try:
        payload = jwt.decode(token, secret, algorithms=[_ALGORITHM])

        if expected_type and payload.get("type") != expected_type:
            return None

        return payload
    except JWTError:
        return None


def generate_unsubscribe_token(user_id: str) -> str:
    """Generate long-lived unsubscribe token for email links."""
    secret = _get_secret()
    payload = {
        "user_id": user_id,
        "type": "unsubscribe",
        "exp": datetime.now(timezone.utc) + _UNSUBSCRIBE_TOKEN_EXPIRY,
    }
    return jwt.encode(payload, secret, algorithm=_ALGORITHM)


def extract_user_id(token: str) -> Optional[str]:
    """Extract user_id from token. For logging only, NOT auth decisions."""
    payload = verify_token(token)
    return payload.get("user_id") if payload else None
