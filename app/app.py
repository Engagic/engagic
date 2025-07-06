from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
from adapters import PrimeGovAdapter, CivicClerkAdapter
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
            city = " ".join(words[:-1])
            return city, last_word.upper()

        # Try last 1-2 words as full state name
        for num_state_words in [2, 1]:
            if len(words) > num_state_words:
                potential_state = " ".join(words[-num_state_words:]).lower()
                if potential_state in state_map:
                    city = " ".join(words[:-num_state_words])
                    return city, state_map[potential_state]

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
        
        print(f"Search request: '{query}'")
        
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
        print(f"Unexpected search error for '{query}': {str(e)}")
        raise HTTPException(status_code=500, detail=f"Search error: {str(e)}")


async def handle_zipcode_search(zipcode: str) -> Dict[str, Any]:
    """Handle zipcode search with cache-first approach"""
    # Update search log
    db.log_search(zipcode, "zipcode", zipcode=zipcode)
    
    # Check database first
    city_info = db.get_city_by_zipcode(zipcode)
    if not city_info:
        # Try to auto-create city from uszipcode data
        city_info = await auto_create_city_from_zipcode(zipcode)
        if not city_info:
            return {
                "success": False,
                "message": "Thanks for asking! We don't have that zipcode yet, but we're working on adding more cities regularly. Try searching by city name instead.",
                "query": zipcode,
                "type": "zipcode",
                "meetings": []
            }
    
    # Get cached meetings
    meetings = db.get_meetings_by_city(city_info['city_slug'], 50)
    
    if meetings:
        print(f"Found {len(meetings)} cached meetings for {city_info['city_name']}")
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
    
    # Try to scrape fresh meetings
    return await scrape_meetings_for_city(city_info)


async def handle_city_search(city_input: str) -> Dict[str, Any]:
    """Handle city name search with cache-first approach"""
    # Parse city, state
    city_name, state = parse_city_state_input(city_input)
    
    if not state:
        return {
            "success": False,
            "message": "Please specify both city and state (e.g., 'Palo Alto, CA' or 'Boston Massachusetts')",
            "query": city_input,
            "type": "city_name",
            "meetings": []
        }
    
    # Check database first
    city_info = db.get_city_by_name(city_name, state)
    if not city_info:
        # Try to auto-create city from uszipcode data
        city_info = await auto_create_city_from_city_name(city_name, state)
        if not city_info:
            return {
                "success": False,
                "message": f"Thanks for asking! We don't have {city_name}, {state} yet, but we're working on adding more cities regularly.",
                "query": city_input,
                "type": "city_name",
                "meetings": []
            }
    
    # Log search with city_id
    db.log_search(city_input, "city_name", city_id=city_info['id'])
    
    # Get cached meetings
    meetings = db.get_meetings_by_city(city_info['city_slug'], 50)
    
    if meetings:
        print(f"Found {len(meetings)} cached meetings for {city_name}, {state}")
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
    
    # Try to scrape fresh meetings
    return await scrape_meetings_for_city(city_info)


async def scrape_meetings_for_city(city_info: Dict[str, Any]) -> Dict[str, Any]:
    """Scrape meetings for a city using appropriate adapter"""
    vendor = city_info.get('vendor')
    city_slug = city_info['city_slug']
    city_name = city_info['city_name']
    
    if not vendor:
        return {
            "success": True,
            "city_name": city_name,
            "state": city_info['state'],
            "city_slug": city_slug,
            "message": f"{city_name} has been registered and will be integrated soon",
            "meetings": [],
            "cached": False,
            "status": "pending_integration"
        }
    
    try:
        scraped_meetings = []
        
        if vendor == "primegov":
            print(f"Scraping meetings for {city_name} using PrimeGov")
            adapter = PrimeGovAdapter(city_slug)
            for meeting in adapter.upcoming_packets():
                # Store in database
                db.store_meeting_data({
                    "city_slug": city_slug,
                    "meeting_name": meeting.get("title"),
                    "packet_url": meeting.get("packet_url"),
                    "meeting_date": meeting.get("start"),
                    "meeting_id": meeting.get("meeting_id")
                })
                scraped_meetings.append(meeting)
                
        elif vendor == "civicclerk":
            print(f"Scraping meetings for {city_name} using CivicClerk")
            adapter = CivicClerkAdapter(city_slug)
            for meeting in adapter.upcoming_packets():
                # Store in database
                db.store_meeting_data({
                    "city_slug": city_slug,
                    "meeting_name": meeting.get("title"),
                    "packet_url": meeting.get("packet_url"),
                    "meeting_date": meeting.get("start"),
                    "meeting_id": meeting.get("meeting_id")
                })
                scraped_meetings.append(meeting)
        else:
            return {
                "success": True,
                "city_name": city_name,
                "state": city_info['state'],
                "city_slug": city_slug,
                "vendor": vendor,
                "message": f"{city_name} integration is in progress - meetings will be available soon",
                "meetings": [],
                "cached": False,
                "status": "vendor_not_implemented"
            }
        
        print(f"Successfully scraped {len(scraped_meetings)} meetings for {city_name}")
        return {
            "success": True,
            "city_name": city_name,
            "state": city_info['state'],
            "city_slug": city_slug,
            "vendor": vendor,
            "meetings": scraped_meetings,
            "cached": False,
            "scraped_count": len(scraped_meetings)
        }
        
    except Exception as scrape_error:
        print(f"Failed to scrape {city_name} with {vendor}: {scrape_error}")
        return {
            "success": True,
            "city_name": city_name,
            "state": city_info['state'],
            "city_slug": city_slug,
            "vendor": vendor,
            "message": f"{city_name} integration is experiencing temporary issues but will be fixed soon",
            "meetings": [],
            "cached": False,
            "status": "integration_error"
        }


async def auto_create_city_from_zipcode(zipcode: str) -> Optional[Dict[str, Any]]:
    """Auto-create city entry from zipcode using uszipcode"""
    try:
        print(f"Auto-creating city entry for zipcode {zipcode}")
        
        # Look up zipcode info
        result = zipcode_search.by_zipcode(zipcode)
        if not result or not result.major_city:
            print(f"No city found for zipcode {zipcode}")
            return None
        
        city_name = result.major_city
        state = result.state
        county = result.county
        
        # Create a basic city slug (we don't know the vendor yet)
        city_slug = f"{city_name.lower().replace(' ', '').replace('.', '')}{state.lower()}"
        
        # Add city to database with no vendor (pending integration)
        city_id = db.add_city(
            city_name=city_name,
            state=state,
            city_slug=city_slug,
            vendor="",  # No vendor yet - pending integration
            county=county,
            zipcodes=[zipcode]
        )
        
        print(f"Auto-created city: {city_name}, {state} (ID: {city_id})")
        
        # Return the created city info
        return db.get_city_by_zipcode(zipcode)
        
    except Exception as e:
        print(f"Error auto-creating city from zipcode {zipcode}: {e}")
        return None


async def auto_create_city_from_city_name(city_name: str, state: str) -> Optional[Dict[str, Any]]:
    """Auto-create city entry from city name using uszipcode"""
    try:
        print(f"Auto-creating city entry for {city_name}, {state}")
        
        # Search for city in uszipcode
        results = zipcode_search.by_city_and_state(city_name, state)
        if not results:
            print(f"No zipcode data found for {city_name}, {state}")
            return None
        
        # Get primary zipcode and county from first result
        primary_result = results[0]
        primary_zipcode = primary_result.zipcode
        county = primary_result.county
        
        # Collect all zipcodes for this city
        zipcodes = [r.zipcode for r in results[:10]]  # Limit to first 10 zipcodes
        
        # Create city slug
        city_slug = f"{city_name.lower().replace(' ', '').replace('.', '')}{state.lower()}"
        
        # Add city to database
        city_id = db.add_city(
            city_name=city_name,
            state=state,
            city_slug=city_slug,
            vendor=None,  # No vendor yet - pending integration
            county=county,
            zipcodes=zipcodes
        )
        
        print(f"Auto-created city: {city_name}, {state} with {len(zipcodes)} zipcodes (ID: {city_id})")
        
        # Return the created city info
        return db.get_city_by_name(city_name, state)
        
    except Exception as e:
        print(f"Error auto-creating city from name {city_name}, {state}: {e}")
        return None


@app.post("/api/process-agenda")
async def process_agenda(request: ProcessRequest):
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


@app.get("/api/stats")
async def get_stats():
    """Get system statistics"""
    try:
        stats = db.get_cache_stats()
        return {
            "status": "healthy",
            "cities": stats.get("cities_count", 0),
            "meetings": stats.get("meetings_count", 0),
            "processed": stats.get("processed_count", 0),
            "recent_activity": stats.get("recent_activity", 0)
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

        return {
            "status": "healthy",
            "database": "connected",
            "llm_processor": "available" if processor else "disabled",
            "cities": stats.get("cities_count", 0),
            "meetings": stats.get("meetings_count", 0)
        }
    except Exception as e:
        print(f"Health check failed: {e}")
        return {"status": "unhealthy", "error": str(e)}


if __name__ == "__main__":
    import uvicorn

    print("Starting engagic API server...")
    print(f"LLM processor: {'enabled' if processor else 'disabled'}")
    uvicorn.run(app, host="0.0.0.0", port=8000)
