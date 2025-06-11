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

        # First check database for cached meetings
        meetings = db.get_meetings_by_city(city, 50)
        if meetings:
            return meetings

        # If no cached meetings, find the vendor for this city and scrape
        # Get zipcode entry to find vendor info
        all_zipcode_entries = db.get_all_zipcode_entries()
        vendor = None
        city_name = None
        for entry in all_zipcode_entries:
            if entry["city_slug"] == city:
                vendor = entry.get("vendor")
                city_name = entry.get("city_name")
                break

        if not vendor:
            print(f"ERROR: No vendor configured for city {city}")
            if city_name:
                return {
                    "message": f"{city_name} has been registered and will be integrated soon",
                    "meetings": [],
                    "city_slug": city,
                    "status": "pending_integration"
                }
            else:
                print(f"ERROR: City {city} not found in database")
                raise HTTPException(
                    status_code=404, detail=f"City {city} not found"
                )

        # Scrape fresh meetings using the appropriate adapter
        if vendor == "primegov":
            try:
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
                return scraped_meetings
            except Exception as scrape_error:
                print(f"ERROR: Failed to scrape {city} with PrimeGov: {scrape_error}")
                return {
                    "message": f"{city_name} integration is experiencing issues and will be fixed soon",
                    "meetings": [],
                    "city_slug": city,
                    "status": "integration_error"
                }
        else:
            # For other vendors, implement adapters as needed
            print(f"ERROR: Vendor {vendor} not yet implemented for city {city}")
            return {
                "message": f"{city_name} has been registered and will be integrated soon",
                "meetings": [],
                "city_slug": city,
                "status": "vendor_not_implemented"
            }

    except HTTPException:
        raise
    except Exception as e:
        print(f"ERROR: Unexpected error fetching meetings for {city}: {str(e)}")
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
    """Unified search endpoint that handles both zipcode and city name input"""
    try:
        query = query.strip()

        # Determine if input is zipcode (5 digits) or city name
        is_zipcode = query.isdigit() and len(query) == 5

        if is_zipcode:
            return await handle_zipcode_search(query)
        else:
            return await handle_city_search(query)

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Search error: {str(e)}")


async def handle_zipcode_search(zipcode: str):
    """Handle zipcode-based search"""
    # Check if we have this zipcode in our database
    cached_entry = db.get_zipcode_entry(zipcode)
    if cached_entry:
        return cached_entry

    # Use uszipcode to resolve zipcode to city
    result = zipcode_search.by_zipcode(zipcode)
    print(f"Zipcode lookup result: {result}")

    if not result.zipcode:
        raise HTTPException(status_code=404, detail=f"Zipcode {zipcode} not found")

    # Create city slug from city name
    city_name = result.major_city or result.post_office_city
    if not city_name:
        raise HTTPException(
            status_code=404, detail=f"No city found for zipcode {zipcode}"
        )

    city_slug = city_name.lower().replace(" ", "").replace("-", "")

    # Try to fetch meetings and create entry
    return await create_city_entry(
        zipcode, city_name, city_slug, result.state, result.county
    )


async def handle_city_search(city_input: str):
    """Handle city name-based search"""
    # Convert city input to potential slug format
    city_slug = city_input.lower().replace(" ", "").replace("-", "")

    # Check if we already have this city in our database
    all_entries = db.get_all_zipcode_entries()
    for entry in all_entries:
        if (
            entry.get("city_slug") == city_slug
            or entry.get("city", "").lower() == city_input.lower()
        ):
            return entry

    # First time encountering this city - create placeholder entry
    print(f"NEW CITY ADDED: {city_input} (slug: {city_slug})")

    return await create_city_entry(None, city_input, city_slug, None, None, is_new=True)


async def create_city_entry(zipcode, city_name, city_slug, state, county, is_new=False):
    """Create a new city entry with optional meeting lookup"""
    meetings = []
    
    # Create entry data (no automatic vendor detection)
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
        "message": f"{city_name} has been registered and will be integrated soon",
        "status": "pending_integration"
    }

    # Store in database
    if zipcode:
        db.store_zipcode_entry(entry_data)
    
    # Log for backend visibility
    print(f"NEW CITY REGISTERED: {city_name} (slug: {city_slug}, zipcode: {zipcode})")

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
        },
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
