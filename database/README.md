# Database - Persistence & Repository Pattern

**Purpose:** Single source of truth for all Engagic data. PostgreSQL with async connection pooling.

Manages:
- Cities and zipcodes
- Meetings and agenda items
- Matters (legislative tracking)
- Council members and sponsorships
- Committees and memberships
- Votes (per member, per matter, per meeting)
- Processing queue (typed jobs)
- Search, topics, and caching
- User engagement (watches, activity, trending)
- User feedback (ratings, issues)
- User authentication and alerts (userland schema)

---

## Architecture Overview

**Repository Pattern** with async PostgreSQL (asyncpg connection pooling):

```
┌─────────────────────┐
│  Database           │  Orchestration (1097 lines)
│  (db_postgres.py)   │
└──────────┬──────────┘
           │
           ├──> repositories_async/base.py            (116 lines) - Base repository with connection pooling
           ├──> repositories_async/cities.py          (318 lines) - City and zipcode operations
           ├──> repositories_async/meetings.py        (319 lines) - Meeting storage and retrieval
           ├──> repositories_async/items.py           (508 lines) - Agenda item operations
           ├──> repositories_async/matters.py         (560 lines) - Matter operations (matters-first)
           ├──> repositories_async/queue.py           (447 lines) - Processing queue management
           ├──> repositories_async/search.py          (259 lines) - PostgreSQL full-text search
           ├──> repositories_async/userland.py        (582 lines) - User auth, alerts, notifications
           ├──> repositories_async/council_members.py (730 lines) - Council member tracking, sponsorships, votes
           ├──> repositories_async/committees.py      (516 lines) - Committee management, memberships
           ├──> repositories_async/engagement.py      (198 lines) - Watches, activity logging, trending
           ├──> repositories_async/feedback.py        (343 lines) - Ratings, issue reporting
           └──> repositories_async/helpers.py         (232 lines) - Shared builders, JSONB deserialization

Supporting Modules:
├── models.py          (467 lines) - Pydantic dataclasses (City, Meeting, AgendaItem, Matter, CouncilMember, Vote, Committee, CommitteeMember)
├── id_generation.py   (587 lines) - Deterministic ID generation (matters, members, committees)
├── schema_postgres.sql - Main database schema (cities, meetings, items, matters, queue, council_members, committees, votes)
└── schema_userland.sql - Userland schema (users, alerts, alert_matches, watches, ratings, issues)
```

**Total: 6,806 lines** (1097 orchestration + 5128 repositories + 1054 supporting + 27 init)

**Why Repository Pattern?**
- **Separation of concerns:** Each repository handles one domain
- **Testability:** Mock repositories independently
- **Maintainability:** Focused modules > monolithic database layer
- **Shared connection pool:** asyncpg pool (5-20 connections) across all repositories
- **True concurrency:** PostgreSQL handles concurrent operations safely

---

## Quick Start

### Basic Usage

```python
from database.db_postgres import Database

# Create database with connection pool
db = await Database.create()

# City operations
city = await db.cities.get_city("paloaltoCA")
cities = await db.cities.get_cities(state="CA", vendor="primegov")

# Meeting operations
meeting = await db.meetings.get_meeting("sanfranciscoCA_2025-11-10")
meetings = await db.meetings.get_meetings_for_city("paloaltoCA", limit=50)

# Agenda item operations
items = await db.items.get_agenda_items("sanfranciscoCA_2025-11-10")
await db.items.update_agenda_item(item_id, summary, topics)

# Queue operations
await db.queue.enqueue_job(source_url, job_type="meeting", payload={...}, priority=150)
job = await db.queue.get_next_for_processing()
await db.queue.mark_processing_complete(job.id)

# Search operations
meetings = await db.search.search_meetings_by_topic("housing", banana="paloaltoCA")
topics = await db.search.get_popular_topics(limit=20)
stats = await db.get_stats()

# Cleanup
await db.close()
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
    id SERIAL PRIMARY KEY,
    job_type TEXT,                     -- "meeting" or "matter"
    payload JSONB,                     -- MeetingJob or MatterJob
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
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_accessed TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

### Userland Schema Tables

**Separate namespace for user authentication and alerts (Phase 2/3):**

#### `userland.users` - User Accounts
```sql
CREATE TABLE userland.users (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    email TEXT UNIQUE NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_login TIMESTAMP
);
```

#### `userland.alerts` - User-Configured Alerts
```sql
CREATE TABLE userland.alerts (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    name TEXT NOT NULL,
    cities JSONB NOT NULL,              -- Array of city bananas: ["paloaltoCA", ...]
    criteria JSONB NOT NULL,            -- {"keywords": ["housing", "zoning"]}
    frequency TEXT DEFAULT 'weekly',    -- 'weekly' or 'daily'
    active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES userland.users(id) ON DELETE CASCADE
);
```

#### `userland.alert_matches` - Matched Meetings/Items
```sql
CREATE TABLE userland.alert_matches (
    id TEXT PRIMARY KEY,
    alert_id TEXT NOT NULL,
    meeting_id TEXT NOT NULL,
    item_id TEXT,                       -- NULL for meeting-level matches
    match_type TEXT NOT NULL,           -- 'keyword' or 'matter'
    confidence REAL NOT NULL,           -- 0.0-1.0
    matched_criteria JSONB NOT NULL,    -- Match details for display
    notified BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (alert_id) REFERENCES userland.alerts(id) ON DELETE CASCADE
);
```

#### `userland.used_magic_links` - Single-Use Token Tracking
```sql
CREATE TABLE userland.used_magic_links (
    token_hash TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    used_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    expires_at TIMESTAMP NOT NULL
);
```

**Security:** Prevents magic link replay attacks by tracking used tokens.

---

## Data Models

All entities are **dataclasses** with convenience methods:

```python
from database.models import City, Meeting, AgendaItem, Matter, CouncilMember, Vote, Committee, CommitteeMember

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

# CouncilMember
member = CouncilMember(
    id="nashvilleTN_a3f2c8d1",  # Hash of (banana + normalized_name)
    banana="nashvilleTN",
    name="Freddie O'Connell",
    normalized_name="freddie o'connell",
    title="Council Member",
    district="District 19",
    status="active",
    sponsorship_count=45,
    vote_count=312
)

# Vote
vote = Vote(
    council_member_id="nashvilleTN_a3f2c8d1",
    matter_id="nashvilleTN_BL2025-1098",
    meeting_id="nashvilleTN_2025-11-10",
    vote="yes",  # yes, no, abstain, absent, present, recused, not_voting
    vote_date=datetime(2025, 11, 10),
    sequence=3
)

# Committee
committee = Committee(
    id="sanfranciscoCA_b7d4e9f2",  # Hash of (banana + normalized_name)
    banana="sanfranciscoCA",
    name="Planning Commission",
    normalized_name="planning commission",
    description="Oversees land use and development",
    status="active"
)

# CommitteeMember
assignment = CommitteeMember(
    committee_id="sanfranciscoCA_b7d4e9f2",
    council_member_id="sanfranciscoCA_c8e5f0a3",
    role="Chair",
    joined_at=datetime(2024, 1, 15),
    left_at=None  # Still serving
)
```

**Model Methods:**

```python
# Convert to dict (for JSON serialization)
city_dict = city.to_dict()
member_dict = member.to_dict()

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

**Meeting ID Generation:**

Adapters return `vendor_id` (native vendor identifier), and the database layer generates canonical meeting IDs:

```python
# Adapter returns vendor_id (native format varies by vendor)
meeting_dict = {
    "vendor_id": "12345",        # PrimeGov/Legistar: API ID
    # "vendor_id": "20251110",   # Berkeley/Menlo Park: date string
    # "vendor_id": "abc-uuid",   # Chicago: UUID from API
    "title": "City Council Meeting",
    "start": "2025-11-10T18:00:00",
    ...
}

# Database layer generates canonical ID
from database.id_generation import generate_meeting_id

meeting_id = generate_meeting_id(
    banana="paloaltoCA",
    vendor_id="12345",
    date=datetime(2025, 11, 10),
    title="City Council Meeting"
)
# Returns: "paloaltoCA_a3f2c8d1" (MD5 hash)
# Hash input: "{banana}:{vendor_id}:{date_iso}:{title}"
```

**ID Format:** `{banana}_{8-char-md5-hash}`

**Properties:**
- Deterministic: Same inputs always produce same ID
- Collision-resistant: 4-component hash prevents duplicates
- Traceable: Original vendor_id preserved in hash computation
- Consistent: All vendors, all cities, same format

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

### 6. SearchRepository (198 lines)

**Operations:**
- PostgreSQL full-text search (FTS with ts_rank)
- Topic-based meeting search (normalized tables)
- Popular topics aggregation

**Methods:**

```python
# Full-text search (PostgreSQL FTS with relevance ranking)
meetings = await db.search.search_meetings_fulltext(
    query="affordable housing",
    banana="sanfranciscoCA",
    limit=50
)

# Topic-based search (normalized meeting_topics table)
meetings = await db.search.search_meetings_by_topic(
    topic="housing",
    banana="sanfranciscoCA",
    limit=50
)

# Get popular topics (aggregated from meeting_topics)
topics = await db.search.get_popular_topics(limit=20)
# [{"topic": "housing", "count": 150}, ...]
```

**PostgreSQL FTS Features:**
- Uses `to_tsvector('english', ...)` for indexing
- GIN indexes for fast text search
- `ts_rank()` for relevance scoring
- Searches both title and summary fields

---

### 7. UserlandRepository (498 lines)

**Operations:**
- User authentication (magic link tokens)
- Alert management (create, update, delete)
- Alert matching (keyword-based, matter-based)
- Notification tracking

**Methods:**

```python
# User operations
user = await db.userland.get_user_by_email("user@example.com")
user = await db.userland.create_user(email="user@example.com", name="Jane Doe")

# Alert operations
alert = await db.userland.create_alert(
    user_id="user_123",
    name="Housing Alerts",
    cities=["paloaltoCA", "mountainviewCA"],
    criteria={"keywords": ["housing", "zoning"]},
    frequency="weekly"
)

alerts = await db.userland.get_user_alerts(user_id="user_123", active_only=True)
await db.userland.update_alert(alert_id, active=False)

# Alert matching
await db.userland.create_alert_match(
    alert_id="alert_123",
    meeting_id="paloaltoCA_2025-11-10",
    item_id="item_5",
    match_type="keyword",
    confidence=0.95,
    matched_criteria={"keywords": ["housing"]}
)

unnotified = await db.userland.get_unnotified_matches(limit=100)
await db.userland.mark_matches_notified([match_id_1, match_id_2])

# Magic link authentication
token_hash = await db.userland.store_used_magic_link(user_id, expires_at)
is_valid = await db.userland.check_magic_link_valid(token_hash)
```

**Userland Schema (separate namespace):**
- `userland.users` - User accounts (email-based auth)
- `userland.alerts` - User-configured alerts (cities + criteria)
- `userland.alert_matches` - Matched meetings/items that triggered alerts
- `userland.used_magic_links` - Single-use token tracking (replay attack prevention)

---

### 8. CouncilMemberRepository (730 lines)

**Operations:**
- Find or create council members from sponsor names
- Link council members to matters via sponsorships
- Track votes per member per matter per meeting
- Update member statistics (sponsorship_count, vote_count, last_seen)

**Methods:**

```python
# Find or create council member (normalizes name for matching)
member = await db.council_members.find_or_create_member(
    banana="nashvilleTN",
    name="Freddie O'Connell",
    appeared_at=datetime(2025, 11, 10)
)

# Link member to matter (sponsorship)
await db.council_members.add_sponsorship(
    member_id=member.id,
    matter_id="nashvilleTN_BL2025-1098",
    appeared_at=datetime(2025, 11, 10)
)

# Get members by city
members = await db.council_members.get_members_by_city("nashvilleTN", active_only=True)

# Get sponsorship history for member
sponsorships = await db.council_members.get_member_sponsorships(member.id, limit=50)

# Get sponsors for matter
sponsors = await db.council_members.get_matter_sponsors("nashvilleTN_BL2025-1098")

# Record vote
await db.council_members.record_vote(
    council_member_id=member.id,
    matter_id="nashvilleTN_BL2025-1098",
    meeting_id="nashvilleTN_2025-11-10",
    vote="yes",
    vote_date=datetime(2025, 11, 10)
)

# Get voting history for member
votes = await db.council_members.get_member_votes(member.id, limit=100)

# Get all votes for matter
votes = await db.council_members.get_matter_votes("nashvilleTN_BL2025-1098")
```

**Name Normalization:**
- Strips whitespace, lowercases for matching
- Handles variations: "Freddie O'Connell" = "FREDDIE O'CONNELL" = " Freddie O'connell "
- ID includes city_banana to prevent cross-city collisions

---

### 9. CommitteeRepository (516 lines)

**Operations:**
- Find or create committees from meeting titles
- Track committee membership (which members serve on which committees)
- Historical tracking via joined_at/left_at for time-aware queries
- Committee-level vote analysis

**Methods:**

```python
# Find or create committee
committee = await db.committees.find_or_create_committee(
    banana="sanfranciscoCA",
    name="Planning Commission",
    description="Oversees land use and development"
)

# Add member to committee
await db.committees.add_member(
    committee_id=committee.id,
    council_member_id=member.id,
    role="Chair",
    joined_at=datetime(2024, 1, 15)
)

# Get committee roster (current members)
members = await db.committees.get_committee_members(committee.id, active_only=True)

# Get historical roster (as of specific date)
members = await db.committees.get_committee_members(
    committee.id,
    as_of=datetime(2024, 6, 1)
)

# Get committees by city
committees = await db.committees.get_committees_by_city("sanfranciscoCA", status="active")

# Get committees a member serves on
committees = await db.committees.get_member_committees(member.id, active_only=True)

# Get committee by ID
committee = await db.committees.get_committee_by_id(committee_id)

# Get voting history for committee
votes = await db.committees.get_committee_vote_history(committee.id, limit=50)
```

**Historical Queries:**
- `joined_at` / `left_at` enable "who was on committee X when matter Y was voted?"
- `left_at = NULL` means currently serving
- Time-aware roster queries for accountability analysis

---

### 10. EngagementRepository (198 lines)

**Operations:**
- Watch/unwatch entities (matters, meetings, topics, cities, council members)
- Activity logging (anonymous and authenticated)
- Trending content aggregation

**Methods:**

```python
# Watch an entity
created = await db.engagement.watch(
    user_id="user_123",
    entity_type="matter",
    entity_id="nashvilleTN_BL2025-1098"
)

# Unwatch
removed = await db.engagement.unwatch(user_id, entity_type, entity_id)

# Check if watching
watching = await db.engagement.is_watching(user_id, entity_type, entity_id)

# Get watch count for entity
count = await db.engagement.get_watch_count("matter", matter_id)

# Get user's watches
watches = await db.engagement.get_user_watches(user_id)

# Log activity (views, actions)
await db.engagement.log_activity(
    user_id="user_123",  # or None for anonymous
    session_id="sess_abc",
    action="view",
    entity_type="meeting",
    entity_id=meeting_id
)

# Get trending matters
trending = await db.engagement.get_trending_matters(limit=10)
```

**Entity Types:** `matter`, `meeting`, `topic`, `city`, `council_member`

---

### 11. FeedbackRepository (343 lines)

**Operations:**
- Submit ratings (1-5 stars) on entities
- Report issues (inaccurate, incomplete, misleading content)
- Quality scores for reprocessing decisions

**Methods:**

```python
# Submit rating (authenticated or anonymous via session)
await db.feedback.submit_rating(
    user_id="user_123",  # or None
    session_id="sess_abc",
    entity_type="item",
    entity_id=item_id,
    rating=4
)

# Get rating stats for entity
stats = await db.feedback.get_rating_stats("item", item_id)
# RatingStats(avg_rating=3.8, rating_count=25, distribution={1: 2, 2: 3, 3: 5, 4: 8, 5: 7})

# Report issue
issue_id = await db.feedback.report_issue(
    user_id="user_123",
    entity_type="item",
    entity_id=item_id,
    issue_type="inaccurate",  # inaccurate, incomplete, misleading, other
    description="Summary misses key budget details"
)

# Get issues for entity
issues = await db.feedback.get_entity_issues("item", item_id, status="open")

# Get all open issues
open_issues = await db.feedback.get_open_issues(limit=100)

# Resolve issue
await db.feedback.resolve_issue(issue_id, admin_notes="Fixed in reprocessing")

# Get low-rated entities (candidates for reprocessing)
low_rated = await db.feedback.get_low_rated_entities(
    entity_type="item",
    threshold=2.5,
    min_ratings=3,
    limit=50
)
```

**Quality Loop:** Low ratings + issue reports trigger reprocessing queue entries.

---

### 12. HelpersRepository (232 lines)

**Shared utilities for consistent object construction across repositories.**

**Functions:**

```python
from database.repositories_async.helpers import (
    # JSONB deserialization
    deserialize_attachments,    # JSONB -> List[AttachmentInfo]
    deserialize_metadata,       # JSONB -> MatterMetadata
    deserialize_participation,  # JSONB -> ParticipationInfo

    # Topic fetching (eliminates N+1 queries)
    fetch_topics_for_ids,       # Batch fetch topics from topic tables

    # Object builders
    build_matter,               # DB row -> Matter object
    build_meeting,              # DB row -> Meeting object
    build_agenda_item,          # DB row -> AgendaItem object
)

# Batch fetch topics for multiple entities (one query instead of N)
topics_map = await fetch_topics_for_ids(
    conn, "meeting_topics", "meeting_id", meeting_ids
)
meeting_topics = topics_map.get(meeting.id, [])
```

**Why:** Eliminates duplication across matters.py, meetings.py, items.py. Each builder centralizes JSONB deserialization and topic handling.

---

## Advanced Patterns

### Store Meeting from Sync (Complex Orchestration)

**Location:** `db_postgres.py` (orchestration layer, not in repositories)

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

**Required Environment Variables:**
```bash
# PostgreSQL connection (defaults to config.get_postgres_dsn())
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
POSTGRES_DB=engagic
POSTGRES_USER=engagic
POSTGRES_PASSWORD=***

# Connection pool settings
POSTGRES_POOL_MIN_SIZE=5   # Minimum connections
POSTGRES_POOL_MAX_SIZE=20  # Maximum connections (tuned for 2GB VPS)
```

**Connection Pool:**
- **asyncpg pool:** 5-20 connections shared across all repositories
- **Automatic JSONB codec:** Python dicts ↔ PostgreSQL JSONB (see ASYNCPG_JSONB_HANDLING.md)
- **Connection timeout:** 60 seconds
- **Pool lifecycle:** Created at Database.create(), closed at db.close()

**Important Documentation:**
- **ASYNCPG_JSONB_HANDLING.md** - Automatic JSONB serialization pattern (critical for understanding JSONB operations)

---

## Key Indices

**Performance-critical indices (PostgreSQL):**

```sql
-- City lookups
CREATE INDEX idx_cities_vendor ON cities(vendor);
CREATE INDEX idx_cities_state ON cities(state);
CREATE INDEX idx_zipcodes_zipcode ON zipcodes(zipcode);

-- Meeting queries
CREATE INDEX idx_meetings_banana_date ON meetings(banana, date DESC);  -- Composite for city timeline
CREATE INDEX idx_meetings_status ON meetings(processing_status);

-- Topic searches (normalized tables)
CREATE INDEX idx_meeting_topics_topic ON meeting_topics(topic);
CREATE INDEX idx_item_topics_topic ON item_topics(topic);
CREATE INDEX idx_matter_topics_topic ON matter_topics(topic);

-- Full-text search (GIN indexes)
CREATE INDEX idx_meetings_fts ON meetings USING gin(to_tsvector('english', COALESCE(title, '') || ' ' || COALESCE(summary, '')));
CREATE INDEX idx_items_fts ON items USING gin(to_tsvector('english', COALESCE(title, '') || ' ' || COALESCE(summary, '')));

-- Queue operations
CREATE INDEX idx_queue_processing ON queue(status, priority DESC, created_at ASC);  -- Composite for dequeue

-- Matter tracking
CREATE INDEX idx_city_matters_banana_file ON city_matters(banana, matter_file) WHERE matter_file IS NOT NULL;
CREATE INDEX idx_matter_appearances_matter ON matter_appearances(matter_id);
```

**See schema_postgres.sql for complete index definitions.**

---

## PostgreSQL-Specific Patterns

### Preservation on Re-Sync (UPSERT)

**CRITICAL:** Re-syncing cities should NOT overwrite existing summaries.

**PostgreSQL Implementation:**
```sql
INSERT INTO meetings (...) VALUES (...)
ON CONFLICT(id) DO UPDATE SET
    summary = CASE
        WHEN excluded.summary IS NOT NULL THEN excluded.summary
        ELSE meetings.summary
    END,
    topics = CASE
        WHEN excluded.topics IS NOT NULL THEN excluded.topics
        ELSE meetings.topics
    END
```

**Why:** Adapters may fetch same meeting multiple times (schedule changes, status updates). UPSERT preserves existing summaries while updating metadata.

### Normalized Topics

**Pattern:** Topics stored in separate tables (meeting_topics, item_topics, matter_topics) instead of JSON arrays.

**Benefits:**
- Efficient filtering: `WHERE topic = 'housing'` uses index
- GIN indexes for topic searches
- No JSON array scanning

**Trade-off:** More joins, but PostgreSQL handles them efficiently with proper indexes.

---

## Related Modules

- **`pipeline/`** - Orchestration and processing logic
- **`vendors/`** - Adapter implementations that populate database
- **`analysis/`** - LLM analysis that creates summaries
- **`server/`** - API that reads from database

---

---

## Supporting Modules

### `models.py` - Data Models (263 lines)

**Pydantic dataclasses with runtime validation.**

```python
from database.models import City, Meeting, AgendaItem, Matter

# All models have:
# - .to_dict() → Convert to dict for JSON serialization
# - Runtime validation via Pydantic dataclasses
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

### `id_generation.py` - Matter ID Generation (332 lines)

**Deterministic, collision-free ID generation for matters with title-based fallback.**

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

**Last Updated:** 2025-12-03 (Added 5 repositories: council_members, committees, engagement, feedback, helpers; added 4 models: CouncilMember, Vote, Committee, CommitteeMember; updated all line counts)
