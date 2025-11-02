"""
Rate limiting middleware
"""

import logging
from fastapi import Request
from fastapi.responses import JSONResponse
from server.rate_limiter import SQLiteRateLimiter

logger = logging.getLogger("engagic")


async def rate_limit_middleware(
    request: Request, call_next, rate_limiter: SQLiteRateLimiter
):
    """Check rate limits for API endpoints"""
    client_ip = request.client.host if request.client else "unknown"

    # Check rate limit for API endpoints
    if request.url.path.startswith("/api/"):
        is_allowed, remaining = rate_limiter.check_rate_limit(client_ip)

        if not is_allowed:
            logger.warning(f"Rate limit exceeded for {client_ip}")
            return JSONResponse(
                status_code=429,
                content={"detail": "Rate limit exceeded. Please try again later."},
                headers={"X-RateLimit-Remaining": "0"},
            )

    response = await call_next(request)
    return response
