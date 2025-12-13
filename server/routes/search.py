"""Search API routes."""

from fastapi import APIRouter, HTTPException, Depends, Request

from config import get_logger
from database.db_postgres import Database
from server.dependencies import get_db
from server.metrics import metrics
from server.models.requests import SearchRequest
from server.services.search import (
    handle_city_search,
    handle_state_search,
    handle_zipcode_search,
)
from server.utils.geo import is_state_query
from server.utils.text import extract_context, strip_markdown
from server.utils.validation import require_city

logger = get_logger(__name__)

router = APIRouter(prefix="/api")


@router.post("/search")
async def search_meetings(search_request: SearchRequest, request: Request, db: Database = Depends(get_db)):
    """Single endpoint for all meeting searches - handles zipcode or city name"""
    try:
        query = search_request.query.strip()
        if not query:
            raise HTTPException(status_code=400, detail="Search query cannot be empty")

        request.state.search_query = query
        client_hash = getattr(request.state, 'client_ip_hash', 'unknown')
        logger.debug("search request", query=query, user=client_hash)

        # Special case: "new york" or "new york city" -> NYC (not the state)
        query_lower = query.lower()
        if query_lower in ["new york", "new york city"]:
            logger.debug("nyc redirect")
            return await handle_city_search("new york, ny", db)

        # Determine if input is zipcode, state, or city name
        # Normalize zipcode: strip dashes/spaces (users type "85-635" or "85 635")
        zipcode_cleaned = query.replace("-", "").replace(" ", "")
        is_zipcode = zipcode_cleaned.isdigit() and len(zipcode_cleaned) == 5
        is_state = is_state_query(query)

        logger.debug("query analysis", is_zipcode=is_zipcode, is_state=is_state)

        # Track search behavior metrics
        metrics.page_views.labels(page_type='search').inc()

        if is_zipcode:
            metrics.search_queries.labels(query_type='zipcode').inc()
            return await handle_zipcode_search(zipcode_cleaned, db)
        elif is_state:
            metrics.search_queries.labels(query_type='state').inc()
            return await handle_state_search(query, db)
        else:
            metrics.search_queries.labels(query_type='city_name').inc()
            return await handle_city_search(query, db)

    except HTTPException:
        raise
    except Exception:
        logger.exception("search error")
        raise HTTPException(
            status_code=500,
            detail="We're having trouble loading search results. If this city matters to you, watch it to ensure priority weekly syncing."
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

    await require_city(db, banana)

    logger.debug("city item search", banana=banana, query=query)

    try:
        results = await db.search.search_items_fulltext(query, banana=banana, limit=limit)
    except Exception:
        logger.exception("city item search error", banana=banana)
        raise HTTPException(status_code=500, detail="Search failed")

    for result in results:
        context_headline = result.get("context_headline")
        if context_headline:
            result["context"] = strip_markdown(context_headline)
        else:
            context_source = result.get("summary") or result.get("item_title") or ""
            result["context"] = strip_markdown(extract_context(context_source, query))

    metrics.search_queries.labels(query_type='city_meetings').inc()

    return {
        "success": True,
        "query": query,
        "banana": banana,
        "results": results,
        "total": len(results)
    }
