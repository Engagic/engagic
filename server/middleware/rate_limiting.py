"""
Rate limiting middleware
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
    """Check rate limits for API endpoints with tier support"""
    # Get real client IP from trusted proxy headers (priority order)
    # X-Forwarded-User-IP: Set by our Cloudflare Worker for SSR requests (highest priority)
    # CF-Connecting-IP: Set by Cloudflare for direct API requests
    # X-Real-IP: Set by nginx
    # X-Forwarded-For: Standard proxy header (take leftmost/original client)
    # Fallback: request.client.host
    client_ip_raw = (
        request.headers.get("X-Forwarded-User-IP")
        or request.headers.get("CF-Connecting-IP")
        or request.headers.get("X-Real-IP")
        or (request.headers.get("X-Forwarded-For", "").split(",")[0].strip() if request.headers.get("X-Forwarded-For") else None)
        or (request.client.host if request.client else "unknown")
    )

    # Hash IP for privacy (GDPR-friendly, can't reverse to get real IP)
    # Same user = same hash = consistent rate limiting
    # Use first 16 chars of SHA-256 hash for brevity
    client_ip_hash = hashlib.sha256(client_ip_raw.encode()).hexdigest()[:16]

    # Store hash in request state for route handlers to access
    request.state.client_ip_hash = client_ip_hash

    # Skip rate limiting for OPTIONS requests (CORS preflight)
    if request.method == "OPTIONS":
        response = await call_next(request)
        return response

    # Apply rate limiting to ALL requests (not just /api/)
    # Scanners bypass /api/ check by hitting root, /login.php, etc.
    should_rate_limit = True

    # Whitelist monitoring endpoints (Prometheus scraping + health checks)
    if request.url.path in ["/health", "/metrics", "/api/health", "/api/metrics"]:
        should_rate_limit = False

    if should_rate_limit:
        # Get API key from header (optional, for future use)
        api_key = request.headers.get("X-API-Key")

        is_allowed, remaining, limit_info = rate_limiter.check_rate_limit(
            client_ip_hash, api_key, client_ip_raw, client_ip_raw
        )

        if not is_allowed:
            limit_type = limit_info.get("limit_type", "unknown")
            tier = limit_info.get("tier", "basic")

            # Log endpoint being accessed for debugging
            endpoint = f"{request.method} {request.url.path}"
            logger.warning(
                f"Rate limit exceeded for {client_ip_hash} (hashed) - tier: {tier}, limit: {limit_type}, endpoint: {endpoint}"
            )

            # Handle temp ban separately
            if limit_type == "temp_ban":
                remaining_seconds = limit_info.get("remaining_seconds", 0)
                ban_message = limit_info.get("message", "Temporarily banned")

                return JSONResponse(
                    status_code=403,
                    content={
                        "error": "Temporarily banned",
                        "message": ban_message,
                        "ban_remaining_seconds": remaining_seconds,
                        "reason": "Excessive rate limit violations - progressive penalty applied"
                    },
                    headers={
                        "Retry-After": str(remaining_seconds),
                        "X-Ban-Until": str(limit_info.get("ban_until", 0)),
                        "Access-Control-Allow-Origin": request.headers.get("origin", "*"),
                        "Access-Control-Allow-Credentials": "true",
                        "Access-Control-Allow-Methods": "*",
                        "Access-Control-Allow-Headers": "*",
                    }
                )

            # Construct graduated messaging based on limit type
            if limit_type == "daily":
                # Hard boundary - need to upgrade or self-host
                message = (
                    f"You've reached your daily limit ({limit_info['day_limit']} requests/day). "
                    f"Resets at midnight UTC. To continue today, you'll need higher access."
                )
                friendly_tone = False
            else:
                # Soft boundary - suggest donation, can continue after waiting
                message = (
                    f"Whoa, you're using this a lot! You've hit the per-minute limit "
                    f"({limit_info['minute_limit']}/min). Wait a moment and you can continue."
                )
                friendly_tone = True

            # Build response based on limit type (graduated approach)
            origin = request.headers.get("origin", "*")

            # Minute limit: friendly, donation-first
            if friendly_tone:
                content = {
                    "error": "Rate limit exceeded",
                    "message": message,
                    "current_tier": tier,
                    "limit_type": limit_type,
                    "limits": {
                        "minute": limit_info.get("minute_limit"),
                        "daily": limit_info.get("day_limit")
                    },
                    "suggestion": (
                        "Looks like you're finding this useful! Engagic is a public good project "
                        "that costs real money to run (~$5 per 1,000 items for LLM processing). "
                        "Consider supporting us:"
                    ),
                    "support": {
                        "donate": {
                            "url": "https://engagic.org/donate",
                            "message": "Help keep this free for everyone"
                        },
                        "self_host": {
                            "repo": "https://github.com/Engagic/engagic",
                            "license": "AGPL-3.0",
                            "message": "Run your own instance, unlimited access"
                        },
                        "nonprofit": {
                            "contact": "hello@engagic.org",
                            "message": "Nonprofit or journalist? We have a free tier with higher limits."
                        },
                        "commercial": {
                            "contact": "admin@motioncount.com",
                            "message": "Commercial use? Let's discuss pricing."
                        }
                    },
                    "retry_after_seconds": 60
                }
            # Daily limit: firmer, upgrade-focused
            else:
                content = {
                    "error": "Daily limit reached",
                    "message": message,
                    "current_tier": tier,
                    "limit_type": limit_type,
                    "limits": {
                        "minute": limit_info.get("minute_limit"),
                        "daily": limit_info.get("day_limit")
                    },
                    "next_steps": (
                        "You're a power user! The free tier is designed for casual use. "
                        "To continue with higher limits, choose an option below:"
                    ),
                    "options": {
                        "self_host": {
                            "limits": "Unlimited",
                            "cost": "Your infrastructure costs (~$5/1k items)",
                            "license": "AGPL-3.0",
                            "repo": "https://github.com/Engagic/engagic",
                            "message": "Best for developers and heavy users"
                        },
                        "nonprofit_tier": {
                            "limits": "100/min, 5,000/day",
                            "cost": "Free with attribution",
                            "requirements": "501(c)(3) status or press credentials",
                            "contact": "hello@engagic.org"
                        },
                        "commercial_tier": {
                            "limits": "Negotiable (1k+/min, 100k+/day)",
                            "cost": "Contact for pricing",
                            "contact": "admin@motioncount.com",
                            "message": "For commercial use and heavy API integration"
                        }
                    },
                    "donate": {
                        "url": "https://engagic.org/donate",
                        "message": "Or support this public good with a donation"
                    },
                    "attribution_note": (
                        "Engagic provides thorough attribution and links to source documents. "
                        "We ask the same courtesy from users."
                    ),
                    "terms": "https://engagic.org/terms"
                }

            return JSONResponse(
                status_code=429,
                content=content,
                headers={
                    "X-RateLimit-Remaining": "0",
                    "X-RateLimit-Tier": tier,
                    "X-RateLimit-Type": limit_type,
                    "Retry-After": "3600" if limit_type == "daily" else "60",
                    "Access-Control-Allow-Origin": origin,
                    "Access-Control-Allow-Credentials": "true",
                    "Access-Control-Allow-Methods": "*",
                    "Access-Control-Allow-Headers": "*",
                },
            )

        # Add rate limit headers to successful responses
        response = await call_next(request)
        response.headers["X-RateLimit-Remaining-Minute"] = str(limit_info.get("remaining_minute", 0))
        response.headers["X-RateLimit-Remaining-Daily"] = str(limit_info.get("remaining_daily", 0))
        response.headers["X-RateLimit-Tier"] = limit_info.get("tier", "basic")
        return response

    response = await call_next(request)
    return response
