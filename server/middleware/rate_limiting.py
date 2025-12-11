"""
Rate limiting middleware

IP Detection Chain (priority order):
1. X-Forwarded-Client-IP + X-SSR-Auth: SSR requests from Cloudflare Pages
   - Pages worker forwards user's cf-connecting-ip
   - X-SSR-Auth validates the request came from our frontend
   - Takes priority because CF-Connecting-IP for Pages requests is Cloudflare's IP

2. CF-Connecting-IP: Direct browser requests via Cloudflare CDN

3. X-Forwarded-For: Local dev fallback (first IP in chain)

4. request.client.host: Direct connection fallback
"""

import hashlib

from fastapi import Request
from fastapi.responses import JSONResponse
from server.rate_limiter import SQLiteRateLimiter

from config import config, get_logger

logger = get_logger(__name__)


async def rate_limit_middleware(
    request: Request, call_next, rate_limiter: SQLiteRateLimiter
):
    """Check rate limits for API endpoints"""
    # IP Detection - prioritize SSR auth over CF-Connecting-IP
    # (Cloudflare Pages requests have CF-Connecting-IP set to Cloudflare's IP, not user's)
    cf_ip = request.headers.get("CF-Connecting-IP")
    xff_ip = request.headers.get("X-Forwarded-Client-IP")
    ssr_auth = request.headers.get("X-SSR-Auth")

    client_ip = None

    # 1. SSR auth takes priority (Cloudflare Pages forwards user IP)
    if xff_ip and ssr_auth and config.SSR_AUTH_SECRET:
        if ssr_auth == config.SSR_AUTH_SECRET:
            client_ip = xff_ip
        else:
            logger.warning("invalid SSR auth token")

    # 2. Fall back to CF-Connecting-IP (direct browser requests)
    if not client_ip and cf_ip:
        client_ip = cf_ip

    # 3. X-Forwarded-For fallback (local dev)
    if not client_ip:
        xff = request.headers.get("X-Forwarded-For", "")
        if xff:
            client_ip = xff.split(",")[0].strip()

    # 4. Direct connection fallback
    if not client_ip:
        client_ip = request.client.host if request.client else "unknown"

    # Hash IP for privacy
    client_ip_hash = hashlib.sha256(client_ip.encode()).hexdigest()[:16]
    request.state.client_ip_hash = client_ip_hash

    # Skip rate limiting for OPTIONS (CORS preflight)
    if request.method == "OPTIONS":
        return await call_next(request)

    # Whitelist health/metrics endpoints (no rate limiting)
    if request.url.path in ["/health", "/metrics", "/api/health", "/api/metrics"]:
        return await call_next(request)

    # Check rate limit (endpoint-aware: /api/events gets lighter limits)
    api_key = request.headers.get("X-API-Key")
    is_allowed, remaining, limit_info = rate_limiter.check_rate_limit(
        client_ip_hash, api_key, client_ip, request.url.path
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
