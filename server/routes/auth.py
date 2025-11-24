"""
Authentication Endpoints

Passwordless auth with magic links, JWT session management.
"""

import hashlib
import os
import secrets
from datetime import datetime, timedelta
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status

from config import get_logger
from database.db_postgres import Database
from server.dependencies import get_db
from userland.auth.jwt import (
    generate_access_token,
    generate_magic_link_token,
    generate_refresh_token,
    verify_token,
)
from userland.database.models import Alert, User
from userland.server.models import (
    LoginRequest,
    MagicLinkResponse,
    SignupRequest,
    TokenResponse,
    UserResponse,
)

logger = get_logger(__name__)
router = APIRouter(prefix="/api/auth", tags=["auth"])


def hash_token(token: str) -> str:
    """Hash magic link token for storage (security: don't store raw tokens)"""
    return hashlib.sha256(token.encode()).hexdigest()


async def get_current_user(request: Request) -> User:
    """
    FastAPI dependency to extract and validate current user from JWT token.

    Accepts either:
    - Access token in Authorization header (preferred)
    - Refresh token from httpOnly cookie (fallback on page load)

    Returns:
        User object

    Raises:
        HTTPException 401 if not authenticated or token invalid
        HTTPException 404 if user not found
    """
    user_id = None

    # Try access token from Authorization header first
    auth_header = request.headers.get("authorization")
    if auth_header and auth_header.startswith("Bearer "):
        access_token = auth_header.replace("Bearer ", "")
        payload = verify_token(access_token, expected_type="access")
        if payload:
            user_id = payload.get("user_id")

    # Fallback to refresh token from cookie
    if not user_id:
        refresh_token = request.cookies.get("refresh_token")
        if refresh_token:
            payload = verify_token(refresh_token, expected_type="refresh")
            if payload:
                user_id = payload.get("user_id")

    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated"
        )

    db: Database = request.app.state.db
    user = await db.userland.get_user(user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="User not found"
        )

    return user


@router.post("/signup", response_model=MagicLinkResponse)
async def signup(signup_request: SignupRequest, db: Database = Depends(get_db)):
    """
    Create user account and send magic link.

    Flow:
    1. Validate email not already registered
    2. Create user
    3. Create default alert with their keywords/cities (if provided)
    4. Generate magic link token
    5. Send email with magic link
    """
    existing = await db.userland.get_user_by_email(signup_request.email)
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Email already registered"
        )

    user_id = secrets.token_urlsafe(16)
    name = signup_request.name or signup_request.email.split("@")[0]

    user = User(id=user_id, name=name, email=signup_request.email)
    await db.userland.create_user(user)

    # Create default alert if city provided (keywords optional)
    alert_cities = []
    if signup_request.city_banana:
        alert_cities = [signup_request.city_banana]
    elif signup_request.cities:
        alert_cities = signup_request.cities

    if alert_cities:
        alert = Alert(
            id=secrets.token_urlsafe(16),
            user_id=user_id,
            name=f"{name}'s Alert",
            cities=alert_cities,
            criteria={"keywords": signup_request.keywords or []},
            frequency="weekly",
            active=True,
        )
        await db.userland.create_alert(alert)

    token = generate_magic_link_token(user_id)

    # Send magic link email (use shared transactional template)
    from userland.email.transactional import send_magic_link

    success = send_magic_link(
        email=signup_request.email,
        token=token,
        user_name=name,
        is_signup=True
    )

    if not success:
        logger.error("email delivery failed", email=signup_request.email)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Email delivery failed. Please try again or contact support.",
        )

    logger.info("user signup", email=signup_request.email, user_id=user_id)

    return MagicLinkResponse()


@router.post("/login", response_model=MagicLinkResponse)
async def login(login_request: LoginRequest, db: Database = Depends(get_db)):
    """
    Send magic link to existing user.

    Flow:
    1. Validate email exists
    2. Generate magic link token
    3. Send email with magic link
    """
    user = await db.userland.get_user_by_email(login_request.email)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No account found with this email",
        )

    token = generate_magic_link_token(user.id)

    # Send magic link email (use shared transactional template)
    from userland.email.transactional import send_magic_link

    success = send_magic_link(
        email=login_request.email,
        token=token,
        user_name=user.name,
        is_signup=False
    )

    if not success:
        logger.error("email delivery failed", email=login_request.email)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Email delivery failed. Please try again or contact support.",
        )

    logger.info("login link sent", email=login_request.email)

    return MagicLinkResponse()


@router.get("/verify")
async def verify_magic_link(token: str, response: Response, request: Request):
    """
    Verify magic link and create session.

    Flow:
    1. Validate magic link token (15min expiry)
    2. Check token hasn't been used (single-use enforcement)
    3. Update user last_login
    4. Generate access + refresh tokens
    5. Set refresh token as httpOnly cookie
    6. Mark magic link as used
    7. Return access token + user info to client
    """
    payload = verify_token(token, expected_type="magic_link")

    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired magic link",
        )

    user_id = payload.get("user_id")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token payload"
        )

    # Security: Check if magic link has already been used (prevent replay attacks)
    token_hash = hash_token(token)
    db: Database = request.app.state.db

    if await db.userland.is_magic_link_used(token_hash):
        logger.warning("magic link reuse attempt", user_id=user_id)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="This magic link has already been used. Request a new one.",
        )

    user = await db.userland.get_user(user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="User not found"
        )

    await db.userland.update_last_login(user_id)

    access_token = generate_access_token(user_id)
    refresh_token = generate_refresh_token(user_id)

    # Set secure cookie
    cookie_secure = os.getenv("COOKIE_SECURE", "true").lower() == "true"
    cookie_samesite_str = os.getenv("COOKIE_SAMESITE", "lax").lower()
    # Type-safe samesite value
    cookie_samesite: Literal["lax", "strict", "none"] = (
        "lax" if cookie_samesite_str not in ("lax", "strict", "none") else cookie_samesite_str  # type: ignore
    )

    response.set_cookie(
        key="refresh_token",
        value=refresh_token,
        path="/",
        httponly=True,
        secure=cookie_secure,
        samesite=cookie_samesite,
        max_age=30 * 24 * 60 * 60,  # 30 days
    )

    # Mark magic link as used
    token_expiry = datetime.now() + timedelta(minutes=15)
    await db.userland.mark_magic_link_used(token_hash, user_id, token_expiry)

    logger.info("magic link verified", email=user.email, user_id=user_id)

    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        user=UserResponse(
            id=user.id,
            name=user.name,
            email=user.email,
            created_at=user.created_at.isoformat(),
        ),
    )


@router.post("/refresh", response_model=TokenResponse)
async def refresh_access_token(request: Request, response: Response):
    """
    Refresh access token using refresh token from cookie.
    """
    refresh_token = request.cookies.get("refresh_token")

    if not refresh_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="No refresh token found"
        )

    payload = verify_token(refresh_token, expected_type="refresh")

    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired refresh token",
        )

    user_id = payload.get("user_id")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token payload"
        )

    # Get user for response
    db: Database = request.app.state.db
    user = await db.userland.get_user(user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="User not found"
        )

    new_access_token = generate_access_token(user_id)
    new_refresh_token = generate_refresh_token(user_id)

    cookie_secure = os.getenv("COOKIE_SECURE", "true").lower() == "true"
    cookie_samesite_str = os.getenv("COOKIE_SAMESITE", "lax").lower()
    cookie_samesite: Literal["lax", "strict", "none"] = (
        "lax" if cookie_samesite_str not in ("lax", "strict", "none") else cookie_samesite_str  # type: ignore
    )

    response.set_cookie(
        key="refresh_token",
        value=new_refresh_token,
        path="/",
        httponly=True,
        secure=cookie_secure,
        samesite=cookie_samesite,
        max_age=30 * 24 * 60 * 60,
    )

    return TokenResponse(
        access_token=new_access_token,
        refresh_token=new_refresh_token,
        user=UserResponse(
            id=user.id,
            name=user.name,
            email=user.email,
            created_at=user.created_at.isoformat(),
        ),
    )


@router.post("/logout")
async def logout(response: Response):
    """Logout by clearing refresh token cookie"""
    response.delete_cookie("refresh_token", path="/")
    return {"status": "logged_out"}


@router.get("/me", response_model=UserResponse)
async def get_current_user_endpoint(user: User = Depends(get_current_user)):
    """
    Get current user profile.

    Uses get_current_user dependency to extract user from:
    - Access token in Authorization header (preferred)
    - Refresh token from httpOnly cookie (fallback on page load)
    """
    return UserResponse(
        id=user.id,
        name=user.name,
        email=user.email,
        created_at=user.created_at.isoformat(),
    )
