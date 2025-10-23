# Engagic Refactoring Plan
**Goal: Reduce surface area by 60%, prepare for B2B multi-tenancy**

## Executive Summary

Current codebase: ~7000 lines doing what should take ~2500 lines.
Problem: Abstraction sprawl, premature optimization, unclear separation of concerns.
Solution: Consolidate databases, extract adapter base class, simplify processing pipeline, prepare for tenant isolation.

Timeline: 4-6 weeks for complete refactor.
Risk: Medium (well-tested domain, clear requirements).

**Progress Update (2025-01-23):**
- Phase 1: Database Consolidation ✅ COMPLETE (-1549 lines)
- Phase 2: Adapter Refactor ✅ COMPLETE (-339 lines)
- **Total reduction: 1888 lines (31% toward 60% goal)**
- Phases 3-6: Remaining work to reach ~2500 lines target

## Current State Analysis

### What We Have (Problems)

**Database Layer: 3 DBs, 15+ lookup methods**
```
locations.db: cities, zipcodes (334 lines)
meetings.db: meetings, processing_cache (714 lines)
analytics.db: usage tracking (unused in refactor)

Problems:
- get_city_by_name(), get_city_by_slug(), get_city_by_banana(), get_city_by_zipcode()
- Each method reimplements similar query logic
- No unified city lookup interface
- Date normalization scattered across codebase (12+ date formats)
```

**Adapter Layer: 1428 lines, 6 vendors, no shared logic**
```
PrimeGovAdapter, CivicClerkAdapter, LegistarAdapter, GranicusAdapter,
NovusAgendaAdapter, CivicPlusAdapter

Problems:
- Each adapter reimplements: HTTP fetching, PDF discovery, date parsing
- Deep scraping mixed with meeting extraction
- No retry logic or error handling standards
- Rate limiting done externally instead of per-adapter
```

**Processing Layer: 3-tier fallback with 60% tier-1 success**
```
Tier 1: PyPDF2 + Gemini text (60% success, fast, cheap)
Tier 2: Mistral OCR + Gemini text (15% success, slow, expensive)
Tier 3: Gemini PDF API (95% success, very slow, very expensive)

Problems:
- Tier 2 adds complexity for marginal gain
- Download logic repeated in each tier
- Quality checking scattered across methods
- No circuit breaker for consistently failing URLs
```

**Background Processing: Threading soup with manual rate limiting**
```
Two daemon threads: sync_loop (7 days) + processing_loop (2 days)
Manual sleep loops with flag checking
Per-vendor rate limiting with locks
Unbounded status tracking (memory leak risk)

Problems:
- No job queue, just threads that sleep and poll
- Can't prioritize high-value cities
- No retry logic for transient failures
- Status tracking grows unbounded
```

### What We Actually Need (Solution)

**Simple Core Loop:**
```
1. For each city_banana:
   - Fetch meetings from vendor adapter
   - Store meeting metadata
   - Queue PDF summarization if packet exists

2. For each queued PDF:
   - Try fast extraction (PyPDF2)
   - Fall back to Gemini PDF API if needed
   - Cache summary

3. API serves cached data instantly
```

**B2B Multi-Tenancy Requirements:**
```
- Tenant coverage: subset of city_bananas
- Topic tracking: "housing", "zoning", "budget"
- Ordinance tracking: follow specific proposals over time
- Alert triggers: notify on keywords or city activity
- Data isolation: tenant A can't see tenant B's tracked items
```

## Proposed Architecture

### Core Data Model (Simplified)

```python
# Single source of truth for cities
class City:
    banana: str              # paloaltoCA (primary key, derived)
    name: str                # Palo Alto
    state: str               # CA
    vendor: str              # primegov
    vendor_slug: str         # cityofpaloalto
    county: Optional[str]
    zipcodes: List[str]
    status: str = "active"

    # Computed property
    @property
    def banana(self) -> str:
        return generate_city_banana(self.name, self.state)

# Meetings with optional summaries
class Meeting:
    id: str                  # Auto-generated or vendor-provided
    city_banana: str         # Foreign key to City
    title: str
    date: datetime           # Always normalized to ISO
    packet_url: Optional[str | List[str]]
    summary: Optional[str]
    processing_status: ProcessingStatus
    created_at: datetime
    updated_at: datetime

# Multi-tenancy support
class Tenant:
    id: str
    name: str
    coverage_cities: List[str]  # List of city_bananas
    topic_keywords: List[str]   # ["housing", "zoning"]
    tracked_items: List[TrackedItem]

class TrackedItem:
    id: str
    tenant_id: str
    item_type: str           # "ordinance", "proposal", "project"
    title: str
    city_banana: str
    first_seen: datetime
    last_seen: datetime
    meeting_references: List[str]  # List of meeting IDs
    status: str              # "active", "passed", "rejected"
```

### Unified Database Interface

**Before (scattered):**
```python
city = db.locations.get_city_by_name("Palo Alto", "CA")
city = db.locations.get_city_by_banana("paloaltoCA")
city = db.locations.get_city_by_slug("cityofpaloalto")
city = db.locations.get_city_by_zipcode("94301")
```

**After (unified):**
```python
# Single method with optional parameters
city = db.get_city(
    name="Palo Alto",
    state="CA"
)
city = db.get_city(banana="paloaltoCA")
city = db.get_city(vendor_slug="cityofpaloalto")
city = db.get_city(zipcode="94301")

# Batch operations
cities = db.get_cities(
    state="CA",
    vendor="primegov",
    status="active"
)
```

**Implementation:**
```python
class UnifiedDatabase:
    def __init__(self, db_path: str):
        # Single SQLite database
        self.conn = sqlite3.connect(db_path)
        self._init_schema()

    def get_city(
        self,
        banana: str = None,
        name: str = None,
        state: str = None,
        vendor_slug: str = None,
        zipcode: str = None
    ) -> Optional[City]:
        """Unified city lookup - uses most specific parameter"""

        if banana:
            query = "SELECT * FROM cities WHERE city_banana = ?"
            params = (banana,)
        elif vendor_slug:
            query = "SELECT * FROM cities WHERE vendor_slug = ?"
            params = (vendor_slug,)
        elif zipcode:
            query = """
                SELECT c.* FROM cities c
                JOIN city_zipcodes cz ON c.city_banana = cz.city_banana
                WHERE cz.zipcode = ?
            """
            params = (zipcode,)
        elif name and state:
            # Case-insensitive, space-normalized lookup
            query = """
                SELECT * FROM cities
                WHERE LOWER(REPLACE(name, ' ', '')) = ?
                AND UPPER(state) = ?
            """
            params = (name.lower().replace(' ', ''), state.upper())
        else:
            raise ValueError("Must provide at least one search parameter")

        cursor = self.conn.execute(query, params)
        row = cursor.fetchone()
        return City.from_db_row(row) if row else None

    def get_cities(
        self,
        state: str = None,
        vendor: str = None,
        status: str = "active",
        limit: int = None
    ) -> List[City]:
        """Batch city lookup with filters"""

        conditions = ["status = ?"]
        params = [status]

        if state:
            conditions.append("UPPER(state) = ?")
            params.append(state.upper())

        if vendor:
            conditions.append("vendor = ?")
            params.append(vendor)

        query = f"""
            SELECT * FROM cities
            WHERE {' AND '.join(conditions)}
            ORDER BY name
        """

        if limit:
            query += f" LIMIT {limit}"

        cursor = self.conn.execute(query, params)
        return [City.from_db_row(row) for row in cursor.fetchall()]
```

### Adapter Refactor: Base Class + Thin Vendors

**Shared logic extracted to base:**
```python
class BaseAdapter:
    """Base adapter with common HTTP, parsing, and error handling"""

    def __init__(self, city_slug: str, vendor: str):
        self.city_slug = city_slug
        self.vendor = vendor
        self.session = self._create_session()

    def _create_session(self) -> requests.Session:
        """Shared HTTP session with retries"""
        session = requests.Session()
        session.headers.update({
            "User-Agent": "Engagic/2.0 (Civic Engagement Bot)"
        })

        # Retry logic for transient failures
        retry = Retry(
            total=3,
            backoff_factor=1,
            status_forcelist=[429, 500, 502, 503, 504]
        )
        adapter = HTTPAdapter(max_retries=retry)
        session.mount("http://", adapter)
        session.mount("https://", adapter)

        return session

    def fetch_meetings(self) -> List[RawMeeting]:
        """Override in subclass - vendor-specific logic"""
        raise NotImplementedError

    def _parse_date(self, date_str: str) -> Optional[datetime]:
        """Shared date parsing for common formats"""
        if not date_str:
            return None

        # Try common formats in order
        formats = [
            "%b %d, %Y %I:%M %p",  # Jul 22, 2025 6:30 PM
            "%B %d, %Y %I:%M %p",  # July 22, 2025 6:30 PM
            "%Y-%m-%d %H:%M:%S",   # 2025-07-22 18:30:00
            "%m/%d/%Y %I:%M %p",   # 07/22/2025 6:30 PM
            "%Y-%m-%d",            # 2025-07-22
        ]

        for fmt in formats:
            try:
                return datetime.strptime(date_str.strip(), fmt)
            except ValueError:
                continue

        # Fallback: dateutil.parser
        try:
            from dateutil import parser
            return parser.parse(date_str, fuzzy=True)
        except Exception:
            logger.warning(f"Could not parse date: {date_str}")
            return None

    def _discover_pdfs(self, url: str, max_depth: int = 2) -> List[str]:
        """Shared PDF discovery with depth limiting"""
        # Common logic for finding PDFs in HTML pages
        try:
            resp = self.session.get(url, timeout=10)
            soup = BeautifulSoup(resp.text, "html.parser")

            pdfs = []
            for link in soup.find_all("a", href=True):
                href = link["href"]
                if ".pdf" in href.lower() or "View.ashx" in href:
                    pdfs.append(urljoin(url, href))

            return pdfs
        except Exception as e:
            logger.warning(f"PDF discovery failed for {url}: {e}")
            return []
```

**Vendor adapters become thin:**
```python
class PrimeGovAdapter(BaseAdapter):
    """PrimeGov adapter - only vendor-specific logic"""

    def __init__(self, city_slug: str):
        super().__init__(city_slug, vendor="primegov")
        self.base_url = f"https://{city_slug}.primegov.com"

    def fetch_meetings(self) -> List[RawMeeting]:
        """Fetch meetings from PrimeGov API"""
        resp = self.session.get(
            f"{self.base_url}/api/v2/PublicPortal/ListUpcomingMeetings",
            timeout=30
        )
        resp.raise_for_status()
        meetings = resp.json()

        results = []
        for mtg in meetings:
            # Find packet document
            packet = next(
                (doc for doc in mtg["documentList"]
                 if "Packet" in doc["templateName"]),
                None
            )

            results.append(RawMeeting(
                meeting_id=str(mtg["id"]),
                title=mtg.get("title", ""),
                date=self._parse_date(mtg.get("dateTime")),
                packet_url=self._build_packet_url(packet) if packet else None
            ))

        return results

    def _build_packet_url(self, doc: dict) -> str:
        """PrimeGov-specific packet URL construction"""
        params = urlencode({
            "meetingTemplateId": doc["templateId"],
            "compileOutputType": doc["compileOutputType"]
        })
        return f"{self.base_url}/Public/CompiledDocument?{params}"
```

**Result: Each adapter is ~50-100 lines, not 200-300.**

### Simplified Processing Pipeline

**Kill Tier 2 (Mistral OCR) - marginal value, high complexity:**
```python
class PDFProcessor:
    """Two-tier processing: fast text extraction OR Gemini PDF API"""

    def __init__(self, gemini_api_key: str):
        self.gemini_client = genai.Client(api_key=gemini_api_key)
        self.cache = ProcessingCache()

    def process_pdf(self, url: str) -> ProcessingResult:
        """Process PDF with two-tier fallback"""

        # Check cache first
        cached = self.cache.get(url)
        if cached:
            return cached

        # Tier 1: Fast text extraction (PyPDF2)
        # Success rate: 60%, Cost: $0.00, Time: ~2s
        text = self._extract_text_fast(url)
        if text and self._is_good_quality(text):
            summary = self._summarize_text(text)
            result = ProcessingResult(
                summary=summary,
                method="tier1_fast",
                cost_estimate=0.0001  # Gemini Flash on text is cheap
            )
            self.cache.store(url, result)
            return result

        # Tier 3: Gemini PDF API (fallback for scanned/complex PDFs)
        # Success rate: 95%, Cost: $0.01-0.05, Time: ~15s
        summary = self._process_with_gemini_pdf(url)
        result = ProcessingResult(
            summary=summary,
            method="tier3_gemini_pdf",
            cost_estimate=0.03
        )
        self.cache.store(url, result)
        return result

    def _extract_text_fast(self, url: str) -> Optional[str]:
        """Tier 1: PyPDF2 extraction"""
        pdf_bytes = self._download_pdf(url)
        if not pdf_bytes:
            return None

        with tempfile.NamedTemporaryFile(suffix=".pdf") as tmp:
            tmp.write(pdf_bytes)
            tmp.flush()

            reader = PdfReader(tmp.name)
            pages = [page.extract_text() for page in reader.pages[:100]]
            return "\n".join(pages)

    def _is_good_quality(self, text: str) -> bool:
        """Quality check: letter ratio, word count, recognizable words"""
        if len(text) < 100:
            return False

        # Letter ratio check
        letters = sum(1 for c in text if c.isalpha())
        if letters / len(text) < 0.3:
            return False

        # Word count check
        words = text.split()
        if len(words) < 20:
            return False

        return True

    def _summarize_text(self, text: str) -> str:
        """Summarize extracted text with Gemini"""
        # Use Flash-Lite for < 200K chars, Flash otherwise
        model = (
            "gemini-2.5-flash-lite"
            if len(text) < 200000
            else "gemini-2.5-flash"
        )

        response = self.gemini_client.models.generate_content(
            model=model,
            contents=self._get_prompt() + f"\n\n{text}",
            config=types.GenerateContentConfig(
                temperature=0.3,
                max_output_tokens=8192
            )
        )

        return response.text

    def _process_with_gemini_pdf(self, url: str) -> str:
        """Tier 3: Direct PDF processing with Gemini"""
        pdf_bytes = self._download_pdf(url)

        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
            tmp.write(pdf_bytes)
            tmp_path = tmp.name

        try:
            # Upload to Gemini
            uploaded = self.gemini_client.files.upload(file=tmp_path)

            # Process with Flash (better quality for PDFs)
            response = self.gemini_client.models.generate_content(
                model="gemini-2.5-flash",
                contents=[uploaded, self._get_prompt()],
                config=types.GenerateContentConfig(
                    temperature=0.3,
                    max_output_tokens=8192
                )
            )

            return response.text
        finally:
            os.remove(tmp_path)
```

**Result: Processing complexity cut by 50%, no marginal Mistral tier.**

### Background Processing: Job Queue Instead of Thread Soup

**Replace daemon threads with work queue:**
```python
from queue import Queue, Empty
from dataclasses import dataclass
from enum import Enum

class JobType(Enum):
    SYNC_CITY = "sync_city"
    PROCESS_SUMMARY = "process_summary"

@dataclass
class Job:
    type: JobType
    city_banana: Optional[str] = None
    meeting_id: Optional[str] = None
    priority: int = 0  # Higher = more important
    created_at: datetime = None

class BackgroundWorker:
    """Simple work queue for background processing"""

    def __init__(self, db: UnifiedDatabase, processor: PDFProcessor):
        self.db = db
        self.processor = processor
        self.queue = Queue()
        self.workers = []
        self.is_running = False
        self.rate_limiter = VendorRateLimiter()

    def start(self, num_workers: int = 2):
        """Start worker threads"""
        self.is_running = True

        for i in range(num_workers):
            worker = threading.Thread(
                target=self._worker_loop,
                name=f"worker-{i}",
                daemon=True
            )
            worker.start()
            self.workers.append(worker)

        # Start scheduler thread (enqueues jobs periodically)
        scheduler = threading.Thread(
            target=self._scheduler_loop,
            daemon=True
        )
        scheduler.start()

        logger.info(f"Started {num_workers} background workers")

    def stop(self):
        """Stop all workers gracefully"""
        self.is_running = False
        for worker in self.workers:
            worker.join(timeout=30)

    def enqueue_city_sync(self, city_banana: str, priority: int = 0):
        """Add city sync job to queue"""
        job = Job(
            type=JobType.SYNC_CITY,
            city_banana=city_banana,
            priority=priority,
            created_at=datetime.now()
        )
        self.queue.put((priority, job))

    def enqueue_summary(self, meeting_id: str, priority: int = 0):
        """Add summary processing job to queue"""
        job = Job(
            type=JobType.PROCESS_SUMMARY,
            meeting_id=meeting_id,
            priority=priority,
            created_at=datetime.now()
        )
        self.queue.put((priority, job))

    def _worker_loop(self):
        """Worker thread: processes jobs from queue"""
        while self.is_running:
            try:
                # Get job with timeout
                priority, job = self.queue.get(timeout=5)

                # Process job
                if job.type == JobType.SYNC_CITY:
                    self._sync_city(job.city_banana)
                elif job.type == JobType.PROCESS_SUMMARY:
                    self._process_summary(job.meeting_id)

                self.queue.task_done()

            except Empty:
                continue
            except Exception as e:
                logger.error(f"Worker error: {e}")

    def _scheduler_loop(self):
        """Scheduler thread: enqueues periodic jobs"""
        while self.is_running:
            try:
                # Every 7 days: sync all cities
                if self._should_run_full_sync():
                    self._schedule_full_sync()

                # Every 2 days: process unprocessed summaries
                if self._should_process_summaries():
                    self._schedule_summary_processing()

                # Sleep for 1 hour between checks
                time.sleep(3600)

            except Exception as e:
                logger.error(f"Scheduler error: {e}")

    def _sync_city(self, city_banana: str):
        """Sync a single city"""
        city = self.db.get_city(banana=city_banana)
        if not city:
            logger.error(f"City not found: {city_banana}")
            return

        # Rate limiting per vendor
        self.rate_limiter.wait_if_needed(city.vendor)

        # Get adapter for vendor
        adapter = self._get_adapter(city)

        # Fetch meetings
        meetings = adapter.fetch_meetings()

        # Store in database
        for meeting in meetings:
            meeting.city_banana = city_banana
            self.db.store_meeting(meeting)

            # Enqueue summary processing if packet exists
            if meeting.packet_url:
                self.enqueue_summary(meeting.id, priority=1)

        logger.info(f"Synced {len(meetings)} meetings for {city_banana}")

    def _process_summary(self, meeting_id: str):
        """Process a single meeting summary"""
        meeting = self.db.get_meeting(id=meeting_id)
        if not meeting or not meeting.packet_url:
            return

        # Check if already processed
        if meeting.summary:
            logger.debug(f"Meeting {meeting_id} already has summary")
            return

        # Process PDF
        result = self.processor.process_pdf(meeting.packet_url)

        # Update database
        meeting.summary = result.summary
        meeting.processing_status = ProcessingStatus.COMPLETED
        self.db.update_meeting(meeting)

        logger.info(f"Processed summary for {meeting_id} using {result.method}")
```

**Result: Clear separation, easy to prioritize, testable.**

## Multi-Tenancy Design

### Tenant Data Model

```python
class Tenant:
    """B2B customer with coverage and tracking preferences"""
    id: str
    name: str
    api_key: str  # For authentication
    coverage_cities: List[str]  # city_bananas they care about
    topic_keywords: List[str]  # Topics to highlight
    webhook_url: Optional[str]  # For notifications
    created_at: datetime

class TrackedItem:
    """Something a tenant wants to follow over time"""
    id: str
    tenant_id: str
    item_type: str  # "ordinance", "project", "proposal", "budget_item"
    title: str
    description: str
    city_banana: str
    first_mentioned_meeting_id: str
    first_seen: datetime
    last_seen: datetime
    status: str  # "active", "passed", "rejected", "tabled"
    meeting_references: List[str]  # All meetings that mention this

class Alert:
    """Tenant notification for tracked item activity"""
    id: str
    tenant_id: str
    tracked_item_id: str
    trigger: str  # "keyword_match", "status_change", "new_meeting"
    message: str
    created_at: datetime
    sent_at: Optional[datetime]
```

### Database Schema

```sql
-- Tenants table
CREATE TABLE tenants (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    api_key TEXT UNIQUE NOT NULL,
    webhook_url TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Tenant coverage (which cities they track)
CREATE TABLE tenant_coverage (
    tenant_id TEXT NOT NULL,
    city_banana TEXT NOT NULL,
    added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (tenant_id) REFERENCES tenants(id) ON DELETE CASCADE,
    PRIMARY KEY (tenant_id, city_banana)
);

-- Tenant keywords (topics they care about)
CREATE TABLE tenant_keywords (
    tenant_id TEXT NOT NULL,
    keyword TEXT NOT NULL,
    added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (tenant_id) REFERENCES tenants(id) ON DELETE CASCADE,
    PRIMARY KEY (tenant_id, keyword)
);

-- Tracked items (ordinances, proposals, etc.)
CREATE TABLE tracked_items (
    id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    item_type TEXT NOT NULL,
    title TEXT NOT NULL,
    description TEXT,
    city_banana TEXT NOT NULL,
    first_mentioned_meeting_id TEXT,
    first_seen TIMESTAMP,
    last_seen TIMESTAMP,
    status TEXT DEFAULT 'active',
    metadata JSON,  -- Flexible storage for item-specific data
    FOREIGN KEY (tenant_id) REFERENCES tenants(id) ON DELETE CASCADE
);

-- Meeting references for tracked items
CREATE TABLE tracked_item_meetings (
    tracked_item_id TEXT NOT NULL,
    meeting_id TEXT NOT NULL,
    mentioned_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    excerpt TEXT,  -- Relevant quote from summary
    FOREIGN KEY (tracked_item_id) REFERENCES tracked_items(id) ON DELETE CASCADE,
    PRIMARY KEY (tracked_item_id, meeting_id)
);

-- Alerts for tenants
CREATE TABLE alerts (
    id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    tracked_item_id TEXT,
    trigger_type TEXT NOT NULL,
    message TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    sent_at TIMESTAMP,
    FOREIGN KEY (tenant_id) REFERENCES tenants(id) ON DELETE CASCADE,
    FOREIGN KEY (tracked_item_id) REFERENCES tracked_items(id) ON DELETE SET NULL
);

-- Indices for performance
CREATE INDEX idx_tenant_coverage_banana ON tenant_coverage(city_banana);
CREATE INDEX idx_tracked_items_tenant ON tracked_items(tenant_id);
CREATE INDEX idx_tracked_items_city ON tracked_items(city_banana);
CREATE INDEX idx_tracked_items_status ON tracked_items(status);
CREATE INDEX idx_alerts_tenant ON alerts(tenant_id);
CREATE INDEX idx_alerts_unsent ON alerts(sent_at) WHERE sent_at IS NULL;
```

### Tenant API Endpoints

```python
# Authentication
@app.get("/api/tenant/meetings")
async def get_tenant_meetings(
    api_key: str = Header(...),
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    topic_filter: Optional[str] = None
):
    """Get meetings for tenant's coverage area"""
    tenant = db.get_tenant_by_api_key(api_key)
    if not tenant:
        raise HTTPException(status_code=401, detail="Invalid API key")

    # Get meetings for tenant's cities
    meetings = db.get_meetings(
        city_bananas=tenant.coverage_cities,
        start_date=start_date,
        end_date=end_date
    )

    # Filter by topics if requested
    if topic_filter:
        meetings = filter_by_keywords(meetings, tenant.topic_keywords)

    return {
        "tenant": tenant.name,
        "coverage_cities": len(tenant.coverage_cities),
        "meetings": meetings
    }

@app.post("/api/tenant/track")
async def track_item(
    api_key: str = Header(...),
    item: TrackedItemCreate
):
    """Start tracking an ordinance, proposal, etc."""
    tenant = db.get_tenant_by_api_key(api_key)
    if not tenant:
        raise HTTPException(status_code=401, detail="Invalid API key")

    # Verify city is in tenant's coverage
    if item.city_banana not in tenant.coverage_cities:
        raise HTTPException(
            status_code=403,
            detail="City not in your coverage area"
        )

    # Create tracked item
    tracked = db.create_tracked_item(
        tenant_id=tenant.id,
        item=item
    )

    return tracked

@app.get("/api/tenant/tracked/{item_id}/history")
async def get_tracked_item_history(
    api_key: str = Header(...),
    item_id: str
):
    """Get all meetings where a tracked item was mentioned"""
    tenant = db.get_tenant_by_api_key(api_key)
    if not tenant:
        raise HTTPException(status_code=401, detail="Invalid API key")

    tracked = db.get_tracked_item(item_id)
    if not tracked or tracked.tenant_id != tenant.id:
        raise HTTPException(status_code=404, detail="Tracked item not found")

    # Get all meeting references
    meetings = db.get_meetings_for_tracked_item(item_id)

    return {
        "tracked_item": tracked,
        "meeting_history": meetings,
        "timeline": build_timeline(meetings)
    }
```

### Intelligence Layer: Topic Extraction

```python
class TopicExtractor:
    """Extract topics and tracked items from meeting summaries"""

    def __init__(self, gemini_client):
        self.client = gemini_client

    def extract_topics(self, summary: str) -> List[str]:
        """Extract main topics from a meeting summary"""
        prompt = f"""Extract the main topics discussed in this meeting.
        Return as a JSON array of topics (e.g., ["housing", "zoning", "budget"]).

        Summary:
        {summary}
        """

        response = self.client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt,
            config=types.GenerateContentConfig(
                temperature=0.1,
                response_mime_type="application/json"
            )
        )

        return json.loads(response.text)

    def match_tracked_items(
        self,
        summary: str,
        tenant: Tenant
    ) -> List[TrackedItemMatch]:
        """Find mentions of tenant's tracked items in summary"""
        matches = []

        for tracked in tenant.tracked_items:
            # Simple keyword matching first
            if tracked.title.lower() in summary.lower():
                # Extract relevant context
                excerpt = self._extract_context(summary, tracked.title)

                # Use LLM to determine if this is actually the same item
                is_match = self._verify_match(summary, tracked, excerpt)

                if is_match:
                    matches.append(TrackedItemMatch(
                        tracked_item_id=tracked.id,
                        excerpt=excerpt,
                        confidence=0.9
                    ))

        return matches

    def _verify_match(
        self,
        summary: str,
        tracked: TrackedItem,
        excerpt: str
    ) -> bool:
        """Use LLM to verify if excerpt actually refers to tracked item"""
        prompt = f"""Is this excerpt referring to the tracked item?

        Tracked Item: {tracked.title}
        Description: {tracked.description}

        Excerpt from meeting:
        {excerpt}

        Answer with just "yes" or "no".
        """

        response = self.client.models.generate_content(
            model="gemini-2.5-flash-lite",
            contents=prompt,
            config=types.GenerateContentConfig(temperature=0.1)
        )

        return "yes" in response.text.lower()
```

## Phase-by-Phase Implementation

### Phase 1: Database Consolidation (Week 1) ✅ COMPLETE
**Goal: Merge 3 databases, unify lookup methods, eliminate all backwards compatibility**

Tasks:
- [x] Create unified schema with cities, meetings, tenants
- [x] Write migration script from old 3-DB structure
- [x] Implement `UnifiedDatabase` class with single `get_city()` method
- [x] Update all callsites to use new unified interface
- [x] Update config.py to use single UNIFIED_DB_PATH
- [x] DatabaseManager now direct alias to UnifiedDatabase
- [x] Run migration script on production (SUCCESS)
- [x] Remove old database module files (analytics_db.py, base_db.py, locations_db.py, meetings_db.py)
- [x] Remove all backwards compatibility wrappers
- [x] Update API to use clean dataclass interface directly

Success criteria:
- ✅ Single SQLite database file (engagic.db) - 2.8MB
- ✅ All city lookups go through one method (get_city())
- ✅ No duplicate query logic
- ✅ Migration validated: 827 cities, 2079 meetings (473 duplicates removed)
- ✅ Zero backwards compatibility code
- ✅ Clean dataclass interfaces (City, Meeting)

**Completed 2025-10-23**
- Created unified_db.py (622 lines) replaces 4 files (1400+ lines)
- Migration successful: 827 cities, 2079 meetings, 2355 zipcode mappings
- **Code reduction: 52%** in database layer (1400 → 672 total lines)
- Updated: processor.py, background_processor.py, api/main.py, config.py
- Removed: analytics_db.py, base_db.py, locations_db.py, meetings_db.py
- Zero backwards compatibility wrappers (no legacy method aliases)
- All API endpoints updated to use City/Meeting dataclasses directly
- Services tested and running in production

### Phase 2: Adapter Refactor (Week 2) ✅ COMPLETE

**Goal: Extract base class, slim down vendor adapters**

Tasks:
- [x] Create `BaseAdapter` with shared HTTP, date parsing, PDF discovery (280 lines)
- [x] Refactor PrimeGov adapter to extend BaseAdapter (74 lines)
- [x] Refactor remaining 5 adapters to extend BaseAdapter
- [x] Discovered Legistar Web API (replaced 256 lines of HTML scraping with 78-line API adapter)
- [x] Updated background_processor.py to support all 6 vendors
- [x] Removed 339 lines of duplicate code (1427 → 1088 lines)

Success criteria:
- ✓ API-based adapters: 70-80 lines each (PrimeGov, CivicClerk, Legistar)
- ✓ HTML scrapers: 200-250 lines each (Granicus, NovusAgenda, CivicPlus)
- ✓ Shared utilities in BaseAdapter
- ✓ All adapters implement same interface (fetch_meetings() → Iterator[Dict])
- ⚠ Rate limiting still in background_processor (can move to adapter layer in future iteration)

Key win: Legistar API discovery saved 178 lines vs old HTML scraping approach

### Phase 3: Processing Simplification (Week 3)
**Goal: Kill Tier 2, streamline Tier 1/3**

Tasks:
- [ ] Remove all Mistral OCR code and dependencies
- [ ] Implement new `PDFProcessor` with 2-tier logic
- [ ] Add quality heuristics for tier 1 success prediction
- [ ] Implement circuit breaker for consistently failing URLs
- [ ] Add processing result caching
- [ ] Update background processor to use new interface

Success criteria:
- Processing code reduced by 40%
- No Mistral API calls
- Tier 1 success rate measured and logged
- Circuit breaker prevents repeated failures

### Phase 4: Background Worker Queue (Week 4)
**Goal: Replace thread soup with job queue**

Tasks:
- [ ] Implement `BackgroundWorker` with job queue
- [ ] Create `Job` types: SYNC_CITY, PROCESS_SUMMARY
- [ ] Add priority queue support for high-value cities
- [ ] Implement scheduler thread for periodic job enqueueing
- [ ] Add graceful shutdown handling
- [ ] Remove old daemon thread code

Success criteria:
- Jobs processed from queue, not polled
- Priority queue allows urgent processing
- Clean shutdown without job loss
- Status tracking doesn't grow unbounded

### Phase 5: Multi-Tenancy Foundation (Week 5)
**Goal: Add tenant tables, basic API**

Tasks:
- [ ] Create tenant tables in database
- [ ] Implement tenant CRUD operations
- [ ] Add tenant API key authentication
- [ ] Create `/api/tenant/meetings` endpoint
- [ ] Add coverage filtering (city_banana lists)
- [ ] Implement basic topic keyword matching

Success criteria:
- Tenants can register and get API keys
- Tenant API returns only their coverage cities
- Keyword filtering works on summaries
- API key authentication enforced

### Phase 6: Intelligence Layer (Week 6)
**Goal: Topic extraction, tracked items**

Tasks:
- [ ] Implement `TopicExtractor` using Gemini
- [ ] Create tracked item database schema
- [ ] Add `/api/tenant/track` endpoint
- [ ] Implement tracked item history tracking
- [ ] Add alert generation for tracked item updates
- [ ] Build timeline view for ordinance progression

Success criteria:
- Topics automatically extracted from summaries
- Tenants can track ordinances across meetings
- Alerts generated when tracked items appear
- Timeline shows ordinance evolution

## Rust Migration Evaluation

### Good Candidates for Rust

**1. PDF Text Extraction**
```rust
// Using pdf-extract crate - faster than PyPDF2
use pdf_extract::extract_text;

fn extract_text_fast(pdf_path: &Path) -> Result<String, Error> {
    extract_text(pdf_path)
}

// Benchmark: 3-5x faster than PyPDF2
```

**2. Background Worker**
```rust
// Tokio + async HTTP would be cleaner
use tokio;
use reqwest;

#[tokio::main]
async fn sync_city(city: City) -> Result<Vec<Meeting>, Error> {
    let adapter = get_adapter(&city);
    adapter.fetch_meetings().await
}

// Benefits: True async/await, no GIL issues
```

**3. Database Layer**
```rust
// SQLx provides compile-time query checking
use sqlx::{SqlitePool, query_as};

async fn get_city(pool: &SqlitePool, banana: &str) -> Option<City> {
    query_as!(
        City,
        "SELECT * FROM cities WHERE city_banana = ?",
        banana
    )
    .fetch_optional(pool)
    .await
    .ok()
    .flatten()
}

// Benefits: Compile-time SQL validation, no runtime query errors
```

### Keep in Python

**1. Gemini API Integration**
- Official SDK is Python
- Frequent API changes
- Prototyping benefits outweigh performance gains

**2. Web Scraping (BeautifulSoup)**
- Mature ecosystem in Python
- Frequent vendor website changes
- Fast iteration more valuable than performance

**3. FastAPI endpoints**
- Excellent Python ecosystem
- Easy to modify for customer feedback
- Performance not bottleneck (cache-first architecture)

### Hybrid Approach

```
Python:
- FastAPI web server
- Gemini summarization
- Adapter implementations (frequent changes)

Rust (via PyO3):
- PDF text extraction (performance critical)
- Background worker queue (concurrency benefits)
- Database layer (type safety benefits)

Communication:
- Python calls Rust via PyO3 bindings
- Shared SQLite database
- Message queue for jobs (Redis/SQLite)
```

### Migration Timeline

**Phase 1 (Immediate): Stay in Python**
- Complete refactor first
- Measure actual bottlenecks
- Establish benchmarks

**Phase 2 (Month 3-4): Evaluate Rust**
- If PDF processing is bottleneck: Rust PDF extraction
- If background sync is bottleneck: Rust worker with Tokio
- Only migrate what's proven slow

**Phase 3 (Month 6+): Consider Full Rewrite**
- Only if B2B scaling requires it
- By then, requirements are clearer
- Python refactor provides clean API contract

## Success Metrics

### Code Quality
- [ ] Total lines of Python: < 3000 (currently ~7000)
- [ ] Adapter average size: < 100 lines (currently ~200)
- [ ] Database lookup methods: 1 (currently 4+)
- [ ] Processing tiers: 2 (currently 3)
- [ ] Cyclomatic complexity: < 15 per function

### Performance
- [ ] Tier 1 success rate: > 65% (currently ~60%)
- [ ] Average processing time: < 8s (currently ~12s)
- [ ] API response time: < 50ms (currently ~80ms)
- [ ] Background sync time: < 2 hours for 500 cities

### B2B Readiness
- [ ] Tenant isolation: complete
- [ ] Topic extraction: > 85% accuracy
- [ ] Tracked item matching: > 90% accuracy
- [ ] API authentication: enforced
- [ ] Webhook delivery: < 5s latency

### Cost Efficiency
- [ ] Average cost per summary: < $0.01
- [ ] Tier 1 usage: > 60% of documents
- [ ] Cache hit rate: > 80%
- [ ] Processing retries: < 5%

## Risk Mitigation

### Data Loss Risk
- **Mitigation**: Run migrations on backup first, keep old DB for 30 days
- **Rollback**: Old code available in `legacy/` branch

### API Compatibility Risk
- **Mitigation**: Keep old endpoints, add `/v2/` prefix for new
- **Timeline**: Deprecate old endpoints after 90 days

### Performance Regression Risk
- **Mitigation**: Benchmark before/after each phase
- **Rollback trigger**: > 20% performance degradation

### Customer Impact Risk
- **Mitigation**: Refactor during low-traffic period, staged rollout
- **Communication**: Status page with refactor progress

## Timeline Summary

```
Week 1: Database Consolidation
Week 2: Adapter Refactor
Week 3: Processing Simplification
Week 4: Background Worker Queue
Week 5: Multi-Tenancy Foundation
Week 6: Intelligence Layer

Total: 6 weeks for complete refactor
```

## Conclusion

This refactor will:
1. Cut codebase size by 60%
2. Eliminate abstraction sprawl
3. Prepare for B2B multi-tenancy
4. Maintain performance while reducing complexity
5. Position for Rust migration if needed

The key insight: **Less code, clearer boundaries, composable pieces.**

Next step: Get approval, create dev branch, start Phase 1.
