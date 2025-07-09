from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
import logging
import time
import uuid
from fullstack import AgendaProcessor
from database import MeetingDatabase
from uszipcode import SearchEngine

# Configure structured logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('/root/engagic/app/engagic.log', mode='a')
    ]
)
logger = logging.getLogger("engagic")

app = FastAPI(title="engagic API", description="EGMI")

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
    allow_origins=[
        "https://engagic.org",
        "https://www.engagic.org",
        "https://api.engagic.org",
        "https://engagic.pages.dev",  # Cloudflare Pages preview domains
        "http://localhost:3000",  # React/Next.js
        "http://localhost:5173",  # Vite (SvelteKit)
        "http://localhost:5000",  # Other common ports
        "http://127.0.0.1:3000",
        "https://165.232.158.241",
    ],
    allow_methods=["*"],
    allow_headers=["*"],
    allow_credentials=True,
)

# Initialize global instances
try:
    processor = AgendaProcessor()
    logger.info("LLM processor initialized successfully")
except ValueError as e:
    logger.warning("ANTHROPIC_API_KEY not found - LLM processing will be disabled")
    processor = None

db = MeetingDatabase()
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


class SearchRequest(BaseModel):
    query: str  # zipcode or "city, state"

class ProcessRequest(BaseModel):
    packet_url: str
    city_slug: str
    meeting_name: Optional[str] = None
    meeting_date: Optional[str] = None
    meeting_id: Optional[str] = None


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
    
    # Get cached meetings
    meetings = db.get_meetings_by_city(city_info['city_slug'], 50)
    
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
    
    # Get cached meetings
    meetings = db.get_meetings_by_city(city_info['city_slug'], 50)
    
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
        
        # Get meetings for this city
        meetings = db.get_meetings_by_city(city_info['city_slug'], 50)
        
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
        sync_status = background_processor.get_sync_status()
        
        request_stats = db.get_city_request_stats()
        
        return {
            "status": "healthy",
            "cities": stats.get("cities_count", 0),
            "meetings": stats.get("meetings_count", 0),
            "processed": stats.get("processed_count", 0),
            "recent_activity": stats.get("recent_activity", 0),
            "city_requests": request_stats,
            "background_processing": {
                "is_running": sync_status.get("is_running", False),
                "last_sync": sync_status.get("last_full_sync"),
                "unprocessed_queue": queue_stats.get("unprocessed_count", 0),
                "processing_success_rate": f"{queue_stats.get('success_rate', 0):.1f}%",
                "recent_meetings": queue_stats.get("recent_count", 0)
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
        "description": "Simplified civic engagement API",
        "endpoints": {
            "search": "POST /api/search - Search for meetings by zipcode or city name",
            "process": "POST /api/process-agenda - Process meeting agenda with LLM",
            "stats": "GET /api/stats - System statistics",
            "health": "GET /api/health - Health check"
        },
        "usage": {
            "search_zipcode": {"method": "POST", "url": "/api/search", "body": {"query": "94301"}},
            "search_city": {"method": "POST", "url": "/api/search", "body": {"query": "Palo Alto, CA"}}
        }
    }


@app.get("/api/health")
async def health_check():
    """Health check endpoint"""
    try:
        # Test database connection
        stats = db.get_cache_stats()
        sync_status = background_processor.get_sync_status()

        return {
            "status": "healthy",
            "database": "connected",
            "llm_processor": "available" if processor else "disabled",
            "background_processor": "running" if sync_status.get("is_running") else "stopped",
            "cities": stats.get("cities_count", 0),
            "meetings": stats.get("meetings_count", 0)
        }
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return {"status": "unhealthy", "error": str(e)}


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
    try:
        result = background_processor.force_sync_city(city_slug)
        return {
            "success": True,
            "city_slug": city_slug,
            "result": {
                "status": result.status.value,
                "meetings_found": result.meetings_found,
                "meetings_processed": result.meetings_processed,
                "duration_seconds": result.duration_seconds,
                "error_message": result.error_message
            }
        }
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Error syncing city: {str(e)}"
        )


@app.post("/api/admin/process-meeting")
async def force_process_meeting(request: ProcessRequest):
    """Force process a specific meeting (admin endpoint)"""
    try:
        success = background_processor.force_process_meeting(request.packet_url)
        return {
            "success": success,
            "packet_url": request.packet_url,
            "message": "Processing completed" if success else "Processing failed"
        }
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Error processing meeting: {str(e)}"
        )


if __name__ == "__main__":
    import uvicorn

    logger.info("Starting engagic API server...")
    logger.info(f"LLM processor: {'enabled' if processor else 'disabled'}")
    uvicorn.run(app, host="0.0.0.0", port=8000)
