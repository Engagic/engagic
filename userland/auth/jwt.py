"""
JWT Authentication Utilities

Magic link generation, session token management, refresh tokens.

Note: Uses module-level state initialized once at server startup.
This is acceptable because the secret is set once and never modified.
For testing, call init_jwt() before using any token functions.
"""

from datetime import datetime, timedelta
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
    """
    Generate short-lived magic link token for passwordless login.

    Expiry: 15 minutes (one-time use)
    """
    secret = _get_secret()
    payload = {
        "user_id": user_id,
        "type": "magic_link",
        "exp": datetime.utcnow() + _MAGIC_LINK_EXPIRY,
    }
    return jwt.encode(payload, secret, algorithm=_ALGORITHM)


def generate_access_token(user_id: str) -> str:
    """
    Generate short-lived access token for API requests.

    Expiry: 1 hour (refresh frequently)
    """
    secret = _get_secret()
    payload = {
        "user_id": user_id,
        "type": "access",
        "exp": datetime.utcnow() + _ACCESS_TOKEN_EXPIRY,
    }
    return jwt.encode(payload, secret, algorithm=_ALGORITHM)


def generate_refresh_token(user_id: str) -> str:
    """
    Generate long-lived refresh token for session persistence.

    Expiry: 30 days (stored in httpOnly cookie)
    """
    secret = _get_secret()
    payload = {
        "user_id": user_id,
        "type": "refresh",
        "exp": datetime.utcnow() + _REFRESH_TOKEN_EXPIRY,
    }
    return jwt.encode(payload, secret, algorithm=_ALGORITHM)


def verify_token(token: str, expected_type: Optional[str] = None) -> Optional[dict]:
    """
    Verify JWT token and return payload.

    Returns None if token is invalid or expired.
    Optionally validates token type (magic_link, access, refresh).
    """
    secret = _get_secret()
    try:
        payload = jwt.decode(token, secret, algorithms=[_ALGORITHM])

        if expected_type and payload.get("type") != expected_type:
            return None

        return payload
    except JWTError:
        return None


def generate_unsubscribe_token(user_id: str) -> str:
    """
    Generate long-lived unsubscribe token for email links.

    Expiry: 1 year (emails may be read months later)
    """
    secret = _get_secret()
    payload = {
        "user_id": user_id,
        "type": "unsubscribe",
        "exp": datetime.utcnow() + _UNSUBSCRIBE_TOKEN_EXPIRY,
    }
    return jwt.encode(payload, secret, algorithm=_ALGORITHM)


def extract_user_id(token: str) -> Optional[str]:
    """
    Extract user_id from token without full validation.

    Useful for logging/debugging, NOT for auth decisions.
    """
    payload = verify_token(token)
    if payload:
        return payload.get("user_id")
    return None
