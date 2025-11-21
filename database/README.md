# Database - Persistence & Repository Pattern

**Purpose:** Single source of truth for all Engagic data. Clean separation of concerns via Repository Pattern.

Manages:
- Cities and zipcodes
- Meetings and agenda items
- Matters (legislative tracking)
- Processing queue (typed jobs)
- Search, topics, and caching

---

## Architecture Overview

The database uses a **Repository Pattern** with a **facade** that delegates to focused repositories:

```
┌─────────────────────┐
│  UnifiedDatabase    │  Facade (775 lines)
│  (db.py)            │
└──────────┬──────────┘
           │
           ├──> repositories/base.py        (95 lines)  - Base repository class
           ├──> repositories/cities.py     (248 lines) - City and zipcode operations
           ├──> repositories/meetings.py   (234 lines) - Meeting storage and retrieval
           ├──> repositories/items.py      (196 lines) - Agenda item operations
           ├──> repositories/matters.py    (300 lines) - Matter operations (matters-first)
           ├──> repositories/queue.py      (578 lines) - Processing queue management
           └──> repositories/search.py     (231 lines) - Search, topics, cache, stats

Supporting Modules:
├── models.py          (393 lines) - Data models (City, Meeting, AgendaItem, Matter)
├── id_generation.py   (148 lines) - Deterministic matter ID generation (SHA256)
└── search_utils.py    (433 lines) - Search utilities (strip_markdown, search_summaries, search_matters)
```

**Why Repository Pattern?**
- **Separation of concerns:** Each repository handles one domain
- **Testability:** Mock repositories independently
- **Maintainability:** 200-line focused modules > 2,000-line monolith
- **Single database connection:** Shared across all repositories

---

## Quick Start

### Basic Usage

```python
from database.db import UnifiedDatabase

db = UnifiedDatabase("/path/to/engagic.db")

# City operations
city = db.get_city(banana="paloaltoCA")
cities = db.get_cities(state="CA", vendor="primegov")

# Meeting operations
meeting = db.get_meeting("sanfranciscoCA_2025-11-10")
meetings = db.get_meetings(bananas=["paloaltoCA"], limit=50)

# Agenda item operations
items = db.get_agenda_items("sanfranciscoCA_2025-11-10")
db.update_agenda_item(item_id, summary, topics)

# Queue operations
db.enqueue_meeting_job(meeting_id, source_url, banana, priority=150)
job = db.get_next_for_processing()
db.mark_processing_complete(job.id)

# Search operations
meetings = db.search_meetings_by_topic("housing", city_banana="paloaltoCA")
topics = db.get_popular_topics(limit=20)
stats = db.get_stats()
```

---

## Database Schema

### Core Tables

#### `cities` - City Registry
```sql
CREATE TABLE cities (
    banana TEXT PRIMARY KEY,           -- paloaltoCA (vendor-agnostic)
    name TEXT NOT NULL,                -- Palo Alto
    state TEXT NOT NULL,               -- CA
    vendor TEXT NOT NULL,              -- primegov, legistar, granicus
    slug TEXT NOT NULL,                -- cityofpaloalto (vendor-specific)
    county TEXT,                       -- Santa Clara
    status TEXT DEFAULT 'active',     -- active, inactive
    created_at TIMESTAMP,
    updated_at TIMESTAMP
);
```

#### `zipcodes` - City Zipcodes (Many-to-Many)
```sql
CREATE TABLE zipcodes (
    banana TEXT NOT NULL,
    zipcode TEXT NOT NULL,
    is_primary BOOLEAN DEFAULT FALSE,
    PRIMARY KEY (banana, zipcode),
    FOREIGN KEY (banana) REFERENCES cities(banana) ON DELETE CASCADE
);
```

#### `meetings` - Meeting Data
```sql
CREATE TABLE meetings (
    id TEXT PRIMARY KEY,               -- sanfranciscoCA_2025-11-10_board-of-supervisors
    banana TEXT NOT NULL,              -- sanfranciscoCA
    title TEXT NOT NULL,               -- Board of Supervisors - Regular Meeting
    date TIMESTAMP,                    -- 2025-11-10T14:00:00
    agenda_url TEXT,                   -- HTML agenda (item-based, primary)
    packet_url TEXT,                   -- PDF packet (monolithic, fallback)
    summary TEXT,                      -- LLM-generated summary (optional)
    participation TEXT,                -- JSON: {email, phone, virtual_url}
    status TEXT,                       -- cancelled, postponed, revised, or NULL
    topics TEXT,                       -- JSON: ["housing", "zoning", "budget"]
    processing_status TEXT DEFAULT 'pending',
    processing_method TEXT,            -- item_level_N_items, pymupdf_gemini
    processing_time REAL,              -- Seconds
    created_at TIMESTAMP,
    updated_at TIMESTAMP,
    FOREIGN KEY (banana) REFERENCES cities(banana) ON DELETE CASCADE
);
```

**URL Architecture:**
- **`agenda_url`** - HTML page (item-based meetings, 58% of cities)
- **`packet_url`** - PDF file (monolithic meetings, 42% of cities)

**One or the other, not both.** Agenda implies items.

#### `items` - Agenda Items
```sql
CREATE TABLE items (
    id TEXT PRIMARY KEY,               -- sanfranciscoCA_2025-11-10_item_5
    meeting_id TEXT NOT NULL,
    title TEXT NOT NULL,
    sequence INTEGER NOT NULL,         -- Order in agenda
    attachments TEXT,                  -- JSON: [{url, name, type}]
    matter_id TEXT,                    -- Backend vendor ID (UUID, numeric)
    matter_file TEXT,                  -- Public ID (BL2025-1005, 25-1209)
    matter_type TEXT,                  -- Ordinance, Resolution, etc.
    agenda_number TEXT,                -- Position on this agenda (1, K. 87)
    sponsors TEXT,                     -- JSON: ["Jane Doe", "John Smith"]
    summary TEXT,                      -- Item-level summary
    topics TEXT,                       -- JSON: ["housing", "zoning"]
    created_at TIMESTAMP,
    FOREIGN KEY (meeting_id) REFERENCES meetings(id) ON DELETE CASCADE
);
```

**Matter Tracking (Unified Schema):**
All vendors (Legistar, PrimeGov, Granicus, etc.) use same fields:
- **`matter_id`** - Backend unique identifier (UUID, numeric ID)
- **`matter_file`** - Official public-facing identifier (BL2025-1005, 25-1209)
- **`matter_type`** - Flexible metadata (Ordinance, Resolution, CD 12)
- **`agenda_number`** - Position on THIS specific agenda
- **`sponsors`** - List of sponsor names (when available)

#### `city_matters` - Matter Registry (Matters-First Architecture)
```sql
CREATE TABLE city_matters (
    id TEXT PRIMARY KEY,               -- sanfranciscoCA_251041 (composite)
    banana TEXT NOT NULL,
    matter_file TEXT,                  -- BL2025-1005, 25-1209
    matter_id TEXT,                    -- UUID, numeric backend ID
    matter_type TEXT,                  -- Ordinance, Resolution
    title TEXT,
    canonical_summary TEXT,            -- Deduplicated summary (stored once)
    canonical_topics TEXT,             -- JSON: ["housing", "zoning"]
    attachments TEXT,                  -- JSON: [{url, name, type}]
    metadata TEXT,                     -- JSON: {attachment_hash, ...}
    first_seen TIMESTAMP,
    last_seen TIMESTAMP,
    appearance_count INTEGER,
    sponsors TEXT,                     -- JSON: ["Jane Doe"]
    created_at TIMESTAMP,
    updated_at TIMESTAMP,
    FOREIGN KEY (banana) REFERENCES cities(banana) ON DELETE CASCADE
);
```

**Matters-First Architecture:**
- **Deduplicate summarization:** Matter processed once, reused across meetings
- **Attachment hash:** Detect changes (re-process only if attachments change)
- **Canonical summary:** Single source of truth for matter description
- **Timeline tracking:** `first_seen`, `last_seen`, `appearance_count`

#### `matter_appearances` - Matter Timeline
```sql
CREATE TABLE matter_appearances (
    matter_id TEXT NOT NULL,           -- sanfranciscoCA_251041
    meeting_id TEXT NOT NULL,
    item_id TEXT NOT NULL,
    appeared_at TIMESTAMP,
    committee TEXT,                    -- Planning Commission, Board of Supervisors
    sequence INTEGER,                  -- Order in meeting
    PRIMARY KEY (matter_id, meeting_id, item_id),
    FOREIGN KEY (matter_id) REFERENCES city_matters(id) ON DELETE CASCADE,
    FOREIGN KEY (meeting_id) REFERENCES meetings(id) ON DELETE CASCADE,
    FOREIGN KEY (item_id) REFERENCES items(id) ON DELETE CASCADE
);
```

**Use case:** Track matter across committees and time:
```python
# Get all appearances of BL2025-1005
SELECT * FROM matter_appearances
WHERE matter_id = 'nashvilleTN_BL2025-1005'
ORDER BY appeared_at;

# Example output:
# 2025-10-15 | Planning Commission | Item 5
# 2025-10-22 | Budget Committee    | Item 3
# 2025-11-05 | City Council        | Item 12 (final vote)
```

#### `queue` - Processing Queue (Typed Jobs)
```sql
CREATE TABLE queue (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_type TEXT,                     -- "meeting" or "matter"
    payload TEXT,                      -- JSON: MeetingJob or MatterJob
    source_url TEXT NOT NULL UNIQUE,   -- Deduplication key
    meeting_id TEXT,
    banana TEXT,
    status TEXT DEFAULT 'pending',     -- pending, processing, completed, failed, dead_letter
    priority INTEGER DEFAULT 0,        -- Higher = processed first
    retry_count INTEGER DEFAULT 0,
    error_message TEXT,
    created_at TIMESTAMP,
    started_at TIMESTAMP,
    completed_at TIMESTAMP,
    failed_at TIMESTAMP,
    FOREIGN KEY (banana) REFERENCES cities(banana) ON DELETE CASCADE,
    FOREIGN KEY (meeting_id) REFERENCES meetings(id) ON DELETE CASCADE
);
```

**Typed Jobs (Discriminated Union):**

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

#### `cache` - Processing Cache
```sql
CREATE TABLE cache (
    packet_url TEXT PRIMARY KEY,
    content_hash TEXT,
    processing_method TEXT,
    processing_time REAL,
    cache_hit_count INTEGER DEFAULT 0,
    created_at TIMESTAMP,
    last_accessed TIMESTAMP
);
```

---

## Data Models

All entities are **dataclasses** with convenience methods:

```python
from database.models import City, Meeting, AgendaItem, Matter

# City
city = City(
    banana="paloaltoCA",
    name="Palo Alto",
    state="CA",
    vendor="primegov",
    slug="cityofpaloalto"
)

# Meeting
meeting = Meeting(
    id="paloaltoCA_2025-11-10",
    banana="paloaltoCA",
    title="City Council - Regular Meeting",
    date=datetime(2025, 11, 10, 19, 0),
    agenda_url="https://...",
    packet_url=None,  # Agenda-first: agenda_url XOR packet_url
    summary=None,
    topics=["housing", "zoning"]
)

# AgendaItem
item = AgendaItem(
    id="paloaltoCA_2025-11-10_item_5",
    meeting_id="paloaltoCA_2025-11-10",
    title="Approve Housing Project",
    sequence=5,
    attachments=[{"url": "...", "name": "staff_report.pdf"}],
    matter_file="25-1234",
    summary="Summary text...",
    topics=["housing"]
)

# Matter
matter = Matter(
    id="sanfranciscoCA_251041",
    banana="sanfranciscoCA",
    matter_file="251041",
    matter_type="Ordinance",
    title="Housing Ordinance Amendment",
    canonical_summary="Summary text...",
    canonical_topics=["housing", "zoning"],
    metadata={"attachment_hash": "abc123"}
)
```

**Model Methods:**

```python
# Convert to dict (for JSON serialization)
city_dict = city.to_dict()

# Create from database row
city = City.from_db_row(db_row)
```

---

## Repository Guide

### 1. CityRepository (248 lines)

**Operations:**
- Unified city lookup (banana, slug, zipcode, name+state)
- Batch city lookup with filters
- City creation and zipcode management
- Meeting frequency and sync tracking

**Methods:**

```python
# Unified lookup (most specific parameter wins)
city = db.get_city(banana="paloaltoCA")
city = db.get_city(slug="cityofpaloalto")
city = db.get_city(zipcode="94301")
city = db.get_city(name="Palo Alto", state="CA")

# Batch lookup with filters
cities = db.get_cities(state="CA", vendor="primegov", status="active")

# Add city
city = db.add_city(
    banana="paloaltoCA",
    name="Palo Alto",
    state="CA",
    vendor="primegov",
    slug="cityofpaloalto",
    zipcodes=["94301", "94303"]
)

# Get zipcodes
zipcodes = db.get_city_zipcodes("paloaltoCA")  # ["94301", "94303"]

# Get meeting frequency (last 30 days)
count = db.get_city_meeting_frequency("paloaltoCA", days=30)

# Get last sync time
last_sync = db.get_city_last_sync("paloaltoCA")  # datetime or None
```

---

### 2. MeetingRepository (234 lines)

**Operations:**
- Meeting storage (upsert with preservation)
- Meeting retrieval with filters
- Summary updates
- Unprocessed meeting queries

**Methods:**

```python
# Get single meeting
meeting = db.get_meeting("sanfranciscoCA_2025-11-10")

# Get meetings with filters
meetings = db.get_meetings(
    bananas=["paloaltoCA", "oaklandCA"],
    start_date=datetime(2025, 11, 1),
    end_date=datetime(2025, 11, 30),
    has_summary=True,
    limit=50
)

# Store meeting (upsert, preserves existing summary)
meeting = db.store_meeting(meeting_obj)

# Update with summary
db.update_meeting_summary(
    meeting_id="sanfranciscoCA_2025-11-10",
    summary="Meeting summary text...",
    processing_method="item_level_5_items",
    processing_time=12.5,
    topics=["housing", "zoning"],
    participation={"email": "clerk@sfgov.org"}
)

# Get unprocessed meetings
meetings = db.get_unprocessed_meetings(limit=50)
```

**CRITICAL: Preservation on Conflict**

```sql
-- On conflict, PRESERVE existing summary/topics if new values are NULL
ON CONFLICT(id) DO UPDATE SET
    summary = CASE
        WHEN excluded.summary IS NOT NULL THEN excluded.summary
        ELSE meetings.summary
    END
```

**Why:** Re-syncing cities should update structural data (title, date) but NOT overwrite already-processed summaries.

---

### 3. ItemRepository (196 lines)

**Operations:**
- Batch item storage (preserves summaries on re-sync)
- Item retrieval (ordered by sequence)
- Summary updates

**Methods:**

```python
# Store agenda items (batch)
count = db.store_agenda_items(meeting_id, [item1, item2, item3])

# Get items for meeting (ordered by sequence)
items = db.get_agenda_items("sanfranciscoCA_2025-11-10")

# Update item with summary
db.update_agenda_item(
    item_id="sanfranciscoCA_2025-11-10_item_5",
    summary="Item summary text...",
    topics=["housing"]
)

# Get single item by ID
item = db.get_agenda_item("sanfranciscoCA_2025-11-10_item_5")

# Get multiple items by IDs
items = db.get_agenda_items_by_ids(["item_1", "item_2"])
```

---

### 4. MatterRepository (300 lines)

**Operations:**
- Matter storage (preserves canonical summary on re-sync)
- Matter retrieval by ID or keys
- Canonical summary updates

**Methods:**

```python
# Store matter (preserves canonical_summary on conflict)
db.store_matter(matter_obj)

# Get matter by composite ID
matter = db.get_matter("sanfranciscoCA_251041")

# Get matter by keys (uses deterministic ID generation)
matter = db.get_matter_by_keys(
    banana="sanfranciscoCA",
    matter_file="251041"
)

# Get all matters for city
matters = db.get_matters_by_city("sanfranciscoCA", include_processed=True)

# Update canonical summary
db.update_matter_summary(
    matter_id="sanfranciscoCA_251041",
    canonical_summary="Summary text...",
    canonical_topics=["housing", "zoning"],
    attachment_hash="abc123"
)

# Generate deterministic matter ID
matter_id = db.generate_matter_id(
    banana="sanfranciscoCA",
    matter_file="251041"
)
# Returns: "sanfranciscoCA_7a8f3b2c1d9e4f5a" (SHA256 hash)
```

**Deduplication Pattern:**

```python
# Check if matter already processed
matter = db.get_matter_by_keys("sanfranciscoCA", matter_file="251041")

if matter and matter.canonical_summary:
    # Compare attachment hash
    current_hash = hash_attachments(new_attachments)
    stored_hash = matter.metadata.get("attachment_hash")

    if current_hash == stored_hash:
        # Unchanged - reuse canonical summary
        db.update_agenda_item(item_id, matter.canonical_summary, matter.canonical_topics)
    else:
        # Changed - re-process and update canonical
        new_summary = process_matter(matter_id)
        db.update_matter_summary(matter_id, new_summary, topics, current_hash)
else:
    # New matter - process and store canonical
    summary = process_matter(matter_id)
    db.update_matter_summary(matter_id, summary, topics, attachment_hash)
```

---

### 5. QueueRepository (578 lines)

**Operations:**
- Enqueue typed jobs (MeetingJob, MatterJob)
- Dequeue with priority sorting
- Status updates (completed, failed, retry, DLQ)
- Queue statistics and management

**Methods:**

```python
# Enqueue meeting job
queue_id = db.enqueue_meeting_job(
    meeting_id="sanfranciscoCA_2025-11-10",
    source_url="https://...",
    banana="sanfranciscoCA",
    priority=150
)

# Enqueue matter job
queue_id = db.enqueue_matter_job(
    matter_id="sanfranciscoCA_251041",
    meeting_id="sanfranciscoCA_2025-11-10",
    item_ids=["item_1", "item_2"],
    banana="sanfranciscoCA",
    priority=150
)

# Get next job (typed)
job: QueueJob = db.get_next_for_processing()
# or for specific city
job = db.get_next_for_processing(banana="paloaltoCA")

# Process job based on type
if job.job_type == "meeting":
    payload: MeetingJob = job.payload
    process_meeting(payload.meeting_id)
elif job.job_type == "matter":
    payload: MatterJob = job.payload
    process_matter(payload.matter_id, payload.item_ids)

# Mark complete
db.mark_processing_complete(job.id)

# Mark failed (with retry logic)
db.mark_processing_failed(job.id, "Error message", increment_retry=True)

# Queue statistics
stats = db.get_queue_stats()
# {
#     "pending_count": 10,
#     "processing_count": 2,
#     "completed_count": 100,
#     "failed_count": 3,
#     "dead_letter_count": 1,
#     "avg_processing_seconds": 12.5
# }

# Dead letter queue
dead_jobs = db.get_dead_letter_jobs(limit=100)

# Reset failed jobs
count = db.reset_failed_items(max_retries=3)

# Clear queue (nuclear option)
cleared = db.clear_queue()  # {"pending": 10, "processing": 2, ...}
```

**Retry Logic:**

```python
# Attempt 1: priority = 150
# Attempt 2: priority = 130 (drops by 20)
# Attempt 3: priority = 110 (drops by 40)
# Attempt 4+: Move to dead_letter queue
```

---

### 6. SearchRepository (231 lines)

**Operations:**
- Topic-based meeting search
- Popular topics aggregation
- Cache lookups and hit tracking
- Database statistics

**Methods:**

```python
# Search by topic
meetings = db.search_meetings_by_topic(
    topic="housing",
    city_banana="sanfranciscoCA",
    limit=50
)

# Get items matching topic
items = db.get_items_by_topic(meeting_id, topic="housing")

# Get popular topics
topics = db.get_popular_topics(limit=20)
# [{"topic": "housing", "count": 150}, ...]

# Get cached summary (increments hit count)
meeting = db.get_cached_summary(packet_url)

# Store processing result
db.store_processing_result(
    packet_url="https://...",
    processing_method="pymupdf_gemini",
    processing_time=12.5
)

# Database statistics
stats = db.get_stats()
# {
#     "active_cities": 500,
#     "total_meetings": 10000,
#     "summarized_meetings": 5000,
#     "pending_meetings": 2000,
#     "summary_rate": "50.0%"
# }

# Random meeting with items (for demos)
random_meeting = db.get_random_meeting_with_items()
```

---

## Advanced Patterns

### Store Meeting from Sync (Complex Orchestration)

**Location:** `db.py` (not in repository)

**What it does:**
1. Parse dates from vendor format
2. Create Meeting + AgendaItem objects
3. Validate meeting data
4. Store meeting and items
5. Track matters (city_matters + matter_appearances)
6. Enqueue for processing (matters-first or item-level)

**Usage:**

```python
# Vendor adapter returns raw meeting dict
meeting_dict = {
    "meeting_id": "sanfranciscoCA_2025-11-10",
    "title": "Board of Supervisors - Regular Meeting",
    "start": "2025-11-10T14:00:00Z",
    "agenda_url": "https://...",
    "items": [
        {
            "item_id": "5",
            "title": "Approve Housing Project",
            "sequence": 5,
            "attachments": [{"url": "...", "name": "staff_report.pdf"}],
            "matter_file": "251041",
            "matter_type": "Ordinance"
        }
    ]
}

# Transform and store (all-in-one)
stored_meeting, stats = db.store_meeting_from_sync(meeting_dict, city)

# Returns:
# stored_meeting: Meeting object
# stats: {
#     "items_stored": 5,
#     "items_skipped_procedural": 2,
#     "matters_tracked": 3,
#     "matters_duplicate": 1
# }
```

**Internal Flow:**

```python
# 1. Parse date
meeting_date = datetime.fromisoformat(meeting_dict["start"])

# 2. Create Meeting object
meeting_obj = Meeting(
    id=meeting_dict["meeting_id"],
    banana=city.banana,
    title=meeting_dict["title"],
    date=meeting_date,
    agenda_url=meeting_dict.get("agenda_url"),
    packet_url=meeting_dict.get("packet_url")
)

# 3. Validate (reject corrupted meetings)
if not MeetingValidator.validate_and_store(meeting_dict, city):
    return None, stats

# 4. Store meeting
stored_meeting = db.store_meeting(meeting_obj)

# 5. Store items
if meeting_dict.get("items"):
    agenda_items = [
        AgendaItem(
            id=f"{meeting_obj.id}_{item['item_id']}",
            meeting_id=meeting_obj.id,
            title=item["title"],
            sequence=item["sequence"],
            attachments=item.get("attachments", []),
            matter_file=item.get("matter_file"),
            matter_id=item.get("matter_id")
        )
        for item in meeting_dict["items"]
    ]

    count = db.store_agenda_items(stored_meeting.id, agenda_items)
    stats["items_stored"] = count

    # 6. Track matters
    matters_stats = db._track_matters(stored_meeting, meeting_dict["items"], agenda_items)
    stats.update(matters_stats)

    # 7. Enqueue for processing (matters-first or item-level)
    enqueued = db._enqueue_matters_first(city.banana, stored_meeting, agenda_items, priority=150)
```

---

### Matter Tracking Workflow

**Problem:** Legislative items appear across multiple meetings. Processing same matter 10 times wastes API credits.

**Solution:** Matters-First Architecture.

**Flow:**

```python
# 1. Create/update Matter object
matter_id = generate_matter_id(banana="sanfranciscoCA", matter_file="251041")
# Returns: "sanfranciscoCA_7a8f3b2c1d9e4f5a" (deterministic SHA256)

matter = Matter(
    id=matter_id,
    banana="sanfranciscoCA",
    matter_file="251041",
    matter_type="Ordinance",
    title="Housing Ordinance Amendment",
    attachments=[{"url": "...", "name": "ordinance.pdf"}],
    metadata={"attachment_hash": hash_attachments(attachments)}
)

db.store_matter(matter)

# 2. Create matter_appearance record
db.conn.execute("""
    INSERT OR IGNORE INTO matter_appearances
    (matter_id, meeting_id, item_id, appeared_at, committee, sequence)
    VALUES (?, ?, ?, ?, ?, ?)
""", (matter_id, meeting_id, item_id, meeting_date, committee, sequence))

# 3. Check if matter already processed
existing_matter = db.get_matter(matter_id)

if existing_matter and existing_matter.canonical_summary:
    # Compare attachment hash
    current_hash = hash_attachments(new_attachments)
    stored_hash = existing_matter.metadata.get("attachment_hash")

    if current_hash == stored_hash:
        # Unchanged - reuse canonical summary (skip processing!)
        for item in agenda_items:
            db.update_agenda_item(
                item_id=item.id,
                summary=existing_matter.canonical_summary,
                topics=existing_matter.canonical_topics
            )
    else:
        # Changed - enqueue for re-processing
        db.enqueue_matter_job(matter_id, meeting_id, item_ids, banana, priority=150)
else:
    # New matter - enqueue for processing
    db.enqueue_matter_job(matter_id, meeting_id, item_ids, banana, priority=150)
```

---

## Common Operations

### City Management

```python
# Add new city
city = db.add_city(
    banana="berkeleyCA",
    name="Berkeley",
    state="CA",
    vendor="civicclerk",
    slug="berkeleyca.gov",
    county="Alameda",
    zipcodes=["94701", "94702", "94703"]
)

# Lookup by zipcode
city = db.get_city(zipcode="94701")  # Returns Berkeley

# Get all California cities
cities = db.get_cities(state="CA", status="active")

# Get Legistar cities
cities = db.get_cities(vendor="legistar")
```

### Meeting Management

```python
# Get recent meetings for city
meetings = db.get_meetings(
    bananas=["paloaltoCA"],
    start_date=datetime(2025, 11, 1),
    limit=20
)

# Get meetings needing processing
unprocessed = db.get_unprocessed_meetings(limit=50)

# Update with summary
db.update_meeting_summary(
    meeting_id="paloaltoCA_2025-11-10",
    summary="Summary text...",
    processing_method="item_level_5_items",
    processing_time=12.5,
    topics=["housing", "zoning"],
    participation={"email": "clerk@cityofpaloalto.org"}
)
```

### Queue Management

```python
# Enqueue recent meetings for city
meetings = db.get_meetings(bananas=["paloaltoCA"], limit=10)
for meeting in meetings:
    if meeting.agenda_url:
        db.enqueue_meeting_job(
            meeting_id=meeting.id,
            source_url=meeting.agenda_url,
            banana=meeting.banana,
            priority=150
        )

# Process queue
while True:
    job = db.get_next_for_processing()
    if not job:
        break

    try:
        if job.job_type == "meeting":
            process_meeting(job.payload.meeting_id)
        elif job.job_type == "matter":
            process_matter(job.payload.matter_id)

        db.mark_processing_complete(job.id)
    except Exception as e:
        db.mark_processing_failed(job.id, str(e))

# Check queue stats
stats = db.get_queue_stats()
print(f"Pending: {stats['pending_count']}, Failed: {stats['failed_count']}")
```

---

## Configuration

**Required:**
```bash
ENGAGIC_DB_DIR=/root/engagic/data
ENGAGIC_UNIFIED_DB=/root/engagic/data/engagic.db
```

**Performance Settings:**
```sql
PRAGMA journal_mode=WAL;          -- Write-Ahead Logging (faster writes)
PRAGMA synchronous=NORMAL;        -- Balance durability vs speed
PRAGMA cache_size=10000;          -- 10K pages (~40MB cache)
PRAGMA foreign_keys=ON;           -- Enforce referential integrity
```

---

## Key Indices

**Performance-critical indices:**

```sql
-- City lookups
CREATE INDEX idx_cities_vendor ON cities(vendor);
CREATE INDEX idx_cities_state ON cities(state);
CREATE INDEX idx_zipcodes_zipcode ON zipcodes(zipcode);

-- Meeting queries
CREATE INDEX idx_meetings_banana ON meetings(banana);
CREATE INDEX idx_meetings_date ON meetings(date);
CREATE INDEX idx_meetings_status ON meetings(processing_status);

-- Queue operations
CREATE INDEX idx_queue_status ON queue(status);
CREATE INDEX idx_queue_priority ON queue(priority DESC);
CREATE INDEX idx_queue_city ON queue(banana);
```

---

## Migration Notes

### Preservation on Re-Sync

**CRITICAL:** Re-syncing cities should NOT overwrite existing summaries.

**Implementation:**
```sql
ON CONFLICT(id) DO UPDATE SET
    summary = CASE
        WHEN excluded.summary IS NOT NULL THEN excluded.summary
        ELSE meetings.summary
    END
```

**Why:** Adapters may fetch same meeting multiple times (schedule changes, status updates). We don't want to erase already-processed summaries.

---

## Related Modules

- **`pipeline/`** - Orchestration and processing logic
- **`vendors/`** - Adapter implementations that populate database
- **`analysis/`** - LLM analysis that creates summaries
- **`server/`** - API that reads from database

---

---

## Supporting Modules

### `models.py` - Data Models (393 lines)

**Dataclasses representing core entities.**

```python
from database.models import City, Meeting, AgendaItem, Matter

# All models have:
# - .to_dict() → Convert to dict for JSON serialization
# - .from_db_row(row) → Create from SQLite row
```

**Models:**
- **City** (19 fields) - City registry with vendor info
- **Meeting** (21 fields) - Meeting with optional summary
- **AgendaItem** (15 fields) - Individual agenda item with matter tracking
- **Matter** (16 fields) - Legislative matter with canonical summary

**Key Features:**
- Automatic datetime conversion (`created_at`, `updated_at`)
- JSON field deserialization (`topics`, `attachments`, `participation`)
- Type safety with dataclasses

---

### `id_generation.py` - Matter ID Generation (148 lines)

**Deterministic, collision-free ID generation for matters.**

```python
from database.id_generation import generate_matter_id, validate_matter_id

# Generate deterministic matter ID
matter_id = generate_matter_id(
    banana="nashvilleTN",
    matter_file="BL2025-1098"
)
# Returns: "nashvilleTN_7a8f3b2c1d9e4f5a" (SHA256 hash, first 16 hex chars)

# Same inputs always produce same ID
matter_id2 = generate_matter_id("nashvilleTN", matter_file="BL2025-1098")
assert matter_id == matter_id2  # ✓ Deterministic

# Validate format
is_valid = validate_matter_id("nashvilleTN_7a8f3b2c1d9e4f5a")  # True

# Extract banana from matter ID
banana = extract_banana_from_matter_id("nashvilleTN_7a8f3b2c1d9e4f5a")
# Returns: "nashvilleTN"
```

**Design Philosophy:**
- **Deterministic:** Same inputs → same ID (enables deduplication)
- **Unique:** SHA256 collision probability negligible
- **Bidirectional:** Can lookup by original identifiers
- **Original data preserved:** Store `matter_file` and `matter_id` in record

**Hash Format:**
- Composite ID: `{banana}_{hash}`
- Hash: First 16 hex chars of SHA256 (64 bits = 2^64 combinations)
- Example: `"nashvilleTN_7a8f3b2c1d9e4f5a"`

**Use case:** Generate consistent IDs for legislative matters across vendors.

---

### `search_utils.py` - Search Utilities (433 lines)

**Full-text search in meeting and item summaries.**

```python
from database.search_utils import search_summaries, search_matters, strip_markdown

# Search in meeting/item summaries (individual occurrences)
results = search_summaries(
    search_term="affordable housing",
    city_banana="sanfranciscoCA",
    state="CA",
    case_sensitive=False
)

# Returns list of dicts:
# [
#     {
#         "type": "meeting",  # or "item"
#         "url": "https://engagic.org/sanfranciscoCA/2025-11-10-2111",
#         "city": "San Francisco, CA",
#         "meeting_title": "Board of Supervisors",
#         "context": "...affordable housing project...",
#         "summary": "Full summary markdown...",
#         "topics": ["housing", "zoning"],
#         ...
#     }
# ]

# Search in matter canonical summaries (deduplicated)
matters = search_matters(
    search_term="zoning amendment",
    city_banana="nashvilleTN"
)

# Returns list of dicts:
# [
#     {
#         "type": "matter",
#         "matter_id": "nashvilleTN_7a8f3b2c",
#         "matter_file": "BL2025-1098",
#         "title": "Zoning Amendment for District 12",
#         "summary": "Canonical summary...",
#         "topics": ["zoning", "development"],
#         "appearance_count": 3,
#         "timeline_url": "https://engagic.org/nashvilleTN?view=matters#bl2025-1098"
#     }
# ]

# Strip markdown for display
clean_text = strip_markdown("**Bold** and *italic* text")
# Returns: "Bold and italic text"

# Build Engagic URL
url = build_engagic_url("nashvilleTN", "2025-11-10T14:00:00Z", "2111")
# Returns: "https://engagic.org/nashvilleTN/2025-11-10-2111"
```

**Functions:**
- **`search_summaries()`** - Search meeting/item summaries (individual occurrences)
- **`search_matters()`** - Search canonical matter summaries (deduplicated)
- **`strip_markdown()`** - Remove markdown formatting for clean display
- **`build_engagic_url()`** - Construct URLs with date-id format
- **`format_date()`** - Convert ISO dates to YYYY_MM_DD
- **`slugify()`** - Convert text to URL-friendly slugs

**Use case:** Full-text search across all civic meeting content.

---

**Last Updated:** 2025-11-20 (Line Count Verification)
