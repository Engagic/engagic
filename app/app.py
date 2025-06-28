from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional
from adapters import PrimeGovAdapter
from fullstack import AgendaProcessor
from database import MeetingDatabase
from uszipcode import SearchEngine

app = FastAPI(title="engagic API", description="EGMI")


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
except ValueError:
    print("Warning: ANTHROPIC_API_KEY not found - LLM processing will be disabled")
    processor = None

db = MeetingDatabase()
zipcode_search = SearchEngine()

def parse_city_state_input(input_str: str) -> tuple[str, str]:
    """Parse city, state from user input
    
    Handles formats like:
    - "Palo Alto, CA"
    - "Palo Alto, California" 
    - "Boston Massachusetts"
    - "New York NY"
    
    Returns: (city_name, state_abbreviation)
    """
    input_str = input_str.strip()
    
    # Common state name to abbreviation mapping
    state_map = {
        'alabama': 'AL', 'alaska': 'AK', 'arizona': 'AZ', 'arkansas': 'AR', 'california': 'CA',
        'colorado': 'CO', 'connecticut': 'CT', 'delaware': 'DE', 'florida': 'FL', 'georgia': 'GA',
        'hawaii': 'HI', 'idaho': 'ID', 'illinois': 'IL', 'indiana': 'IN', 'iowa': 'IA',
        'kansas': 'KS', 'kentucky': 'KY', 'louisiana': 'LA', 'maine': 'ME', 'maryland': 'MD',
        'massachusetts': 'MA', 'michigan': 'MI', 'minnesota': 'MN', 'mississippi': 'MS', 'missouri': 'MO',
        'montana': 'MT', 'nebraska': 'NE', 'nevada': 'NV', 'new hampshire': 'NH', 'new jersey': 'NJ',
        'new mexico': 'NM', 'new york': 'NY', 'north carolina': 'NC', 'north dakota': 'ND', 'ohio': 'OH',
        'oklahoma': 'OK', 'oregon': 'OR', 'pennsylvania': 'PA', 'rhode island': 'RI', 'south carolina': 'SC',
        'south dakota': 'SD', 'tennessee': 'TN', 'texas': 'TX', 'utah': 'UT', 'vermont': 'VT',
        'virginia': 'VA', 'washington': 'WA', 'west virginia': 'WV', 'wisconsin': 'WI', 'wyoming': 'WY'
    }
    
    # Try comma-separated format first: "City, State"
    if ',' in input_str:
        parts = [p.strip() for p in input_str.split(',')]
        if len(parts) == 2:
            city, state = parts
            state_lower = state.lower()
            
            # Check if it's already an abbreviation
            if len(state) == 2 and state.upper() in state_map.values():
                return city, state.upper()
            # Check if it's a full state name
            elif state_lower in state_map:
                return city, state_map[state_lower]
    
    # Try space-separated format: "City State" or "City Full State Name"
    words = input_str.split()
    if len(words) >= 2:
        # Try last word as state abbreviation
        last_word = words[-1].lower()
        if len(last_word) == 2 and last_word.upper() in state_map.values():
            city = ' '.join(words[:-1])
            return city, last_word.upper()
        
        # Try last 1-2 words as full state name
        for num_state_words in [2, 1]:
            if len(words) > num_state_words:
                potential_state = ' '.join(words[-num_state_words:]).lower()
                if potential_state in state_map:
                    city = ' '.join(words[:-num_state_words])
                    return city, state_map[potential_state]
    
    # No state found
    return input_str, None


class MeetingRequest(BaseModel):
    packet_url: str
    city_slug: str
    meeting_name: Optional[str] = None
    meeting_date: Optional[str] = None
    meeting_id: Optional[str] = None


@app.get("/api/meetings")
async def get_meetings(city: Optional[str] = None):
    """Get meetings for a city - from database first, scrape if missing"""
    try:
        if not city:
            raise HTTPException(status_code=400, detail="city parameter is required")

        print(f"Fetching meetings for city: {city}")

        # First check database for cached meetings
        meetings = db.get_meetings_by_city(city, 50)
        if meetings:
            print(f"Found {len(meetings)} cached meetings for {city}")
            return meetings

        # If no cached meetings, find the vendor for this city and scrape
        city_entry = db.get_city_by_slug(city)
        if city_entry:
            vendor = city_entry.get("vendor")
            city_name = city_entry.get("city")
        else:
            vendor = None
            city_name = None

        if not vendor:
            print(f"No vendor configured for city {city}")

            if city_name:
                return {
                    "message": f"{city_name} has been registered and will be integrated soon",
                    "meetings": [],
                    "city_slug": city,
                    "status": "pending_integration"
                }
            else:
                print(f"City {city} not found in database")

                raise HTTPException(
                    status_code=404, detail=f"City {city} not found"
                )

        # Scrape fresh meetings using the appropriate adapter
        if vendor == "primegov":
            try:
                print(f"Scraping meetings for {city} using PrimeGov")
                adapter = PrimeGovAdapter(city)
                scraped_meetings = []
                for meeting in adapter.upcoming_packets():
                    # Store the meeting in database
                    db.store_meeting_data(
                        {
                            "city_slug": city,
                            "meeting_name": meeting.get("title"),
                            "packet_url": meeting.get("packet_url"),
                            "meeting_date": meeting.get("start"),
                        },
                        vendor,
                    )
                    scraped_meetings.append(meeting)
                print(f"Successfully scraped {len(scraped_meetings)} meetings for {city}")
                return scraped_meetings
            except Exception as scrape_error:
                print(f"Failed to scrape {city} with PrimeGov: {scrape_error}")
                return {
                    "message": f"{city_name} integration is experiencing issues and will be fixed soon",
                    "meetings": [],
                    "city_slug": city,
                    "status": "integration_error"
                }
        else:
            print(f"Vendor {vendor} not yet implemented for city {city}")
            return {
                "message": f"{city_name} has been registered and will be integrated soon",
                "meetings": [],
                "city_slug": city,
                "status": "vendor_not_implemented"
            }

    except HTTPException:
        raise
    except Exception as e:
        print(f"Unexpected error fetching meetings for {city}: {str(e)}")
        raise HTTPException(
            status_code=500, detail=f"Error fetching meetings: {str(e)}"
        )


@app.post("/api/process-agenda")
async def process_agenda(request: MeetingRequest):
    """Process an agenda with caching - returns cached or newly processed summary"""
    if not processor:
        raise HTTPException(
            status_code=503,
            detail="LLM processing not available - ANTHROPIC_API_KEY required",
        )

    try:
        # Convert request to meeting data format
        meeting_data = {
            "packet_url": request.packet_url,
            "city_slug": request.city_slug,
            "meeting_name": request.meeting_name,
            "meeting_date": request.meeting_date,
            "meeting_id": request.meeting_id,
        }

        # Process with caching
        result = processor.process_agenda_with_cache(meeting_data)

        return {
            "success": True,
            "summary": result["summary"],
            "processing_time_seconds": result["processing_time"],
            "cached": result["cached"],
            "meeting_data": result["meeting_data"],
        }

    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Error processing agenda: {str(e)}"
        )


@app.get("/api/meetings/{city_slug}")
async def get_city_meetings(city_slug: str, limit: int = 50):
    """Get cached meetings for a specific city"""
    try:
        meetings = db.get_meetings_by_city(city_slug, limit)
        return {"city_slug": city_slug, "meetings": meetings, "count": len(meetings)}
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Error fetching city meetings: {str(e)}"
        )


@app.get("/api/meetings/recent")
async def get_recent_meetings(limit: int = 20):
    """Get most recently accessed meetings across all cities"""
    try:
        meetings = db.get_recent_meetings(limit)
        return {"meetings": meetings, "count": len(meetings)}
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Error fetching recent meetings: {str(e)}"
        )


@app.get("/api/cache/stats")
async def get_cache_stats():
    """Get cache statistics"""
    try:
        stats = db.get_cache_stats()
        return stats
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Error fetching cache stats: {str(e)}"
        )


@app.delete("/api/cache/cleanup")
async def cleanup_cache(days_old: int = 90):
    """Clean up old cache entries"""
    try:
        deleted_count = db.cleanup_old_entries(days_old)
        return {
            "deleted_count": deleted_count,
            "message": f"Cleaned up {deleted_count} entries older than {days_old} days",
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error cleaning cache: {str(e)}")


@app.get("/api/search/{query}")
async def unified_search(query: str):
    """Unified search endpoint that handles zipcode and city, state input"""
    try:
        query = query.strip()
        print(f"Search request: '{query}'")

        if not query:
            raise HTTPException(status_code=400, detail="Search query cannot be empty")

        # Determine if input is zipcode (5 digits) or city name
        is_zipcode = query.isdigit() and len(query) == 5

        if is_zipcode:
            print(f"Processing as zipcode: {query}")
            return await handle_zipcode_search(query)
        else:
            print(f"Processing as city, state: {query}")
            return await handle_city_search(query)

    except HTTPException:
        raise
    except Exception as e:
        print(f"Unexpected search error for '{query}': {str(e)}")
        raise HTTPException(status_code=500, detail=f"Search error: {str(e)}")


async def handle_zipcode_search(zipcode: str):
    """Handle zipcode-based search"""
    # Check if we have this zipcode in our database
    cached_entry = db.get_city_by_zipcode(zipcode)
    if cached_entry:
        print(f"Found cached entry for zipcode {zipcode}: {cached_entry.get('city')}")
        return cached_entry

    # Use uszipcode to resolve zipcode to city
    try:
        result = zipcode_search.by_zipcode(zipcode)
        print(f"Zipcode lookup result for {zipcode}: {result}")
    except Exception as e:
        print(f"Error looking up zipcode {zipcode}: {e}")
        raise HTTPException(status_code=400, detail="Please enter a valid zipcode and try again")

    if not result or not result.zipcode:
        print(f"Invalid zipcode {zipcode}: not found in database")
        raise HTTPException(status_code=400, detail="Please enter a valid zipcode and try again")

    # Create city slug from city name
    city_name = result.major_city or result.post_office_city
    if not city_name:
        print(f"Invalid zipcode {zipcode}: no associated city found")
        raise HTTPException(status_code=400, detail="Please enter a valid zipcode and try again")

    city_slug = city_name.lower().replace(" ", "").replace("-", "")
    print(f"Creating entry for new zipcode {zipcode} -> {city_name} ({city_slug})")

    # Create entry for new zipcode/city
    return await create_city_entry(
        zipcode, city_name, city_slug, result.state, result.county, is_new=True
    )


async def handle_city_search(city_input: str):
    """Handle city name-based search - requires city, state format"""
    # Clean and validate city input
    city_input = city_input.strip()
    if len(city_input) < 2:
        raise HTTPException(status_code=400, detail="City name must be at least 2 characters")

    # Parse city, state from input
    city_name, state = parse_city_state_input(city_input)
    
    if not state:
        raise HTTPException(
            status_code=400, 
            detail="Please specify both city and state (e.g., 'Palo Alto, CA' or 'Boston Massachusetts')"
        )

    # Check if we already have this city in our database
    cached_entry = db.get_city_by_name(city_name, state)
    if cached_entry:
        print(f"Found cached entry for {city_name}, {state}")
        return cached_entry

    # First time encountering this city - resolve using uszipcode
    print(f"NEW CITY REGISTERED: {city_name}, {state}")
    
    # Use uszipcode to resolve city to get complete information
    try:
        city_results = zipcode_search.by_city_and_state(city_name, state)
        print(f"City lookup result for {city_name}, {state}: found {len(city_results)} zipcodes")
    except Exception as e:
        print(f"Error looking up city {city_name}, {state}: {e}")
        raise HTTPException(status_code=400, detail="Please enter a valid city name and state and try again")
    
    if not city_results:
        print(f"Invalid city name {city_name}, {state}: not found in database")
        raise HTTPException(status_code=400, detail="Please enter a valid city name and state and try again")
    
    # Use the first/primary result for the city
    primary_result = city_results[0]
    primary_zipcode = primary_result.zipcode
    county = primary_result.county
    
    # Generate city slug for URL purposes (but not for DB searching)
    city_slug = city_name.lower().replace(" ", "").replace("-", "")
    
    print(f"Creating entry for new city {city_name}, {state} -> {primary_zipcode} ({county})")
    
    return await create_city_entry(primary_zipcode, city_name, city_slug, state, county, is_new=True)


async def create_city_entry(zipcode, city_name, city_slug, state, county, is_new=False):
    """Create a new city entry with optional meeting lookup"""
    meetings = []
    
    # Create entry data with better messaging
    entry_data = {
        "zipcode": zipcode,
        "city": city_name,
        "city_slug": city_slug,
        "vendor": None,
        "state": state,
        "county": county,
        "meetings": meetings,
        "is_new_city": is_new,
        "needs_manual_config": True,
        "status": "registered",
        "message": f"Great! We've added {city_name} to our system and we're working to integrate their meeting data."
    }

    # Store in database - always attempt to store new cities
    try:
        db.store_city_entry(entry_data)
        if zipcode:
            print(f"Successfully stored new zipcode entry: {zipcode} -> {city_name}")
        else:
            print(f"Successfully stored new city entry: {city_name} ({city_slug})")
    except Exception as e:
        print(f"Error storing city entry for {city_name}: {e}")
        # Don't fail the request if storage fails - continue to show welcome message

    return entry_data


@app.get("/")
async def root():
    """API status and info"""
    return {
        "service": "engagic API",
        "status": "running",
        "version": "1.0.0",
        "endpoints": {
            "search": "/api/search/{zipcode_or_city}",
            "meetings": "/api/meetings?city={city}",
            "process": "/api/process-agenda",
            "city_meetings": "/api/meetings/{city_slug}",
            "recent": "/api/meetings/recent",
            "cache_stats": "/api/cache/stats",
            "health": "/api/health",
        },
    }


@app.get("/api/health")
async def health_check():
    """Health check endpoint"""
    try:
        # Test database connection
        stats = db.get_cache_stats()
        
        # Test zipcode service
        test_result = zipcode_search.by_zipcode("90210")
        
        return {
            "status": "healthy",
            "database": "connected",
            "zipcode_service": "available",
            "llm_processor": "available" if processor else "disabled",
            "cache_entries": stats.get("total_entries", 0)
        }
    except Exception as e:
        print(f"Health check failed: {e}")
        return {
            "status": "unhealthy",
            "error": str(e)
        }


if __name__ == "__main__":
    import uvicorn
    
    print("Starting engagic API server...")
    print(f"LLM processor: {'enabled' if processor else 'disabled'}")
    uvicorn.run(app, host="0.0.0.0", port=8000)
