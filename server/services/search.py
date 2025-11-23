"""
Search service layer

Business logic for handling different search types
"""

from typing import Dict, Any
from difflib import get_close_matches
from database.db import UnifiedDatabase
from server.services.meeting import get_meetings_with_items
from server.utils.geo import parse_city_state_input, get_state_abbreviation, get_state_full_name
from server.utils.vendor_urls import get_vendor_source_url, get_vendor_display_name

from config import get_logger

logger = get_logger(__name__)



async def handle_zipcode_search(zipcode: str, db: UnifiedDatabase) -> Dict[str, Any]:
    """Handle zipcode search with cache-first approach

    Returns city data with banana field which serves as the city_url.
    Example: "paloaltoCA" is both the city identifier and the URL path.
    Frontend uses: /{banana} for routing.
    """
    # Check database - CACHED ONLY
    city = await db.get_city(zipcode=zipcode)
    if not city:
        return {
            "success": False,
            "message": "We're not covering that area yet, but we're always expanding! Thanks for your interest - we'll prioritize cities with high demand.",
            "query": zipcode,
            "type": "zipcode",
            "meetings": [],
        }

    # Get cached meetings (include cancelled - frontend shows status badge)
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
            "meetings": meetings_with_items,
            "cached": True,
            "query": zipcode,
            "type": "zipcode",
        }

    # No cached meetings - background processor will handle this
    return {
        "success": True,
        "city_name": city.name,
        "state": city.state,
        "banana": city.banana,
        "vendor": city.vendor,
        "vendor_display_name": get_vendor_display_name(city.vendor),
        "source_url": get_vendor_source_url(city.vendor, city.slug),
        "meetings": [],
        "cached": False,
        "query": zipcode,
        "type": "zipcode",
        "message": f"No meetings available yet for {city.name} - check back soon as we sync with the city website",
    }


async def handle_city_search(city_input: str, db: UnifiedDatabase) -> Dict[str, Any]:
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
        return {
            "success": False,
            "message": f"We're not covering {city_name}, {state} yet, but we're always expanding! Your interest has been noted - we prioritize cities with high demand.",
            "query": city_input,
            "type": "city_name",
            "meetings": [],
        }

    # Get cached meetings (include cancelled - frontend shows status badge)
    meetings = await db.get_meetings(bananas=[city.banana], limit=50, exclude_cancelled=False)

    if meetings:
        logger.info(f"Found {len(meetings)} cached meetings for {city_name}, {state}")

        meetings_with_items = await get_meetings_with_items(meetings, db)

        return {
            "success": True,
            "city_name": city.name,
            "state": city.state,
            "banana": city.banana,
            "vendor": city.vendor,
            "vendor_display_name": get_vendor_display_name(city.vendor),
            "source_url": get_vendor_source_url(city.vendor, city.slug),
            "meetings": meetings_with_items,
            "cached": True,
            "query": city_input,
            "type": "city",
        }

    # No cached meetings - return empty
    return {
        "success": False,
        "city_name": city.name,
        "state": city.state,
        "banana": city.banana,
        "vendor": city.vendor,
        "vendor_display_name": get_vendor_display_name(city.vendor),
        "source_url": get_vendor_source_url(city.vendor, city.slug),
        "meetings": [],
        "cached": True,
        "query": city_input,
        "type": "city",
        "message": f"No meetings cached yet for {city_name}, {state}, please check back soon!",
    }


async def handle_state_search(state_input: str, db: UnifiedDatabase) -> Dict[str, Any]:
    """Handle state search - return list of cities in that state"""
    # Normalize state input
    state_abbr = get_state_abbreviation(state_input)
    state_full = get_state_full_name(state_input)

    if not state_abbr:
        return {
            "success": False,
            "message": f"'{state_input}' is not a recognized state.",
            "query": state_input,
            "type": "state",
            "meetings": [],
        }

    # Get all cities in this state
    cities = await db.get_cities(state=state_abbr)

    if not cities:
        return {
            "success": False,
            "message": f"We don't have any cities in {state_full} yet, but we're always expanding!",
            "query": state_input,
            "type": "state",
            "meetings": [],
        }

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
    city_name: str, original_input: str, db: UnifiedDatabase
) -> Dict[str, Any]:
    """Handle city search when no state is provided - check for ambiguous matches"""

    # Look for all cities with this name (exact match)
    cities = await db.get_cities(name=city_name)

    # If no exact match, try fuzzy matching to handle typos
    if not cities:
        # Get all active city names from database
        all_cities = await db.get_cities()  # Gets all active cities
        city_names = [city.name.lower() for city in all_cities]

        # Find close matches (cutoff=0.7 means 70% similarity required)
        close_matches = get_close_matches(city_name.lower(), city_names, n=5, cutoff=0.7)

        if close_matches:
            # Get cities matching the fuzzy results
            fuzzy_cities = []
            for match in close_matches:
                matched_cities = await db.get_cities(name=match.title())
                fuzzy_cities.extend(matched_cities)

            if fuzzy_cities:
                cities = fuzzy_cities
                logger.info(f"Fuzzy match: '{city_name}' -> {[c.name for c in cities]}")

    if not cities:
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
