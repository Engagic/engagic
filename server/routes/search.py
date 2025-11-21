"""
Search API routes
"""

from fastapi import APIRouter, HTTPException, Depends, Request
from server.models.requests import SearchRequest
from server.services.search import (
    handle_zipcode_search,
    handle_city_search,
    handle_state_search,
)
from server.utils.geo import is_state_query
from server.metrics import metrics
from database.db import UnifiedDatabase

from config import get_logger

logger = get_logger(__name__)


router = APIRouter(prefix="/api")


def get_db(request: Request) -> UnifiedDatabase:
    """Dependency to get shared database instance from app state"""
    return request.app.state.db


@router.post("/search")
async def search_meetings(search_request: SearchRequest, request: Request, db: UnifiedDatabase = Depends(get_db)):
    """Single endpoint for all meeting searches - handles zipcode or city name"""
    try:
        query = search_request.query.strip()
        if not query:
            raise HTTPException(status_code=400, detail="Search query cannot be empty")

        # Store query in request state for middleware logging
        request.state.search_query = query

        # Get client hash from middleware (set in rate_limiting.py)
        client_hash = getattr(request.state, 'client_ip_hash', 'unknown')
        logger.debug("search request", query=query, user=client_hash)

        # Special case: "new york" or "new york city" -> NYC (not the state)
        query_lower = query.lower()
        if query_lower in ["new york", "new york city"]:
            logger.debug("nyc redirect")
            return handle_city_search("new york, ny", db)

        # Determine if input is zipcode, state, or city name
        is_zipcode = query.isdigit() and len(query) == 5
        is_state = is_state_query(query)

        logger.debug("query analysis", is_zipcode=is_zipcode, is_state=is_state)

        # Track search behavior metrics
        metrics.page_views.labels(page_type='search').inc()

        if is_zipcode:
            metrics.search_queries.labels(query_type='zipcode').inc()
            return handle_zipcode_search(query, db)
        elif is_state:
            metrics.search_queries.labels(query_type='state').inc()
            return handle_state_search(query, db)
        else:
            metrics.search_queries.labels(query_type='city_name').inc()
            return handle_city_search(query, db)

    except HTTPException:
        raise
    except Exception as e:
        logger.error("search error", error=str(e))
        raise HTTPException(
            status_code=500, detail="We humbly thank you for your patience"
        )
