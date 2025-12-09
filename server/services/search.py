"""
Search service layer

Business logic for handling different search types
"""

from typing import cast, Dict, Any, List, Optional, TypedDict, Literal, Union
from typing_extensions import NotRequired
from difflib import get_close_matches
from database.db_postgres import Database
from server.services.meeting import get_meetings_with_items
from server.utils.geo import parse_city_state_input, get_state_abbreviation, get_state_full_name
from server.utils.vendor_urls import get_vendor_source_url, get_vendor_display_name

from config import get_logger

logger = get_logger(__name__)


class CityOption(TypedDict):
    """City option for ambiguous search results (multiple cities match)."""
    city_name: str
    state: str
    banana: str
    vendor: str
    display_name: str
    total_meetings: int
    meetings_with_packet: int
    summarized_meetings: int


class SearchSuccessResponse(TypedDict):
    """Response when search finds a city with meetings."""
    success: Literal[True]
    city_name: str
    state: str
    banana: str
    vendor: str
    vendor_display_name: str
    source_url: Optional[str]
    participation: Optional[Dict[str, Any]]
    meetings: List[Dict[str, Any]]
    cached: bool
    query: str
    type: str


class SearchNotFoundResponse(TypedDict):
    """Response when search doesn't find the city or finds city without meetings."""
    success: Literal[False]
    message: str
    query: str
    type: str
    meetings: List[Any]
    ambiguous: NotRequired[Literal[False]]
    city_name: NotRequired[str]
    state: NotRequired[str]
    banana: NotRequired[str]
    vendor: NotRequired[str]
    vendor_display_name: NotRequired[str]
    source_url: NotRequired[Optional[str]]
    participation: NotRequired[Optional[Dict[str, Any]]]
    cached: NotRequired[bool]


class SearchAmbiguousResponse(TypedDict):
    """Response when multiple cities match (user must select one)."""
    success: Literal[False]
    message: str
    query: str
    type: str
    ambiguous: Literal[True]
    city_options: List[CityOption]
    meetings: List[Any]


SearchResponse = Union[SearchSuccessResponse, SearchNotFoundResponse, SearchAmbiguousResponse]



async def handle_zipcode_search(zipcode: str, db: Database) -> SearchResponse:
    """Handle zipcode search with cache-first approach

    Returns city data with banana field which serves as the city_url.
    Example: "paloaltoCA" is both the city identifier and the URL path.
    Frontend uses: /{banana} for routing.
    """
    # Check database - CACHED ONLY
    city = await db.get_city(zipcode=zipcode)
    if not city:
        return cast(SearchResponse, {
            "success": False,
            "message": "We're not covering that area yet, but we're always expanding! Thanks for your interest - we'll prioritize cities with high demand.",
            "query": zipcode,
            "type": "zipcode",
            "meetings": [],
        })

    # Get cached meetings (include cancelled - frontend shows status badge)
    meetings = await db.get_meetings(bananas=[city.banana], limit=50, exclude_cancelled=False)

    if meetings:
        logger.info(
            "found cached meetings",
            count=len(meetings),
            city=city.name,
            state=city.state
        )

        meetings_with_items = await get_meetings_with_items(meetings, db)

        return cast(SearchResponse, {
            "success": True,
            "city_name": city.name,
            "state": city.state,
            "banana": city.banana,
            "vendor": city.vendor,
            "vendor_display_name": get_vendor_display_name(city.vendor),
            "source_url": get_vendor_source_url(city.vendor, city.slug),
            "participation": city.participation,
            "meetings": meetings_with_items,
            "cached": True,
            "query": zipcode,
            "type": "zipcode",
        })

    # No cached meetings - background processor will handle this
    return cast(SearchResponse, {
        "success": True,
        "city_name": city.name,
        "state": city.state,
        "banana": city.banana,
        "vendor": city.vendor,
        "vendor_display_name": get_vendor_display_name(city.vendor),
        "source_url": get_vendor_source_url(city.vendor, city.slug),
        "participation": city.participation,
        "meetings": [],
        "cached": False,
        "query": zipcode,
        "type": "zipcode",
        "message": f"No meetings available yet for {city.name} - check back soon as we sync with the city website",
    })


async def handle_city_search(city_input: str, db: Database) -> SearchResponse:
    """Handle city name search with cache-first approach and ambiguous city handling

    Returns city data with banana field which serves as the city_url.
    Example: "paloaltoCA" is both the city identifier and the URL path.
    Frontend uses: /{banana} for routing.
    """
    # Parse city, state
    city_name, state = parse_city_state_input(city_input)

    if not state:
        # No state provided - check for ambiguous cities
        return await handle_ambiguous_city_search(city_name, city_input, db)

    # Check database - CACHED ONLY
    city = await db.get_city(name=city_name, state=state)
    if not city:
        # Record demand for this city
        requested_banana = f"{city_name.lower().replace(' ', '')}{state.upper()}"
        try:
            await db.userland.record_city_request(requested_banana)
            logger.info("city request recorded", banana=requested_banana)
        except Exception as e:
            logger.warning("failed to record city request", banana=requested_banana, error=str(e))

        return cast(SearchResponse, {
            "success": False,
            "message": f"We're not covering {city_name}, {state} yet, but we're always expanding! Your interest has been noted - we prioritize cities with high demand.",
            "query": city_input,
            "type": "city_name",
            "meetings": [],
        })

    # Get cached meetings (include cancelled - frontend shows status badge)
    meetings = await db.get_meetings(bananas=[city.banana], limit=50, exclude_cancelled=False)

    if meetings:
        logger.info("found cached meetings for city", count=len(meetings), city=city_name, state=state)

        meetings_with_items = await get_meetings_with_items(meetings, db)

        return cast(SearchResponse, {
            "success": True,
            "city_name": city.name,
            "state": city.state,
            "banana": city.banana,
            "vendor": city.vendor,
            "vendor_display_name": get_vendor_display_name(city.vendor),
            "source_url": get_vendor_source_url(city.vendor, city.slug),
            "participation": city.participation,
            "meetings": meetings_with_items,
            "cached": True,
            "query": city_input,
            "type": "city",
        })

    # No cached meetings - return empty
    return cast(SearchResponse, {
        "success": False,
        "city_name": city.name,
        "state": city.state,
        "banana": city.banana,
        "vendor": city.vendor,
        "vendor_display_name": get_vendor_display_name(city.vendor),
        "source_url": get_vendor_source_url(city.vendor, city.slug),
        "participation": city.participation,
        "meetings": [],
        "cached": True,
        "query": city_input,
        "type": "city",
        "message": f"No meetings cached yet for {city_name}, {state}, please check back soon!",
    })


async def handle_state_search(state_input: str, db: Database) -> SearchResponse:
    """Handle state search - return list of cities in that state"""
    # Normalize state input
    state_abbr = get_state_abbreviation(state_input)
    state_full = get_state_full_name(state_input)

    if not state_abbr:
        return cast(SearchResponse, {
            "success": False,
            "message": f"'{state_input}' is not a recognized state.",
            "query": state_input,
            "type": "state",
            "meetings": [],
        })

    # Get all cities in this state
    cities = await db.get_cities(state=state_abbr)

    if not cities:
        return cast(SearchResponse, {
            "success": False,
            "message": f"We don't have any cities in {state_full} yet, but we're always expanding!",
            "query": state_input,
            "type": "state",
            "meetings": [],
        })

    # Convert cities to the format expected by frontend
    city_options = []
    bananas = [city.banana for city in cities]

    # Build city_options
    for city in cities:
        city_options.append(
            {
                "city_name": city.name,
                "state": city.state,
                "banana": city.banana,
                "vendor": city.vendor,
                "display_name": f"{city.name}, {city.state}",
            }
        )

    # Get meeting stats for all cities in one query
    stats = await db.get_city_meeting_stats(bananas)

    # Add stats to each city option
    for option in city_options:
        city_stats = stats.get(
            option["banana"],
            {"total_meetings": 0, "meetings_with_packet": 0, "summarized_meetings": 0},
        )
        option["total_meetings"] = city_stats["total_meetings"]
        option["meetings_with_packet"] = city_stats["meetings_with_packet"]
        option["summarized_meetings"] = city_stats["summarized_meetings"]

    return {
        "success": False,  # User needs to select a city (ambiguous result)
        "message": f"Found {len(city_options)} cities in {state_full} -- [<span style='color: #64748b'>total</span> | <span style='color: #4f46e5'>with packet</span> | <span style='color: #10b981'>summarized</span>]\n\nSelect a city to view its meetings:",
        "query": state_input,
        "type": "state",
        "ambiguous": True,  # Indicates city selection required (reuse ambiguous UI)
        "city_options": city_options,
        "meetings": [],  # No meetings at state level, only city options
    }


async def handle_ambiguous_city_search(
    city_name: str, original_input: str, db: Database
) -> SearchResponse:
    """Handle city search when no state is provided - check for ambiguous matches"""

    # Look for all cities with this name (exact match, no zipcodes needed)
    cities = await db.get_cities(name=city_name)

    # If no exact match, try fuzzy matching to handle typos
    if not cities:
        # Lightweight query: just city names, no full objects, no zipcodes N+1
        all_names = await db.get_city_names()

        # Find close matches (cutoff=0.8 means 80% similarity required)
        close_matches = get_close_matches(city_name.lower(), [n.lower() for n in all_names], n=5, cutoff=0.8)

        if close_matches:
            # Prefer exact case-insensitive match if present in fuzzy results
            exact_match = next(
                (m for m in close_matches if m.lower() == city_name.lower()), None
            )
            if exact_match:
                close_matches = [exact_match]

            # Get cities matching the fuzzy results (no zipcodes needed)
            fuzzy_cities = []
            for match in close_matches:
                matched_cities = await db.get_cities(name=match)
                fuzzy_cities.extend(matched_cities)

            if fuzzy_cities:
                cities = fuzzy_cities
                logger.info("fuzzy match found", query=city_name, matches=[c.name for c in cities])

    if not cities:
        # Record demand - use generic banana without state (user didn't provide state)
        requested_banana = f"{city_name.lower().replace(' ', '')}UNKNOWN"
        try:
            await db.userland.record_city_request(requested_banana)
            logger.info("city request recorded (no state)", banana=requested_banana)
        except Exception as e:
            logger.warning("failed to record city request", banana=requested_banana, error=str(e))

        return {
            "success": False,
            "message": f"We don't have '{city_name}' in our database yet. Please include the state (e.g., '{city_name}, CA') - your interest has been noted!",
            "query": original_input,
            "type": "city",
            "meetings": [],
            "ambiguous": False,
        }

    if len(cities) == 1:
        # Only one match - proceed with this city
        city = cities[0]

        # Get meetings for this city (include cancelled - frontend shows status badge)
        meetings = await db.get_meetings(bananas=[city.banana], limit=50, exclude_cancelled=False)

        if meetings:
            logger.info(
                f"Found {len(meetings)} cached meetings for {city.name}, {city.state}"
            )

            meetings_with_items = await get_meetings_with_items(meetings, db)

            return {
                "success": True,
                "city_name": city.name,
                "state": city.state,
                "banana": city.banana,
                "vendor": city.vendor,
                "vendor_display_name": get_vendor_display_name(city.vendor),
                "source_url": get_vendor_source_url(city.vendor, city.slug),
                "participation": city.participation,
                "meetings": meetings_with_items,
                "cached": True,
                "query": original_input,
                "type": "city",
                "ambiguous": False,
            }
        else:
            return {
                "success": False,
                "city_name": city.name,
                "state": city.state,
                "banana": city.banana,
                "vendor": city.vendor,
                "vendor_display_name": get_vendor_display_name(city.vendor),
                "source_url": get_vendor_source_url(city.vendor, city.slug),
                "participation": city.participation,
                "meetings": [],
                "cached": True,
                "query": original_input,
                "type": "city",
                "message": f"No meetings cached yet for {city.name}, {city.state}, please check back soon!",
                "ambiguous": False,
            }

    # Multiple matches - return ambiguous result
    city_options = []
    bananas = [city.banana for city in cities]

    # Build city_options
    for city in cities:
        city_options.append(
            {
                "city_name": city.name,
                "state": city.state,
                "banana": city.banana,
                "vendor": city.vendor,
                "display_name": f"{city.name}, {city.state}",
            }
        )

    # Get meeting stats for all cities in one query
    stats = await db.get_city_meeting_stats(bananas)

    # Add stats to each city option
    for option in city_options:
        city_stats = stats.get(
            option["banana"],
            {"total_meetings": 0, "meetings_with_packet": 0, "summarized_meetings": 0},
        )
        option["total_meetings"] = city_stats["total_meetings"]
        option["meetings_with_packet"] = city_stats["meetings_with_packet"]
        option["summarized_meetings"] = city_stats["summarized_meetings"]

    return {
        "success": False,
        "message": f"Multiple cities named '{city_name}' found. Please specify which one:",
        "query": original_input,
        "type": "city",
        "ambiguous": True,
        "city_options": city_options,
        "meetings": [],
    }
