from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional
from adapters import PrimeGovAdapter
from fullstack import AgendaProcessor
from database import MeetingDatabase

app = FastAPI(
    title="engagic API", description="Civic meeting agenda processing with caching"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://engagic.org"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize global instances
processor = AgendaProcessor()
db = MeetingDatabase()


class MeetingRequest(BaseModel):
    packet_url: str
    city_slug: str
    meeting_name: Optional[str] = None
    meeting_date: Optional[str] = None
    meeting_id: Optional[str] = None


@app.get("/api/meetings")
async def get_meetings(city: str = "cityofpaloalto"):
    """Get upcoming meetings for a city"""
    try:
        adapter = PrimeGovAdapter(city)
        meetings = []
        for meeting in adapter.upcoming_packets():
            # Add city_slug to each meeting
            meeting["city_slug"] = city
            meetings.append(meeting)
        return meetings
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Error fetching meetings: {str(e)}"
        )


@app.post("/api/process-agenda")
async def process_agenda(request: MeetingRequest):
    """Process an agenda with caching - returns cached or newly processed summary"""
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
