"""Search API routes."""

from fastapi import APIRouter, HTTPException, Depends, Request
from server.models.requests import SearchRequest
from server.services.search import (
    handle_zipcode_search,
    handle_city_search,
    handle_state_search,
)
from server.utils.geo import is_state_query
from server.utils.text import extract_context
from server.metrics import metrics
from server.dependencies import get_db
from database.db_postgres import Database

from config import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/api")


@router.post("/search")
async def search_meetings(search_request: SearchRequest, request: Request, db: Database = Depends(get_db)):
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
            return await handle_city_search("new york, ny", db)

        # Determine if input is zipcode, state, or city name
        is_zipcode = query.isdigit() and len(query) == 5
        is_state = is_state_query(query)

        logger.debug("query analysis", is_zipcode=is_zipcode, is_state=is_state)

        # Track search behavior metrics
        metrics.page_views.labels(page_type='search').inc()

        if is_zipcode:
            metrics.search_queries.labels(query_type='zipcode').inc()
            return await handle_zipcode_search(query, db)
        elif is_state:
            metrics.search_queries.labels(query_type='state').inc()
            return await handle_state_search(query, db)
        else:
            metrics.search_queries.labels(query_type='city_name').inc()
            return await handle_city_search(query, db)

    except HTTPException:
        raise
    except Exception as e:
        logger.error("search error", error=str(e))
        raise HTTPException(
            status_code=500, detail="We humbly thank you for your patience"
        )


@router.get("/city/{banana}/search/meetings")
async def search_city_meetings(
    banana: str,
    q: str,
    limit: int = 50,
    db: Database = Depends(get_db)
):
    """Full-text search items within a city using PostgreSQL FTS.

    Returns item-level results with meeting context and highlighted snippets.
    Searches item title, summary, and matter_file.
    """
    query = q.strip()
    if not query:
        raise HTTPException(status_code=400, detail="Search query cannot be empty")

    city = await db.get_city(banana=banana)
    if not city:
        raise HTTPException(status_code=404, detail="City not found")

    logger.debug("city item search", banana=banana, query=query)

    try:
        results = await db.search.search_items_fulltext(query, banana=banana, limit=limit)
    except Exception as e:
        logger.error("city item search error", error=str(e), banana=banana)
        raise HTTPException(status_code=500, detail="Search failed")

    # Add context snippets to each result
    for result in results:
        # Try to extract context from summary first, then title
        context_source = result.get("summary") or result.get("item_title") or ""
        result["context"] = extract_context(context_source, query)

    metrics.search_queries.labels(query_type='city_meetings').inc()

    return {
        "success": True,
        "query": query,
        "banana": banana,
        "results": results,
        "count": len(results)
    }
