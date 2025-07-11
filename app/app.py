from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, validator
from typing import Optional, List, Dict, Any
import logging
import time
import uuid
import re
from collections import defaultdict
from datetime import datetime, timedelta
from fullstack import AgendaProcessor
from databases import DatabaseManager
from uszipcode import SearchEngine
from config import config
from utils import generate_city_banana

# Configure structured logging
logging.basicConfig(
    level=getattr(logging, config.LOG_LEVEL),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(config.LOG_PATH, mode='a')
    ]
)
logger = logging.getLogger("engagic")

app = FastAPI(title="engagic API", description="EGMI")

# Rate limiting storage
rate_limits = defaultdict(list)

# Rate limiting middleware
@app.middleware("http")
async def rate_limit_middleware(request: Request, call_next):
    client_ip = request.client.host if request.client else "unknown"
    current_time = time.time()
    
    # Clean old entries
    rate_limits[client_ip] = [
        timestamp for timestamp in rate_limits[client_ip] 
        if current_time - timestamp < config.RATE_LIMIT_WINDOW
    ]
    
    # Check rate limit for API endpoints
    if request.url.path.startswith("/api/"):
        if len(rate_limits[client_ip]) >= config.RATE_LIMIT_REQUESTS:
            logger.warning(f"Rate limit exceeded for {client_ip}")
            raise HTTPException(status_code=429, detail="Rate limit exceeded. Please try again later.")
        
        # Add current request
        rate_limits[client_ip].append(current_time)
    
    response = await call_next(request)
    return response

# Request/Response logging middleware
@app.middleware("http")
async def log_requests(request: Request, call_next):
    request_id = str(uuid.uuid4())[:8]
    start_time = time.time()
    
    # Log incoming request
    logger.info(f"[{request_id}] {request.method} {request.url.path} - Client: {request.client.host if request.client else 'unknown'}")
    
    # Process request
    try:
        response = await call_next(request)
        duration = time.time() - start_time
        
        # Log response
        logger.info(f"[{request_id}] Response: {response.status_code} - Duration: {duration:.3f}s")
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
    processor = AgendaProcessor(api_key=config.get_api_key(), db_path=config.MEETINGS_DB_PATH)
    logger.info("LLM processor initialized successfully")
except ValueError as e:
    logger.warning("API key not found - LLM processing will be disabled")
    processor = None

# Initialize database manager with separate databases
db = DatabaseManager(
    locations_db_path=config.LOCATIONS_DB_PATH,
    meetings_db_path=config.MEETINGS_DB_PATH,
    analytics_db_path=config.ANALYTICS_DB_PATH
)
zipcode_search = SearchEngine()

def normalize_city_name(city_name: str) -> str:
    """Normalize city name for consistent formatting"""
    city = city_name.strip()
    
    # Handle special cases where simple title() doesn't work well
    special_cases = {
        'lasvegas': 'Las Vegas',
        'newyork': 'New York',
        'losangeles': 'Los Angeles',
        'sanfrancisco': 'San Francisco',
        'sanjose': 'San Jose',
        'sandiego': 'San Diego',
        'santaana': 'Santa Ana',
        'santabarbara': 'Santa Barbara',
        'stlouis': 'St. Louis',
        'stpaul': 'St. Paul',
        'ftworth': 'Fort Worth',
        'fortworth': 'Fort Worth',
    }
    
    city_lower_nospace = city.lower().replace(' ', '').replace('.', '')
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


def sanitize_string(value: str) -> str:
    """Sanitize string input to prevent injection attacks"""
    if not value:
        return ""
    # Remove potentially dangerous characters
    sanitized = re.sub(r'[<>"\';()&+]', '', value.strip())
    return sanitized[:config.MAX_QUERY_LENGTH]

class SearchRequest(BaseModel):
    query: str
    
    @validator('query')
    def validate_query(cls, v):
        if not v or not v.strip():
            raise ValueError('Search query cannot be empty')
        
        sanitized = sanitize_string(v)
        if len(sanitized) < 2:
            raise ValueError('Search query too short')
        if len(sanitized) > config.MAX_QUERY_LENGTH:
            raise ValueError(f'Search query too long (max {config.MAX_QUERY_LENGTH} characters)')
        
        # Basic pattern validation
        if not re.match(r'^[a-zA-Z0-9\s,.-]+$', sanitized):
            raise ValueError('Search query contains invalid characters')
        
        return sanitized

class ProcessRequest(BaseModel):
    packet_url: str
    city_slug: str
    meeting_name: Optional[str] = None
    meeting_date: Optional[str] = None
    meeting_id: Optional[str] = None
    
    @validator('packet_url')
    def validate_packet_url(cls, v):
        if not v or not v.strip():
            raise ValueError('Packet URL cannot be empty')
        
        # Basic URL validation
        if not re.match(r'^https?://', v):
            raise ValueError('Packet URL must be a valid HTTP/HTTPS URL')
        
        if len(v) > 2000:
            raise ValueError('Packet URL too long')
        
        return v.strip()
    
    @validator('city_slug')
    def validate_city_slug(cls, v):
        if not v or not v.strip():
            raise ValueError('City slug cannot be empty')
        
        # City slug should be alphanumeric
        if not re.match(r'^[a-z0-9]+$', v.lower()):
            raise ValueError('City slug contains invalid characters')
        
        return v.lower().strip()
    
    @validator('meeting_name', 'meeting_date', 'meeting_id', pre=True, always=True)
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
        
        # Log the search
        db.log_search(query, "unknown")  # We'll determine type below
        
        # Determine if input is zipcode or city name
        is_zipcode = query.isdigit() and len(query) == 5
        
        if is_zipcode:
            return await handle_zipcode_search(query)
        else:
            return await handle_city_search(query)
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Unexpected search error for '{query}': {str(e)}")
        raise HTTPException(status_code=500, detail=f"Search error: {str(e)}")


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
                db.log_city_request(city_name, state, zipcode, "zipcode", zipcode=zipcode)
        except Exception as e:
            logger.warning(f"Failed to log city request for zipcode {zipcode}: {e}")
        
        return {
            "success": False,
            "message": "We're not covering that area yet, but we're always expanding! Thanks for your interest - we'll prioritize cities with high demand.",
            "query": zipcode,
            "type": "zipcode",
            "meetings": []
        }
    
    # Get cached meetings using city_banana
    city_banana = city_info.get('city_banana') or generate_city_banana(city_info['city_name'], city_info['state'])
    meetings = db.get_meetings_by_city(city_banana, 50)
    
    if meetings:
        logger.info(f"Found {len(meetings)} cached meetings for {city_info['city_name']}, {city_info.get('state', 'Unknown')}")
        return {
            "success": True,
            "city_name": city_info['city_name'],
            "state": city_info['state'],
            "city_slug": city_info['city_slug'],
            "vendor": city_info['vendor'],
            "meetings": meetings,
            "cached": True,
            "query": zipcode,
            "type": "zipcode"
        }
    
    # No cached meetings - background processor will handle this
    return {
        "success": True,
        "city_name": city_info['city_name'],
        "state": city_info['state'],
        "city_slug": city_info['city_slug'],
        "vendor": city_info['vendor'],
        "meetings": [],
        "cached": False,
        "query": zipcode,
        "type": "zipcode",
        "message": f"No meetings available yet for {city_info['city_name']} - check back soon as we sync with the city website"
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
            "meetings": []
        }
    
    # Log search with city_id
    db.log_search(city_input, "city_name", city_id=city_info['id'])
    
    # Get cached meetings using city_banana
    city_banana = city_info.get('city_banana') or generate_city_banana(city_info['city_name'], city_info['state'])
    meetings = db.get_meetings_by_city(city_banana, 50)
    
    if meetings:
        logger.info(f"Found {len(meetings)} cached meetings for {city_name}, {state}")
        return {
            "success": True,
            "city_name": city_info['city_name'],
            "state": city_info['state'],
            "city_slug": city_info['city_slug'],
            "vendor": city_info['vendor'],
            "meetings": meetings,
            "cached": True,
            "query": city_input,
            "type": "city_name"
        }
    
    # No cached meetings - return empty
    return {
        "success": False,
        "city_name": city_info['city_name'],
        "state": city_info['state'],
        "city_slug": city_info['city_slug'],
        "vendor": city_info['vendor'],
        "meetings": [],
        "cached": True,
        "query": city_input,
        "type": "city_name",
        "message": f"No meetings cached yet for {city_name}, {state}"
    }


async def handle_ambiguous_city_search(city_name: str, original_input: str) -> Dict[str, Any]:
    """Handle city search when no state is provided - check for ambiguous matches"""
    
    # Look for all cities with this name
    cities = db.get_cities_by_name_only(city_name)
    
    if not cities:
        # No cities found - log the request
        try:
            db.log_city_request(city_name, "UNKNOWN", original_input, "city_name_ambiguous")
        except Exception as e:
            logger.warning(f"Failed to log ambiguous city request for {city_name}: {e}")
        
        return {
            "success": False,
            "message": f"We don't have '{city_name}' in our database yet. Please include the state (e.g., '{city_name}, CA') - your interest has been noted!",
            "query": original_input,
            "type": "city_name",
            "meetings": [],
            "ambiguous": False
        }
    
    if len(cities) == 1:
        # Only one match - proceed with this city
        city_info = cities[0]
        
        # Log search with city_id
        db.log_search(original_input, "city_name", city_id=city_info['id'])
        
        # Get meetings for this city using city_banana
        city_banana = city_info.get('city_banana') or generate_city_banana(city_info['city_name'], city_info['state'])
        meetings = db.get_meetings_by_city(city_banana, 50)
        
        if meetings:
            logger.info(f"Found {len(meetings)} cached meetings for {city_info['city_name']}, {city_info['state']}")
            return {
                "success": True,
                "city_name": city_info['city_name'],
                "state": city_info['state'],
                "city_slug": city_info['city_slug'],
                "vendor": city_info['vendor'],
                "meetings": meetings,
                "cached": True,
                "query": original_input,
                "type": "city_name",
                "ambiguous": False
            }
        else:
            return {
                "success": False,
                "city_name": city_info['city_name'],
                "state": city_info['state'],
                "city_slug": city_info['city_slug'],
                "vendor": city_info['vendor'],
                "meetings": [],
                "cached": True,
                "query": original_input,
                "type": "city_name",
                "message": f"No meetings cached yet for {city_info['city_name']}, {city_info['state']}",
                "ambiguous": False
            }
    
    # Multiple matches - return ambiguous result
    city_options = []
    for city in cities:
        city_options.append({
            "city_name": city['city_name'],
            "state": city['state'],
            "city_slug": city['city_slug'],
            "vendor": city['vendor'],
            "display_name": f"{city['city_name']}, {city['state']}"
        })
    
    return {
        "success": False,
        "message": f"Multiple cities named '{city_name}' found. Please specify which one:",
        "query": original_input,
        "type": "city_name",
        "ambiguous": True,
        "city_options": city_options,
        "meetings": []
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
                "summary": cached_summary["processed_summary"],
                "processing_time_seconds": cached_summary.get("processing_time_seconds", 0),
                "cached": True,
                "meeting_data": cached_summary,
            }
        
        # No cached summary available
        return {
            "success": False,
            "message": "Summary not yet available - processing in background",
            "cached": False,
            "packet_url": request.packet_url,
            "estimated_wait_minutes": 10  # Rough estimate
        }

    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Error retrieving agenda: {str(e)}"
        )


@app.get("/api/stats")
async def get_stats():
    """Get system statistics"""
    try:
        stats = db.get_cache_stats()
        queue_stats = db.get_processing_queue_stats()
        request_stats = db.get_city_request_stats()
        
        # Background processor info (separate service)
        background_info = {
            "status": "separate_service",
            "note": "Background processing runs as separate daemon service"
        }
        
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
                "note": "Check daemon status: systemctl status engagic-daemon"
            }
        }
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Error fetching stats: {str(e)}"
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
                "process_meeting": "POST /api/admin/process-meeting - Force process specific meeting"
            }
        },
        "usage_examples": {
            "search_by_zipcode": {
                "method": "POST",
                "url": "/api/search",
                "body": {"query": "94301"},
                "description": "Search meetings by ZIP code"
            },
            "search_by_city": {
                "method": "POST",
                "url": "/api/search", 
                "body": {"query": "Palo Alto, CA"},
                "description": "Search meetings by city and state"
            },
            "search_ambiguous": {
                "method": "POST",
                "url": "/api/search",
                "body": {"query": "Springfield"},
                "description": "Search by city name only (may return multiple options)"
            },
            "get_summary": {
                "method": "POST",
                "url": "/api/process-agenda",
                "body": {
                    "packet_url": "https://example.com/agenda.pdf",
                    "city_slug": "paloaltoca",
                    "meeting_name": "City Council Meeting"
                },
                "description": "Get cached AI summary of meeting agenda"
            }
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
            "Request demand tracking"
        ],
        "data_sources": [
            "PrimeGov (city council management)",
            "CivicClerk (municipal systems)",
            "Direct city websites"
        ]
    }


@app.get("/api/health")
async def health_check():
    """Health check endpoint"""
    health_status = {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "version": "2.0.0",
        "checks": {}
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
            "processed": stats.get("processed_count", 0)
        }
    except Exception as e:
        health_status["checks"]["databases"] = {
            "status": "unhealthy",
            "error": str(e)
        }
        health_status["status"] = "degraded"
    
    # LLM processor check
    health_status["checks"]["llm_processor"] = {
        "status": "available" if processor else "disabled",
        "has_api_key": bool(config.get_api_key())
    }
    
    # Configuration check
    health_status["checks"]["configuration"] = {
        "status": "healthy",
        "is_development": config.is_development(),
        "rate_limiting": f"{config.RATE_LIMIT_REQUESTS} req/{config.RATE_LIMIT_WINDOW}s",
        "background_processing": config.BACKGROUND_PROCESSING
    }
    
    # Background processor check (separate service)
    health_status["checks"]["background_processor"] = {
        "status": "separate_service",
        "note": "Background processing runs as independent daemon",
        "check_command": "systemctl status engagic-daemon"
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
                "recent_activity": stats.get("recent_activity", 0)
            },
            "processing": {
                "unprocessed_queue": queue_stats.get("unprocessed_count", 0),
                "success_rate": f"{queue_stats.get('success_rate', 0):.1f}%",
                "recent_meetings": queue_stats.get("recent_count", 0)
            },
            "demand": {
                "total_city_requests": request_stats.get("total_unique_cities_requested", 0),
                "total_demand": request_stats.get("total_demand", 0),
                "recent_requests": request_stats.get("recent_activity", 0)
            },
            "configuration": {
                "rate_limit_window": config.RATE_LIMIT_WINDOW,
                "rate_limit_requests": config.RATE_LIMIT_REQUESTS,
                "background_processing": config.BACKGROUND_PROCESSING
            }
        }
    except Exception as e:
        logger.error(f"Metrics endpoint failed: {e}")
        raise HTTPException(status_code=500, detail=f"Error fetching metrics: {str(e)}")


@app.get("/api/admin/city-requests")
async def get_city_requests():
    """Get top city requests for admin review"""
    try:
        top_requests = db.get_top_city_requests(50)
        return {
            "success": True,
            "city_requests": top_requests,
            "total_count": len(top_requests)
        }
    except Exception as e:
        logger.error(f"Error getting city requests: {e}")
        raise HTTPException(status_code=500, detail="Failed to get city requests")


@app.post("/api/admin/sync-city/{city_slug}")
async def force_sync_city(city_slug: str):
    """Force sync a specific city (admin endpoint)"""
    # This endpoint requires the background processor daemon to be running
    # Admin should use the daemon directly: python daemon.py --sync-city SLUG
    return {
        "success": False,
        "city_slug": city_slug,
        "message": "Background processing runs as separate service. Use daemon directly:",
        "command": f"python /root/engagic/app/daemon.py --sync-city {city_slug}",
        "alternative": f"systemctl status engagic-daemon"
    }


@app.post("/api/admin/process-meeting")
async def force_process_meeting(request: ProcessRequest):
    """Force process a specific meeting (admin endpoint)"""
    # This endpoint requires the background processor daemon to be running
    # Admin should use the daemon directly
    return {
        "success": False,
        "packet_url": request.packet_url,
        "message": "Background processing runs as separate service. Use daemon directly:",
        "command": f"python /root/engagic/app/daemon.py --process-meeting {request.packet_url}",
        "alternative": "systemctl status engagic-daemon"
    }


if __name__ == "__main__":
    import uvicorn

    logger.info("Starting engagic API server...")
    logger.info(f"Configuration: {config.summary()}")
    logger.info(f"LLM processor: {'enabled' if processor else 'disabled'}")
    uvicorn.run(app, host=config.API_HOST, port=config.API_PORT)
