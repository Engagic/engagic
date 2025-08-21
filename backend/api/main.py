from fastapi import FastAPI, HTTPException, Request, Depends, Header
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, validator
from typing import Optional, Dict, Any
import logging
import time
import uuid
import re
from datetime import datetime
from backend.core.processor import AgendaProcessor
from backend.core.async_processor import AsyncAgendaProcessor
from backend.database import DatabaseManager
from uszipcode import SearchEngine
from backend.core.config import config
from backend.core.utils import generate_city_banana
from backend.api.rate_limiter import SQLiteRateLimiter

# Configure structured logging
logging.basicConfig(
    level=getattr(logging, config.LOG_LEVEL),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(), logging.FileHandler(config.LOG_PATH, mode="a")],
)
logger = logging.getLogger("engagic")

app = FastAPI(title="engagic API", description="EGMI")

# CORS configured once below with config.ALLOWED_ORIGINS


# Initialize SQLite rate limiter (persistent across restarts)
rate_limiter = SQLiteRateLimiter(
    db_path=config.ANALYTICS_DB_PATH.replace("analytics.db", "rate_limits.db"),
    requests_limit=config.RATE_LIMIT_REQUESTS,
    window_seconds=config.RATE_LIMIT_WINDOW
)

# Rate limiting middleware
@app.middleware("http")
async def rate_limit_middleware(request: Request, call_next):
    # Extract client IP (handle proxies)
    client_ip = request.client.host if request.client else "unknown"
    
    # Get X-Forwarded-For if behind proxy
    x_forwarded_for = request.headers.get("X-Forwarded-For")
    if x_forwarded_for:
        # Take the first IP from the chain
        client_ip = x_forwarded_for.split(",")[0].strip()
    
    # Check rate limit for API endpoints
    if request.url.path.startswith("/api/"):
        is_allowed, remaining = rate_limiter.check_rate_limit(client_ip)
        
        if not is_allowed:
            logger.warning(f"Rate limit exceeded for client from {client_ip[:16]}...")
            raise HTTPException(
                status_code=429, 
                detail="Rate limit exceeded. Please try again later.",
                headers={"X-RateLimit-Remaining": "0", "Retry-After": str(config.RATE_LIMIT_WINDOW)}
            )
    
    response = await call_next(request)
    return response


# Request/Response logging middleware
@app.middleware("http")
async def log_requests(request: Request, call_next):
    request_id = str(uuid.uuid4())[:8]
    start_time = time.time()

    # Log incoming request (anonymize IP for privacy)
    client_ip = request.client.host if request.client else 'unknown'
    # Only log first two octets of IP for privacy
    if client_ip != 'unknown' and '.' in client_ip:
        ip_parts = client_ip.split('.')
        anonymized_ip = f"{ip_parts[0]}.{ip_parts[1] if len(ip_parts) > 1 else 'x'}.x.x"
    else:
        anonymized_ip = 'anonymous'
    
    logger.info(
        f"[{request_id}] {request.method} {request.url.path} - Client: {anonymized_ip}"
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
    # Use async processor for non-blocking operations
    processor = AsyncAgendaProcessor(
        api_key=config.get_api_key()
    )
    logger.info("Async LLM processor initialized successfully")
except ValueError:
    logger.warning("API key not found - LLM processing will be disabled")
    processor = None

# Initialize database manager with separate databases
db = DatabaseManager(
    locations_db_path=config.LOCATIONS_DB_PATH,
    meetings_db_path=config.MEETINGS_DB_PATH,
    analytics_db_path=config.ANALYTICS_DB_PATH,
)
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
    return input_str, None


def is_state_query(query: str) -> bool:
    """Check if the query is just a state name or abbreviation"""
    query_lower = query.strip().lower()
    
    # State abbreviation map
    state_map = {
        "alabama": "AL", "alaska": "AK", "arizona": "AZ", "arkansas": "AR",
        "california": "CA", "colorado": "CO", "connecticut": "CT", "delaware": "DE",
        "florida": "FL", "georgia": "GA", "hawaii": "HI", "idaho": "ID",
        "illinois": "IL", "indiana": "IN", "iowa": "IA", "kansas": "KS",
        "kentucky": "KY", "louisiana": "LA", "maine": "ME", "maryland": "MD",
        "massachusetts": "MA", "michigan": "MI", "minnesota": "MN", "mississippi": "MS",
        "missouri": "MO", "montana": "MT", "nebraska": "NE", "nevada": "NV",
        "new hampshire": "NH", "new jersey": "NJ", "new mexico": "NM", "new york": "NY",
        "north carolina": "NC", "north dakota": "ND", "ohio": "OH", "oklahoma": "OK",
        "oregon": "OR", "pennsylvania": "PA", "rhode island": "RI", "south carolina": "SC",
        "south dakota": "SD", "tennessee": "TN", "texas": "TX", "utah": "UT",
        "vermont": "VT", "virginia": "VA", "washington": "WA", "west virginia": "WV",
        "wisconsin": "WI", "wyoming": "WY"
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
    city_banana: str
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

    @validator("city_banana")
    def validate_city_banana(cls, v):
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
            status_code=500, 
            detail={"error": "Search failed", "message": "An unexpected error occurred while searching"}
        )


async def handle_zipcode_search(zipcode: str) -> Dict[str, Any]:
    """Handle zipcode search with cache-first approach"""
    # Update search log
    db.log_search(zipcode, "zipcode", zipcode=zipcode)

    # Check database - CACHED ONLY
    city_info = db.get_city_by_zipcode(zipcode)
    if not city_info:
        # Log the request for demand tracking
        try:
            # Try to get city info from zipcode for logging
            result = zipcode_search.by_zipcode(zipcode)
            if result and result.major_city:
                city_name = result.major_city
                state = result.state
                db.log_city_request(
                    city_name, state, zipcode, "zipcode", zipcode=zipcode
                )
        except Exception as e:
            logger.warning(f"Failed to log city request for zipcode {zipcode}: {e}")

        return {
            "success": False,
            "message": "We're not covering that area yet, but we're always expanding! Thanks for your interest - we'll prioritize cities with high demand.",
            "query": zipcode,
            "type": "zipcode",
            "meetings": [],
        }

    # Get cached meetings using city_banana
    city_banana = city_info.get("city_banana") or generate_city_banana(
        city_info["city_name"], city_info["state"]
    )
    meetings = db.get_meetings_by_city(city_banana, 50)

    if meetings:
        logger.info(
            f"Found {len(meetings)} cached meetings for {city_info['city_name']}, {city_info.get('state', 'Unknown')}"
        )
        return {
            "success": True,
            "city_name": city_info["city_name"],
            "state": city_info["state"],
            "city_banana": city_info.get("city_banana")
            or generate_city_banana(city_info["city_name"], city_info["state"]),
            "vendor": city_info["vendor"],
            "meetings": meetings,
            "cached": True,
            "query": zipcode,
            "type": "zipcode",
        }

    # No cached meetings - background processor will handle this
    return {
        "success": True,
        "city_name": city_info["city_name"],
        "state": city_info["state"],
        "city_banana": city_info.get("city_banana")
        or generate_city_banana(city_info["city_name"], city_info["state"]),
        "vendor": city_info["vendor"],
        "meetings": [],
        "cached": False,
        "query": zipcode,
        "type": "zipcode",
        "message": f"No meetings available yet for {city_info['city_name']} - check back soon as we sync with the city website",
    }


async def handle_city_search(city_input: str) -> Dict[str, Any]:
    """Handle city name search with cache-first approach and ambiguous city handling"""
    # Parse city, state
    city_name, state = parse_city_state_input(city_input)

    if not state:
        # No state provided - check for ambiguous cities
        return await handle_ambiguous_city_search(city_name, city_input)

    # Check database - CACHED ONLY
    city_info = db.get_city_by_name(city_name, state)
    if not city_info:
        # Log the request for demand tracking
        try:
            db.log_city_request(city_name, state, city_input, "city_name")
        except Exception as e:
            logger.warning(f"Failed to log city request for {city_name}, {state}: {e}")

        return {
            "success": False,
            "message": f"We're not covering {city_name}, {state} yet, but we're always expanding! Your interest has been noted - we prioritize cities with high demand.",
            "query": city_input,
            "type": "city_name",
            "meetings": [],
        }

    # Log search with city_id
    db.log_search(city_input, "city_name", city_id=city_info["id"])

    # Get cached meetings using city_banana
    city_banana = city_info.get("city_banana") or generate_city_banana(
        city_info["city_name"], city_info["state"]
    )
    meetings = db.get_meetings_by_city(city_banana, 50)

    if meetings:
        logger.info(f"Found {len(meetings)} cached meetings for {city_name}, {state}")
        return {
            "success": True,
            "city_name": city_info["city_name"],
            "state": city_info["state"],
            "city_banana": city_info.get("city_banana")
            or generate_city_banana(city_info["city_name"], city_info["state"]),
            "vendor": city_info["vendor"],
            "meetings": meetings,
            "cached": True,
            "query": city_input,
            "type": "city_name",
        }

    # No cached meetings - return empty
    return {
        "success": False,
        "city_name": city_info["city_name"],
        "state": city_info["state"],
        "city_banana": city_info.get("city_banana")
        or generate_city_banana(city_info["city_name"], city_info["state"]),
        "vendor": city_info["vendor"],
        "meetings": [],
        "cached": True,
        "query": city_input,
        "type": "city_name",
        "message": f"No meetings cached yet for {city_name}, {state}, please check back soon!",
    }


async def handle_state_search(state_input: str) -> Dict[str, Any]:
    """Handle state search - return list of cities in that state"""
    # Normalize state input
    state_input_lower = state_input.strip().lower()
    
    # State abbreviation map
    state_map = {
        "alabama": "AL", "alaska": "AK", "arizona": "AZ", "arkansas": "AR",
        "california": "CA", "colorado": "CO", "connecticut": "CT", "delaware": "DE",
        "florida": "FL", "georgia": "GA", "hawaii": "HI", "idaho": "ID",
        "illinois": "IL", "indiana": "IN", "iowa": "IA", "kansas": "KS",
        "kentucky": "KY", "louisiana": "LA", "maine": "ME", "maryland": "MD",
        "massachusetts": "MA", "michigan": "MI", "minnesota": "MN", "mississippi": "MS",
        "missouri": "MO", "montana": "MT", "nebraska": "NE", "nevada": "NV",
        "new hampshire": "NH", "new jersey": "NJ", "new mexico": "NM", "new york": "NY",
        "north carolina": "NC", "north dakota": "ND", "ohio": "OH", "oklahoma": "OK",
        "oregon": "OR", "pennsylvania": "PA", "rhode island": "RI", "south carolina": "SC",
        "south dakota": "SD", "tennessee": "TN", "texas": "TX", "utah": "UT",
        "vermont": "VT", "virginia": "VA", "washington": "WA", "west virginia": "WV",
        "wisconsin": "WI", "wyoming": "WY"
    }
    
    # Determine state abbreviation
    if state_input_lower in state_map:
        state_abbr = state_map[state_input_lower]
        # Proper title case for multi-word states
        state_full = " ".join(word.capitalize() for word in state_input_lower.split())
    elif len(state_input) == 2 and state_input.upper() in state_map.values():
        state_abbr = state_input.upper()
        # Find full name from abbreviation
        state_full = next((k.title() for k, v in state_map.items() if v == state_abbr), state_abbr)
    else:
        return {
            "success": False,
            "message": f"'{state_input}' is not a recognized state.",
            "query": state_input,
            "type": "state",
            "meetings": [],
        }
    
    # Get all cities in this state
    cities = db.get_cities_by_state(state_abbr)
    
    if not cities:
        return {
            "success": False,
            "message": f"We don't have any cities in {state_full} yet, but we're always expanding!",
            "query": state_input,
            "type": "state",
            "meetings": [],
        }
    
    # Log the state search
    db.log_search(state_input, "state")
    
    # Convert cities to the format expected by frontend
    city_options = []
    for city in cities:
        city_options.append({
            "city_name": city["city_name"],
            "state": city["state"],
            "city_banana": city.get("city_banana") or generate_city_banana(city["city_name"], city["state"]),
            "vendor": city.get("vendor", "unknown"),
            "display_name": f"{city['city_name']}, {city['state']}"
        })
    
    return {
        "success": False,  # False because we're not returning meetings directly
        "message": f"Found {len(city_options)} cities in {state_full}. Select a city to view meetings:",
        "query": state_input,
        "type": "state",
        "ambiguous": True,  # Reuse ambiguous city UI pattern
        "city_options": city_options,
    }


async def handle_ambiguous_city_search(
    city_name: str, original_input: str
) -> Dict[str, Any]:
    """Handle city search when no state is provided - check for ambiguous matches"""

    # Look for all cities with this name
    cities = db.get_cities_by_name_only(city_name)

    if not cities:
        # No cities found - log the request
        try:
            db.log_city_request(
                city_name, "UNKNOWN", original_input, "city_name_ambiguous"
            )
        except Exception as e:
            logger.warning(f"Failed to log ambiguous city request for {city_name}: {e}")

        return {
            "success": False,
            "message": f"We don't have '{city_name}' in our database yet. Please include the state (e.g., '{city_name}, CA') - your interest has been noted!",
            "query": original_input,
            "type": "city_name",
            "meetings": [],
            "ambiguous": False,
        }

    if len(cities) == 1:
        # Only one match - proceed with this city
        city_info = cities[0]

        # Log search with city_id
        db.log_search(original_input, "city_name", city_id=city_info["id"])

        # Get meetings for this city using city_banana
        city_banana = city_info.get("city_banana") or generate_city_banana(
            city_info["city_name"], city_info["state"]
        )
        meetings = db.get_meetings_by_city(city_banana, 50)

        if meetings:
            logger.info(
                f"Found {len(meetings)} cached meetings for {city_info['city_name']}, {city_info['state']}"
            )
            return {
                "success": True,
                "city_name": city_info["city_name"],
                "state": city_info["state"],
                "city_banana": city_info.get("city_banana")
                or generate_city_banana(city_info["city_name"], city_info["state"]),
                "vendor": city_info["vendor"],
                "meetings": meetings,
                "cached": True,
                "query": original_input,
                "type": "city_name",
                "ambiguous": False,
            }
        else:
            return {
                "success": False,
                "city_name": city_info["city_name"],
                "state": city_info["state"],
                "city_banana": city_info.get("city_banana")
                or generate_city_banana(city_info["city_name"], city_info["state"]),
                "vendor": city_info["vendor"],
                "meetings": [],
                "cached": True,
                "query": original_input,
                "type": "city_name",
                "message": f"No meetings cached yet for {city_info['city_name']}, {city_info['state']}, please check back soon!",
                "ambiguous": False,
            }

    # Multiple matches - return ambiguous result
    city_options = []
    for city in cities:
        city_options.append(
            {
                "city_name": city["city_name"],
                "state": city["state"],
                "city_banana": city.get("city_banana")
                or generate_city_banana(city["city_name"], city["state"]),
                "vendor": city["vendor"],
                "display_name": f"{city['city_name']}, {city['state']}",
            }
        )

    return {
        "success": False,
        "message": f"Multiple cities named '{city_name}' found. Please specify which one:",
        "query": original_input,
        "type": "city_name",
        "ambiguous": True,
        "city_options": city_options,
        "meetings": [],
    }


# Auto-creation functions removed - CACHED ONLY mode


@app.post("/api/process-agenda")
async def process_agenda(request: ProcessRequest):
    """Process agenda with async processor or return cached result"""
    try:
        # Check for cached summary first
        cached_summary = db.get_cached_summary(request.packet_url)

        if cached_summary:
            return {
                "success": True,
                "summary": cached_summary["processed_summary"],
                "processing_time_seconds": cached_summary.get(
                    "processing_time_seconds", 0
                ),
                "cached": True,
                "meeting_data": cached_summary,
            }

        # If processor is available, process asynchronously
        if processor:
            logger.info(f"Processing agenda asynchronously for {request.packet_url}")
            
            meeting_data = {
                "city_banana": request.city_banana,
                "meeting_name": request.meeting_name,
                "meeting_date": request.meeting_date,
                "meeting_id": request.meeting_id,
                "packet_url": request.packet_url
            }
            
            # Process asynchronously without blocking
            result = await processor.process_agenda_with_cache(meeting_data)
            
            if result["success"]:
                return {
                    "success": True,
                    "summary": result["summary"],
                    "processing_time_seconds": result["processing_time"],
                    "cached": False,
                    "meeting_data": result.get("meeting_data"),
                    "processing_method": result.get("processing_method"),
                }
            else:
                return {
                    "success": False,
                    "message": f"Processing failed: {result.get('error', 'Unknown error')}",
                    "cached": False,
                    "packet_url": request.packet_url,
                }
        else:
            # No processor available
            return {
                "success": False,
                "message": "Processing service unavailable - API key not configured",
                "cached": False,
                "packet_url": request.packet_url,
            }

    except Exception as e:
        logger.error(f"Error processing agenda for {request.packet_url}: {str(e)}")
        raise HTTPException(
            status_code=500, 
            detail={
                "error": "Failed to process agenda",
                "message": str(e),
                "packet_url": request.packet_url
            }
        )


@app.get("/api/stats")
async def get_stats():
    """Get system statistics"""
    try:
        stats = db.get_cache_stats()
        queue_stats = db.get_processing_queue_stats()
        request_stats = db.get_city_request_stats()

        return {
            "status": "healthy",
            "cities": stats.get("cities_count", 0),
            "meetings": stats.get("meetings_count", 0),
            "processed": stats.get("processed_count", 0),
            "recent_activity": stats.get("recent_activity", 0),
            "city_requests": request_stats,
            "background_processing": {
                "service_status": "separate_daemon",
                "unprocessed_queue": queue_stats.get("unprocessed_count", 0),
                "processing_success_rate": f"{queue_stats.get('success_rate', 0):.1f}%",
                "recent_meetings": queue_stats.get("recent_count", 0),
                "note": "Check daemon status: systemctl status engagic-daemon",
            },
        }
    except Exception as e:
        logger.error(f"Error fetching stats: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail={"error": "Statistics unavailable", "message": "Failed to retrieve system statistics"}
        )


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
            "stats": "GET /api/stats - System statistics and metrics",
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
                    "city_banana": "paloaltoCA",
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
        db_health = db.get_system_health()
        health_status["checks"]["databases"] = db_health

        if db_health["overall_status"] != "healthy":
            health_status["status"] = "degraded"

        # Add basic stats
        stats = db.get_cache_stats()
        health_status["checks"]["data_summary"] = {
            "cities": stats.get("cities_count", 0),
            "meetings": stats.get("meetings_count", 0),
            "processed": stats.get("processed_count", 0),
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
        stats = db.get_cache_stats()
        queue_stats = db.get_processing_queue_stats()
        request_stats = db.get_city_request_stats()

        return {
            "timestamp": datetime.now().isoformat(),
            "database": {
                "cities_count": stats.get("cities_count", 0),
                "meetings_count": stats.get("meetings_count", 0),
                "processed_count": stats.get("processed_count", 0),
                "recent_activity": stats.get("recent_activity", 0),
            },
            "processing": {
                "unprocessed_queue": queue_stats.get("unprocessed_count", 0),
                "success_rate": f"{queue_stats.get('success_rate', 0):.1f}%",
                "recent_meetings": queue_stats.get("recent_count", 0),
            },
            "demand": {
                "total_city_requests": request_stats.get(
                    "total_unique_cities_requested", 0
                ),
                "total_demand": request_stats.get("total_demand", 0),
                "recent_requests": request_stats.get("recent_activity", 0),
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
            status_code=500,
            detail={"error": "Metrics unavailable", "message": "Failed to collect system metrics"}
        )


@app.get("/api/analytics")
async def get_analytics():
    """Get comprehensive analytics for public dashboard"""
    try:
        # Get only hard, verifiable facts from the database
        meetings_stats = db.meetings.get_meetings_stats()
        
        # Get city stats from locations database
        with db.locations.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) as total_cities FROM cities")
            total_cities = cursor.fetchone()
            
            cursor.execute("SELECT COUNT(DISTINCT state) as states_covered FROM cities")
            states_covered = cursor.fetchone()
            
            cursor.execute("SELECT COUNT(*) as total_zipcodes FROM zipcodes")
            zipcodes_covered = cursor.fetchone()
        
        # Get actual summary count
        with db.meetings.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT COUNT(*) as summaries_count
                FROM meetings 
                WHERE processed_summary IS NOT NULL
            """)
            summaries_stats = cursor.fetchone()
            
            # Get active cities (cities with at least one meeting)
            cursor.execute("""
                SELECT COUNT(DISTINCT city_banana) as active_cities
                FROM meetings
            """)
            active_cities_stats = cursor.fetchone()
        
        return {
            "success": True,
            "timestamp": datetime.now().isoformat(),
            "real_metrics": {
                "cities_covered": total_cities["total_cities"],
                "meetings_tracked": meetings_stats["meetings_count"],
                "agendas_summarized": summaries_stats["summaries_count"],
                "states_covered": states_covered["states_covered"],
                "zipcodes_served": zipcodes_covered["total_zipcodes"],
                "active_cities": active_cities_stats["active_cities"]
            }
        }
        
    except Exception as e:
        logger.error(f"Analytics endpoint failed: {e}")
        raise HTTPException(
            status_code=500,
            detail={"error": "Analytics error", "message": "Failed to retrieve analytics data"}
        )


async def verify_admin_token(request: Request, authorization: str = Header(None)):
    """Verify admin bearer token with rate limiting and audit logging"""
    if not config.ADMIN_TOKEN:
        raise HTTPException(
            status_code=500, detail="Admin authentication not configured"
        )

    if not authorization:
        raise HTTPException(status_code=401, detail="Authorization header required")

    # Extract client IP for audit logging
    client_ip = request.client.host if request.client else "unknown"
    x_forwarded_for = request.headers.get("X-Forwarded-For")
    if x_forwarded_for:
        client_ip = x_forwarded_for.split(",")[0].strip()
    
    # Rate limit admin endpoints more strictly (5 attempts per minute)
    admin_rate_key = f"admin_{client_ip}"
    is_allowed, remaining = rate_limiter.check_rate_limit(admin_rate_key)
    
    if not is_allowed:
        logger.warning(f"Admin rate limit exceeded for {client_ip[:16]}...")
        # Log potential attack
        db.analytics.log_search(
            search_query=f"ADMIN_RATE_LIMIT_EXCEEDED",
            search_type="security_event",
            city_banana=None,
            zipcode=None,
            topic_flags=["rate_limit", "admin", client_ip[:16]]
        )
        raise HTTPException(
            status_code=429, 
            detail="Too many authentication attempts. Please try again later.",
            headers={"Retry-After": "60"}
        )

    try:
        scheme, token = authorization.split(" ")
        if scheme.lower() != "bearer":
            logger.warning(f"Invalid admin auth scheme from {client_ip[:16]}...")
            raise HTTPException(status_code=401, detail="Invalid authentication scheme")

        # Hash comparison for timing attack resistance
        import hmac
        if not hmac.compare_digest(token, config.ADMIN_TOKEN):
            logger.warning(f"Invalid admin token attempt from {client_ip[:16]}...")
            # Log failed authentication
            db.analytics.log_search(
                search_query=f"ADMIN_AUTH_FAILED",
                search_type="security_event",
                city_banana=None,
                zipcode=None,
                topic_flags=["auth_failed", "admin", client_ip[:16]]
            )
            raise HTTPException(status_code=403, detail="Invalid admin token")
        
        # Log successful admin access
        logger.info(f"Admin access granted for {client_ip[:16]}... to {request.url.path}")
        db.analytics.log_search(
            search_query=f"ADMIN_ACCESS:{request.url.path}",
            search_type="admin_activity",
            city_banana=None,
            zipcode=None,
            topic_flags=["admin_success", client_ip[:16]]
        )

    except ValueError:
        raise HTTPException(
            status_code=401, detail="Invalid authorization header format"
        )

    return True


@app.get("/api/admin/city-requests")
async def get_city_requests(request: Request, is_admin: bool = Depends(verify_admin_token)):
    """Get top city requests for admin review"""
    try:
        top_requests = db.get_top_city_requests(50)
        return {
            "success": True,
            "city_requests": top_requests,
            "total_count": len(top_requests),
        }
    except Exception as e:
        logger.error(f"Error getting city requests: {e}")
        raise HTTPException(status_code=500, detail="Failed to get city requests")


@app.post("/api/admin/sync-city/{city_banana}")
async def force_sync_city(
    city_banana: str, request: Request, is_admin: bool = Depends(verify_admin_token)
):
    """Force sync a specific city (admin endpoint)"""
    # This endpoint requires the background processor daemon to be running
    # Admin should use the daemon directly: python daemon.py --sync-city CITY_BANANA
    return {
        "success": False,
        "city_banana": city_banana,
        "message": "Background processing runs as separate service. Use daemon directly:",
        "command": f"python /root/engagic/app/daemon.py --sync-city {city_banana}",
        "alternative": "systemctl status engagic-daemon",
    }


@app.post("/api/admin/process-meeting")
async def force_process_meeting(
    process_request: ProcessRequest, request: Request, is_admin: bool = Depends(verify_admin_token)
):
    """Force process a specific meeting (admin endpoint)"""
    # This endpoint requires the background processor daemon to be running
    # Admin should use the daemon directly
    return {
        "success": False,
        "packet_url": process_request.packet_url,
        "message": "Background processing runs as separate service. Use daemon directly:",
        "command": f"python /root/engagic/app/daemon.py --process-meeting {process_request.packet_url}",
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
        _ = db.get_cache_stats()
        logger.info("Databases initialized successfully")
        sys.exit(0)

    uvicorn.run(app, host=config.API_HOST, port=config.API_PORT)
