from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional
from adapters import PrimeGovAdapter
from fullstack import AgendaProcessor
from database import MeetingDatabase
from uszipcode import SearchEngine

app = FastAPI(
    title="engagic API", description="Civic meeting agenda processing with caching"
)


app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://engagic.org",
        "http://localhost:3000",      # React/Next.js
        "http://localhost:5173",      # Vite
        "http://localhost:5000",      # Other common ports
        "http://127.0.0.1:3000"
    ],
    allow_methods=["*"],
    allow_headers=["*"],
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
async def get_meetings(city: str):
    """Get meetings for a city - from database first, scrape if missing"""
    try:
        # First check database for cached meetings
        meetings = db.get_meetings_by_city(city, 50)
        if meetings:
            return meetings
        
        # If no cached meetings, find the vendor for this city and scrape
        # Get zipcode entry to find vendor info
        all_zipcode_entries = db.get_all_zipcode_entries()
        vendor = "primegov"  # default
        for entry in all_zipcode_entries:
            if entry["city_slug"] == city:
                vendor = entry.get("vendor", "primegov")
                break
        
        # Scrape fresh meetings using the appropriate adapter
        if vendor == "primegov":
            adapter = PrimeGovAdapter(city)
            scraped_meetings = []
            for meeting in adapter.upcoming_packets():
                # Store the meeting in database
                db.store_meeting_data({
                    "city_slug": city,
                    "meeting_name": meeting.get("title"),
                    "packet_url": meeting.get("packet_url"),
                    "meeting_date": meeting.get("start")
                }, vendor)
                scraped_meetings.append(meeting)
            return scraped_meetings
        else:
            # For other vendors, implement adapters as needed
            raise HTTPException(status_code=501, detail=f"Vendor {vendor} not yet implemented")
            
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Error fetching meetings: {str(e)}"
        )


@app.post("/api/process-agenda")
async def process_agenda(request: MeetingRequest):
    """Process an agenda with caching - returns cached or newly processed summary"""
    if not processor:
        raise HTTPException(status_code=503, detail="LLM processing not available - ANTHROPIC_API_KEY required")
    
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


@app.get("/api/search")
async def search_meetings(q: str, city_slug: Optional[str] = None, limit: int = 50):
    """Search meetings by content or meeting name"""
    try:
        if not q.strip():
            raise HTTPException(status_code=400, detail="Search query required")

        meetings = db.search_meetings(q, city_slug, limit)
        return {
            "query": q,
            "city_slug": city_slug,
            "meetings": meetings,
            "count": len(meetings),
        }
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Error searching meetings: {str(e)}"
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


@app.get("/api/zipcode-lookup/{zipcode}")
async def lookup_zipcode(zipcode: str):
    """Convert zipcode to city information and fetch/store meetings"""
    try:
        # Validate zipcode format
        if not zipcode.isdigit() or len(zipcode) != 5:
            raise HTTPException(status_code=400, detail="Invalid zipcode format")
        
        # Check if we have this zipcode in our database
        cached_entry = db.get_zipcode_entry(zipcode)
        if cached_entry:
            return cached_entry
        
        # Use uszipcode to resolve zipcode to city
        result = zipcode_search.by_zipcode(zipcode)
        print(f"the result is: {result}")
        
        if not result.zipcode:
            raise HTTPException(status_code=404, detail=f"Zipcode {zipcode} not found")
        
        # Create city slug from city name (lowercase, replace spaces with empty)
        city_name = result.major_city or result.post_office_city
        if not city_name:
            raise HTTPException(status_code=404, detail=f"No city found for zipcode {zipcode}")
        
        # Convert city name to city slug format (lowercase, no spaces/hyphens)
        city_slug = city_name.lower().replace(' ', '').replace('-', '')
        
        # Try to fetch meetings for this city
        meetings = []
        try:
            adapter = PrimeGovAdapter(city_slug)
            for meeting in adapter.upcoming_packets():
                meetings.append({
                    "meeting_id": meeting.get("meeting_id"),
                    "title": meeting.get("title"),
                    "start": meeting.get("start"),
                    "packet_url": meeting.get("packet_url")
                })
        except Exception as e:
            print(f"Warning: Could not fetch meetings for {city_slug}: {e}")
            # Continue without meetings - we'll store the zipcode entry anyway
        
        # Create zipcode entry in database
        entry_data = {
            "zipcode": zipcode,
            "city": city_name,
            "city_slug": city_slug,
            "vendor": "primegov",  # Default vendor
            "state": result.state,
            "county": result.county,
            "meetings": meetings
        }
        
        # Store in database
        db.store_zipcode_entry(entry_data)
        
        return entry_data
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error looking up zipcode: {str(e)}")


@app.get("/")
async def root():
    """API status and info"""
    return {
        "service": "engagic API",
        "status": "running",
        "version": "1.0.0",
        "endpoints": {
            "meetings": "/api/meetings/{city}",
            "process": "/api/process-agenda",
            "city_meetings": "/api/meetings/{city_slug}",
            "recent": "/api/meetings/recent",
            "search": "/api/search",
            "cache_stats": "/api/cache/stats",
        },
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
