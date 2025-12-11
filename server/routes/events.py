"""
Frontend Analytics Events Endpoint

Receives anonymous event data and stores for journey analysis.
Events linked to IP hash (same as rate limiting) for user journey tracking.
Privacy: IP hashes are one-way, auto-deleted after 7 days.

Usage:
    POST /api/events
    {"event": "page_view", "url": "/raleighNC", "properties": {"referrer": "google"}}

Confidence: 8/10 - Simple event ingestion with journey storage
"""

import json
import time

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel

from config import get_logger
from database.db_postgres import Database
from server.dependencies import get_db
from server.metrics import metrics
from server.routes.admin import verify_admin_token

logger = get_logger(__name__)

router = APIRouter(prefix="/api", tags=["events"])

# DB cleanup interval (rate limiting handled by main limiter with endpoint-aware limits)
_last_cleanup_time: float = 0
CLEANUP_INTERVAL = 300  # Run DB cleanup every 5 minutes


async def _maybe_cleanup_old_events(db: Database):
    """Periodically cleanup events older than 7 days."""
    global _last_cleanup_time
    now = time.time()

    if now - _last_cleanup_time < CLEANUP_INTERVAL:
        return

    _last_cleanup_time = now

    try:
        result = await db.pool.execute(
            "DELETE FROM session_events WHERE created_at < NOW() - INTERVAL '7 days'"
        )
        # Log if significant cleanup happened
        if result and "DELETE" in result:
            deleted = result.split()[-1] if result else "0"
            if deleted != "0":
                logger.info("cleaned up old session events", deleted=deleted)
    except Exception as e:
        logger.warning("session events cleanup failed", error=str(e))


class FrontendEvent(BaseModel):
    """Frontend analytics event payload"""
    event: str
    url: str | None = None
    properties: dict | None = None


# Prometheus counter handlers (kept for backward compatibility)
EVENT_HANDLERS = {
    "search_success": lambda p: metrics.search_queries.labels(query_type="success").inc(),
    "search_not_found": lambda p: metrics.search_queries.labels(query_type="not_found").inc(),
    "search_ambiguous": lambda p: metrics.search_queries.labels(query_type="ambiguous").inc(),
    "signup_view": lambda p: metrics.page_views.labels(page_type="signup").inc(),
    "signup_submit": lambda p: metrics.matter_engagement.labels(action="signup").inc(),
    "flyer_click": lambda p: metrics.matter_engagement.labels(action="flyer_click").inc(),
    "deliberate_view": lambda p: metrics.page_views.labels(page_type="deliberate").inc(),
    "meeting_view": lambda p: metrics.page_views.labels(page_type="meeting_frontend").inc(),
    "item_expand": lambda p: metrics.matter_engagement.labels(action="item_expand").inc(),
    "matter_view": lambda p: metrics.matter_engagement.labels(action="matter_view").inc(),
    "random_meeting_click": lambda p: metrics.matter_engagement.labels(action="random_meeting").inc(),
    "random_policy_click": lambda p: metrics.matter_engagement.labels(action="random_policy").inc(),
    "state_search": lambda p: metrics.search_queries.labels(query_type="state").inc(),
    "page_view": lambda p: metrics.page_views.labels(page_type="frontend").inc(),
}


@router.post("/events")
async def track_event(
    event: FrontendEvent,
    request: Request,
    db: Database = Depends(get_db)
):
    """Receive frontend event and store for journey analysis.

    IP hash from rate limiting middleware links events to user journeys.
    Rate limited via main middleware (120/min for /api/events endpoint).
    """
    # Get IP hash from rate limiting middleware (set in request.state)
    ip_hash = getattr(request.state, "client_ip_hash", "unknown")

    # Periodic cleanup of old events
    await _maybe_cleanup_old_events(db)

    # Store event in database for journey tracking
    try:
        await db.pool.execute(
            """
            INSERT INTO session_events (ip_hash, event, url, properties)
            VALUES ($1, $2, $3, $4)
            """,
            ip_hash,
            event.event,
            event.url,
            json.dumps(event.properties) if event.properties else None
        )
    except Exception as e:
        # Log but don't fail - analytics shouldn't break UX
        logger.warning("failed to store event", event=event.event, error=str(e))

    # Also update Prometheus counters for aggregate metrics
    handler = EVENT_HANDLERS.get(event.event)
    if handler:
        try:
            handler(event.properties or {})
        except Exception as e:
            logger.warning("event handler failed", event=event.event, error=str(e))

    return {"ok": True}


@router.get("/funnel/journeys")
async def get_journeys(
    limit: int = Query(default=50, ge=1, le=200),
    hours: int = Query(default=24, ge=1, le=168),
    db: Database = Depends(get_db),
    _: bool = Depends(verify_admin_token)
):
    """Get recent user journeys for flow analysis.

    Returns events grouped by IP hash, showing what paths users take.
    """
    rows = await db.pool.fetch(
        """
        SELECT ip_hash, event, url, properties, created_at
        FROM session_events
        WHERE created_at > NOW() - ($1 || ' hours')::INTERVAL
        ORDER BY ip_hash, created_at
        """,
        str(hours)
    )

    # Group by ip_hash
    journeys: dict = {}
    for row in rows:
        ip = row["ip_hash"]
        if ip not in journeys:
            journeys[ip] = []
        journeys[ip].append({
            "event": row["event"],
            "url": row["url"],
            "properties": json.loads(row["properties"]) if row["properties"] else None,
            "at": row["created_at"].isoformat()
        })

    # Convert to list and limit
    journey_list = [
        {"ip_hash": ip, "events": events, "count": len(events)}
        for ip, events in journeys.items()
    ]
    journey_list.sort(key=lambda j: len(j["events"]), reverse=True)

    return {
        "hours": hours,
        "unique_users": len(journey_list),
        "journeys": journey_list[:limit]
    }


@router.get("/funnel/patterns")
async def get_patterns(
    hours: int = Query(default=24, ge=1, le=168),
    db: Database = Depends(get_db),
    _: bool = Depends(verify_admin_token)
):
    """Get common user flow patterns.

    Aggregates journeys to show most common paths through the site.
    """
    rows = await db.pool.fetch(
        """
        SELECT ip_hash, array_agg(event ORDER BY created_at) as path
        FROM session_events
        WHERE created_at > NOW() - ($1 || ' hours')::INTERVAL
        GROUP BY ip_hash
        """,
        str(hours)
    )

    # Count path patterns (first 5 events of each journey)
    patterns: dict = {}
    for row in rows:
        path = tuple(row["path"][:5])  # Truncate to first 5 events
        path_str = " -> ".join(path)
        patterns[path_str] = patterns.get(path_str, 0) + 1

    # Sort by frequency
    sorted_patterns = sorted(patterns.items(), key=lambda x: x[1], reverse=True)

    return {
        "hours": hours,
        "unique_users": len(rows),
        "patterns": [
            {"path": p, "count": c}
            for p, c in sorted_patterns[:20]
        ]
    }


@router.get("/funnel/dropoffs")
async def get_dropoffs(
    hours: int = Query(default=24, ge=1, le=168),
    db: Database = Depends(get_db),
    _: bool = Depends(verify_admin_token)
):
    """Identify where users drop off.

    Shows last event for each user session to identify abandonment points.
    """
    rows = await db.pool.fetch(
        """
        WITH last_events AS (
            SELECT DISTINCT ON (ip_hash)
                ip_hash, event, url, created_at
            FROM session_events
            WHERE created_at > NOW() - ($1 || ' hours')::INTERVAL
            ORDER BY ip_hash, created_at DESC
        )
        SELECT event, url, COUNT(*) as drop_count
        FROM last_events
        GROUP BY event, url
        ORDER BY drop_count DESC
        LIMIT 20
        """,
        str(hours)
    )

    return {
        "hours": hours,
        "dropoffs": [
            {"event": row["event"], "url": row["url"], "count": row["drop_count"]}
            for row in rows
        ]
    }
