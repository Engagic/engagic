"""
Authentication Endpoints

Passwordless auth with magic links, JWT session management.
"""

import hashlib
import os
import secrets
import time
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Literal, cast

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status

from config import get_logger
from database.db_postgres import Database
from server.dependencies import get_current_user, get_db
from userland.auth.jwt import (
    generate_access_token,
    generate_magic_link_token,
    generate_refresh_token,
    generate_unsubscribe_token,
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

# Per-email rate limiting (in-memory, resets on restart)
_email_requests: dict[str, list[float]] = defaultdict(list)
_EMAIL_RATE_LIMIT = 3
_EMAIL_RATE_WINDOW = 3600  # seconds


def check_email_rate_limit(email: str) -> bool:
    """Returns True if request allowed, False if rate limited."""
    email_lower = email.lower()
    now = time.time()
    cutoff = now - _EMAIL_RATE_WINDOW

    _email_requests[email_lower] = [
        t for t in _email_requests[email_lower] if t > cutoff
    ]

    if len(_email_requests[email_lower]) >= _EMAIL_RATE_LIMIT:
        return False

    _email_requests[email_lower].append(now)
    return True


def _get_cookie_config() -> tuple[bool, Literal["lax", "strict", "none"]]:
    """Read cookie security settings from environment."""
    secure = os.getenv("COOKIE_SECURE", "true").lower() == "true"
    samesite_str = os.getenv("COOKIE_SAMESITE", "lax").lower()
    samesite: Literal["lax", "strict", "none"] = (
        cast(Literal["lax", "strict", "none"], samesite_str)
        if samesite_str in ("lax", "strict", "none")
        else "lax"
    )
    return secure, samesite


router = APIRouter(prefix="/api/auth", tags=["auth"])


def hash_token(token: str) -> str:
    """Hash magic link token for storage (security: don't store raw tokens)"""
    return hashlib.sha256(token.encode()).hexdigest()


@router.post("/signup", response_model=MagicLinkResponse)
async def signup(signup_request: SignupRequest, db: Database = Depends(get_db)):
    """Create user account and send magic link. Returns same response for existing users to prevent enumeration."""
    if not check_email_rate_limit(signup_request.email):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many requests. Please try again later.",
        )

    existing = await db.userland.get_user_by_email(signup_request.email)
    if existing:
        # Existing user signing up with a city - add city to their alerts
        alert_cities = []
        if signup_request.city_banana:
            alert_cities = [signup_request.city_banana]
        elif signup_request.cities:
            alert_cities = signup_request.cities

        if alert_cities:
            alerts = await db.userland.get_alerts(user_id=existing.id)
            if alerts:
                # Add city to existing alert
                await db.userland.update_alert(
                    alert_id=alerts[0].id,
                    cities=alert_cities,
                    keywords=alerts[0].criteria.get("keywords", []),
                )
                logger.info(
                    "city added to existing alert",
                    email=signup_request.email,
                    cities=alert_cities,
                )
            else:
                # Create new alert for existing user
                alert = Alert(
                    id=secrets.token_urlsafe(16),
                    user_id=existing.id,
                    name=f"{existing.name}'s Alert",
                    cities=alert_cities,
                    criteria={"keywords": signup_request.keywords or []},
                    frequency="weekly",
                    active=True,
                )
                await db.userland.create_alert(alert)
                logger.info(
                    "alert created for existing user",
                    email=signup_request.email,
                    cities=alert_cities,
                )

        token = generate_magic_link_token(existing.id)

        from userland.email.transactional import send_magic_link

        success = await send_magic_link(
            email=signup_request.email,
            token=token,
            user_name=existing.name,
            is_signup=False,
        )

        if not success:
            logger.error("email delivery failed", email=signup_request.email)
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Email delivery failed. Please try again or contact support.",
            )

        logger.info("signup for existing user, sent login link", email=signup_request.email)
        return MagicLinkResponse()

    user_id = secrets.token_urlsafe(16)
    name = signup_request.name or signup_request.email.split("@")[0]

    user = User(id=user_id, name=name, email=signup_request.email)
    await db.userland.create_user(user)

    alert_cities = []
    if signup_request.city_banana:
        alert_cities = [signup_request.city_banana]
        try:
            await db.userland.record_city_request(signup_request.city_banana)
        except Exception:
            pass  # Non-critical: demand tracking failure shouldn't block signup
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

    from userland.email.transactional import send_magic_link

    success = await send_magic_link(
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
    """Send magic link to existing user. Returns same response for unknown emails to prevent enumeration."""
    if not check_email_rate_limit(login_request.email):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many requests. Please try again later.",
        )

    user = await db.userland.get_user_by_email(login_request.email)
    if not user:
        return MagicLinkResponse()

    token = generate_magic_link_token(user.id)

    from userland.email.transactional import send_magic_link

    success = await send_magic_link(
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
    """Verify magic link and create session with access + refresh tokens."""
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
    refresh_token, refresh_token_hash = generate_refresh_token(user_id)

    refresh_expiry = datetime.now(timezone.utc) + timedelta(days=30)
    await db.userland.create_refresh_token(refresh_token_hash, user_id, refresh_expiry)

    cookie_secure, cookie_samesite = _get_cookie_config()
    response.set_cookie(
        key="refresh_token",
        value=refresh_token,
        path="/",
        httponly=True,
        secure=cookie_secure,
        samesite=cookie_samesite,
        max_age=30 * 24 * 60 * 60,
    )

    token_expiry_unix = payload.get("exp")
    token_expiry = (
        datetime.fromtimestamp(token_expiry_unix, tz=timezone.utc)
        if token_expiry_unix
        else datetime.now(timezone.utc) + timedelta(minutes=15)
    )
    # Strip timezone for naive timestamp column
    token_expiry_naive = token_expiry.replace(tzinfo=None)
    await db.userland.mark_magic_link_used(token_hash, user_id, token_expiry_naive)

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
    """Refresh access token using httpOnly cookie. Implements token rotation."""
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

    db: Database = request.app.state.db
    old_token_hash = hashlib.sha256(refresh_token.encode()).hexdigest()

    # TODO: After migration period, reject tokens not in database
    if not await db.userland.validate_refresh_token(old_token_hash):
        logger.warning("refresh token not in database", user_id=user_id)

    user = await db.userland.get_user(user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="User not found"
        )

    await db.userland.revoke_refresh_token(old_token_hash, reason="rotation")

    new_access_token = generate_access_token(user_id)
    new_refresh_token, new_refresh_token_hash = generate_refresh_token(user_id)

    refresh_expiry = datetime.now(timezone.utc) + timedelta(days=30)
    await db.userland.create_refresh_token(new_refresh_token_hash, user_id, refresh_expiry)

    cookie_secure, cookie_samesite = _get_cookie_config()
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
async def logout(request: Request, response: Response):
    """Revoke refresh token and clear cookie."""
    refresh_token = request.cookies.get("refresh_token")
    if refresh_token:
        token_hash = hashlib.sha256(refresh_token.encode()).hexdigest()
        db: Database = request.app.state.db
        await db.userland.revoke_refresh_token(token_hash, reason="logout")

    response.delete_cookie("refresh_token", path="/")
    return {"status": "logged_out"}


@router.get("/me", response_model=UserResponse)
async def get_current_user_endpoint(user: User = Depends(get_current_user)):
    """Get current user profile."""
    return UserResponse(
        id=user.id,
        name=user.name,
        email=user.email,
        created_at=user.created_at.isoformat(),
    )


@router.get("/unsubscribe")
async def unsubscribe(token: str, request: Request):
    """One-click unsubscribe from email digest (CAN-SPAM compliance)."""
    payload = verify_token(token, expected_type="unsubscribe")

    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired unsubscribe link",
        )

    user_id = payload.get("user_id")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token payload"
        )

    db: Database = request.app.state.db
    user = await db.userland.get_user(user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="User not found"
        )

    alerts = await db.userland.get_alerts(user_id=user_id)
    deactivated_count = 0
    for alert in alerts:
        if alert.active:
            await db.userland.update_alert(alert_id=alert.id, active=False)
            deactivated_count += 1

    logger.info("user unsubscribed", user_id=user_id, email=user.email, alerts_deactivated=deactivated_count)

    return {
        "status": "unsubscribed",
        "message": f"You have been unsubscribed from {deactivated_count} digest(s).",
        "email": user.email
    }


@router.get("/unsubscribe-token")
async def get_unsubscribe_token(user: User = Depends(get_current_user)):
    """Get unsubscribe token for current user (testing/debugging)."""
    return {"token": generate_unsubscribe_token(user.id)}
