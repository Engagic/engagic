"""
Rate limiting middleware - simplified single tier
"""

import hashlib

from fastapi import Request
from fastapi.responses import JSONResponse
from server.rate_limiter import SQLiteRateLimiter

from config import get_logger

logger = get_logger(__name__)


async def rate_limit_middleware(
    request: Request, call_next, rate_limiter: SQLiteRateLimiter
):
    """Check rate limits for API endpoints"""
    # IP Detection - Priority chain with SSR support
    # When request comes via Cloudflare Pages SSR, CF-Connecting-IP is the Worker's IP.
    # The SSR layer forwards the real user IP as X-Forwarded-Client-IP.
    # nginx validates Cloudflare IPs and sets X-Real-Client-IP.
    client_ip_raw = "unknown"

    if request.headers.get("X-Real-Client-IP"):
        client_ip_raw = request.headers.get("X-Real-Client-IP") or "unknown"
    elif request.headers.get("X-Real-IP"):
        client_ip_raw = request.headers.get("X-Real-IP") or "unknown"
    elif request.headers.get("X-Forwarded-Client-IP"):
        # SSR layer (Cloudflare Pages) forwards the original client IP here
        # Only trusted when request comes through Cloudflare (validated by nginx)
        client_ip_raw = request.headers.get("X-Forwarded-Client-IP") or "unknown"
    elif request.headers.get("CF-Connecting-IP"):
        client_ip_raw = request.headers.get("CF-Connecting-IP") or "unknown"
    elif request.headers.get("X-Forwarded-For"):
        client_ip_raw = request.headers.get("X-Forwarded-For", "").split(",")[0].strip() or "unknown"
    elif request.client:
        client_ip_raw = request.client.host

    # Hash IP for privacy
    client_ip_hash = hashlib.sha256(client_ip_raw.encode()).hexdigest()[:16]
    request.state.client_ip_hash = client_ip_hash

    # Skip rate limiting for OPTIONS (CORS preflight)
    if request.method == "OPTIONS":
        return await call_next(request)

    # Whitelist health/metrics endpoints
    if request.url.path in ["/health", "/metrics", "/api/health", "/api/metrics"]:
        return await call_next(request)

    # Check rate limit
    api_key = request.headers.get("X-API-Key")
    is_allowed, remaining, limit_info = rate_limiter.check_rate_limit(
        client_ip_hash, api_key, client_ip_raw, client_ip_raw
    )

    if not is_allowed:
        limit_type = limit_info.get("limit_type", "unknown")
        tier = limit_info.get("tier", "standard")
        endpoint = f"{request.method} {request.url.path}"

        logger.warning(
            f"Rate limit exceeded for {client_ip_hash} - tier: {tier}, limit: {limit_type}, endpoint: {endpoint}"
        )

        # Temp ban response
        if limit_type == "temp_ban":
            remaining_seconds = limit_info.get("remaining_seconds", 0)
            return JSONResponse(
                status_code=403,
                content={
                    "error": "Temporarily banned",
                    "message": limit_info.get("message", "Temporarily banned"),
                    "ban_remaining_seconds": remaining_seconds,
                },
                headers={
                    "Retry-After": str(remaining_seconds),
                    "Access-Control-Allow-Origin": request.headers.get("origin", "*"),
                    "Access-Control-Allow-Credentials": "true",
                    "Access-Control-Allow-Methods": "*",
                    "Access-Control-Allow-Headers": "*",
                }
            )

        # Rate limit response
        if limit_type == "daily":
            message = f"Daily limit reached ({limit_info['day_limit']}/day). Resets at midnight UTC."
            retry_after = "3600"
        else:
            message = f"Rate limit exceeded ({limit_info['minute_limit']}/min). Wait a moment."
            retry_after = "60"

        return JSONResponse(
            status_code=429,
            content={
                "error": "Rate limit exceeded",
                "message": message,
                "limit_type": limit_type,
                "limits": {
                    "minute": limit_info.get("minute_limit"),
                    "daily": limit_info.get("day_limit")
                },
                "retry_after_seconds": int(retry_after)
            },
            headers={
                "X-RateLimit-Remaining": "0",
                "Retry-After": retry_after,
                "Access-Control-Allow-Origin": request.headers.get("origin", "*"),
                "Access-Control-Allow-Credentials": "true",
                "Access-Control-Allow-Methods": "*",
                "Access-Control-Allow-Headers": "*",
            },
        )

    # Success - add rate limit headers
    response = await call_next(request)
    response.headers["X-RateLimit-Remaining-Minute"] = str(limit_info.get("remaining_minute", 0))
    response.headers["X-RateLimit-Remaining-Daily"] = str(limit_info.get("remaining_daily", 0))
    return response
