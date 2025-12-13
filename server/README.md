# Server - Public API Layer

**Purpose:** FastAPI application serving civic meeting data. Cache-only, async PostgreSQL, clean modular architecture.

Provides:
- Meeting search (zipcode, city, state, topic)
- Meeting retrieval with agenda items
- Topic browsing and filtering
- Matter tracking with legislative timeline
- Council/committee voting records
- User engagement (watches, trending)
- Feedback collection (ratings, issue reports)
- Deliberation (opinion clustering for civic engagement)
- Admin operations (force sync, status)
- Monitoring (health, stats, metrics)
- Flyer generation (civic action printables)
- Authentication (magic link, JWT sessions)
- User dashboard (alerts, subscriptions)

---

## Architecture Overview

**Modular FastAPI with clean separation of concerns:**

```
server/
├── main.py                 - FastAPI app initialization
├── dependencies.py         - Centralized dependency injection
├── rate_limiter.py         - SQLite tiered rate limiting (Standard/Enterprise)
├── metrics.py              - Prometheus instrumentation
│
├── routes/                 - HTTP request handlers (17 modules)
│   ├── search.py           - Universal search endpoint
│   ├── meetings.py         - Meeting retrieval
│   ├── topics.py           - Topic browsing
│   ├── admin.py            - Admin operations (auth required)
│   ├── monitoring.py       - Health, stats, metrics
│   ├── flyer.py            - Civic action flyer generation
│   ├── matters.py          - Matter tracking, timeline
│   ├── donate.py           - Stripe donation integration
│   ├── auth.py             - Magic link authentication, JWT sessions
│   ├── dashboard.py        - User dashboard and alerts
│   ├── votes.py            - Voting records, council member analysis
│   ├── committees.py       - Committee rosters, voting history
│   ├── engagement.py       - User watches, trending topics
│   ├── feedback.py         - User ratings, issue reporting
│   ├── deliberation.py     - Opinion clustering for civic engagement
│   ├── events.py           - Frontend analytics events
│   └── happening.py        - Active/upcoming items
│
├── services/               - Business logic
│   ├── meeting.py          - Meeting retrieval with items
│   ├── search.py           - Core search logic
│   ├── flyer.py            - Flyer HTML generation
│   └── flyer_template.html - Jinja2 template
│
├── middleware/             - Cross-cutting concerns
│   ├── logging.py          - Request/response logging
│   ├── rate_limiting.py    - Rate limit enforcement
│   ├── metrics.py          - Prometheus request metrics
│   └── request_id.py       - Request ID correlation for tracing
│
├── models/                 - Request validation
│   └── requests.py         - Pydantic models (search, flyer, donate, deliberation)
│
└── utils/                  - Reusable utilities
    ├── validation.py       - Input sanitization, entity validation
    ├── constants.py        - State mappings, entity types
    ├── geo.py              - City/state parsing
    ├── vendor_urls.py      - Vendor attribution URL construction
    ├── responses.py        - Standard API response helpers
    └── text.py             - Text processing utilities
```

**Why this structure?**
- **Minimal main.py** - Just wiring, no business logic
- **Focused route modules** - Single responsibility per file (17 modules)
- **Service layer** - Business logic separate from HTTP concerns
- **Dependency injection** - Centralized in dependencies.py
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

### 1. `main.py` - Application Entry Point

**Minimal FastAPI app initialization.** Just wiring, no business logic.

#### Structure

```python
# FastAPI app with lifespan for async db pool
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Initialize async PostgreSQL connection pool
    db = Database()
    await db.connect()
    app.state.db = db
    yield
    await db.close()

app = FastAPI(title="engagic API", lifespan=lifespan)

# CORS middleware
app.add_middleware(CORSMiddleware, allow_origins=config.ALLOWED_ORIGINS, ...)

# Global rate limiter (SQLite-based)
rate_limiter = SQLiteRateLimiter(db_path="rate_limits.db", ...)

# Middleware registration
app.add_middleware(RequestIDMiddleware)

@app.middleware("http")
async def rate_limit_middleware_wrapper(request, call_next):
    return await rate_limit_middleware(request, call_next, rate_limiter)

# Route mounting (17 routers)
app.include_router(monitoring.router)
app.include_router(search.router)
app.include_router(meetings.router)
app.include_router(topics.router)
app.include_router(admin.router)
app.include_router(flyer.router)
app.include_router(matters.router)
app.include_router(donate.router)
app.include_router(auth.router)
app.include_router(dashboard.router)
app.include_router(votes.router)
app.include_router(committees.router)
app.include_router(engagement.router)
app.include_router(feedback.router)
app.include_router(deliberation.router)
app.include_router(events.router)
app.include_router(happening.router)
```

#### Dependency Injection Pattern

**Database:**
```python
# In dependencies.py:
async def get_db(request: Request) -> Database:
    """Get shared async PostgreSQL database from app state"""
    return request.app.state.db

# In routes:
@router.post("/search")
async def search_meetings(request: SearchRequest, db: Database = Depends(get_db)):
    city = await db.get_city(zipcode=request.query)
```

**Why async PostgreSQL?** Connection pooling, better concurrency, production-ready.

---

### 2. `rate_limiter.py` - Tiered Rate Limiting

**SQLite-based rate limiter with two tiers: Standard (everyone), Enterprise (API key holders).**

#### SQLiteRateLimiter

```python
rate_limiter = SQLiteRateLimiter(db_path="rate_limits.db")

# Check rate limit (returns tier info)
is_allowed, remaining, limit_info = rate_limiter.check_rate_limit(
    client_ip_hash,  # SHA256[:16] of raw IP
    api_key,         # Optional API key for enterprise tier
    client_ip_raw,   # For whitelist check and logging
    endpoint         # Optional: endpoint-specific limits (e.g., "/api/events")
)

# limit_info contains: tier, minute_limit, day_limit, remaining_minute, remaining_daily
```

**Limits:**
- Standard: 60/min, 2000/day
- Enterprise: 1000/min, 100000/day
- /api/events: 120/min, 10000/day (endpoint override)

**Features:**
- **Endpoint-aware:** Different limits per endpoint (e.g., lighter for analytics)
- **Dual limits:** Per-minute burst + daily quota
- **Progressive penalties:** Temp bans for repeated violations (10+ violations = 1h, 50+ = 24h, 100+ = 7d)
- **Persistent:** SQLite, survives API restarts, WAL mode for concurrency
- **nginx integration:** Exports blocked IPs for nginx geo blocking

---

### 3. `metrics.py` - Prometheus Instrumentation

**Centralized metrics for observability.**

```python
from server.metrics import metrics

# Sync metrics
metrics.meetings_synced.labels(city="paloaltoCA", vendor="primegov").inc()
metrics.items_extracted.labels(city="paloaltoCA", vendor="primegov").inc(5)
metrics.matters_tracked.labels(city="sanfranciscoCA").inc()

# Processing metrics
with metrics.processing_duration.labels(job_type="meeting").time():
    await process_meeting(meeting_id)

# LLM metrics
metrics.record_llm_call(
    model="gemini-2.5-flash",
    prompt_type="item",
    duration_seconds=3.5,
    input_tokens=1000,
    output_tokens=200,
    cost_dollars=0.0025,
    success=True
)

# Matter engagement
metrics.matter_engagement.labels(action='votes').inc()
```

#### Prometheus Endpoint

```
GET /metrics  # Returns Prometheus text format
```

---

## Route Modules (17)

**Each route module focuses on one domain.** No business logic - delegate to services.

### 1. `routes/search.py`

**Single unified search endpoint** - handles zipcode, city, or state.

```python
@router.post("/api/search")
async def search_meetings(request: SearchRequest, db: Database = Depends(get_db)):
    """Universal search - detects input type and routes appropriately"""
    query = request.query.strip()

    is_zipcode = query.isdigit() and len(query) == 5
    is_state = is_state_query(query)

    if is_zipcode:
        return await handle_zipcode_search(query, db)
    elif is_state:
        return await handle_state_search(query, db)
    else:
        return await handle_city_search(query, db)
```

**Examples:**
```python
POST /api/search {"query": "94301"}           # Zipcode -> Palo Alto meetings
POST /api/search {"query": "Palo Alto, CA"}   # City + State
POST /api/search {"query": "Springfield"}     # Ambiguous -> city options
POST /api/search {"query": "California"}      # State -> city list
```

---

### 2. `routes/meetings.py`

**Meeting retrieval and city-based queries.**

```python
@router.get("/api/meeting/{meeting_id}")
async def get_meeting(meeting_id: str, db: Database = Depends(get_db)):
    """Get single meeting by ID with items attached"""

@router.get("/api/city/{banana}/meetings")
async def get_city_meetings(banana: str, db: Database = Depends(get_db)):
    """Get meetings for a city"""

@router.get("/api/random-meeting-with-items")
async def get_random_meeting_with_items(db: Database = Depends(get_db)):
    """Get random meeting with item summaries (for demos)"""
```

---

### 3. `routes/topics.py`

**Topic-based search and browsing.**

```python
@router.get("/api/topics")
async def get_all_topics():
    """Get all canonical topics (16 topics from taxonomy.json)"""

@router.post("/api/search/by-topic")
async def search_by_topic(request: TopicSearchRequest, db: Database = Depends(get_db)):
    """Search meetings by topic"""

@router.get("/api/topics/popular")
async def get_popular_topics(db: Database = Depends(get_db)):
    """Get most common topics (for UI suggestions)"""

@router.get("/api/city/{banana}/topics")
async def get_city_topics(banana: str, db: Database = Depends(get_db)):
    """Get topics discussed in a city's meetings"""
```

---

### 4. `routes/admin.py`

**Admin endpoints with bearer token authentication.**

```python
async def verify_admin_token(authorization: str = Header(None)):
    """Verify admin bearer token"""

@router.post("/api/admin/sync-city/{banana}")
async def force_sync_city(banana: str, is_admin: bool = Depends(verify_admin_token)):
    """Force sync a specific city"""

@router.get("/api/admin/dead-letter-queue")
async def get_dead_letter_queue(is_admin: bool = Depends(verify_admin_token)):
    """Get failed items from dead letter queue"""

@router.get("/api/admin/activity-feed")
async def get_activity_feed(is_admin: bool = Depends(verify_admin_token)):
    """Get recent processing activity"""

@router.get("/api/admin/live-metrics")
async def get_live_metrics(is_admin: bool = Depends(verify_admin_token)):
    """Get real-time system metrics"""
```

**Usage:**
```bash
curl -X POST http://localhost:8000/api/admin/sync-city/paloaltoCA \
  -H "Authorization: Bearer YOUR_ADMIN_TOKEN"
```

---

### 5. `routes/monitoring.py`

**Health checks, stats, metrics, and analytics.**

```python
@router.get("/")
async def root():
    """API status and documentation"""

@router.get("/api/health")
async def health_check(db: Database = Depends(get_db)):
    """Health check with detailed status"""

@router.get("/api/stats")
async def get_stats(db: Database = Depends(get_db)):
    """System statistics"""

@router.get("/api/queue-stats")
async def get_queue_stats(db: Database = Depends(get_db)):
    """Processing queue statistics"""

@router.get("/metrics")
async def prometheus_metrics(db: Database = Depends(get_db)):
    """Prometheus metrics endpoint"""

@router.get("/api/analytics")
async def get_analytics(db: Database = Depends(get_db)):
    """Public dashboard analytics"""
```

---

### 6. `routes/flyer.py`

**Civic action flyer generation.**

```python
@router.post("/api/flyer/generate")
async def generate_flyer(request: FlyerRequest, db: Database = Depends(get_db)):
    """Generate printable civic action flyer

    Returns HTML ready for browser print-to-PDF.
    """
```

**Request:**
```python
POST /api/flyer/generate
{
    "meeting_id": "paloaltoCA_2025-11-10",
    "item_id": "item_5",  # Optional
    "position": "support",  # support | oppose | more_info
    "custom_message": "I support this housing project because...",
    "user_name": "Jane Doe",
    "dark_mode": false
}
```

---

### 7. `routes/matters.py`

**Matter tracking and timeline endpoints.**

```python
@router.get("/api/matters/{matter_id}")
async def get_matter(matter_id: str, db: Database = Depends(get_db)):
    """Get matter details with timeline across all appearances"""

@router.get("/api/city/{banana}/matters")
async def get_city_matters(banana: str, db: Database = Depends(get_db)):
    """Get all tracked matters for a city"""

@router.get("/api/matters/{matter_id}/sponsors")
async def get_matter_sponsors(matter_id: str, db: Database = Depends(get_db)):
    """Get sponsors/introducers for a matter"""

@router.get("/api/city/{banana}/search/matters")
async def search_city_matters(banana: str, q: str, db: Database = Depends(get_db)):
    """Search matters within a city"""

@router.get("/api/random-matter")
async def get_random_matter(db: Database = Depends(get_db)):
    """Get a random matter with good data (for demos)"""
```

---

### 8. `routes/donate.py`

**Stripe donation integration for sustainable funding.**

```python
@router.post("/api/donate/checkout")
async def create_checkout_session(donate_request: DonateRequest):
    """Create Stripe checkout session for one-time donations

    Args:
        donate_request: Contains amount in cents

    Returns:
        dict with checkout_url for redirecting user to Stripe Checkout
    """
```

**Request:**
```python
POST /api/donate/checkout
{"amount": 2000}  # $20.00 in cents
```

---

### 9. `routes/auth.py`

**Magic link authentication with JWT sessions.**

```python
@router.post("/api/auth/signup")
async def signup(signup_request: SignupRequest, db: Database = Depends(get_db)):
    """Create user account and send magic link"""

@router.post("/api/auth/login")
async def login(login_request: LoginRequest, db: Database = Depends(get_db)):
    """Send magic link to existing user"""

@router.get("/api/auth/verify")
async def verify_magic_link(token: str, response: Response, request: Request):
    """Verify magic link and create session (JWT tokens)"""

@router.post("/api/auth/refresh")
async def refresh_access_token(request: Request, response: Response):
    """Refresh access token using refresh token from cookie"""

@router.post("/api/auth/logout")
async def logout(response: Response):
    """Logout by clearing refresh token cookie"""

@router.get("/api/auth/me")
async def get_current_user_endpoint(user: User = Depends(get_current_user)):
    """Get current user profile"""

@router.get("/api/auth/unsubscribe")
async def unsubscribe(token: str, request: Request):
    """One-click unsubscribe from email digest (CAN-SPAM compliance)"""
```

**Security features:**
- No passwords (magic links only)
- Tokens hashed with SHA-256 before storage
- Single-use magic links (15-minute expiry)
- JWT access tokens (15-minute expiry)
- Refresh tokens in httpOnly cookies (30-day expiry)

---

### 10. `routes/dashboard.py`

**User dashboard for alert management.**

```python
@router.get("/api/dashboard")
async def get_dashboard(user: User = Depends(get_current_user), db: Database = Depends(get_db)):
    """Get consolidated dashboard: stats, digests, recent matches"""

@router.get("/api/dashboard/stats")
async def get_dashboard_stats(user: User = Depends(get_current_user)):
    """Get dashboard statistics"""

@router.get("/api/dashboard/activity")
async def get_recent_activity(user: User = Depends(get_current_user)):
    """Get recent match activity"""

@router.put("/api/dashboard/alert/{alert_id}")
async def update_alert(alert_id: str, update_request: AlertUpdateRequest, user: User = Depends(get_current_user)):
    """Update an alert configuration"""

@router.delete("/api/dashboard/alert/{alert_id}")
async def delete_alert(alert_id: str, user: User = Depends(get_current_user)):
    """Delete an alert"""

@router.patch("/api/dashboard/alerts/{alert_id}")
async def patch_alert(alert_id: str, updates: Dict[str, Any], user: User = Depends(get_current_user)):
    """Partially update an alert"""

@router.post("/api/dashboard/alerts/{alert_id}/keywords")
async def add_keyword_to_alert(alert_id: str, keyword_data: Dict[str, str]):
    """Add keyword to alert (max 3 keywords)"""

@router.delete("/api/dashboard/alerts/{alert_id}/keywords")
async def remove_keyword_from_alert(alert_id: str, keyword_data: Dict[str, str]):
    """Remove keyword from alert"""

@router.post("/api/dashboard/alerts/{alert_id}/cities")
async def add_city_to_alert(alert_id: str, city_data: Dict[str, str]):
    """Set city for alert (simplified UX: 1 city only)"""
```

---

### 11. `routes/votes.py`

**Voting records and council member analysis.**

```python
@router.get("/api/matters/{matter_id}/votes")
async def get_matter_votes(matter_id: str, db: Database = Depends(get_db)):
    """Get all votes on a matter across all meetings"""

@router.get("/api/meetings/{meeting_id}/votes")
async def get_meeting_votes(meeting_id: str, db: Database = Depends(get_db)):
    """Get all votes cast in a meeting, grouped by matter"""

@router.get("/api/council-members/{member_id}/votes")
async def get_member_votes(member_id: str, db: Database = Depends(get_db)):
    """Get voting record for a council member"""

@router.get("/api/city/{banana}/council-members")
async def get_city_council(banana: str, db: Database = Depends(get_db)):
    """Get city council roster with vote counts"""
```

---

### 12. `routes/committees.py`

**Committee rosters and voting history.**

```python
@router.get("/api/city/{banana}/committees")
async def get_city_committees(banana: str, db: Database = Depends(get_db)):
    """Get all committees for a city with member counts"""

@router.get("/api/committees/{committee_id}")
async def get_committee(committee_id: str, db: Database = Depends(get_db)):
    """Get committee details with current roster"""

@router.get("/api/committees/{committee_id}/members")
async def get_committee_members(committee_id: str, active_only: bool = True, as_of: str = None):
    """Get committee membership roster (supports historical queries)"""

@router.get("/api/committees/{committee_id}/votes")
async def get_committee_votes(committee_id: str, db: Database = Depends(get_db)):
    """Get voting history for a committee"""

@router.get("/api/council-members/{member_id}/committees")
async def get_member_committees(member_id: str, db: Database = Depends(get_db)):
    """Get committees a council member serves on"""
```

---

### 13. `routes/engagement.py`

**User engagement tracking - watches and trending.**

```python
@router.post("/api/watch/{entity_type}/{entity_id}")
async def watch_entity(entity_type: str, entity_id: str, user: User = Depends(get_current_user)):
    """Add entity to user's watch list (requires auth)"""

@router.delete("/api/watch/{entity_type}/{entity_id}")
async def unwatch_entity(entity_type: str, entity_id: str, user: User = Depends(get_current_user)):
    """Remove entity from user's watch list"""

@router.get("/api/me/watching")
async def get_user_watches(entity_type: str = None, user: User = Depends(get_current_user)):
    """Get user's watched entities"""

@router.get("/api/trending/matters")
async def get_trending_matters(limit: int = 20, db: Database = Depends(get_db)):
    """Get trending matters based on engagement (public)"""

@router.get("/api/matters/{matter_id}/engagement")
async def get_matter_engagement(matter_id: str, request: Request):
    """Get engagement stats for a matter (watch count, user's watch status)"""

@router.get("/api/meetings/{meeting_id}/engagement")
async def get_meeting_engagement(meeting_id: str, request: Request):
    """Get engagement stats for a meeting"""

@router.post("/api/activity/view/{entity_type}/{entity_id}")
async def log_view(entity_type: str, entity_id: str, request: Request):
    """Log a page view for analytics (works for anonymous users)"""

@router.post("/api/activity/search")
async def log_search(request: Request, query: str):
    """Log a search query for analytics"""
```

**Watchable entity types:** matter, meeting, topic, city, council_member

---

### 14. `routes/feedback.py`

**User feedback collection - ratings and issue reporting.**

```python
@router.post("/api/rate/{entity_type}/{entity_id}")
async def rate_entity(entity_type: str, entity_id: str, body: RatingRequest, request: Request):
    """Submit rating (1-5 stars) for an entity"""

@router.post("/api/report/{entity_type}/{entity_id}")
async def report_issue(entity_type: str, entity_id: str, body: IssueRequest, request: Request):
    """Report an issue with a summary (inaccurate, incomplete, misleading, etc.)"""

@router.get("/api/{entity_type}/{entity_id}/rating")
async def get_entity_rating(entity_type: str, entity_id: str, request: Request):
    """Get rating statistics for an entity (public)"""

@router.get("/api/{entity_type}/{entity_id}/issues")
async def get_entity_issues(entity_type: str, entity_id: str, status: str = None):
    """Get issues reported for an entity (public for transparency)"""

@router.get("/api/admin/issues")
async def get_open_issues(user: User = Depends(get_current_user)):
    """Admin: Get unresolved issues for review"""

@router.post("/api/admin/issues/{issue_id}/resolve")
async def resolve_issue(issue_id: int, body: IssueResolutionRequest, user: User = Depends(get_current_user)):
    """Admin: Mark issue as resolved or dismissed"""

@router.get("/api/admin/low-rated")
async def get_low_rated_entities(threshold: float = 2.5, min_ratings: int = 3):
    """Admin: Get entities with low ratings for reprocessing"""
```

**Ratable entity types:** item, meeting, matter
**Issue types:** inaccurate, incomplete, misleading, offensive, other

---

### 15. `routes/deliberation.py`

**Opinion clustering for civic engagement.** Structured public input on legislative matters.

```python
# Public endpoints
@router.get("/api/v1/deliberations/{deliberation_id}")
async def get_deliberation(deliberation_id: str, db: Database = Depends(get_db)):
    """Get deliberation state and approved comments"""

@router.get("/api/v1/deliberations/{deliberation_id}/results")
async def get_results(deliberation_id: str, db: Database = Depends(get_db)):
    """Get clustering results (positions, clusters, consensus, group votes)"""

@router.get("/api/v1/deliberations/matter/{matter_id}")
async def get_deliberation_for_matter(matter_id: str, db: Database = Depends(get_db)):
    """Get active deliberation for a matter"""

# Authenticated endpoints
@router.post("/api/v1/deliberations")
async def create_deliberation(body: DeliberationCreateRequest, user: User = Depends(get_current_user)):
    """Create a new deliberation for a matter"""

@router.post("/api/v1/deliberations/{deliberation_id}/comments")
async def create_comment(deliberation_id: str, body: CommentCreateRequest, user: User = Depends(get_current_user)):
    """Submit a comment (trusted users auto-approved, others queued for moderation)"""

@router.post("/api/v1/deliberations/{deliberation_id}/votes")
async def vote_on_comment(deliberation_id: str, body: VoteRequest, user: User = Depends(get_current_user)):
    """Vote on a comment: 1=agree, 0=pass, -1=disagree"""

@router.get("/api/v1/deliberations/{deliberation_id}/my-votes")
async def get_my_votes(deliberation_id: str, user: User = Depends(get_current_user)):
    """Get current user's votes for a deliberation"""

# Admin/moderation endpoints
@router.get("/api/v1/deliberations/{deliberation_id}/pending")
async def get_pending_comments(deliberation_id: str, is_admin: bool = Depends(verify_admin_token)):
    """Get pending comments for moderation"""

@router.post("/api/v1/deliberations/{deliberation_id}/moderate")
async def moderate_comment(deliberation_id: str, body: ModerateRequest, is_admin: bool = Depends(verify_admin_token)):
    """Approve or hide a pending comment"""

@router.post("/api/v1/deliberations/{deliberation_id}/compute")
async def compute_clusters(deliberation_id: str, is_admin: bool = Depends(verify_admin_token)):
    """Trigger clustering computation"""
```

**Use case:** Enable structured public input on contentious matters with opinion clustering to surface consensus and identify distinct viewpoints.

---

### 16. `routes/events.py`

**Frontend analytics event tracking** for user journey analysis.

```python
@router.post("/api/events")
async def track_event(event: FrontendEvent, request: Request, db: Database = Depends(get_db)):
    """Receive frontend event and store for journey analysis"""

# Admin endpoints for journey analytics
@router.get("/api/funnel/journeys")
async def get_journeys(limit: int = 50, hours: int = 24, _: bool = Depends(verify_admin_token)):
    """Get recent user journeys for flow analysis"""

@router.get("/api/funnel/patterns")
async def get_patterns(hours: int = 24, _: bool = Depends(verify_admin_token)):
    """Get common user flow patterns"""

@router.get("/api/funnel/dropoffs")
async def get_dropoffs(hours: int = 24, _: bool = Depends(verify_admin_token)):
    """Identify where users drop off"""
```

**Features:**
- IP hash links events to user journeys (privacy-preserving)
- 7-day automatic cleanup of old events
- Prometheus counter integration for aggregate metrics

---

### 17. `routes/happening.py`

**Active/upcoming items** - Claude-analyzed important civic items.

```python
@router.get("/api/happening")
async def get_happening(banana: Optional[str] = None, db: Database = Depends(get_db)):
    """Get important/trending items for this week"""
```

---

## Service Layer

**Business logic separated from HTTP concerns.**

### `services/search.py`

Core search logic for zipcode, city, and state searches.

```python
async def handle_zipcode_search(zipcode: str, db: Database) -> SearchResponse:
    """Handle zipcode search with cache-first approach"""

async def handle_city_search(city_input: str, db: Database) -> SearchResponse:
    """Handle city name search with ambiguous city handling"""

async def handle_state_search(state_input: str, db: Database) -> SearchResponse:
    """Handle state search - return list of cities"""

async def handle_ambiguous_city_search(city_name: str, original_input: str, db: Database) -> SearchResponse:
    """Handle city search when no state is provided - fuzzy matching for typos"""
```

**Key patterns:**
- **Cache-first:** Only return cached data, never fetch live
- **Fuzzy matching:** Handle typos with `difflib.get_close_matches()`
- **Ambiguous handling:** Return city options when multiple matches

---

### `services/meeting.py`

Meeting retrieval with items attached.

```python
async def get_meeting_with_items(meeting: Meeting, db: Database) -> Dict[str, Any]:
    """Convert meeting to dict with items attached"""

async def get_meetings_with_items(meetings: List[Meeting], db: Database) -> List[Dict[str, Any]]:
    """Batch fetch items for all meetings - eliminates N+1 queries"""
```

---

### `services/flyer.py`

Generate printable civic action flyers with QR codes.

```python
async def generate_meeting_flyer(
    meeting: Meeting,
    item: Optional[AgendaItem],
    position: str,
    custom_message: Optional[str],
    user_name: Optional[str],
    db: Database,
    dark_mode: bool = False
) -> str:
    """Generate HTML flyer ready for printing"""
```

**Features:**
- Print-optimized layout (single page)
- QR code linking to meeting/item
- Participation info (email, phone, virtual URL)
- Position-specific styling (support/oppose/more_info)
- Dark mode support

---

## Middleware

**Cross-cutting concerns applied to all requests.**

### `middleware/rate_limiting.py`

Rate limit enforcement with endpoint-aware limits and comprehensive 429 responses.

```python
async def rate_limit_middleware(request: Request, call_next, rate_limiter: SQLiteRateLimiter):
    """Check rate limits with unified endpoint-aware system

    IP Detection:
    - CF-Connecting-IP (Cloudflare, trusted)
    - X-Forwarded-For (nginx fallback, for local dev)

    Features:
    - Endpoint-aware: /api/events gets 120/min, others get 60/min
    - Privacy-preserving IP hashing (SHA256[:16])
    - Graduated responses: friendly for burst limits, firm for daily limits
    - Temp ban for repeated violations (nginx IP blocking)
    """
```

---

### `middleware/request_id.py`

Request ID correlation for distributed tracing.

```python
class RequestIDMiddleware(BaseHTTPMiddleware):
    """Add unique request ID for tracing across logs

    - Generated or accepted from X-Request-ID header
    - Bound to structlog context (appears in all logs)
    - Returned in X-Request-ID response header
    """
```

---

## Models

**Pydantic models for request validation.**

### `models/requests.py`

```python
class SearchRequest(BaseModel):
    query: str  # Validated: 2-200 chars, alphanumeric + basic punctuation

class ProcessRequest(BaseModel):
    packet_url: str  # HTTP/HTTPS URL
    banana: str      # City banana (e.g., "paloaltoCA")

class TopicSearchRequest(BaseModel):
    topic: str
    banana: Optional[str] = None
    limit: int = 50

class FlyerRequest(BaseModel):
    meeting_id: str
    item_id: Optional[str] = None
    position: str  # support | oppose | more_info
    custom_message: Optional[str] = None  # Max 500 chars
    user_name: Optional[str] = None       # Max 100 chars
    dark_mode: bool = False

class DonateRequest(BaseModel):
    amount: int  # Cents, min $1.00 (100), max $10,000 (1000000)

# Deliberation models
class DeliberationCreateRequest(BaseModel):
    matter_id: str
    topic: Optional[str] = None

class CommentCreateRequest(BaseModel):
    txt: str  # 10-500 characters

class VoteRequest(BaseModel):
    comment_id: int
    vote: Literal[-1, 0, 1]  # -1=disagree, 0=pass, 1=agree

class ModerateRequest(BaseModel):
    comment_id: int
    approve: bool
```

---

## Utils

### `utils/validation.py`

Input sanitization, SQL injection prevention, and entity existence checks.

```python
def sanitize_string(value: str) -> str:
    """Sanitize string input to prevent injection attacks"""

def validate_watchable_entity(entity_type: str):
    """Validate entity_type is watchable (matter, meeting, topic, city, council_member)"""

def validate_ratable_entity(entity_type: str):
    """Validate entity_type is ratable (item, meeting, matter)"""

def validate_issue_type(issue_type: str):
    """Validate issue_type (inaccurate, incomplete, misleading, offensive, other)"""

async def require_city(db, banana: str):
    """Get city or raise 404"""

async def require_meeting(db, meeting_id: str):
    """Get meeting or raise 404"""

async def require_matter(db, matter_id: str):
    """Get matter or raise 404"""

async def require_council_member(db, member_id: str):
    """Get council member or raise 404"""
```

---

### `utils/vendor_urls.py`

Vendor attribution URL construction for source transparency.

```python
def get_vendor_source_url(vendor: str, slug: str) -> Optional[str]:
    """Construct the source URL for a city's meeting calendar

    Supports: legistar, primegov, granicus, iqm2, novusagenda,
              escribe, civicclerk, civicplus, berkeley, chicago, menlopark
    """

def get_vendor_display_name(vendor: str) -> str:
    """Get human-readable vendor name for attribution"""
```

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
GET    /api/city/{banana}/meetings   Get meetings for a city
GET    /api/random-meeting-with-items Get random meeting (for demos)
POST   /api/process-agenda           Get cached meeting summary
```

### Topics

```
GET    /api/topics                   Get all canonical topics (16 topics)
GET    /api/topics/popular           Get most common topics
GET    /api/city/{banana}/topics     Get topics for a city
```

### Matters

```
GET    /api/matters/{matter_id}           Get matter with timeline
GET    /api/matters/{matter_id}/sponsors  Get matter sponsors
GET    /api/city/{banana}/matters         Get all matters for a city
GET    /api/city/{banana}/search/matters  Search matters in a city
GET    /api/random-matter                 Get random matter (for demos)
```

### Votes

```
GET    /api/matters/{matter_id}/votes         Get all votes on a matter
GET    /api/meetings/{meeting_id}/votes       Get all votes in a meeting
GET    /api/council-members/{member_id}/votes Get member voting record
GET    /api/city/{banana}/council-members     Get city council roster
```

### Committees

```
GET    /api/city/{banana}/committees          Get all committees for a city
GET    /api/committees/{committee_id}         Get committee details
GET    /api/committees/{committee_id}/members Get committee roster
GET    /api/committees/{committee_id}/votes   Get committee voting history
GET    /api/council-members/{member_id}/committees Get member's committees
```

### Engagement

```
POST   /api/watch/{entity_type}/{entity_id}   Watch an entity (auth required)
DELETE /api/watch/{entity_type}/{entity_id}   Unwatch an entity
GET    /api/me/watching                       Get user's watched entities
GET    /api/trending/matters                  Get trending matters (public)
GET    /api/matters/{matter_id}/engagement    Get matter engagement stats
GET    /api/meetings/{meeting_id}/engagement  Get meeting engagement stats
POST   /api/activity/view/{entity_type}/{entity_id}  Log page view
POST   /api/activity/search                   Log search query
```

### Feedback

```
POST   /api/rate/{entity_type}/{entity_id}    Submit rating (1-5)
POST   /api/report/{entity_type}/{entity_id}  Report issue
GET    /api/{entity_type}/{entity_id}/rating  Get rating stats
GET    /api/{entity_type}/{entity_id}/issues  Get reported issues
GET    /api/admin/issues                      Admin: Get open issues
POST   /api/admin/issues/{issue_id}/resolve   Admin: Resolve issue
GET    /api/admin/low-rated                   Admin: Get low-rated entities
```

### Deliberation

```
GET    /api/v1/deliberations/{deliberation_id}           Get deliberation
GET    /api/v1/deliberations/{deliberation_id}/results   Get clustering results
GET    /api/v1/deliberations/matter/{matter_id}          Get deliberation for matter
POST   /api/v1/deliberations                             Create deliberation (auth)
POST   /api/v1/deliberations/{deliberation_id}/comments  Submit comment (auth)
POST   /api/v1/deliberations/{deliberation_id}/votes     Vote on comment (auth)
GET    /api/v1/deliberations/{deliberation_id}/my-votes  Get user's votes (auth)
GET    /api/v1/deliberations/{deliberation_id}/pending   Admin: pending comments
POST   /api/v1/deliberations/{deliberation_id}/moderate  Admin: moderate comment
POST   /api/v1/deliberations/{deliberation_id}/compute   Admin: compute clusters
```

### Auth

```
POST   /api/auth/signup              Create account, send magic link
POST   /api/auth/login               Send magic link to existing user
GET    /api/auth/verify              Verify magic link, create session
POST   /api/auth/refresh             Refresh access token
POST   /api/auth/logout              Clear session
GET    /api/auth/me                  Get current user profile
GET    /api/auth/unsubscribe         One-click unsubscribe from digests
```

### Dashboard

```
GET    /api/dashboard                Get consolidated dashboard
GET    /api/dashboard/stats          Get dashboard statistics
GET    /api/dashboard/activity       Get recent activity
GET    /api/dashboard/config         Get alert configuration
PUT    /api/dashboard/alert/{id}     Update alert
DELETE /api/dashboard/alert/{id}     Delete alert
PATCH  /api/dashboard/alerts/{id}    Partial update alert
POST   /api/dashboard/alerts/{id}/keywords   Add keyword
DELETE /api/dashboard/alerts/{id}/keywords   Remove keyword
POST   /api/dashboard/alerts/{id}/cities     Set city
DELETE /api/dashboard/alerts/{id}/cities     Remove city
```

### Flyer

```
POST   /api/flyer/generate           Generate printable flyer (HTML)
```

### Donate

```
POST   /api/donate/checkout          Create Stripe checkout session
```

### Events (Analytics)

```
POST   /api/events                   Track frontend event
GET    /api/funnel/journeys          Admin: Get user journeys
GET    /api/funnel/patterns          Admin: Get flow patterns
GET    /api/funnel/dropoffs          Admin: Get dropoff points
```

### Happening

```
GET    /api/happening                Get important items this week
```

### Admin (requires Bearer token)

```
GET    /api/admin/city-requests      View requested cities
POST   /api/admin/sync-city/{banana} Force sync city
POST   /api/admin/process-meeting    Force process meeting
GET    /api/admin/dead-letter-queue  Get failed items
GET    /api/admin/activity-feed      Get processing activity
GET    /api/admin/live-metrics       Get real-time metrics
```

### Monitoring

```
GET    /                             API status and documentation
GET    /api/health                   Health check
GET    /api/stats                    System statistics
GET    /api/queue-stats              Processing queue statistics
GET    /api/metrics                  Basic metrics (JSON)
GET    /metrics                      Prometheus metrics (text format)
GET    /api/analytics                Public dashboard analytics
```

---

## Configuration

**Required:**
```bash
DATABASE_URL=postgresql://user:pass@host:5432/engagic
ENGAGIC_API_HOST=0.0.0.0
ENGAGIC_API_PORT=8000
```

**Rate Limiting:**
Rate limits are hardcoded in `rate_limiter.py`:
- Standard: 60 req/min, 2000 req/day
- Enterprise: 1000 req/min, 100000 req/day

**CORS:**
```bash
ENGAGIC_ALLOWED_ORIGINS=http://localhost:5173,https://engagic.org
```

**Admin:**
```bash
ENGAGIC_ADMIN_TOKEN=your_secret_token_here
```

**Auth:**
```bash
JWT_SECRET=your_jwt_secret
COOKIE_SECURE=true
COOKIE_SAMESITE=lax
SSR_AUTH_SECRET=your_ssr_secret
```

**Stripe:**
```bash
STRIPE_SECRET_KEY=sk_live_...
FRONTEND_URL=https://engagic.org
```

---

## Performance Characteristics

- **Response time:** <100ms (cache hit)
- **Rate limit:** 60 req/min, 2000/day per IP (Standard tier)
- **Concurrent requests:** 1000+ (uvicorn default)
- **Database:** Async PostgreSQL with connection pooling
- **Memory:** ~200MB (API process)

**Scaling:**
- Horizontal: Multiple API instances (shared PostgreSQL)
- Vertical: Increase uvicorn workers (`--workers 4`)

---

## Key Design Decisions

1. **Cache-only API:** Never fetch live data, only return cached results from background daemon
2. **Async PostgreSQL:** Connection pooling, better concurrency than SQLite
3. **Repository Pattern:** Database operations encapsulated in focused repositories
4. **Service layer:** Business logic separated from HTTP concerns
5. **Dependency injection:** Database and rate limiter injected via FastAPI deps
6. **Persistent rate limiting:** SQLite-based, survives restarts, supports tiers
7. **Modular routes:** 16 focused modules instead of one monolith
8. **Pydantic validation:** Input validation + SQL injection prevention
9. **Prometheus metrics:** Comprehensive instrumentation for observability
10. **JWT sessions:** Stateless authentication with refresh token rotation

---

## Related Modules

- **`database/`** - Repository Pattern for PostgreSQL persistence
- **`pipeline/`** - Background processing that populates database
- **`vendors/`** - Adapters that fetch data from civic tech platforms
- **`analysis/`** - LLM analysis and topic extraction
- **`userland/`** - Civic alerts system
- **`deliberation/`** - Opinion clustering algorithms

---

**Last Updated:** 2025-12-13 (17 route modules, funnel analytics documented)
