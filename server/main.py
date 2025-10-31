from fastapi import FastAPI, HTTPException, Request, Depends, Header
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, validator
from typing import Optional, Dict, Any
import logging
import time
import uuid
import re
from datetime import datetime
from pipeline.processor import AgendaProcessor
from database.db import UnifiedDatabase
from server.rate_limiter import SQLiteRateLimiter
from uszipcode import SearchEngine
from config import config

# Configure structured logging
logging.basicConfig(
    level=getattr(logging, config.LOG_LEVEL),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(), logging.FileHandler(config.LOG_PATH, mode="a")],
)
logger = logging.getLogger("engagic")

app = FastAPI(title="engagic API", description="EGMI")

# CORS configured below after config import

# Persistent rate limiter with SQLite
rate_limiter = SQLiteRateLimiter(
    db_path=str(config.UNIFIED_DB_PATH).replace("engagic.db", "rate_limits.db"),
    requests_limit=config.RATE_LIMIT_REQUESTS,
    window_seconds=config.RATE_LIMIT_WINDOW,
)


# Rate limiting middleware
@app.middleware("http")
async def rate_limit_middleware(request: Request, call_next):
    client_ip = request.client.host if request.client else "unknown"

    # Check rate limit for API endpoints
    if request.url.path.startswith("/api/"):
        is_allowed, remaining = rate_limiter.check_rate_limit(client_ip)

        if not is_allowed:
            logger.warning(f"Rate limit exceeded for {client_ip}")
            raise HTTPException(
                status_code=429,
                detail="Rate limit exceeded. Please try again later.",
                headers={"X-RateLimit-Remaining": "0"},
            )

    response = await call_next(request)
    return response


# Request/Response logging middleware
@app.middleware("http")
async def log_requests(request: Request, call_next):
    request_id = str(uuid.uuid4())[:8]
    start_time = time.time()

    # Log incoming request
    logger.info(
        f"[{request_id}] {request.method} {request.url.path} - Client: {request.client.host if request.client else 'unknown'}"
    )

    # Process request
    try:
        response = await call_next(request)
        duration = time.time() - start_time

        # Log response
        logger.info(
            f"[{request_id}] Response: {response.status_code} - Duration: {duration:.3f}s"
        )
        return response

    except Exception as e:
        duration = time.time() - start_time
        logger.error(f"[{request_id}] Error: {str(e)} - Duration: {duration:.3f}s")
        raise


app.add_middleware(
    CORSMiddleware,
    allow_origins=config.ALLOWED_ORIGINS,
    allow_methods=["*"],
    allow_headers=["*"],
    allow_credentials=True,
)

# Initialize global instances
try:
    processor = AgendaProcessor(api_key=config.get_api_key())
    logger.info("LLM processor initialized successfully")
except ValueError:
    logger.warning("API key not found - LLM processing will be disabled")
    processor = None

# Initialize unified database
db = UnifiedDatabase(config.UNIFIED_DB_PATH)
zipcode_search = SearchEngine()


def normalize_city_name(city_name: str) -> str:
    """Normalize city name for consistent formatting"""
    city = city_name.strip()

    # Handle special cases where simple title() doesn't work well
    special_cases = {
        "lasvegas": "Las Vegas",
        "newyork": "New York",
        "losangeles": "Los Angeles",
        "sanfrancisco": "San Francisco",
        "sanjose": "San Jose",
        "sandiego": "San Diego",
        "santaana": "Santa Ana",
        "santabarbara": "Santa Barbara",
        "stlouis": "St. Louis",
        "stpaul": "St. Paul",
        "ftworth": "Fort Worth",
        "fortworth": "Fort Worth",
    }

    city_lower_nospace = city.lower().replace(" ", "").replace(".", "")
    if city_lower_nospace in special_cases:
        return special_cases[city_lower_nospace]

    # Default to title case
    return city.title()


def parse_city_state_input(input_str: str) -> tuple[str, str]:
    """Parse city, state from user input

    Handles formats like:
    - "Palo Alto, CA"
    - "Palo Alto, California"
    - "Boston Massachusetts"
    - "New York NY"
    - "lasvegas nevada" (normalizes to "Las Vegas, NV")

    Returns: (city_name, state_abbreviation)
    """
    input_str = input_str.strip()

    # Common state name to abbreviation mapping
    state_map = {
        "alabama": "AL",
        "alaska": "AK",
        "arizona": "AZ",
        "arkansas": "AR",
        "california": "CA",
        "colorado": "CO",
        "connecticut": "CT",
        "delaware": "DE",
        "florida": "FL",
        "georgia": "GA",
        "hawaii": "HI",
        "idaho": "ID",
        "illinois": "IL",
        "indiana": "IN",
        "iowa": "IA",
        "kansas": "KS",
        "kentucky": "KY",
        "louisiana": "LA",
        "maine": "ME",
        "maryland": "MD",
        "massachusetts": "MA",
        "michigan": "MI",
        "minnesota": "MN",
        "mississippi": "MS",
        "missouri": "MO",
        "montana": "MT",
        "nebraska": "NE",
        "nevada": "NV",
        "new hampshire": "NH",
        "new jersey": "NJ",
        "new mexico": "NM",
        "new york": "NY",
        "north carolina": "NC",
        "north dakota": "ND",
        "ohio": "OH",
        "oklahoma": "OK",
        "oregon": "OR",
        "pennsylvania": "PA",
        "rhode island": "RI",
        "south carolina": "SC",
        "south dakota": "SD",
        "tennessee": "TN",
        "texas": "TX",
        "utah": "UT",
        "vermont": "VT",
        "virginia": "VA",
        "washington": "WA",
        "west virginia": "WV",
        "wisconsin": "WI",
        "wyoming": "WY",
    }

    # Try comma-separated format first: "City, State"
    if "," in input_str:
        parts = [p.strip() for p in input_str.split(",")]
        if len(parts) == 2:
            city, state = parts
            state_lower = state.lower()

            # Check if it's already an abbreviation
            if len(state) == 2 and state.upper() in state_map.values():
                return normalize_city_name(city), state.upper()
            # Check if it's a full state name
            elif state_lower in state_map:
                return normalize_city_name(city), state_map[state_lower]

    # Try space-separated format: "City State" or "City Full State Name"
    words = input_str.split()
    if len(words) >= 2:
        # Try last word as state abbreviation
        last_word = words[-1].lower()
        if len(last_word) == 2 and last_word.upper() in state_map.values():
            city = " ".join(words[:-1]).strip()
            return normalize_city_name(city), last_word.upper()

        # Try last 1-2 words as full state name
        for num_state_words in [2, 1]:
            if len(words) > num_state_words:
                potential_state = " ".join(words[-num_state_words:]).lower()
                if potential_state in state_map:
                    city = " ".join(words[:-num_state_words]).strip()
                    return normalize_city_name(city), state_map[potential_state]

    # No state found
    return input_str, ""


def is_state_query(query: str) -> bool:
    """Check if the query is just a state name or abbreviation"""
    query_lower = query.strip().lower()

    # State abbreviation map
    state_map = {
        "alabama": "AL",
        "alaska": "AK",
        "arizona": "AZ",
        "arkansas": "AR",
        "california": "CA",
        "colorado": "CO",
        "connecticut": "CT",
        "delaware": "DE",
        "florida": "FL",
        "georgia": "GA",
        "hawaii": "HI",
        "idaho": "ID",
        "illinois": "IL",
        "indiana": "IN",
        "iowa": "IA",
        "kansas": "KS",
        "kentucky": "KY",
        "louisiana": "LA",
        "maine": "ME",
        "maryland": "MD",
        "massachusetts": "MA",
        "michigan": "MI",
        "minnesota": "MN",
        "mississippi": "MS",
        "missouri": "MO",
        "montana": "MT",
        "nebraska": "NE",
        "nevada": "NV",
        "new hampshire": "NH",
        "new jersey": "NJ",
        "new mexico": "NM",
        "new york": "NY",
        "north carolina": "NC",
        "north dakota": "ND",
        "ohio": "OH",
        "oklahoma": "OK",
        "oregon": "OR",
        "pennsylvania": "PA",
        "rhode island": "RI",
        "south carolina": "SC",
        "south dakota": "SD",
        "tennessee": "TN",
        "texas": "TX",
        "utah": "UT",
        "vermont": "VT",
        "virginia": "VA",
        "washington": "WA",
        "west virginia": "WV",
        "wisconsin": "WI",
        "wyoming": "WY",
    }

    # Check if it's a full state name
    if query_lower in state_map:
        return True

    # Check if it's a state abbreviation
    if len(query) == 2 and query.upper() in state_map.values():
        return True

    return False


def sanitize_string(value: str) -> str:
    """Sanitize string input to prevent injection attacks"""
    if not value:
        return ""

    # Basic SQL injection prevention - reject obvious patterns
    sql_patterns = [
        r"';\s*DROP",
        r"';\s*DELETE",
        r"';\s*UPDATE",
        r"';\s*INSERT",
        r"--",
        r"/\*.*\*/",
        r"UNION\s+SELECT",
        r"OR\s+1\s*=\s*1",
    ]
    for pattern in sql_patterns:
        if re.search(pattern, value, re.IGNORECASE):
            raise ValueError("Invalid characters in input")

    # Remove potentially dangerous characters
    sanitized = re.sub(r'[<>"\';()&+]', "", value.strip())
    return sanitized[: config.MAX_QUERY_LENGTH]


class SearchRequest(BaseModel):
    query: str

    @validator("query")
    def validate_query(cls, v):
        if not v or not v.strip():
            raise ValueError("Search query cannot be empty")

        sanitized = sanitize_string(v)
        if len(sanitized) < 2:
            raise ValueError("Search query too short")
        if len(sanitized) > config.MAX_QUERY_LENGTH:
            raise ValueError(
                f"Search query too long (max {config.MAX_QUERY_LENGTH} characters)"
            )

        # Basic pattern validation
        if not re.match(r"^[a-zA-Z0-9\s,.-]+$", sanitized):
            raise ValueError("Search query contains invalid characters")

        return sanitized


class ProcessRequest(BaseModel):
    packet_url: str
    banana: str
    meeting_name: Optional[str] = None
    meeting_date: Optional[str] = None
    meeting_id: Optional[str] = None

    @validator("packet_url")
    def validate_packet_url(cls, v):
        if not v or not v.strip():
            raise ValueError("Packet URL cannot be empty")

        # Basic URL validation
        if not re.match(r"^https?://", v):
            raise ValueError("Packet URL must be a valid HTTP/HTTPS URL")

        if len(v) > 2000:
            raise ValueError("Packet URL too long")

        return v.strip()

    @validator("banana")
    def validate_banana(cls, v):
        if not v or not v.strip():
            raise ValueError("City banana cannot be empty")

        # City banana should be alphanumeric with state code
        if not re.match(r"^[a-z0-9]+[A-Z]{2}$", v):
            raise ValueError(
                "City banana must be lowercase city name + uppercase state code"
            )

        return v.strip()

    @validator("meeting_name", "meeting_date", "meeting_id", pre=True, always=True)
    def validate_optional_strings(cls, v):
        if v is None:
            return None
        return sanitize_string(str(v))


@app.post("/api/search")
async def search_meetings(request: SearchRequest):
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
            return await handle_city_search("new york, ny")

        # Determine if input is zipcode, state, or city name
        is_zipcode = query.isdigit() and len(query) == 5
        is_state = is_state_query(query)

        logger.info(f"Query analysis - is_zipcode: {is_zipcode}, is_state: {is_state}")

        if is_zipcode:
            return await handle_zipcode_search(query)
        elif is_state:
            return await handle_state_search(query)
        else:
            return await handle_city_search(query)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Unexpected search error for '{query}': {str(e)}")
        raise HTTPException(
            status_code=500, detail="We humbly thank you for your patience"
        )


async def handle_zipcode_search(zipcode: str) -> Dict[str, Any]:
    """Handle zipcode search with cache-first approach

    Returns city data with banana field which serves as the city_url.
    Example: "paloaltoCA" is both the city identifier and the URL path.
    Frontend uses: /{banana} for routing.
    """
    # Check database - CACHED ONLY
    city = db.get_city(zipcode=zipcode)
    if not city:
        return {
            "success": False,
            "message": "We're not covering that area yet, but we're always expanding! Thanks for your interest - we'll prioritize cities with high demand.",
            "query": zipcode,
            "type": "zipcode",
            "meetings": [],
        }

    # Get cached meetings
    meetings = db.get_meetings(bananas=[city.banana], limit=50)

    if meetings:
        logger.info(
            f"Found {len(meetings)} cached meetings for {city.name}, {city.state}"
        )

        # Include items for item-based meetings
        meetings_with_items = []
        for meeting in meetings:
            meeting_dict = meeting.to_dict()
            items = db.get_agenda_items(meeting.id)
            if items:
                meeting_dict["items"] = [item.to_dict() for item in items]
                meeting_dict["has_items"] = True
            else:
                meeting_dict["has_items"] = False
            meetings_with_items.append(meeting_dict)

        return {
            "success": True,
            "city_name": city.name,
            "state": city.state,
            "banana": city.banana,
            "vendor": city.vendor,
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
        "meetings": [],
        "cached": False,
        "query": zipcode,
        "type": "zipcode",
        "message": f"No meetings available yet for {city.name} - check back soon as we sync with the city website",
    }


async def handle_city_search(city_input: str) -> Dict[str, Any]:
    """Handle city name search with cache-first approach and ambiguous city handling

    Returns city data with banana field which serves as the city_url.
    Example: "paloaltoCA" is both the city identifier and the URL path.
    Frontend uses: /{banana} for routing.
    """
    # Parse city, state
    city_name, state = parse_city_state_input(city_input)

    if not state:
        # No state provided - check for ambiguous cities
        return await handle_ambiguous_city_search(city_name, city_input)

    # Check database - CACHED ONLY
    city = db.get_city(name=city_name, state=state)
    if not city:
        return {
            "success": False,
            "message": f"We're not covering {city_name}, {state} yet, but we're always expanding! Your interest has been noted - we prioritize cities with high demand.",
            "query": city_input,
            "type": "city_name",
            "meetings": [],
        }

    # Get cached meetings
    meetings = db.get_meetings(bananas=[city.banana], limit=50)

    if meetings:
        logger.info(f"Found {len(meetings)} cached meetings for {city_name}, {state}")

        # Include items for item-based meetings
        meetings_with_items = []
        for meeting in meetings:
            meeting_dict = meeting.to_dict()
            items = db.get_agenda_items(meeting.id)
            if items:
                meeting_dict["items"] = [item.to_dict() for item in items]
                meeting_dict["has_items"] = True
            else:
                meeting_dict["has_items"] = False
            meetings_with_items.append(meeting_dict)

        return {
            "success": True,
            "city_name": city.name,
            "state": city.state,
            "banana": city.banana,
            "vendor": city.vendor,
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
        "meetings": [],
        "cached": True,
        "query": city_input,
        "type": "city",
        "message": f"No meetings cached yet for {city_name}, {state}, please check back soon!",
    }


async def handle_state_search(state_input: str) -> Dict[str, Any]:
    """Handle state search - return list of cities in that state"""
    # Normalize state input
    state_input_lower = state_input.strip().lower()

    # State abbreviation map
    state_map = {
        "alabama": "AL",
        "alaska": "AK",
        "arizona": "AZ",
        "arkansas": "AR",
        "california": "CA",
        "colorado": "CO",
        "connecticut": "CT",
        "delaware": "DE",
        "florida": "FL",
        "georgia": "GA",
        "hawaii": "HI",
        "idaho": "ID",
        "illinois": "IL",
        "indiana": "IN",
        "iowa": "IA",
        "kansas": "KS",
        "kentucky": "KY",
        "louisiana": "LA",
        "maine": "ME",
        "maryland": "MD",
        "massachusetts": "MA",
        "michigan": "MI",
        "minnesota": "MN",
        "mississippi": "MS",
        "missouri": "MO",
        "montana": "MT",
        "nebraska": "NE",
        "nevada": "NV",
        "new hampshire": "NH",
        "new jersey": "NJ",
        "new mexico": "NM",
        "new york": "NY",
        "north carolina": "NC",
        "north dakota": "ND",
        "ohio": "OH",
        "oklahoma": "OK",
        "oregon": "OR",
        "pennsylvania": "PA",
        "rhode island": "RI",
        "south carolina": "SC",
        "south dakota": "SD",
        "tennessee": "TN",
        "texas": "TX",
        "utah": "UT",
        "vermont": "VT",
        "virginia": "VA",
        "washington": "WA",
        "west virginia": "WV",
        "wisconsin": "WI",
        "wyoming": "WY",
    }

    # Determine state abbreviation
    if state_input_lower in state_map:
        state_abbr = state_map[state_input_lower]
        # Proper title case for multi-word states
        state_full = " ".join(word.capitalize() for word in state_input_lower.split())
    elif len(state_input) == 2 and state_input.upper() in state_map.values():
        state_abbr = state_input.upper()
        # Find full name from abbreviation
        state_full = next(
            (k.title() for k, v in state_map.items() if v == state_abbr), state_abbr
        )
    else:
        return {
            "success": False,
            "message": f"'{state_input}' is not a recognized state.",
            "query": state_input,
            "type": "state",
            "meetings": [],
        }

    # Get all cities in this state
    cities = db.get_cities(state=state_abbr)

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
    stats = db.get_city_meeting_stats(bananas)

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
    city_name: str, original_input: str
) -> Dict[str, Any]:
    """Handle city search when no state is provided - check for ambiguous matches"""

    # Look for all cities with this name (exact match)
    cities = db.get_cities(name=city_name)

    # If no exact match, try fuzzy matching to handle typos
    if not cities:
        from difflib import get_close_matches

        # Get all active city names from database
        all_cities = db.get_cities()  # Gets all active cities
        city_names = [city.name.lower() for city in all_cities]

        # Find close matches (cutoff=0.7 means 70% similarity required)
        close_matches = get_close_matches(city_name.lower(), city_names, n=5, cutoff=0.7)

        if close_matches:
            # Get cities matching the fuzzy results
            fuzzy_cities = []
            for match in close_matches:
                matched_cities = db.get_cities(name=match.title())
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

        # Get meetings for this city
        meetings = db.get_meetings(bananas=[city.banana], limit=50)

        if meetings:
            logger.info(
                f"Found {len(meetings)} cached meetings for {city.name}, {city.state}"
            )

            # Include items for item-based meetings
            meetings_with_items = []
            for meeting in meetings:
                meeting_dict = meeting.to_dict()
                items = db.get_agenda_items(meeting.id)
                if items:
                    meeting_dict["items"] = [item.to_dict() for item in items]
                    meeting_dict["has_items"] = True
                else:
                    meeting_dict["has_items"] = False
                meetings_with_items.append(meeting_dict)

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
    stats = db.get_city_meeting_stats(bananas)

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


# Auto-creation functions removed - CACHED ONLY mode


@app.post("/api/process-agenda")
async def process_agenda(request: ProcessRequest):
    """Get cached agenda summary - no longer processes on-demand"""
    try:
        # Check for cached summary
        cached_summary = db.get_cached_summary(request.packet_url)

        if cached_summary:
            return {
                "success": True,
                "summary": cached_summary.summary,
                "processing_time_seconds": cached_summary.processing_time or 0,
                "cached": True,
                "meeting_data": cached_summary.to_dict(),
            }

        # No cached summary available
        return {
            "success": False,
            "message": "Summary not yet available - processing in background",
            "cached": False,
            "packet_url": request.packet_url,
            "estimated_wait_minutes": 10,  # Rough estimate
        }

    except Exception as e:
        logger.error(f"Error retrieving agenda for {request.packet_url}: {str(e)}")
        raise HTTPException(
            status_code=500, detail="We humbly thank you for your patience"
        )


@app.get("/api/random-best-meeting")
async def get_random_best_meeting():
    """Get a random high-quality meeting summary for showcasing"""
    try:
        # Import the quality checker
        import sys
        import os

        sys.path.insert(
            0,
            os.path.dirname(
                os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            ),
        )
        from scripts.summary_quality_checker import SummaryQualityChecker

        checker = SummaryQualityChecker()
        random_meeting = checker.get_random_best_summary()

        if not random_meeting:
            raise HTTPException(
                status_code=404,
                detail="No high-quality meeting summaries available yet",
            )

        # Format for frontend consumption
        return {
            "status": "success",
            "meeting": {
                "banana": random_meeting["banana"],
                "city_url": f"/city/{random_meeting['banana']}",
                "title": random_meeting["title"],
                "date": random_meeting["date"],
                "packet_url": random_meeting["packet_url"],
                "summary": random_meeting["summary"],
                "quality_score": random_meeting["quality_score"],
            },
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting random best meeting: {str(e)}")
        raise HTTPException(status_code=500, detail="Error retrieving meeting summary")


@app.get("/api/random-meeting-with-items")
async def get_random_meeting_with_items():
    """Get a random meeting that has high-quality item-level summaries"""
    try:
        conn = db.conn
        cursor = conn.cursor()

        # Get meetings that have multiple items with summaries
        cursor.execute("""
            SELECT
                m.id,
                m.banana,
                m.title,
                m.date,
                m.packet_url,
                COUNT(i.id) as item_count,
                AVG(LENGTH(i.summary)) as avg_summary_length
            FROM meetings m
            JOIN items i ON m.id = i.meeting_id
            WHERE i.summary IS NOT NULL
                AND LENGTH(i.summary) > 100
            GROUP BY m.id
            HAVING COUNT(i.id) >= 3
            ORDER BY RANDOM()
            LIMIT 1
        """)

        result = cursor.fetchone()

        if not result:
            raise HTTPException(
                status_code=404,
                detail="No meetings with item summaries available yet",
            )

        meeting_id, banana, title, date, packet_url, item_count, avg_summary_length = result

        return {
            "success": True,
            "meeting": {
                "id": meeting_id,
                "banana": banana,
                "title": title,
                "date": date,
                "packet_url": packet_url,
                "item_count": item_count,
                "avg_summary_length": round(avg_summary_length) if avg_summary_length else 0
            },
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting random meeting with items: {str(e)}")
        raise HTTPException(status_code=500, detail="Error retrieving meeting")


@app.get("/api/stats")
async def get_stats():
    """Get system statistics"""
    try:
        stats = db.get_stats()

        # TODO(Phase 5): Add analytics tracking for user behavior
        # For now, use API logs to track usage patterns
        return {
            "status": "healthy",
            "active_cities": stats.get("active_cities", 0),
            "total_meetings": stats.get("total_meetings", 0),
            "summarized_meetings": stats.get("summarized_meetings", 0),
            "pending_meetings": stats.get("pending_meetings", 0),
            "summary_rate": stats.get("summary_rate", "0%"),
            "background_processing": {
                "service_status": "separate_daemon",
                "note": "Check daemon status: systemctl status engagic-daemon",
            },
        }
    except Exception as e:
        logger.error(f"Error fetching stats: {str(e)}")
        raise HTTPException(
            status_code=500, detail="We humbly thank you for your patience"
        )


@app.get("/api/queue-stats")
async def get_queue_stats():
    """Get processing queue statistics (Phase 4)"""
    try:
        queue_stats = db.get_queue_stats()

        return {
            "status": "healthy",
            "queue": {
                "pending": queue_stats.get("pending_count", 0),
                "processing": queue_stats.get("processing_count", 0),
                "completed": queue_stats.get("completed_count", 0),
                "failed": queue_stats.get("failed_count", 0),
                "permanently_failed": queue_stats.get("permanently_failed", 0),
                "avg_processing_seconds": round(
                    queue_stats.get("avg_processing_seconds", 0), 2
                ),
            },
            "note": "Queue is processed continuously by background daemon",
        }
    except Exception as e:
        logger.error(f"Error fetching queue stats: {str(e)}")
        raise HTTPException(status_code=500, detail="Error fetching queue statistics")


@app.get("/api/topics")
async def get_all_topics():
    """Get all available canonical topics for browsing/filtering"""
    try:
        from analysis.topics.normalizer import get_normalizer

        normalizer = get_normalizer()
        all_topics = normalizer.get_all_canonical_topics()

        # Build response with display names
        topics_with_display = [
            {
                "canonical": topic,
                "display_name": normalizer.get_display_name(topic)
            }
            for topic in all_topics
        ]

        return {
            "success": True,
            "topics": topics_with_display,
            "count": len(topics_with_display)
        }
    except Exception as e:
        logger.error(f"Error fetching topics: {str(e)}")
        raise HTTPException(status_code=500, detail="Error fetching topics")


class TopicSearchRequest(BaseModel):
    topic: str
    banana: Optional[str] = None  # Filter by city
    limit: int = 50

    @validator("topic")
    def validate_topic(cls, v):
        if not v or not v.strip():
            raise ValueError("Topic cannot be empty")
        return sanitize_string(v)


@app.post("/api/search/by-topic")
async def search_by_topic(request: TopicSearchRequest):
    """Search meetings by topic (Phase 1 - Topic Extraction)"""
    try:
        from analysis.topics.normalizer import get_normalizer

        # Normalize the search topic
        normalizer = get_normalizer()
        normalized_topic = normalizer.normalize_single(request.topic)

        logger.info(f"Topic search: '{request.topic}' -> '{normalized_topic}', city: {request.banana}")

        # Build SQL query to find meetings with this topic
        conditions = []
        params = []

        # Topic match (check if JSON array contains the topic)
        # SQLite JSON support: json_each to expand array
        conditions.append("EXISTS (SELECT 1 FROM json_each(meetings.topics) WHERE value = ?)")
        params.append(normalized_topic)

        # City filter
        if request.banana:
            conditions.append("meetings.banana = ?")
            params.append(request.banana)

        # Only return meetings with topics
        conditions.append("meetings.topics IS NOT NULL")

        where_clause = " AND ".join(conditions)

        query = f"""
            SELECT * FROM meetings
            WHERE {where_clause}
            ORDER BY date DESC
            LIMIT ?
        """
        params.append(request.limit)

        cursor = db.conn.cursor()
        cursor.execute(query, params)
        rows = cursor.fetchall()

        from database.db import Meeting
        meetings = [Meeting.from_db_row(row) for row in rows]

        # For each meeting, get the items that match this topic
        results = []
        for meeting in meetings:
            # Get items with this topic
            items_query = """
                SELECT * FROM items
                WHERE meeting_id = ?
                AND EXISTS (SELECT 1 FROM json_each(items.topics) WHERE value = ?)
                ORDER BY sequence ASC
            """
            cursor.execute(items_query, (meeting.id, normalized_topic))
            item_rows = cursor.fetchall()

            from database.db import AgendaItem
            matching_items = [AgendaItem.from_db_row(row) for row in item_rows]

            results.append({
                "meeting": meeting.to_dict(),
                "matching_items": [
                    {
                        "id": item.id,
                        "title": item.title,
                        "sequence": item.sequence,
                        "summary": item.summary,
                        "topics": item.topics
                    }
                    for item in matching_items
                ]
            })

        return {
            "success": True,
            "query": request.topic,
            "normalized_topic": normalized_topic,
            "display_name": normalizer.get_display_name(normalized_topic),
            "results": results,
            "count": len(results)
        }

    except Exception as e:
        logger.error(f"Error searching by topic '{request.topic}': {str(e)}")
        raise HTTPException(status_code=500, detail="Error searching by topic")


@app.get("/api/topics/popular")
async def get_popular_topics():
    """Get most common topics across all meetings (for UI suggestions)"""
    try:
        # Query to count topic frequency across all meetings
        cursor = db.conn.cursor()
        cursor.execute("""
            SELECT value as topic, COUNT(*) as count
            FROM meetings, json_each(meetings.topics)
            WHERE meetings.topics IS NOT NULL
            GROUP BY value
            ORDER BY count DESC
            LIMIT 20
        """)

        rows = cursor.fetchall()

        from analysis.topics.normalizer import get_normalizer
        normalizer = get_normalizer()

        popular_topics = [
            {
                "topic": row["topic"],
                "display_name": normalizer.get_display_name(row["topic"]),
                "count": row["count"]
            }
            for row in rows
        ]

        return {
            "success": True,
            "topics": popular_topics,
            "count": len(popular_topics)
        }

    except Exception as e:
        logger.error(f"Error fetching popular topics: {str(e)}")
        raise HTTPException(status_code=500, detail="Error fetching popular topics")


@app.get("/")
async def root():
    """API status and info"""
    return {
        "service": "engagic API",
        "status": "running",
        "version": "2.0.0",
        "description": "Civic engagement made simple - Search and access local government meetings",
        "documentation": "https://github.com/Engagic/engagic#api-documentation",
        "endpoints": {
            "search": "POST /api/search - Search for meetings by zipcode or city name",
            "process": "POST /api/process-agenda - Get cached meeting agenda summary",
            "random_best": "GET /api/random-best-meeting - Get a random high-quality meeting for showcasing",
            "topics": "GET /api/topics - Get all available topics for filtering",
            "topics_popular": "GET /api/topics/popular - Get most common topics across all meetings",
            "search_by_topic": "POST /api/search/by-topic - Search meetings by topic",
            "stats": "GET /api/stats - System statistics and metrics",
            "queue_stats": "GET /api/queue-stats - Processing queue statistics",
            "health": "GET /api/health - Health check with detailed status",
            "metrics": "GET /api/metrics - Detailed system metrics",
            "admin": {
                "city_requests": "GET /api/admin/city-requests - View requested cities",
                "sync_city": "POST /api/admin/sync-city/{city_slug} - Force sync specific city",
                "process_meeting": "POST /api/admin/process-meeting - Force process specific meeting",
            },
        },
        "usage_examples": {
            "search_by_zipcode": {
                "method": "POST",
                "url": "/api/search",
                "body": {"query": "94301"},
                "description": "Search meetings by ZIP code",
            },
            "search_by_city": {
                "method": "POST",
                "url": "/api/search",
                "body": {"query": "Palo Alto, CA"},
                "description": "Search meetings by city and state",
            },
            "search_ambiguous": {
                "method": "POST",
                "url": "/api/search",
                "body": {"query": "Springfield"},
                "description": "Search by city name only (may return multiple options)",
            },
            "get_summary": {
                "method": "POST",
                "url": "/api/process-agenda",
                "body": {
                    "packet_url": "https://example.com/agenda.pdf",
                    "banana": "paloaltoCA",
                    "meeting_name": "City Council Meeting",
                },
                "description": "Get cached AI summary of meeting agenda",
            },
        },
        "rate_limiting": f"{config.RATE_LIMIT_REQUESTS} requests per {config.RATE_LIMIT_WINDOW} seconds per IP",
        "features": [
            "ZIP code and city name search",
            "AI-powered meeting summaries",
            "Ambiguous city name handling",
            "Real-time meeting data caching",
            "Multiple city system adapters",
            "Background data processing",
            "Comprehensive error handling",
            "Request demand tracking",
        ],
        "data_sources": [
            "PrimeGov (city council management)",
            "CivicClerk (municipal systems)",
            "Direct city websites",
        ],
    }


@app.get("/api/health")
async def health_check():
    """Health check endpoint"""
    health_status = {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "version": "2.0.0",
        "checks": {},
    }

    try:
        # Database health check
        stats = db.get_stats()
        health_status["checks"]["databases"] = {
            "status": "healthy",
            "cities": stats["active_cities"],
            "meetings": stats["total_meetings"],
        }

        # Add basic stats
        health_status["checks"]["data_summary"] = {
            "cities": stats["active_cities"],
            "meetings": stats["total_meetings"],
            "processed": stats["summarized_meetings"],
        }
    except Exception as e:
        health_status["checks"]["databases"] = {"status": "unhealthy", "error": str(e)}
        health_status["status"] = "degraded"

    # LLM processor check
    health_status["checks"]["llm_processor"] = {
        "status": "available" if processor else "disabled",
        "has_api_key": bool(config.get_api_key()),
    }

    # Configuration check
    health_status["checks"]["configuration"] = {
        "status": "healthy",
        "is_development": config.is_development(),
        "rate_limiting": f"{config.RATE_LIMIT_REQUESTS} req/{config.RATE_LIMIT_WINDOW}s",
        "background_processing": config.BACKGROUND_PROCESSING,
    }

    # Background processor check (separate service)
    health_status["checks"]["background_processor"] = {
        "status": "separate_service",
        "note": "Background processing runs as independent daemon",
        "check_command": "systemctl status engagic-daemon",
    }

    # Set overall status based on critical services
    if health_status["checks"]["databases"].get("overall_status") == "error":
        health_status["status"] = "unhealthy"

    return health_status


@app.get("/api/metrics")
async def get_metrics():
    """Basic metrics endpoint for monitoring"""
    try:
        stats = db.get_stats()

        # TODO(Phase 5): Add detailed metrics tracking
        return {
            "timestamp": datetime.now().isoformat(),
            "database": {
                "active_cities": stats.get("active_cities", 0),
                "total_meetings": stats.get("total_meetings", 0),
                "summarized_meetings": stats.get("summarized_meetings", 0),
                "pending_meetings": stats.get("pending_meetings", 0),
            },
            "configuration": {
                "rate_limit_window": config.RATE_LIMIT_WINDOW,
                "rate_limit_requests": config.RATE_LIMIT_REQUESTS,
                "background_processing": config.BACKGROUND_PROCESSING,
            },
        }
    except Exception as e:
        logger.error(f"Metrics endpoint failed: {e}")
        raise HTTPException(
            status_code=500, detail="We humbly thank you for your patience"
        )


@app.get("/api/analytics")
async def get_analytics():
    """Get comprehensive analytics for public dashboard"""
    try:
        # Get stats directly from unified database
        if db.conn is None:
            raise HTTPException(
                status_code=500, detail="Database connection not established"
            )
        cursor = db.conn.cursor()

        # City stats
        cursor.execute("SELECT COUNT(*) as total_cities FROM cities")
        total_cities = dict(cursor.fetchone())

        # Meeting stats
        cursor.execute("SELECT COUNT(*) as meetings_count FROM meetings")
        meetings_stats = dict(cursor.fetchone())

        cursor.execute(
            "SELECT COUNT(*) as packets_count FROM meetings WHERE packet_url IS NOT NULL AND packet_url != ''"
        )
        packets_stats = dict(cursor.fetchone())

        cursor.execute(
            "SELECT COUNT(*) as summaries_count FROM meetings WHERE summary IS NOT NULL AND summary != ''"
        )
        summaries_stats = dict(cursor.fetchone())

        cursor.execute("SELECT COUNT(DISTINCT banana) as active_cities FROM meetings")
        active_cities_stats = dict(cursor.fetchone())

        return {
            "success": True,
            "timestamp": datetime.now().isoformat(),
            "real_metrics": {
                "cities_covered": total_cities["total_cities"],
                "meetings_tracked": meetings_stats["meetings_count"],
                "meetings_with_packet": packets_stats["packets_count"],
                "agendas_summarized": summaries_stats["summaries_count"],
                "active_cities": active_cities_stats["active_cities"],
            },
        }

    except Exception as e:
        logger.error(f"Analytics endpoint failed: {e}")
        raise HTTPException(
            status_code=500, detail="We humbly thank you for your patience"
        )


async def verify_admin_token(authorization: str = Header(None)):
    """Verify admin bearer token"""
    if not config.ADMIN_TOKEN:
        raise HTTPException(
            status_code=500, detail="Admin authentication not configured"
        )

    if not authorization:
        raise HTTPException(status_code=401, detail="Authorization header required")

    try:
        scheme, token = authorization.split(" ")
        if scheme.lower() != "bearer":
            raise HTTPException(status_code=401, detail="Invalid authentication scheme")

        if token != config.ADMIN_TOKEN:
            raise HTTPException(status_code=403, detail="Invalid admin token")

    except ValueError:
        raise HTTPException(
            status_code=401, detail="Invalid authorization header format"
        )

    return True


@app.get("/api/admin/city-requests")
async def get_city_requests(is_admin: bool = Depends(verify_admin_token)):
    """Get top city requests for admin review"""
    # TODO(Phase 5): Implement analytics tracking for city requests
    # For now, check API logs for usage patterns
    return {
        "success": True,
        "message": "City request tracking not yet implemented. Check API logs for usage patterns.",
        "city_requests": [],
        "total_count": 0,
    }


@app.post("/api/admin/sync-city/{banana}")
async def force_sync_city(banana: str, is_admin: bool = Depends(verify_admin_token)):
    """Force sync a specific city (admin endpoint)"""
    # This endpoint requires the background processor daemon to be running
    # Admin should use the daemon directly: python daemon.py --sync-city BANANA
    return {
        "success": False,
        "banana": banana,
        "message": "Background processing runs as separate service. Use daemon directly:",
        "command": f"python /root/engagic/app/daemon.py --sync-city {banana}",
        "alternative": "systemctl status engagic-daemon",
    }


@app.post("/api/admin/process-meeting")
async def force_process_meeting(
    request: ProcessRequest, is_admin: bool = Depends(verify_admin_token)
):
    """Force process a specific meeting (admin endpoint)"""
    # This endpoint requires the background processor daemon to be running
    # Admin should use the daemon directly
    return {
        "success": False,
        "packet_url": request.packet_url,
        "message": "Background processing runs as separate service. Use daemon directly:",
        "command": f"python /root/engagic/app/daemon.py --process-meeting {request.packet_url}",
        "alternative": "systemctl status engagic-daemon",
    }


if __name__ == "__main__":
    import uvicorn
    import sys
    import os

    # Validate critical environment variables on startup
    if not config.get_api_key():
        logger.warning(
            "WARNING: No LLM API key configured. AI features will be disabled."
        )
        logger.warning("Set ANTHROPIC_API_KEY or LLM_API_KEY to enable AI summaries.")

    if not config.ADMIN_TOKEN:
        logger.warning(
            "WARNING: No admin token configured. Admin endpoints will not work."
        )
        logger.warning("Set ENGAGIC_ADMIN_TOKEN to enable admin functionality.")

    logger.info("Starting engagic API server...")
    logger.info(f"Configuration: {config.summary()}")
    logger.info(f"LLM processor: {'enabled' if processor else 'disabled'}")

    # Check if databases exist
    for db_name, db_path in [
        ("locations", config.LOCATIONS_DB_PATH),
        ("meetings", config.MEETINGS_DB_PATH),
        ("analytics", config.ANALYTICS_DB_PATH),
    ]:
        if not os.path.exists(db_path):
            logger.warning(f"{db_name} database not found at {db_path}")
            logger.info("Databases will be created automatically on first use")

    # Handle command line arguments
    if len(sys.argv) > 1 and sys.argv[1] == "--init-db":
        logger.info("Initializing databases...")
        # Access the database manager to trigger creation
        _ = db.get_stats()
        logger.info("Databases initialized successfully")
        sys.exit(0)

    uvicorn.run(
        app,
        host=config.API_HOST,
        port=config.API_PORT,
        access_log=False,  # Disable default uvicorn logs (we have custom middleware logging)
    )
