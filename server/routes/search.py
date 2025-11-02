"""
Search API routes
"""

import logging
from fastapi import APIRouter, HTTPException, Depends
from server.models.requests import SearchRequest
from server.services.search import (
    handle_zipcode_search,
    handle_city_search,
    handle_state_search,
)
from server.utils.geo import is_state_query
from database.db import UnifiedDatabase

logger = logging.getLogger("engagic")

router = APIRouter(prefix="/api")


def get_db():
    """Dependency to get database instance"""
    from config import config
    return UnifiedDatabase(config.UNIFIED_DB_PATH)


@router.post("/search")
async def search_meetings(request: SearchRequest, db: UnifiedDatabase = Depends(get_db)):
    """Single endpoint for all meeting searches - handles zipcode or city name"""
    try:
        query = request.query.strip()
        if not query:
            raise HTTPException(status_code=400, detail="Search query cannot be empty")

        logger.info(f"Search request: '{query}'")

        # Special case: "new york" or "new york city" -> NYC (not the state)
        query_lower = query.lower()
        if query_lower in ["new york", "new york city"]:
            logger.info("nyc redirect")
            return handle_city_search("new york, ny", db)

        # Determine if input is zipcode, state, or city name
        is_zipcode = query.isdigit() and len(query) == 5
        is_state = is_state_query(query)

        logger.info(f"Query analysis - is_zipcode: {is_zipcode}, is_state: {is_state}")

        if is_zipcode:
            return handle_zipcode_search(query, db)
        elif is_state:
            return handle_state_search(query, db)
        else:
            return handle_city_search(query, db)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Unexpected search error for '{query}': {str(e)}")
        raise HTTPException(
            status_code=500, detail="We humbly thank you for your patience"
        )
