# Server - Public API Layer

**Purpose:** FastAPI application serving civic meeting data. Cache-only, clean modular architecture.

Provides:
- Meeting search (zipcode, city, state, topic)
- Meeting retrieval with agenda items
- Topic browsing and filtering
- Admin operations (force sync, status)
- Monitoring (health, stats, metrics)
- Flyer generation (civic action printables)

---

## Architecture Overview

**Modular FastAPI with clean separation of concerns:**

```
server/
├── main.py                 109 lines  - FastAPI app initialization
├── rate_limiter.py         309 lines  - SQLite-based rate limiting
├── metrics.py              222 lines  - Prometheus instrumentation
│
├── routes/                1271 lines  - HTTP request handlers
│   ├── search.py            (61 lines)
│   ├── admin.py             (81 lines)
│   ├── flyer.py             (82 lines)
│   ├── topics.py           (128 lines)
│   ├── meetings.py         (149 lines)
│   ├── monitoring.py       (340 lines)
│   └── matters.py          (430 lines)
│
├── services/                894 lines  - Business logic (+ 369 HTML)
│   ├── meeting.py           (41 lines)
│   ├── ticker.py           (177 lines)
│   ├── search.py           (315 lines)
│   ├── flyer.py            (361 lines)
│   └── flyer_template.html (369 lines)
│
├── middleware/               92 lines  - Cross-cutting concerns
│   ├── logging.py           (37 lines)
│   └── rate_limiting.py     (55 lines)
│
├── models/                  119 lines  - Request validation
│   └── requests.py         (119 lines)
│
└── utils/                   245 lines  - Reusable utilities
    ├── validation.py        (31 lines) - Input sanitization
    ├── constants.py         (96 lines) - State mappings
    └── geo.py              (118 lines) - City/state parsing
```

**Why this structure?**
- **109-line main.py** (down from 1,245) - Minimal entry point
- **Focused route modules** - Single responsibility per file (7 modules)
- **Service layer** - Business logic separate from HTTP concerns
- **Dependency injection** - Database and rate limiter via FastAPI deps
- **Clean imports** - No circular dependencies

---

## Quick Start

### Running the API

```bash
# Development
python server/main.py

# Production
uvicorn server.main:app --host 0.0.0.0 --port 8000

# With auto-reload
uvicorn server.main:app --reload
```

### Basic Usage

```python
import requests

# Search by zipcode
response = requests.post("http://localhost:8000/api/search", json={"query": "94301"})

# Search by city
response = requests.post("http://localhost:8000/api/search", json={"query": "Palo Alto, CA"})

# Get meeting by ID
response = requests.get("http://localhost:8000/api/meeting/paloaltoCA_2025-11-10")

# Search by topic
response = requests.post("http://localhost:8000/api/search/by-topic", json={
    "topic": "housing",
    "banana": "paloaltoCA",
    "limit": 20
})
```

---

## Module Reference

### 1. `main.py` - Application Entry Point (109 lines)

**Minimal FastAPI app initialization.** Just wiring, no business logic.

#### Structure

```python
# FastAPI app
app = FastAPI(title="engagic API", description="EGMI")

# CORS middleware
app.add_middleware(CORSMiddleware, allow_origins=config.ALLOWED_ORIGINS, ...)

# Global instances (shared across requests)
rate_limiter = SQLiteRateLimiter(db_path="rate_limits.db", ...)
db = UnifiedDatabase(config.UNIFIED_DB_PATH)
app.state.db = db  # Dependency injection

# Middleware registration
@app.middleware("http")
async def rate_limit_middleware_wrapper(request, call_next):
    from server.middleware.rate_limiting import rate_limit_middleware
    return await rate_limit_middleware(request, call_next, rate_limiter)

@app.middleware("http")
async def log_requests_middleware(request, call_next):
    return await log_requests(request, call_next)

# Route mounting
app.include_router(monitoring.router)  # Root and monitoring endpoints
app.include_router(search.router)      # Search endpoints
app.include_router(meetings.router)    # Meeting endpoints
app.include_router(topics.router)      # Topic endpoints
app.include_router(admin.router)       # Admin endpoints
app.include_router(flyer.router)       # Flyer generation endpoints

# CLI entry point
if __name__ == "__main__":
    uvicorn.run(app, host=config.API_HOST, port=config.API_PORT)
```

#### Dependency Injection Pattern

**Database:**
```python
# In routes (e.g., search.py):
def get_db(request: Request) -> UnifiedDatabase:
    """Dependency to get shared database instance from app state"""
    return request.app.state.db

@router.post("/search")
async def search_meetings(request: SearchRequest, db: UnifiedDatabase = Depends(get_db)):
    # Use db instance (shared across all requests)
    city = db.get_city(zipcode=request.query)
```

**Why shared database?** Single connection pool, better performance, simpler lifecycle.

---

### 2. `rate_limiter.py` - Persistent Rate Limiting (309 lines)

**SQLite-based rate limiter that survives restarts.**

#### SQLiteRateLimiter

```python
rate_limiter = SQLiteRateLimiter(
    db_path="rate_limits.db",
    requests_limit=30,       # 30 requests
    window_seconds=60        # per 60 seconds
)

# Check rate limit
is_allowed, remaining = rate_limiter.check_rate_limit(client_ip)

# Get client status
status = rate_limiter.get_client_status(client_ip)
# {
#     "requests_made": 15,
#     "requests_limit": 30,
#     "remaining": 15,
#     "window_seconds": 60,
#     "reset_time": 1699564800.0
# }

# Reset specific client (admin)
rate_limiter.reset_client(client_ip)
```

**Features:**
- **Persistent:** Survives API restarts
- **Multi-instance:** Works across multiple API servers (shared SQLite)
- **Automatic cleanup:** Old entries removed every 5 minutes
- **WAL mode:** Better concurrency

**Schema:**
```sql
CREATE TABLE rate_limits (
    client_ip TEXT NOT NULL,
    timestamp REAL NOT NULL,
    PRIMARY KEY (client_ip, timestamp)
);
```

#### RateLimitHandler (for LLM API calls)

```python
handler = RateLimitHandler(
    initial_delay=1.0,
    max_delay=60.0,
    max_retries=5,
    backoff_factor=2.0
)

@with_rate_limit_retry(handler)
def call_gemini_api():
    # Automatically retries with exponential backoff
    return gemini.generate(...)
```

**Use case:** Vendor API rate limits (Legistar, PrimeGov, Gemini)

---

### 3. `metrics.py` - Prometheus Instrumentation (222 lines)

**Centralized metrics for observability.**

#### Metrics Available

```python
from server.metrics import metrics

# Sync metrics
metrics.meetings_synced.labels(city="paloaltoCA", vendor="primegov").inc()
metrics.items_extracted.labels(city="paloaltoCA", vendor="primegov").inc(5)
metrics.matters_tracked.labels(city="sanfranciscoCA").inc()

# Processing metrics
with metrics.processing_duration.labels(job_type="meeting").time():
    process_meeting(meeting_id)

with metrics.pdf_extraction_duration.labels(document_type="agenda").time():
    extract_pdf(url)

# LLM metrics (convenience method)
metrics.record_llm_call(
    model="gemini-2.5-flash",
    prompt_type="item",
    duration_seconds=3.5,
    input_tokens=1000,
    output_tokens=200,
    cost_dollars=0.0025,
    success=True
)

# Queue metrics
queue_stats = db.get_queue_stats()
metrics.update_queue_sizes(queue_stats)

# Error tracking
try:
    process_meeting(meeting_id)
except Exception as e:
    metrics.record_error(component="processor", error=e)
```

#### Prometheus Endpoint

```python
# GET /metrics
# Returns Prometheus text format

# HELP engagic_meetings_synced_total Total meetings synced from vendors
# TYPE engagic_meetings_synced_total counter
engagic_meetings_synced_total{city="paloaltoCA",vendor="primegov"} 125

# HELP engagic_queue_size Current queue size by status
# TYPE engagic_queue_size gauge
engagic_queue_size{status="pending"} 10
engagic_queue_size{status="processing"} 2
engagic_queue_size{status="completed"} 500

# HELP engagic_llm_api_cost_dollars Total LLM API cost in dollars
# TYPE engagic_llm_api_cost_dollars counter
engagic_llm_api_cost_dollars{model="gemini-2.5-flash"} 15.75
```

**Usage:** Connect Prometheus server, visualize with Grafana.

---

## Route Modules (1271 lines total)

**Each route module focuses on one domain.** No business logic - delegate to services.

### 1. `routes/search.py` (61 lines)

**Single unified search endpoint** - handles zipcode, city, or state.

```python
@router.post("/api/search")
async def search_meetings(request: SearchRequest, db: UnifiedDatabase = Depends(get_db)):
    """Universal search - detects input type and routes appropriately"""
    query = request.query.strip()

    # Determine input type
    is_zipcode = query.isdigit() and len(query) == 5
    is_state = is_state_query(query)

    if is_zipcode:
        return handle_zipcode_search(query, db)
    elif is_state:
        return handle_state_search(query, db)
    else:
        return handle_city_search(query, db)
```

**Examples:**
```python
# Zipcode
POST /api/search {"query": "94301"}
# Returns: meetings for Palo Alto, CA

# City + State
POST /api/search {"query": "Palo Alto, CA"}
# Returns: meetings for Palo Alto

# Ambiguous city
POST /api/search {"query": "Springfield"}
# Returns: list of cities named Springfield (MA, IL, MO, etc.)

# State
POST /api/search {"query": "California"}
# Returns: list of cities in California
```

---

### 2. `routes/meetings.py` (149 lines)

**Meeting retrieval and processing.**

```python
@router.get("/api/meeting/{meeting_id}")
async def get_meeting(meeting_id: str, db: UnifiedDatabase = Depends(get_db)):
    """Get single meeting by ID"""
    meeting = db.get_meeting(meeting_id)
    meeting_dict = get_meeting_with_items(meeting, db)

    return {
        "success": True,
        "meeting": meeting_dict,
        "city_name": city.name,
        "state": city.state
    }

@router.post("/api/process-agenda")
async def process_agenda(request: ProcessRequest, db: UnifiedDatabase = Depends(get_db)):
    """Get cached summary (no on-demand processing)"""
    cached_summary = db.get_cached_summary(request.packet_url)

    if cached_summary:
        return {
            "success": True,
            "summary": cached_summary.summary,
            "cached": True
        }

    return {
        "success": False,
        "message": "Summary not yet available - processing in background"
    }

@router.get("/api/random-meeting-with-items")
async def get_random_meeting_with_items(db: UnifiedDatabase = Depends(get_db)):
    """Get random meeting with item summaries (for demos)"""
    result = db.get_random_meeting_with_items()
    return {"success": True, "meeting": result}
```

---

### 3. `routes/topics.py` (128 lines)

**Topic-based search and browsing.**

```python
@router.get("/api/topics")
async def get_all_topics():
    """Get all canonical topics (16 topics from taxonomy.json)"""
    from analysis.topics.normalizer import get_normalizer

    normalizer = get_normalizer()
    all_topics = normalizer.get_all_canonical_topics()

    return {
        "success": True,
        "topics": [
            {"canonical": t, "display_name": normalizer.get_display_name(t)}
            for t in all_topics
        ]
    }

@router.post("/api/search/by-topic")
async def search_by_topic(request: TopicSearchRequest, db: UnifiedDatabase = Depends(get_db)):
    """Search meetings by topic"""
    from analysis.topics.normalizer import get_normalizer

    normalizer = get_normalizer()
    normalized_topic = normalizer.normalize_single(request.topic)

    # Search meetings
    meetings = db.search_meetings_by_topic(
        topic=normalized_topic,
        city_banana=request.banana,
        limit=request.limit
    )

    # For each meeting, get matching items
    results = []
    for meeting in meetings:
        matching_items = db.get_items_by_topic(meeting.id, normalized_topic)
        results.append({
            "meeting": meeting.to_dict(),
            "matching_items": [item.to_dict() for item in matching_items]
        })

    return {"success": True, "results": results}

@router.get("/api/topics/popular")
async def get_popular_topics(db: UnifiedDatabase = Depends(get_db)):
    """Get most common topics (for UI suggestions)"""
    topic_counts = db.get_popular_topics(limit=20)

    return {
        "success": True,
        "topics": [
            {
                "topic": item["topic"],
                "display_name": normalizer.get_display_name(item["topic"]),
                "count": item["count"]
            }
            for item in topic_counts
        ]
    }
```

---

### 4. `routes/admin.py` (81 lines)

**Admin endpoints with bearer token authentication.**

```python
async def verify_admin_token(authorization: str = Header(None)):
    """Verify admin bearer token"""
    if not authorization:
        raise HTTPException(status_code=401, detail="Authorization header required")

    scheme, token = authorization.split(" ")
    if scheme.lower() != "bearer" or token != config.ADMIN_TOKEN:
        raise HTTPException(status_code=403, detail="Invalid admin token")

    return True

@router.post("/api/admin/sync-city/{banana}")
async def force_sync_city(banana: str, is_admin: bool = Depends(verify_admin_token)):
    """Force sync a specific city (admin endpoint)"""
    # Background processing runs as separate daemon
    return {
        "success": False,
        "message": "Use daemon directly:",
        "command": f"python daemon.py --sync-city {banana}"
    }
```

**Usage:**
```bash
curl -X POST http://localhost:8000/api/admin/sync-city/paloaltoCA \
  -H "Authorization: Bearer YOUR_ADMIN_TOKEN"
```

---

### 5. `routes/monitoring.py` (340 lines)

**Health checks, stats, metrics, and analytics.**

```python
@router.get("/")
async def root():
    """API status and documentation"""
    return {
        "service": "engagic API",
        "status": "running",
        "version": "2.0.0",
        "endpoints": {...},
        "usage_examples": {...}
    }

@router.get("/api/health")
async def health_check(db: UnifiedDatabase = Depends(get_db)):
    """Health check with detailed status"""
    return {
        "status": "healthy",
        "checks": {
            "databases": {"status": "healthy", "cities": 500},
            "llm_analyzer": {"status": "available"},
            "configuration": {"status": "healthy"}
        }
    }

@router.get("/api/stats")
async def get_stats(db: UnifiedDatabase = Depends(get_db)):
    """System statistics"""
    stats = db.get_stats()
    return {
        "active_cities": stats["active_cities"],
        "total_meetings": stats["total_meetings"],
        "summarized_meetings": stats["summarized_meetings"],
        "summary_rate": stats["summary_rate"]
    }

@router.get("/api/queue-stats")
async def get_queue_stats(db: UnifiedDatabase = Depends(get_db)):
    """Processing queue statistics"""
    queue_stats = db.get_queue_stats()
    return {
        "queue": {
            "pending": queue_stats["pending_count"],
            "processing": queue_stats["processing_count"],
            "completed": queue_stats["completed_count"],
            "failed": queue_stats["failed_count"],
            "dead_letter": queue_stats["dead_letter_count"]
        }
    }

@router.get("/metrics")
async def prometheus_metrics(db: UnifiedDatabase = Depends(get_db)):
    """Prometheus metrics endpoint"""
    queue_stats = db.get_queue_stats()
    metrics.update_queue_sizes(queue_stats)
    return Response(content=get_metrics_text(), media_type="text/plain")

@router.get("/api/ticker")
async def get_ticker_items(db: UnifiedDatabase = Depends(get_db)):
    """Get ticker items for homepage news ticker"""
    ticker_items = []
    for i in range(15):
        meeting = db.get_random_meeting_with_items()
        if meeting:
            ticker_items.append(generate_ticker_item(meeting, db))
    return {"success": True, "items": ticker_items}
```

---

### 6. `routes/flyer.py` (82 lines)

**Civic action flyer generation.**

```python
@router.post("/api/flyer/generate")
async def generate_flyer(request: FlyerRequest, db: UnifiedDatabase = Depends(get_db)):
    """Generate printable civic action flyer

    Returns HTML ready for browser print-to-PDF.
    """
    meeting = db.get_meeting(request.meeting_id)
    item = db.get_agenda_item(request.item_id) if request.item_id else None

    html = generate_meeting_flyer(
        meeting=meeting,
        item=item,
        position=request.position,  # "support" | "oppose" | "more_info"
        custom_message=request.custom_message,
        user_name=request.user_name,
        db=db,
        dark_mode=request.dark_mode
    )

    return HTMLResponse(content=html)
```

**Request:**
```python
POST /api/flyer/generate
{
    "meeting_id": "paloaltoCA_2025-11-10",
    "item_id": "item_5",  # Optional
    "position": "support",
    "custom_message": "I support this housing project because...",
    "user_name": "Jane Doe",
    "dark_mode": false
}
```

**Response:** HTML document ready for `window.print()` or print-to-PDF.

---

### 7. `routes/matters.py` (430 lines)

**Matter tracking and timeline endpoints.**

```python
@router.get("/api/matters/{matter_id}")
async def get_matter(matter_id: str, db: UnifiedDatabase = Depends(get_db)):
    """Get matter details with timeline across all appearances

    Returns:
        - Canonical summary (from city_matters table)
        - Timeline of all appearances across meetings
        - Attachment history (if attachments changed)
        - Vote history (if tracking votes)
    """
    matter = db.get_matter(matter_id)
    if not matter:
        raise HTTPException(status_code=404, detail="Matter not found")

    # Get all appearances
    appearances = db.get_matter_appearances(matter_id)

    # Build timeline
    timeline = []
    for appearance in appearances:
        meeting = db.get_meeting(appearance.meeting_id)
        item = db.get_agenda_item(appearance.item_id)

        timeline.append({
            "meeting_id": meeting.id,
            "meeting_date": meeting.date,
            "meeting_title": meeting.title,
            "item_title": item.title,
            "item_sequence": item.sequence,
            "action_taken": appearance.action_taken,
            "vote_result": appearance.vote_result
        })

    return {
        "success": True,
        "matter": {
            "id": matter.id,
            "matter_file": matter.matter_file,
            "title": matter.title,
            "canonical_summary": matter.canonical_summary,
            "topics": matter.canonical_topics,
            "sponsors": matter.sponsors,
            "first_seen": matter.first_seen,
            "last_seen": matter.last_seen,
            "appearance_count": len(timeline)
        },
        "timeline": sorted(timeline, key=lambda x: x["meeting_date"], reverse=True)
    }

@router.get("/api/city/{banana}/matters")
async def get_city_matters(
    banana: str,
    limit: int = 50,
    db: UnifiedDatabase = Depends(get_db)
):
    """Get all tracked matters for a city

    Returns matters sorted by recency (last_seen DESC)
    """
    matters = db.get_city_matters(banana, limit=limit)

    return {
        "success": True,
        "matters": [
            {
                "id": m.id,
                "matter_file": m.matter_file,
                "title": m.title,
                "canonical_summary": m.canonical_summary,
                "topics": m.canonical_topics,
                "appearance_count": m.appearance_count,
                "first_seen": m.first_seen,
                "last_seen": m.last_seen
            }
            for m in matters
        ]
    }
```

**Use case:** Track legislation across multiple meetings (bills, ordinances, projects).

**Matters-first architecture:** One summary for a matter, reused across all appearances.

---

## Service Layer (894 lines + 369 HTML)

**Business logic separated from HTTP concerns.**

### 1. `services/search.py` (315 lines)

**Core search logic** for zipcode, city, and state searches.

```python
def handle_zipcode_search(zipcode: str, db: UnifiedDatabase) -> Dict[str, Any]:
    """Handle zipcode search with cache-first approach"""
    city = db.get_city(zipcode=zipcode)
    if not city:
        return {"success": False, "message": "We're not covering that area yet"}

    meetings = db.get_meetings(bananas=[city.banana], limit=50)
    meetings_with_items = get_meetings_with_items(meetings, db)

    return {
        "success": True,
        "city_name": city.name,
        "state": city.state,
        "banana": city.banana,
        "meetings": meetings_with_items
    }

def handle_city_search(city_input: str, db: UnifiedDatabase) -> Dict[str, Any]:
    """Handle city name search with ambiguous city handling"""
    city_name, state = parse_city_state_input(city_input)

    if not state:
        # Ambiguous - check for multiple matches
        return handle_ambiguous_city_search(city_name, city_input, db)

    city = db.get_city(name=city_name, state=state)
    meetings = db.get_meetings(bananas=[city.banana], limit=50)

    return {
        "success": True,
        "city_name": city.name,
        "meetings": meetings_with_items
    }

def handle_ambiguous_city_search(city_name: str, original_input: str, db: UnifiedDatabase) -> Dict[str, Any]:
    """Handle city search when no state is provided"""
    cities = db.get_cities(name=city_name)

    if not cities:
        # Try fuzzy matching for typos
        all_cities = db.get_cities()
        city_names = [city.name.lower() for city in all_cities]
        close_matches = get_close_matches(city_name.lower(), city_names, n=5, cutoff=0.7)
        # ... (build fuzzy results)

    if len(cities) == 1:
        # Only one match - proceed
        return handle_city_search(f"{cities[0].name}, {cities[0].state}", db)

    # Multiple matches - return city options
    city_options = [
        {
            "city_name": city.name,
            "state": city.state,
            "banana": city.banana,
            "display_name": f"{city.name}, {city.state}"
        }
        for city in cities
    ]

    return {
        "success": False,
        "ambiguous": True,
        "city_options": city_options
    }

def handle_state_search(state_input: str, db: UnifiedDatabase) -> Dict[str, Any]:
    """Handle state search - return list of cities"""
    state_abbr = get_state_abbreviation(state_input)
    cities = db.get_cities(state=state_abbr)

    city_options = [
        {
            "city_name": city.name,
            "state": city.state,
            "banana": city.banana,
            "display_name": f"{city.name}, {city.state}"
        }
        for city in cities
    ]

    return {
        "success": False,
        "ambiguous": True,  # User needs to select city
        "city_options": city_options
    }
```

**Key patterns:**
- **Cache-first:** Only return cached data, never fetch live
- **Fuzzy matching:** Handle typos with `difflib.get_close_matches()`
- **Ambiguous handling:** Return city options when multiple matches
- **State search:** List all cities in state

---

### 2. `services/meeting.py` (41 lines)

**Meeting retrieval with items attached.**

```python
def get_meeting_with_items(meeting: Meeting, db: UnifiedDatabase) -> Dict[str, Any]:
    """Convert meeting to dict with items attached

    Only sets has_items=True if items have summaries.
    """
    meeting_dict = meeting.to_dict()
    items = db.get_agenda_items(meeting.id)

    if items:
        items_with_summaries = [item for item in items if item.summary]
        if items_with_summaries:
            meeting_dict["items"] = [item.to_dict() for item in items]
            meeting_dict["has_items"] = True
        else:
            meeting_dict["has_items"] = False
    else:
        meeting_dict["has_items"] = False

    return meeting_dict

def get_meetings_with_items(meetings: List[Meeting], db: UnifiedDatabase) -> List[Dict[str, Any]]:
    """Batch version"""
    return [get_meeting_with_items(m, db) for m in meetings]
```

**Why separate function?** Used in 5+ places across API (search, meeting detail, random, etc.)

---

### 3. `services/flyer.py` (361 lines)

**Generate printable civic action flyers.**

```python
def generate_meeting_flyer(
    meeting: Meeting,
    item: Optional[AgendaItem],
    position: str,
    custom_message: Optional[str],
    user_name: Optional[str],
    db: UnifiedDatabase,
    dark_mode: bool = False
) -> str:
    """Generate HTML flyer for a meeting or specific agenda item

    Args:
        meeting: Meeting object
        item: Optional specific agenda item
        position: "support" | "oppose" | "more_info"
        custom_message: User's custom message
        user_name: User's name (for signature)
        db: Database instance (for city info)
        dark_mode: Use dark theme

    Returns:
        HTML document ready for printing
    """
    # Get city information
    city = db.get_city(banana=meeting.banana)

    # Build flyer context
    context = {
        "city_name": city.name,
        "meeting_title": meeting.title,
        "meeting_date": meeting.date.strftime("%B %d, %Y") if meeting.date else "TBD",
        "meeting_time": meeting.date.strftime("%I:%M %p") if meeting.date else "TBD",
        "position": position,
        "position_display": {
            "support": "IN SUPPORT",
            "oppose": "IN OPPOSITION",
            "more_info": "REQUESTING MORE INFORMATION"
        }[position],
        "custom_message": custom_message,
        "user_name": user_name or "A Concerned Resident",
        "participation": meeting.participation or {},
        "dark_mode": dark_mode
    }

    # Add item-specific context
    if item:
        context["item_title"] = item.title
        context["item_summary"] = item.summary
        context["item_sequence"] = item.sequence

    # Render template
    template = load_flyer_template()
    return template.render(**context)
```

**Template:** `services/flyer_template.html` (369 lines) - Jinja2 template with print-optimized CSS.

**Features:**
- Print-optimized layout (single page, no page breaks)
- QR code for meeting details
- Participation info (email, phone, Zoom)
- Position-specific styling (green=support, red=oppose, blue=more_info)
- Dark mode support
- Professional typography

---

### 4. `services/ticker.py` (177 lines)

**Generate homepage ticker items.**

```python
def generate_ticker_item(meeting_dict: Dict[str, Any], db: UnifiedDatabase) -> Dict[str, Any]:
    """Generate a ticker item from a meeting

    Args:
        meeting_dict: Meeting dict with items
        db: Database instance

    Returns:
        Ticker item dict with headline and link
    """
    city = db.get_city(banana=meeting_dict["banana"])

    # Extract most interesting item
    items = meeting_dict.get("items", [])
    if items:
        # Prioritize items with high-interest topics
        high_interest_topics = ["housing", "zoning", "development", "transportation", "environment"]
        interesting_items = [
            item for item in items
            if any(topic in (item.get("topics") or []) for topic in high_interest_topics)
        ]

        if interesting_items:
            item = interesting_items[0]
            headline = f"{city.name}: {item['title'][:100]}"
        else:
            item = items[0]
            headline = f"{city.name}: {item['title'][:100]}"
    else:
        headline = f"{city.name}: {meeting_dict['title'][:100]}"

    return {
        "headline": headline,
        "meeting_id": meeting_dict["id"],
        "city_name": city.name,
        "state": city.state,
        "meeting_date": meeting_dict.get("date"),
        "topics": meeting_dict.get("topics", [])
    }
```

**Use case:** Homepage "news ticker" showing recent civic activity across all cities.

---

## Middleware (92 lines)

**Cross-cutting concerns applied to all requests.**

### 1. `middleware/logging.py` (37 lines)

**Request/response logging with unique IDs.**

```python
async def log_requests(request: Request, call_next):
    """Log incoming requests and responses"""
    request_id = str(uuid.uuid4())[:8]
    start_time = time.time()

    logger.info(
        f"[{request_id}] {request.method} {request.url.path} - Client: {request.client.host}"
    )

    response = await call_next(request)
    duration = time.time() - start_time

    logger.info(
        f"[{request_id}] Response: {response.status_code} - Duration: {duration:.3f}s"
    )

    return response
```

**Output:**
```
[a3f9c2d1] POST /api/search - Client: 192.168.1.100
[a3f9c2d1] Response: 200 - Duration: 0.125s
```

---

### 2. `middleware/rate_limiting.py` (55 lines)

**Rate limit enforcement.**

```python
async def rate_limit_middleware(request: Request, call_next, rate_limiter: SQLiteRateLimiter):
    """Check rate limits for API endpoints"""
    client_ip = request.client.host

    # Skip OPTIONS requests (CORS preflight)
    if request.method == "OPTIONS":
        return await call_next(request)

    # Check rate limit for /api/* endpoints
    if request.url.path.startswith("/api/"):
        is_allowed, remaining = rate_limiter.check_rate_limit(client_ip)

        if not is_allowed:
            logger.warning(f"Rate limit exceeded for {client_ip}")
            return JSONResponse(
                status_code=429,
                content={"detail": "Rate limit exceeded. Please try again later."}
            )

    response = await call_next(request)
    return response
```

---

## Models (119 lines)

**Pydantic models for request validation.**

### `models/requests.py` (119 lines)

```python
class SearchRequest(BaseModel):
    query: str

    @validator("query")
    def validate_query(cls, v):
        sanitized = sanitize_string(v)
        if len(sanitized) < 2:
            raise ValueError("Search query too short")
        if len(sanitized) > config.MAX_QUERY_LENGTH:
            raise ValueError("Search query too long")
        if not re.match(r"^[a-zA-Z0-9\s,.-]+$", sanitized):
            raise ValueError("Search query contains invalid characters")
        return sanitized


class ProcessRequest(BaseModel):
    packet_url: str
    banana: str
    meeting_name: Optional[str] = None

    @validator("packet_url")
    def validate_packet_url(cls, v):
        if not re.match(r"^https?://", v):
            raise ValueError("Packet URL must be a valid HTTP/HTTPS URL")
        return v.strip()


class TopicSearchRequest(BaseModel):
    topic: str
    banana: Optional[str] = None
    limit: int = 50

    @validator("topic")
    def validate_topic(cls, v):
        return sanitize_string(v)


class FlyerRequest(BaseModel):
    meeting_id: str
    item_id: Optional[str] = None
    position: str  # "support" | "oppose" | "more_info"
    custom_message: Optional[str] = None
    user_name: Optional[str] = None
    dark_mode: bool = False

    @validator("position")
    def validate_position(cls, v):
        allowed = ["support", "oppose", "more_info"]
        if v not in allowed:
            raise ValueError(f"Position must be one of: {', '.join(allowed)}")
        return v
```

**Why Pydantic?** Automatic validation, OpenAPI docs generation, type safety.

---

## Utils (245 lines)

**Reusable utilities across the server.**

### 1. `utils/constants.py` (96 lines)

**State mappings and special city names.**

```python
STATE_MAP = {
    "california": "CA",
    "new york": "NY",
    "texas": "TX",
    # ... 50 states
}

STATE_ABBREV_TO_FULL = {
    "CA": "California",
    "NY": "New York",
    # ... reverse mapping
}

SPECIAL_CITIES = {
    "lasvegas": "Las Vegas",
    "newyork": "New York",
    "sanfrancisco": "San Francisco",
    "paloalto": "Palo Alto",
    # ... cities with non-standard capitalization
}
```

---

### 2. `utils/geo.py` (118 lines)

**City and state parsing.**

```python
def parse_city_state_input(input_str: str) -> tuple[str, str]:
    """Parse city, state from user input

    Handles:
    - "Palo Alto, CA"
    - "Palo Alto, California"
    - "Boston Massachusetts"
    - "lasvegas nevada" (normalizes to "Las Vegas, NV")
    """
    # Comma-separated format
    if "," in input_str:
        city, state = input_str.split(",")
        return normalize_city_name(city), get_state_abbreviation(state)

    # Space-separated format
    words = input_str.split()
    if len(words) >= 2:
        # Try last word as state abbreviation
        if words[-1].upper() in STATE_MAP.values():
            city = " ".join(words[:-1])
            return normalize_city_name(city), words[-1].upper()

    return input_str, ""

def normalize_city_name(city_name: str) -> str:
    """Normalize city name using SPECIAL_CITIES mapping"""
    city_lower_nospace = city_name.lower().replace(" ", "")
    if city_lower_nospace in SPECIAL_CITIES:
        return SPECIAL_CITIES[city_lower_nospace]
    return city_name.title()

def is_state_query(query: str) -> bool:
    """Check if query is just a state name/abbreviation"""
    query_lower = query.strip().lower()
    return query_lower in STATE_MAP or query.upper() in STATE_MAP.values()

def get_state_abbreviation(state_input: str) -> str:
    """Convert state input to abbreviation"""
    state_lower = state_input.strip().lower()
    if state_lower in STATE_MAP:
        return STATE_MAP[state_lower]
    return state_input.upper() if len(state_input) == 2 else ""
```

---

### 3. `utils/validation.py` (31 lines)

**Input sanitization and SQL injection prevention.**

```python
def sanitize_string(value: str) -> str:
    """Sanitize string input to prevent injection attacks"""
    if not value:
        return ""

    # SQL injection prevention
    sql_patterns = [
        r"';\s*DROP",
        r"';\s*DELETE",
        r"--",
        r"/\*.*\*/",
        r"UNION\s+SELECT",
        r"OR\s+1\s*=\s*1"
    ]

    for pattern in sql_patterns:
        if re.search(pattern, value, re.IGNORECASE):
            raise ValueError("Invalid characters in input")

    # Remove dangerous characters
    sanitized = re.sub(r'[<>"\';()&+]', "", value.strip())
    return sanitized[:config.MAX_QUERY_LENGTH]
```

**Used by:** All Pydantic validators to prevent SQL injection.

---

## API Endpoints Reference

### Search

```
POST   /api/search                   Search by zipcode/city/state
POST   /api/search/by-topic          Search meetings by topic
```

### Meetings

```
GET    /api/meeting/{meeting_id}     Get single meeting with items
POST   /api/process-agenda            Get cached meeting summary
GET    /api/random-best-meeting       Get random high-quality meeting
GET    /api/random-meeting-with-items Get random meeting with items
```

### Topics

```
GET    /api/topics                    Get all canonical topics (16 topics)
GET    /api/topics/popular            Get most common topics
```

### Matters

```
GET    /api/matters/{matter_id}       Get matter with timeline of appearances
GET    /api/city/{banana}/matters     Get all tracked matters for a city
```

### Admin (requires Bearer token)

```
GET    /api/admin/city-requests       View requested cities
POST   /api/admin/sync-city/{banana}  Force sync city
POST   /api/admin/process-meeting     Force process meeting
```

### Monitoring

```
GET    /                              API status and documentation
GET    /api/health                    Health check with detailed status
GET    /api/stats                     System statistics
GET    /api/queue-stats               Processing queue statistics
GET    /api/metrics                   Basic metrics (JSON)
GET    /metrics                       Prometheus metrics (text format)
GET    /api/analytics                 Public dashboard analytics
GET    /api/ticker                    Homepage ticker items
```

### Flyer

```
POST   /api/flyer/generate            Generate printable flyer (HTML)
```

---

## Configuration

**Required:**
```bash
ENGAGIC_API_HOST=0.0.0.0
ENGAGIC_API_PORT=8000
ENGAGIC_DB_DIR=/root/engagic/data
ENGAGIC_UNIFIED_DB=/root/engagic/data/engagic.db
```

**Rate Limiting:**
```bash
ENGAGIC_RATE_LIMIT_REQUESTS=30     # Requests per window
ENGAGIC_RATE_LIMIT_WINDOW=60       # Window in seconds
```

**CORS:**
```bash
ENGAGIC_ALLOWED_ORIGINS=http://localhost:5173,https://engagic.com
```

**Admin:**
```bash
ENGAGIC_ADMIN_TOKEN=your_secret_token_here
```

**Logging:**
```bash
ENGAGIC_LOG_LEVEL=INFO
ENGAGIC_LOG_PATH=/root/engagic/logs/engagic.log
```

---

## Deployment

### Local Development

```bash
# Start API server
python server/main.py

# Or with auto-reload
uvicorn server.main:app --reload --port 8000

# Check health
curl http://localhost:8000/api/health
```

### Production (VPS)

**systemd service** (`engagic-api.service`):
```ini
[Unit]
Description=Engagic API Server
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=/root/engagic
ExecStart=/usr/bin/python3 -m uvicorn server.main:app --host 0.0.0.0 --port 8000
Restart=on-failure
Environment="ENGAGIC_DB_DIR=/root/engagic/data"

[Install]
WantedBy=multi-user.target
```

**Start service:**
```bash
systemctl start engagic-api
systemctl enable engagic-api
systemctl status engagic-api
```

**Nginx reverse proxy:**
```nginx
server {
    listen 80;
    server_name api.engagic.com;

    location / {
        proxy_pass http://localhost:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```

---

## Common Patterns

### Adding a New Endpoint

**1. Create request model** (`models/requests.py`):
```python
class MyRequest(BaseModel):
    field: str

    @validator("field")
    def validate_field(cls, v):
        return sanitize_string(v)
```

**2. Create service function** (`services/my_service.py`):
```python
def handle_my_request(field: str, db: UnifiedDatabase) -> Dict[str, Any]:
    # Business logic here
    result = db.some_operation(field)
    return {"success": True, "result": result}
```

**3. Create route** (`routes/my_routes.py`):
```python
router = APIRouter(prefix="/api")

def get_db(request: Request) -> UnifiedDatabase:
    return request.app.state.db

@router.post("/my-endpoint")
async def my_endpoint(request: MyRequest, db: UnifiedDatabase = Depends(get_db)):
    return handle_my_request(request.field, db)
```

**4. Mount router** (`main.py`):
```python
from server.routes import my_routes
app.include_router(my_routes.router)
```

---

### Error Handling Pattern

```python
@router.get("/api/something")
async def get_something(db: UnifiedDatabase = Depends(get_db)):
    try:
        result = db.get_something()

        if not result:
            raise HTTPException(status_code=404, detail="Not found")

        return {"success": True, "result": result}

    except HTTPException:
        raise  # Re-raise HTTP exceptions
    except Exception as e:
        logger.error(f"Error in get_something: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail="We humbly thank you for your patience"
        )
```

**Why "We humbly thank you for your patience"?** User-friendly error message (no technical details exposed).

---

## Testing

### Manual Testing

```bash
# Health check
curl http://localhost:8000/api/health

# Search by zipcode
curl -X POST http://localhost:8000/api/search \
  -H "Content-Type: application/json" \
  -d '{"query": "94301"}'

# Get meeting
curl http://localhost:8000/api/meeting/paloaltoCA_2025-11-10

# Search by topic
curl -X POST http://localhost:8000/api/search/by-topic \
  -H "Content-Type: application/json" \
  -d '{"topic": "housing", "banana": "paloaltoCA"}'

# Admin endpoint (requires token)
curl -X POST http://localhost:8000/api/admin/sync-city/paloaltoCA \
  -H "Authorization: Bearer YOUR_ADMIN_TOKEN"
```

### Load Testing

```bash
# Using wrk
wrk -t4 -c100 -d30s http://localhost:8000/api/health

# Using hey
hey -n 10000 -c 100 http://localhost:8000/api/health
```

---

## Performance Characteristics

- **Response time:** <100ms (cache hit)
- **Rate limit:** 30 requests/60s per IP (configurable)
- **Concurrent requests:** 1000+ (uvicorn default)
- **Database connections:** Single shared connection (SQLite)
- **Memory:** ~200MB (API process)

**Bottlenecks:**
- SQLite read conturrency (fine for <10K req/min)
- Rate limiter database writes (separate database)

**Scaling:**
- Horizontal: Multiple API instances (shared SQLite via NFS or switch to Postgres)
- Vertical: Increase uvicorn workers (`--workers 4`)

---

## Key Design Decisions

1. **Cache-only API:** Never fetch live data, only return cached results from background daemon
2. **Shared database connection:** Single connection shared across all requests (SQLite limitation)
3. **Repository Pattern:** Database operations encapsulated in focused repositories
4. **Service layer:** Business logic separated from HTTP concerns
5. **Dependency injection:** Database and rate limiter injected via FastAPI deps
6. **Persistent rate limiting:** SQLite-based, survives restarts
7. **Modular routes:** 6 focused modules instead of one monolith
8. **Pydantic validation:** Input validation + SQL injection prevention
9. **Prometheus metrics:** Comprehensive instrumentation for observability
10. **Admin endpoints:** Separate auth, delegate to daemon for heavy operations

---

## Related Modules

- **`database/`** - Repository Pattern for data persistence
- **`pipeline/`** - Background processing that populates database
- **`vendors/`** - Adapters that fetch data from civic tech platforms
- **`analysis/`** - LLM analysis and topic extraction

---

**Last Updated:** 2025-11-11 (Documentation Sprint)
