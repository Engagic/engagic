"""
Frontend Analytics Events Endpoint

Receives anonymous event data from the frontend and records to Prometheus counters.
Privacy-first design: no IP storage, no PII, aggregate metrics only.

Usage:
    POST /api/events
    {"event": "signup_view", "properties": {"source": "homepage"}}

Confidence: 8/10 - Simple event ingestion pattern
"""

from fastapi import APIRouter
from pydantic import BaseModel

from config import get_logger
from server.metrics import metrics, get_funnel_stats

logger = get_logger(__name__)

router = APIRouter(prefix="/api", tags=["events"])


class FrontendEvent(BaseModel):
    """Frontend analytics event payload"""
    event: str
    properties: dict | None = None


EVENT_HANDLERS = {
    # Search funnel
    "search_success": lambda p: metrics.search_queries.labels(query_type="success").inc(),
    "search_not_found": lambda p: metrics.search_queries.labels(query_type="not_found").inc(),
    "search_ambiguous": lambda p: metrics.search_queries.labels(query_type="ambiguous").inc(),

    # Signup funnel
    "signup_view": lambda p: metrics.page_views.labels(page_type="signup").inc(),
    "signup_submit": lambda p: metrics.matter_engagement.labels(action="signup").inc(),

    # Content engagement
    "flyer_click": lambda p: metrics.matter_engagement.labels(action="flyer_click").inc(),
    "deliberate_view": lambda p: metrics.page_views.labels(page_type="deliberate").inc(),
    "meeting_view": lambda p: metrics.page_views.labels(page_type="meeting_frontend").inc(),
    "item_expand": lambda p: metrics.matter_engagement.labels(action="item_expand").inc(),
    "matter_view": lambda p: metrics.matter_engagement.labels(action="matter_view").inc(),

    # Discovery features
    "random_meeting_click": lambda p: metrics.matter_engagement.labels(action="random_meeting").inc(),
    "random_policy_click": lambda p: metrics.matter_engagement.labels(action="random_policy").inc(),

    # Navigation
    "state_search": lambda p: metrics.search_queries.labels(query_type="state").inc(),
}


@router.post("/events")
async def track_event(event: FrontendEvent):
    """Receive frontend analytics events and record to Prometheus

    Privacy: No IP logging, no PII storage. Just increment aggregate counters.
    """
    handler = EVENT_HANDLERS.get(event.event)

    if handler:
        try:
            handler(event.properties or {})
        except Exception as e:
            # Log but don't fail - analytics shouldn't break UX
            logger.warning("event handler failed", event=event.event, error=str(e))
    else:
        # Unknown event - log for debugging but don't fail
        logger.debug("unknown frontend event", event=event.event)

    return {"ok": True}


@router.get("/funnel")
async def get_funnel():
    """User behavior funnel - simple stats for understanding what people use"""
    return get_funnel_stats()
