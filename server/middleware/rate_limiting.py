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
    # Get real client IP from trusted proxy headers (priority order)
    # Cloudflare: CF-Connecting-IP (most reliable)
    # nginx: X-Real-IP
    # Standard: X-Forwarded-For (take leftmost/original client)
    # Fallback: request.client.host
    client_ip = (
        request.headers.get("CF-Connecting-IP")
        or request.headers.get("X-Real-IP")
        or (request.headers.get("X-Forwarded-For", "").split(",")[0].strip() if request.headers.get("X-Forwarded-For") else None)
        or (request.client.host if request.client else "unknown")
    )

    # Skip rate limiting for OPTIONS requests (CORS preflight)
    if request.method == "OPTIONS":
        response = await call_next(request)
        return response

    # Check rate limit for API endpoints
    if request.url.path.startswith("/api/"):
        is_allowed, remaining = rate_limiter.check_rate_limit(client_ip)

        if not is_allowed:
            logger.warning(f"Rate limit exceeded for {client_ip}")
            # Get origin from request for CORS header
            origin = request.headers.get("origin", "*")
            return JSONResponse(
                status_code=429,
                content={"detail": "Rate limit exceeded. Please try again later."},
                headers={
                    "X-RateLimit-Remaining": "0",
                    "Access-Control-Allow-Origin": origin,
                    "Access-Control-Allow-Credentials": "true",
                    "Access-Control-Allow-Methods": "*",
                    "Access-Control-Allow-Headers": "*",
                },
            )

    response = await call_next(request)
    return response
