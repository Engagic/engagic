# Engagic Database Schema

Complete reference for the Engagic unified SQLite database.

**Database:** SQLite 3.x with WAL mode
**Location:** `/root/engagic/data/engagic.db` (production)
**Code:** Repository Pattern (database/db.py facade → 5 focused repositories)
**Last Updated:** November 2, 2025

---

## Table of Contents

- [Overview](#overview)
- [Core Tables](#core-tables)
- [Processing Tables](#processing-tables)
- [Future Tables](#future-tables-not-yet-used)
- [JSON Structures](#json-structures)
- [Indices](#indices)
- [Relationships](#relationships)

---

## Overview

### Database Philosophy

**Single Source of Truth:** One unified database replaces the previous 3-database architecture.

**JSON for Flexibility:** Complex structures (topics, attachments, participation) stored as JSON TEXT columns for rapid iteration without schema migrations.

**Foreign Keys Enforced:** Referential integrity with CASCADE deletes.

**WAL Mode:** Write-Ahead Logging for better concurrency.

---

## Core Tables

### `cities`

Cities covered by Engagic across 6 vendor platforms.

**Primary Key:** `banana` (vendor-agnostic identifier)

| Column | Type | Description |
|--------|------|-------------|
| `banana` | TEXT PRIMARY KEY | Vendor-agnostic city identifier (e.g., "paloaltoCA") |
| `name` | TEXT NOT NULL | City name (e.g., "Palo Alto") |
| `state` | TEXT NOT NULL | State code (e.g., "CA") |
| `vendor` | TEXT NOT NULL | Platform vendor (legistar, primegov, granicus, etc.) |
| `slug` | TEXT NOT NULL | Vendor-specific identifier |
| `county` | TEXT | County name (optional) |
| `status` | TEXT | City status: 'active', 'inactive' (default: 'active') |
| `created_at` | TIMESTAMP | Record creation timestamp |
| `updated_at` | TIMESTAMP | Last update timestamp |

**Constraints:**
- `UNIQUE(name, state)` - One record per city

**Indices:**
- `idx_cities_vendor` on `vendor`
- `idx_cities_state` on `state`
- `idx_cities_status` on `status`

**Example:**
```sql
INSERT INTO cities (banana, name, state, vendor, slug)
VALUES ('paloaltoCA', 'Palo Alto', 'CA', 'granicus', 'paloalto_ca');
```

---

### `zipcodes`

Many-to-many relationship between cities and zipcodes.

**Primary Key:** Composite `(banana, zipcode)`

| Column | Type | Description |
|--------|------|-------------|
| `banana` | TEXT NOT NULL | City identifier (FK to cities) |
| `zipcode` | TEXT NOT NULL | 5-digit zipcode |
| `is_primary` | BOOLEAN | Primary zipcode for this city (default: FALSE) |

**Constraints:**
- `FOREIGN KEY (banana) REFERENCES cities(banana) ON DELETE CASCADE`

**Indices:**
- `idx_zipcodes_zipcode` on `zipcode`

**Example:**
```sql
INSERT INTO zipcodes (banana, zipcode, is_primary)
VALUES ('paloaltoCA', '94301', TRUE);

INSERT INTO zipcodes (banana, zipcode)
VALUES ('paloaltoCA', '94302');
```

---

### `meetings`

Meeting records with optional summaries and metadata.

**Primary Key:** `id` (vendor-generated meeting ID)

| Column | Type | Description |
|--------|------|-------------|
| `id` | TEXT PRIMARY KEY | Unique meeting identifier |
| `banana` | TEXT NOT NULL | City identifier (FK to cities) |
| `title` | TEXT NOT NULL | Meeting title |
| `date` | TIMESTAMP | Meeting date/time |
| `agenda_url` | TEXT | URL to HTML agenda page (item-based, primary) |
| `packet_url` | TEXT | URL to PDF packet (monolithic, fallback) |
| `summary` | TEXT | LLM-generated meeting summary (markdown) |
| `participation` | TEXT | JSON: email, phone, virtual_url, is_hybrid |
| `status` | TEXT | Meeting status (scheduled, completed, etc.) |
| `topics` | TEXT | JSON array of canonical topics |
| `processing_status` | TEXT | Processing state: 'pending', 'completed', 'failed' |
| `processing_method` | TEXT | How processed: 'item-based', 'monolithic', 'batch' |
| `processing_time` | REAL | Processing duration in seconds |
| `created_at` | TIMESTAMP | Record creation timestamp |
| `updated_at` | TIMESTAMP | Last update timestamp |

**Constraints:**
- `FOREIGN KEY (banana) REFERENCES cities(banana) ON DELETE CASCADE`

**Indices:**
- `idx_meetings_banana` on `banana`
- `idx_meetings_date` on `date`
- `idx_meetings_status` on `processing_status`

**Example:**
```sql
INSERT INTO meetings (id, banana, title, date, topics, participation)
VALUES (
  'meeting_123',
  'paloaltoCA',
  'City Council Meeting',
  '2025-11-01 19:00:00',
  '["housing", "zoning", "transportation"]',
  '{"email": "council@city.gov", "phone": "+1-650-329-2477", "virtual_url": "https://zoom.us/j/123", "is_hybrid": true}'
);
```

---

### `items` (agenda_items)

Individual agenda items within meetings.

**Primary Key:** `id` (generated item identifier)

| Column | Type | Description |
|--------|------|-------------|
| `id` | TEXT PRIMARY KEY | Unique item identifier |
| `meeting_id` | TEXT NOT NULL | Parent meeting ID (FK to meetings) |
| `title` | TEXT NOT NULL | Agenda item title |
| `sequence` | INTEGER NOT NULL | Order within agenda (1, 2, 3...) |
| `attachments` | TEXT | JSON array of attachment objects |
| `summary` | TEXT | LLM-generated item summary (markdown) |
| `topics` | TEXT | JSON array of canonical topics |
| `created_at` | TIMESTAMP | Record creation timestamp |

**Constraints:**
- `FOREIGN KEY (meeting_id) REFERENCES meetings(id) ON DELETE CASCADE`

**Example:**
```sql
INSERT INTO items (id, meeting_id, title, sequence, topics, attachments, summary)
VALUES (
  'item_456',
  'meeting_123',
  'Affordable Housing Development at 123 Main St',
  1,
  '["housing", "zoning"]',
  '[{"name": "Staff Report", "url": "https://...", "type": "pdf"}]',
  'Council to consider a 150-unit affordable housing development...'
);
```

---

## Processing Tables

### `cache`

Processing cache for cost optimization and deduplication.

**Primary Key:** `packet_url`

| Column | Type | Description |
|--------|------|-------------|
| `packet_url` | TEXT PRIMARY KEY | PDF URL (cache key) |
| `content_hash` | TEXT | SHA-256 hash of PDF content |
| `processing_method` | TEXT | Method used: 'gemini', 'fallback' |
| `processing_time` | REAL | Processing duration in seconds |
| `cache_hit_count` | INTEGER | Number of cache hits (default: 0) |
| `created_at` | TIMESTAMP | First processing timestamp |
| `last_accessed` | TIMESTAMP | Most recent access timestamp |

**Indices:**
- `idx_cache_hash` on `content_hash`

**Purpose:** Avoid reprocessing identical PDFs across meetings.

---

### `queue`

Processing job queue with priority support.

**Primary Key:** `id` (auto-increment)

| Column | Type | Description |
|--------|------|-------------|
| `id` | INTEGER PRIMARY KEY | Auto-increment job ID |
| `packet_url` | TEXT NOT NULL UNIQUE | PDF URL to process |
| `meeting_id` | TEXT | Associated meeting ID (FK to meetings) |
| `banana` | TEXT | City identifier (FK to cities) |
| `status` | TEXT | Job status: 'pending', 'processing', 'completed', 'failed' |
| `priority` | INTEGER | Priority score (higher = more urgent, default: 0) |
| `retry_count` | INTEGER | Number of retry attempts (default: 0) |
| `created_at` | TIMESTAMP | Job creation timestamp |
| `started_at` | TIMESTAMP | Processing start timestamp |
| `completed_at` | TIMESTAMP | Processing completion timestamp |
| `error_message` | TEXT | Failure details if status='failed' |
| `processing_metadata` | TEXT | JSON metadata about processing |

**Constraints:**
- `FOREIGN KEY (banana) REFERENCES cities(banana) ON DELETE CASCADE`
- `FOREIGN KEY (meeting_id) REFERENCES meetings(id) ON DELETE CASCADE`
- `CHECK (status IN ('pending', 'processing', 'completed', 'failed'))`

**Indices:**
- `idx_queue_status` on `status`
- `idx_queue_priority` on `priority DESC`

**Priority Calculation:**
```python
# Recent meetings get higher priority
days_old = (now - meeting_date).days
priority = max(0, 100 - days_old)
```

---

## Future Tables (Not Yet Used)

These tables support planned features (Phases 5-6) but are not actively used yet.

### `tenants`

B2B customers for paid API access (Phase 5).

| Column | Type | Description |
|--------|------|-------------|
| `id` | TEXT PRIMARY KEY | Tenant identifier (UUID) |
| `name` | TEXT NOT NULL | Organization name |
| `api_key` | TEXT UNIQUE NOT NULL | API authentication key |
| `webhook_url` | TEXT | Webhook endpoint for notifications |
| `created_at` | TIMESTAMP | Account creation timestamp |

---

### `tenant_coverage`

Cities each tenant tracks.

| Column | Type | Description |
|--------|------|-------------|
| `tenant_id` | TEXT NOT NULL | Tenant ID (FK to tenants) |
| `banana` | TEXT NOT NULL | City identifier (FK to cities) |
| `added_at` | TIMESTAMP | When city was added to coverage |

**Primary Key:** Composite `(tenant_id, banana)`

---

### `tenant_keywords`

Topics/keywords tenants care about.

| Column | Type | Description |
|--------|------|-------------|
| `tenant_id` | TEXT NOT NULL | Tenant ID (FK to tenants) |
| `keyword` | TEXT NOT NULL | Search keyword or topic |
| `added_at` | TIMESTAMP | When keyword was added |

**Primary Key:** Composite `(tenant_id, keyword)`

---

### `tracked_items`

Ordinances, proposals tracked across meetings (Phase 6).

| Column | Type | Description |
|--------|------|-------------|
| `id` | TEXT PRIMARY KEY | Tracked item ID |
| `tenant_id` | TEXT NOT NULL | Tenant tracking this item (FK to tenants) |
| `item_type` | TEXT NOT NULL | Type: 'ordinance', 'proposal', 'resolution' |
| `title` | TEXT NOT NULL | Item title |
| `description` | TEXT | Description |
| `banana` | TEXT NOT NULL | City identifier (FK to cities) |
| `first_mentioned_meeting_id` | TEXT | First meeting where mentioned |
| `first_seen` | TIMESTAMP | First mention timestamp |
| `last_seen` | TIMESTAMP | Most recent mention timestamp |
| `status` | TEXT | Status: 'active', 'passed', 'rejected' |
| `metadata` | TEXT | JSON metadata |

---

### `tracked_item_meetings`

Links tracked items to meetings where mentioned.

| Column | Type | Description |
|--------|------|-------------|
| `tracked_item_id` | TEXT NOT NULL | Tracked item ID (FK to tracked_items) |
| `meeting_id` | TEXT NOT NULL | Meeting ID (FK to meetings) |
| `mentioned_at` | TIMESTAMP | When this link was created |
| `excerpt` | TEXT | Relevant excerpt from meeting |

**Primary Key:** Composite `(tracked_item_id, meeting_id)`

---

## JSON Structures

### `topics` (meetings and items tables)

Array of canonical topic identifiers.

```json
["housing", "zoning", "transportation"]
```

**Canonical Topics:**
- `housing` - Housing & Development
- `zoning` - Zoning & Land Use
- `transportation` - Transportation & Traffic
- `budget` - Budget & Finance
- `public_safety` - Public Safety
- `environment` - Environment & Sustainability
- `parks` - Parks & Recreation
- `utilities` - Utilities & Infrastructure
- `economic_development` - Economic Development
- `education` - Education & Schools
- `health` - Public Health
- `planning` - City Planning
- `permits` - Permits & Licensing
- `contracts` - Contracts & Procurement
- `appointments` - Appointments & Personnel
- `other` - Other

---

### `participation` (meetings table)

Contact information for meeting participation.

```json
{
  "email": "council@cityofpaloalto.org",
  "phone": "+1-650-329-2477",
  "virtual_url": "https://zoom.us/j/123456789",
  "meeting_id": "123456789",
  "is_hybrid": true
}
```

**Fields:**
- `email` (string, optional) - Contact email for public comment
- `phone` (string, optional) - Phone number (E.164 format)
- `virtual_url` (string, optional) - Zoom/virtual meeting URL
- `meeting_id` (string, optional) - Virtual meeting ID
- `is_hybrid` (boolean) - True if both in-person and virtual

---

### `attachments` (items table)

Array of attachment objects for agenda items.

```json
[
  {
    "name": "Staff Report",
    "url": "https://granicus.com/MetaViewer.php?meta_id=845318",
    "type": "pdf",
    "meta_id": "845318"
  },
  {
    "name": "Public Comments",
    "url": "https://...",
    "type": "pdf"
  }
]
```

**Fields:**
- `name` (string) - Human-readable attachment name
- `url` (string) - Direct URL to attachment
- `type` (string) - MIME type or format (usually 'pdf')
- `meta_id` (string, optional) - Vendor-specific metadata ID

---

## Indices

### Performance Indices

```sql
-- Cities
CREATE INDEX idx_cities_vendor ON cities(vendor);
CREATE INDEX idx_cities_state ON cities(state);
CREATE INDEX idx_cities_status ON cities(status);

-- Zipcodes
CREATE INDEX idx_zipcodes_zipcode ON zipcodes(zipcode);

-- Meetings
CREATE INDEX idx_meetings_banana ON meetings(banana);
CREATE INDEX idx_meetings_date ON meetings(date);
CREATE INDEX idx_meetings_status ON meetings(processing_status);

-- Cache
CREATE INDEX idx_cache_hash ON cache(content_hash);

-- Queue
CREATE INDEX idx_queue_status ON queue(status);
CREATE INDEX idx_queue_priority ON queue(priority DESC);
```

**Purpose:**
- Fast zipcode lookups for search
- Efficient meeting queries by city
- Date-based meeting filtering
- Queue priority ordering

---

## Relationships

### Entity Relationship Diagram

```
cities (1) ----< (N) zipcodes
  |
  | (1) ----< (N) meetings
  |              |
  |              | (1) ----< (N) items
  |
  | (1) ----< (N) queue

tenants (1) ----< (N) tenant_coverage >---- (N) cities
        (1) ----< (N) tenant_keywords
        (1) ----< (N) tracked_items >---- (N) meetings (via tracked_item_meetings)
```

### Foreign Key Relationships

**cities → zipcodes**
- One city can have many zipcodes
- Delete city → cascade delete zipcodes

**cities → meetings**
- One city can have many meetings
- Delete city → cascade delete meetings

**meetings → items**
- One meeting can have many agenda items
- Delete meeting → cascade delete items

**cities → queue**
- One city can have many queued jobs
- Delete city → cascade delete queue jobs

**tenants → tracked_items** (Future)
- One tenant can track many items
- Delete tenant → cascade delete tracked items

---

## Querying Examples

### Get all meetings for a city
```sql
SELECT * FROM meetings
WHERE banana = 'paloaltoCA'
ORDER BY date DESC
LIMIT 50;
```

### Search by zipcode
```sql
SELECT c.*, m.*
FROM cities c
JOIN zipcodes z ON c.banana = z.banana
JOIN meetings m ON c.banana = m.banana
WHERE z.zipcode = '94301'
ORDER BY m.date DESC;
```

### Find meetings by topic
```sql
SELECT * FROM meetings
WHERE topics LIKE '%"housing"%'
ORDER BY date DESC;
```

**Note:** SQLite json_each() can be used for more precise JSON queries:

```sql
SELECT m.* FROM meetings m
WHERE EXISTS (
  SELECT 1 FROM json_each(m.topics)
  WHERE value = 'housing'
)
ORDER BY m.date DESC;
```

### Get agenda items for a meeting
```sql
SELECT * FROM items
WHERE meeting_id = 'meeting_123'
ORDER BY sequence ASC;
```

### Queue processing priorities
```sql
SELECT * FROM queue
WHERE status = 'pending'
ORDER BY priority DESC, created_at ASC
LIMIT 10;
```

---

## Migrations

### Schema Versioning

Currently managed via `PRAGMA user_version`:

```sql
PRAGMA user_version;  -- Get current version
PRAGMA user_version = 2;  -- Set version
```

**Recommended:** Add formal migration framework with versioned SQL files.

### Adding Topics Column (October 2025)

```sql
-- Add topics to meetings
ALTER TABLE meetings ADD COLUMN topics TEXT;

-- Add topics to items
ALTER TABLE items ADD COLUMN topics TEXT;

-- Backfill with empty arrays
UPDATE meetings SET topics = '[]' WHERE topics IS NULL;
UPDATE items SET topics = '[]' WHERE topics IS NULL;
```

---

## Database Maintenance

### Vacuum

Reclaim unused space and optimize database file:

```bash
sqlite3 /root/engagic/data/engagic.db "VACUUM;"
```

### Integrity Check

Verify database integrity:

```bash
sqlite3 /root/engagic/data/engagic.db "PRAGMA integrity_check;"
```

### Backup

```bash
# Daily backup (automated via cron)
cp /root/engagic/data/engagic.db \
   /root/engagic/data/backups/engagic.db.$(date +%Y%m%d)

# Restore from backup
cp /root/engagic/data/backups/engagic.db.20251031 \
   /root/engagic/data/engagic.db
```

### Statistics

```sql
-- Table row counts
SELECT 'cities', COUNT(*) FROM cities
UNION ALL
SELECT 'meetings', COUNT(*) FROM meetings
UNION ALL
SELECT 'items', COUNT(*) FROM items
UNION ALL
SELECT 'queue', COUNT(*) FROM queue;

-- Database file size
SELECT page_count * page_size as size FROM pragma_page_count(), pragma_page_size();
```

---

## Future Improvements

### Considered Enhancements

1. **PostgreSQL Migration**
   - Native JSONB support (faster JSON queries)
   - Better full-text search
   - Horizontal scaling

2. **Full-Text Search**
   - SQLite FTS5 extension for summary/title search
   - Topic-based search optimization

3. **Partitioning**
   - Archive old meetings (>2 years)
   - Separate hot/cold data

4. **Analytics Tables**
   - Pre-computed topic statistics
   - Materialized views for common queries

---

**Last Updated:** October 31, 2025
