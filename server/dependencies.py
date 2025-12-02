"""FastAPI Dependencies

Centralized dependency injection for reuse across all route modules.
Provides type-safe, testable access to shared resources.
"""

from typing import Optional

from fastapi import HTTPException, Request, status

from database.db_postgres import Database
from userland.auth.jwt import verify_token
from userland.database.models import User


def get_db(request: Request) -> Database:
    """Dependency to get shared database instance from app state

    Usage in routes:
        @router.get("/endpoint")
        async def endpoint(db: Database = Depends(get_db)):
            meetings = await db.meetings.get_recent_meetings()
            return meetings

    Benefits:
    - Type-safe database access (IDE autocomplete works)
    - Testable (can mock database in tests)
    - Cleaner than manual request.app.state.db access
    """
    return request.app.state.db


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


async def get_optional_user(request: Request) -> Optional[User]:
    """Optional user dependency - returns None if not authenticated."""
    try:
        return await get_current_user(request)
    except HTTPException:
        return None
