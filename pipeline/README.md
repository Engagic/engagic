# Pipeline - Orchestration & Processing

Orchestrates data flow from vendor fetching to LLM analysis to database storage.

---

## Structure

```
pipeline/
  conductor.py      # Daemon lifecycle, CLI entry point
  fetcher.py        # City sync, vendor routing
  processor.py      # Queue processing, item assembly
  models.py         # Job type definitions
  utils.py          # Matter-first utilities
  admin.py          # Debug commands
  click_types.py    # CLI validation

  protocols/        # Dependency injection interfaces
  filters/          # Processing decision logic (from vendors/)
  orchestrators/    # Business logic (from database/)
  workers/          # Focused processing components (from processor.py)
```

See READMEs in subdirectories for details on `protocols/`, `filters/`, `orchestrators/`, `workers/`.

---

## Architecture

```
Conductor
  ├─> Fetcher    (city sync, rate limiting)
  └─> Processor  (queue processing)
           │
           ├─> orchestrators/  (business logic)
           ├─> filters/        (skip decisions)
           └─> workers/        (focused tasks)
```

**Key patterns:**
- Conductor delegates to Fetcher and Processor
- Processor uses orchestrators for business logic
- Database delegates decisions to orchestrators
- Metrics injected via Protocol (no server dependency)

---

## Module Reference

### 1. `conductor.py` - Orchestration (851 lines)

**Entry point for all pipeline operations.** Coordinates sync and processing loops.

#### Responsibilities
- Start/stop background daemon (async tasks)
- Sync loop (runs every 72 hours)
- Processing loop (continuously processes queue)
- Admin commands (force sync, status, preview)
- Global state management (graceful shutdown)

#### Key Methods

```python
conductor = Conductor(db=database_instance)

# Background daemon (production)
await conductor.start()  # Starts sync + processing tasks
conductor.stop()         # Graceful shutdown (sets stop flag)

# Single city operations (admin/testing) - via CLI only
# conductor.force_sync_city("paloaltoCA")
# conductor.sync_and_process_city("paloaltoCA")

# Preview and debugging - via CLI only
# conductor.preview_queue(city_banana="paloaltoCA", limit=10)
# conductor.extract_text_preview(meeting_id, output_file="text.txt")
# conductor.preview_items(meeting_id, extract_text=True)
```

#### CLI Usage

```bash
# Background daemon (continuous sync + processing)
engagic-daemon

# Fetcher only (sync without processing)
engagic-daemon --fetcher

# Admin operations
engagic-daemon --sync-city paloaltoCA
engagic-daemon --sync-and-process-city paloaltoCA
engagic-daemon --preview-queue paloaltoCA
engagic-daemon --status
```

#### Async Architecture
- **Single event loop:** Uses `asyncio` with concurrent tasks
- **Sync task:** Runs `_sync_loop()` every 72 hours (calls `fetcher.sync_all()`)
- **Processing task:** Runs `_processing_loop()` continuously (calls `processor.process_queue()`)
- **Graceful shutdown:** Tasks check stop flag and clean up on SIGTERM/SIGINT

---

### 2. `fetcher.py` - City Sync & Vendor Routing (535 lines)

**Fetches meetings from vendor platforms.** Handles rate limiting, retry logic, and database storage.

#### Responsibilities
- Sync all cities (vendor-grouped, rate-limited)
- Adaptive sync scheduling (high activity = more frequent)
- Vendor-aware rate limiting (3-5s delays)
- Meeting + item storage via `db.store_meeting_from_sync()`
- Matter tracking (Matters-First architecture)
- Failed city tracking

#### Key Methods

```python
fetcher = Fetcher(db=unified_db)

# Sync all active cities (vendor-grouped, rate-limited)
results: List[SyncResult] = fetcher.sync_all()

# Sync specific cities
results = await fetcher.sync_cities(["paloaltoCA", "oaklandCA"])

# Single city sync
result: SyncResult = fetcher.sync_city("paloaltoCA")
```

#### SyncResult Object

```python
@dataclass
class SyncResult:
    city_banana: str
    status: SyncStatus  # COMPLETED, FAILED, SKIPPED
    meetings_found: int = 0
    meetings_processed: int = 0
    duration_seconds: float = 0.0
    error_message: Optional[str] = None
```

#### Sync Flow

1. **Group cities by vendor** (primegov, legistar, granicus, etc.)
2. **Prioritize by activity** (high activity cities first)
3. **Check sync schedule** (`_should_sync_city()` - adaptive intervals)
4. **Apply rate limiting** (`RateLimiter.wait_if_needed(vendor)`)
5. **Fetch meetings** (`adapter.fetch_meetings()`)
6. **Store in database** (`db.store_meeting_from_sync()`)
   - Creates Meeting + AgendaItem objects
   - Validates meeting data
   - Tracks matters (city_matters + matter_appearances)
   - Enqueues for processing (matters-first or item-level)
7. **Track failures** (`failed_cities` set)

#### Adaptive Sync Scheduling

```python
# High activity (2+ meetings/week): Sync every 12 hours
# Medium activity (1+ meeting/week): Sync every 24 hours
# Low activity (some meetings): Sync every 7 days
# Very low activity (no recent meetings): Sync every 7 days
```

#### Vendor Rate Limiting

- **3-5 second delay** between requests to same vendor
- **30-40 second break** between vendor groups
- **Polite crawling** to avoid overloading civic tech platforms

---

### 3. `processor.py` - Queue Processing & Item Assembly (1350 lines)

**Processes jobs from the queue.** Extracts text from PDFs, assembles items, orchestrates LLM analysis.

#### Responsibilities
- Process queue continuously (`process_queue()`)
- Extract text from PDFs (via `Analyzer.pdf_extractor`)
- Filter procedural items and public comments
- Document-level caching (deduplication within meeting)
- Batch item processing (50% cost savings)
- Topic normalization and aggregation
- Incremental saving (per-chunk)

#### Key Methods

```python
processor = Processor(db=unified_db, analyzer=analyzer)

# Continuous queue processing (production)
processor.process_queue()

# Process specific city (admin/testing)
stats = processor.process_city_jobs("paloaltoCA")
# Returns: {"processed_count": 5, "failed_count": 1}

# Process single meeting (internal)
processor.process_meeting(meeting)  # Agenda-first: items > packet
```

#### Processing Paths

**Path 1: Item-Level Processing (PRIMARY - 58% of cities)**
```
Meeting has agenda_items
  ├─ Filter procedural items (minutes, roll call, etc.)
  ├─ Build document cache (meeting-level, shared URLs)
  │   └─ Extract each unique PDF once (not per-item)
  ├─ Separate shared vs item-specific documents
  ├─ Build batch requests (item-specific text only)
  ├─ Process via Analyzer.process_batch_items()
  │   └─ Gemini Batch API (50% cost savings)
  │   └─ Generator yields chunks as they complete
  ├─ Normalize topics (via TopicNormalizer)
  ├─ Save incrementally (per-chunk, not end-of-batch)
  ├─ Aggregate topics to meeting level
  └─ Update meeting metadata (topics, participation)
```

**Path 2: Monolithic Processing (FALLBACK - 42% of cities)**
```
Meeting has packet_url (no items)
  ├─ Extract full PDF text
  ├─ Meeting-level prompt (short/comprehensive)
  ├─ Single LLM call
  └─ Store meeting summary
```

**Path 3: Matters-First Processing (NEW - Nov 2025)**
```
Agenda item has matter_file/matter_id
  ├─ Check if matter already processed
  ├─ Compare attachment hash (changed?)
  │   ├─ If unchanged: Reuse canonical summary
  │   └─ If changed: Process and update canonical
  ├─ Process matter once (representative item)
  └─ Backfill all appearances with canonical summary
```

#### Document Caching (Item-Level Path)

**Problem:** Multiple items reference the same PDF → extract once, reuse many times.

**Solution:** Meeting-level document cache.

```python
# Example: Staff report shared across 3 agenda items
document_cache = {
    "staff_report.pdf": {
        "text": "...",
        "page_count": 45,
        "name": "staff_report.pdf"
    }
}

# Shared documents go in meeting context (cached once)
shared_context = "=== staff_report.pdf ===\n{text}"

# Item-specific documents go in item request
item_request = {
    "item_id": "item_123",
    "title": "Approve Contract",
    "text": "=== contract.pdf ===\n{text}",  # Item-specific only
    "page_count": 12
}
```

#### Two-Tier Filtering

**Adapter level - discard entirely (zero metadata value):**

```python
ADAPTER_SKIP_PATTERNS = [
    "roll call",
    "approval of minutes",
    "pledge of allegiance",
    "adjournment"
]
```

**Processor level - save but skip LLM (searchable metadata):**

```python
PROCESSOR_SKIP_PATTERNS = [
    "proclamation",
    "commendation",
    "appointment",
    "liquor license"
]
```

#### Incremental Saving

**Generator-based processing:** Save results immediately after each chunk completes.

```python
for chunk_results in analyzer.process_batch_items(batch_requests):
    # Save IMMEDIATELY (not at end of batch)
    for result in chunk_results:
        db.update_agenda_item(item_id, summary, topics)

    # If crash occurs, already-saved items are preserved
```

**Why this matters:** Gemini Batch API can take minutes. If crash occurs, we don't lose all work.

---

### 4. `models.py` - Job Type Definitions (155 lines)

**Type-safe job payload definitions.** Enables exhaustive type checking and safe dispatch.

#### Responsibilities
- Define job types (MeetingJob, MatterJob)
- Serialize/deserialize payloads to/from JSON
- Helper functions for job creation
- Database row to job object conversion

#### Job Types

```python
@dataclass
class MeetingJob:
    """Process a meeting (monolithic or item-level)"""
    meeting_id: str
    source_url: str  # agenda_url or packet_url

@dataclass
class MatterJob:
    """Process a matter across all its appearances (matters-first)"""
    matter_id: str  # Composite ID: {banana}_{matter_key}
    meeting_id: str  # Representative meeting where matter appears
    item_ids: List[str]  # All agenda item IDs for this matter

@dataclass
class QueueJob:
    """Typed queue job with discriminated union payload"""
    id: int
    job_type: JobType  # "meeting" | "matter"
    payload: JobPayload  # MeetingJob | MatterJob
    banana: str
    priority: int
    status: str
    retry_count: int = 0
    error_message: Optional[str] = None
    created_at: Optional[str] = None
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
```

#### Helper Functions

```python
# Create meeting job
job_data = create_meeting_job(
    meeting_id="paloaltoCA_2025-11-10",
    source_url="https://...",
    banana="paloaltoCA",
    priority=150
)

# Create matter job
job_data = create_matter_job(
    matter_id="sanfranciscoCA_251041",
    meeting_id="sanfranciscoCA_2025-11-10",
    item_ids=["item_1", "item_2", "item_3"],
    banana="sanfranciscoCA",
    priority=150
)

# Deserialize from database row
job = QueueJob.from_db_row(db_row)
```

#### Type Safety

**Discriminated union pattern:** `job_type` field determines which payload type is present.

```python
# Type-safe dispatch
if job.job_type == "meeting":
    assert isinstance(job.payload, MeetingJob)
    process_meeting(job.payload.meeting_id)
elif job.job_type == "matter":
    assert isinstance(job.payload, MatterJob)
    process_matter(job.payload.matter_id, job.payload.item_ids)
```

---

### 5. `utils.py` - Matter-First Utilities (216 lines)

**Utilities for matter-first processing.** Attachment hashing and matter key extraction.

#### Responsibilities
- Generate stable attachment hashes for deduplication
- Extract canonical matter keys from vendor data
- Support URL-only or metadata-enhanced hashing modes

#### Key Functions

```python
from pipeline.utils import hash_attachments, get_matter_key

# Hash attachments for deduplication (URL-only mode, fast)
attachments = [
    {"url": "https://city.gov/doc1.pdf", "name": "Staff Report"},
    {"url": "https://city.gov/doc2.pdf", "name": "Ordinance"}
]
hash_value = hash_attachments(attachments)  # SHA256 hex digest

# Hash with metadata (slower, more accurate)
hash_value = hash_attachments(attachments, include_metadata=True)
# Fetches Content-Length and Last-Modified headers via HEAD requests

# Extract canonical matter key (prefer semantic ID over UUID)
matter_key = get_matter_key(matter_file="25-1234", matter_id="uuid-abc")
# Returns: "25-1234" (semantic ID preferred)

matter_key = get_matter_key(matter_file=None, matter_id="uuid-abc")
# Returns: "uuid-abc" (fallback to UUID)
```

#### Attachment Hashing Strategy

**Two modes:**

1. **URL-only (default):** Fast, but misses CDN rotations
   ```python
   hash_attachments(attachments)
   # Hashes: [(url, name), (url, name), ...]
   ```

2. **Metadata-enhanced:** Slower, better change detection
   ```python
   hash_attachments(attachments, include_metadata=True)
   # Hashes: [(url, name, content_length, last_modified), ...]
   # Makes HEAD requests to get metadata
   ```

**Use case:** Detect when matter attachments have changed across appearances.

```python
# In processor.py (matters-first path)
attachment_hash = hash_attachments(item.attachments)

# Compare with stored hash
existing_matter = db.get_matter(matter_id)
if existing_matter and existing_matter.attachment_hash == attachment_hash:
    # Reuse canonical summary (no changes)
    reuse_canonical_summary()
else:
    # Re-process (attachments changed)
    process_matter_fresh()
```

#### Matter Key Strategy

**Problem:** Vendors use different identifiers for legislative matters.

- **Semantic IDs:** Public-facing (e.g., "BL2025-1098", "25-1234")
- **Backend UUIDs:** Internal tracking (e.g., "uuid-abc-123")

**Solution:** Prefer semantic ID over UUID.

```python
# Nashville (Legistar)
matter_file = "BL2025-1098"  # Public bill number
matter_id = "12345"  # Internal ID
get_matter_key(matter_file, matter_id)  # Returns: "BL2025-1098"

# San Francisco (Legistar)
matter_file = "251041"  # Public file number
matter_id = "uuid-..."  # Internal UUID
get_matter_key(matter_file, matter_id)  # Returns: "251041"

# Fallback (no semantic ID)
get_matter_key(None, "uuid-abc")  # Returns: "uuid-abc"
```

**Why this matters:** Matter keys are used as primary keys in `city_matters` table. Semantic IDs are more stable and user-friendly than UUIDs.

---

### 6. `admin.py` - Admin & Debug Utilities (201 lines)

**Debug utilities for manual inspection.** Not used in production daemon, only CLI commands.

#### Responsibilities
- Extract and preview text from meeting PDFs
- Preview agenda items with optional text extraction
- Support manual debugging workflows

#### Key Functions

```python
from pipeline.admin import extract_text_preview, preview_items

# Extract full text to file (for manual review)
extract_text_preview(
    db=db,
    meeting_id="paloaltoCA_2025-11-10",
    output_file="text.txt"
)

# Preview agenda items (with optional text extraction)
preview_items(
    db=db,
    meeting_id="paloaltoCA_2025-11-10",
    extract_text=True  # Also extract and display text
)
```

**CLI Usage:**
```bash
# Extract text to file
engagic-daemon --extract-text paloaltoCA_2025-11-10 --output-file debug.txt

# Preview items
engagic-daemon --preview-items paloaltoCA_2025-11-10
```

---

### 7. `click_types.py` - CLI Parameter Types (57 lines)

**Custom Click parameter types for CLI validation.**

#### Responsibilities
- Validate city_banana format
- Provide clear error messages for invalid inputs

#### BananaType Validator

```python
from pipeline.click_types import BananaType

# Used in CLI commands
@click.command()
@click.argument("city_banana", type=BananaType())
def sync_city(city_banana: str):
    """Sync a single city"""
    pass
```

**Validation:**
- Format: lowercase alphanumeric + uppercase 2-letter state code
- Examples: `paloaltoCA`, `nashvilleTN`, `stlouisMO`
- Invalid: `PaloAltoCA` (capital), `paloaltoca` (lowercase state), `paloalto` (missing state)

---

## Data Flow Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│ Conductor (Async Event Loop)                                    │
│  ├─ Sync Task (every 72 hours)                                  │
│  │   └─> Fetcher.sync_all()                                     │
│  │                                                               │
│  └─ Processing Task (continuous)                                │
│      └─> Processor.process_queue()                              │
└─────────────────────────────────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────────┐
│ Fetcher (City Sync)                                             │
│  ├─ Group cities by vendor                                      │
│  ├─ Prioritize by activity                                      │
│  ├─ Rate limit (3-5s delays)                                    │
│  ├─ Adapter.fetch_meetings()                                    │
│  └─ db.store_meeting_from_sync()                                │
│      ├─ Store Meeting + AgendaItem objects                      │
│      ├─ Track matters (city_matters + matter_appearances)       │
│      └─ Enqueue for processing (matters-first or item-level)    │
└─────────────────────────────────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────────┐
│ Processing Queue (PostgreSQL)                                   │
│  ├─ Priority-based (recent meetings first)                      │
│  ├─ Typed jobs (MeetingJob, MatterJob)                          │
│  ├─ Retry logic (3 attempts → DLQ)                              │
│  └─ Status tracking (pending, processing, completed, failed)    │
└─────────────────────────────────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────────┐
│ Processor (Queue Processing)                                    │
│  ├─ Get next job from queue                                     │
│  ├─ Dispatch by job type:                                       │
│  │   ├─ MeetingJob → process_meeting()                          │
│  │   └─ MatterJob → process_matter()                            │
│  │                                                               │
│  ├─ ITEM-LEVEL PATH (if meeting has items):                     │
│  │   ├─ Build document cache (shared URLs)                      │
│  │   ├─ Build batch requests (item-specific text)               │
│  │   ├─ Analyzer.process_batch_items() [generator]              │
│  │   ├─ Save incrementally (per-chunk)                          │
│  │   └─ Aggregate topics to meeting                             │
│  │                                                               │
│  ├─ MONOLITHIC PATH (if packet_url only):                       │
│  │   ├─ Analyzer.process_agenda(packet_url)                     │
│  │   └─ Store meeting summary                                   │
│  │                                                               │
│  └─ MATTERS-FIRST PATH (if matter_file/matter_id):              │
│      ├─ Check if matter already processed                       │
│      ├─ Compare attachment hash                                 │
│      ├─ Process matter once (representative item)               │
│      └─ Backfill all appearances with canonical summary         │
└─────────────────────────────────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────────┐
│ Analyzer (LLM Analysis)                                         │
│  ├─ PdfExtractor.extract_from_url()                             │
│  ├─ parse_participation_info()                                  │
│  ├─ GeminiSummarizer.summarize_meeting()                        │
│  └─ GeminiSummarizer.summarize_batch() [generator]              │
└─────────────────────────────────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────────┐
│ Database (UnifiedDatabase)                                      │
│  ├─ update_meeting_summary()                                    │
│  ├─ update_agenda_item()                                        │
│  ├─ update_matter_summary()                                     │
│  └─ mark_processing_complete()                                  │
└─────────────────────────────────────────────────────────────────┘
```

---

## Processing Queue Architecture

**Location:** `database/repositories/queue.py` (managed by `database/`)

**Schema:**
```sql
CREATE TABLE queue (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_type TEXT,  -- "meeting" or "matter"
    payload TEXT,   -- JSON payload (MeetingJob or MatterJob)
    source_url TEXT NOT NULL UNIQUE,
    meeting_id TEXT,
    banana TEXT,
    status TEXT DEFAULT 'pending',
    priority INTEGER DEFAULT 0,
    retry_count INTEGER DEFAULT 0,
    error_message TEXT,
    created_at TIMESTAMP,
    started_at TIMESTAMP,
    completed_at TIMESTAMP,
    failed_at TIMESTAMP
);
```

**Job Types:**

```python
# MeetingJob (item-level or monolithic)
{
    "job_type": "meeting",
    "payload": {
        "meeting_id": "sanfranciscoCA_2025-11-10",
        "source_url": "https://..."
    }
}

# MatterJob (matters-first)
{
    "job_type": "matter",
    "payload": {
        "matter_id": "sanfranciscoCA_251041",
        "meeting_id": "sanfranciscoCA_2025-11-10",
        "item_ids": ["item_1", "item_2"]
    }
}
```

**Status Flow:**
```
pending → processing → completed
                    └──> failed (retry < 3)
                    └──> dead_letter (retry >= 3)
```

**Priority Scoring:**
```python
# Recent meetings = high priority
# Today: 150, Yesterday: 149, 2 days ago: 148, etc.
priority = max(0, 150 - days_distance)
```

---

## Configuration

**Required Environment Variables:**
```bash
GEMINI_API_KEY=your_api_key_here
POSTGRES_HOST=localhost
POSTGRES_DB=engagic
POSTGRES_USER=engagic
POSTGRES_PASSWORD=***
```

**Optional:**
```bash
NYC_LEGISTAR_TOKEN=token_for_nyc_api  # NYC requires API token
ENGAGIC_LOG_LEVEL=INFO
```

---

## Common Operations

### Local Development (One-Off Sync)

```bash
# Sync single city
engagic-daemon --sync-city paloaltoCA

# Sync and process immediately
engagic-daemon --sync-and-process-city paloaltoCA

# Preview queue
engagic-daemon --preview-queue paloaltoCA

# Extract text for debugging
engagic-daemon --extract-text meeting_id --output-file text.txt
```

### Production Deployment (Background Daemon)

```bash
# Fetcher service (sync only, no processing)
engagic-daemon --fetcher

# Full daemon (sync + processing)
engagic-daemon
```

**Deployment:** VPS runs two systemd services:
1. **`engagic-fetcher.service`** - Syncs cities every 72 hours
2. **`engagic-processor.service`** - Processes queue continuously

---

## Error Handling & Retry Logic

### Sync Errors (Fetcher)

**Retry:** 2 attempts with exponential backoff (5s, 20s)
```python
# Attempt 1: Immediate
# Attempt 2: Wait 5s + jitter
# Attempt 3: Wait 20s + jitter
# If all fail: Add to failed_cities set
```

### Processing Errors (Processor)

**Retry:** 3 attempts with priority decay
```python
# Attempt 1: priority = 150 (recent meeting)
# Attempt 2: priority = 130 (drops by 20)
# Attempt 3: priority = 110 (drops by 40)
# If all fail: Move to dead_letter queue
```

**Non-retryable errors:**
- "Analyzer not available" (no API key)
- These are marked as `failed` without retry logic

---

## Performance Characteristics

- **Sync cycle:** ~2 hours for 500 cities (rate-limited)
- **Item processing:** 10-30s per item (Gemini latency)
- **Batch processing:** 50% cost savings over individual calls
- **Document caching:** Reduces API costs for shared attachments
- **Memory:** ~500MB for daemon (PDF extraction peak)
- **Incremental saving:** Prevents data loss on crashes

---

## Key Patterns

1. **Agenda-First:** Check for items before falling back to packet_url
2. **Matters-First:** Deduplicate summarization work across meetings
3. **Document Caching:** Extract shared PDFs once per meeting
4. **Incremental Saving:** Save results per-chunk, not end-of-batch
5. **Generator-Based:** Yield chunk results immediately (don't buffer)
6. **Fail-Fast:** Single processing tier (no fallback to premium)
7. **Procedural Filtering:** Skip low-value items to save costs

---

## Related Modules

- **`vendors/`** - Adapter implementations for civic tech platforms
- **`parsing/`** - PDF text extraction and participation parsing
- **`analysis/`** - LLM summarization and topic normalization (includes analyzer)
- **`database/`** - Repository Pattern for data persistence

**Note:** The `Analyzer` class lives in `analysis/analyzer_async.py`, not `pipeline/`. Processor imports and uses it.

---

**Last Updated:** 2025-12-03 (Updated all line counts: conductor 657→851, processor 1335→1350)
