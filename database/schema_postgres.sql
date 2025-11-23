-- Engagic PostgreSQL Database Schema
-- Migrated from SQLite: 2025-11-22
--
-- Key improvements over SQLite:
-- - Normalized JSON columns (topics) to relational tables for indexing
-- - JSONB for complex structures (attachments, metadata, participation)
-- - Full-text search via tsvector and GIN indexes
-- - Connection pooling support (asyncpg)
-- - Proper SERIAL for auto-increment
-- - Cross-city collision prevention via composite keys with city_banana

-- Cities table: Core city registry
CREATE TABLE IF NOT EXISTS cities (
    banana TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    state TEXT NOT NULL,
    vendor TEXT NOT NULL,
    slug TEXT NOT NULL,
    county TEXT,
    status TEXT DEFAULT 'active',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(name, state)
);

-- City zipcodes: Many-to-many relationship
CREATE TABLE IF NOT EXISTS zipcodes (
    banana TEXT NOT NULL,
    zipcode TEXT NOT NULL,
    is_primary BOOLEAN DEFAULT FALSE,
    FOREIGN KEY (banana) REFERENCES cities(banana) ON DELETE CASCADE,
    PRIMARY KEY (banana, zipcode)
);

-- Meetings table: Meeting data with optional summaries
-- NOTE: topics and participation moved to separate tables for PostgreSQL normalization
CREATE TABLE IF NOT EXISTS meetings (
    id TEXT PRIMARY KEY,
    banana TEXT NOT NULL,
    title TEXT NOT NULL,
    date TIMESTAMP,
    agenda_url TEXT,
    packet_url TEXT,
    summary TEXT,
    participation JSONB,  -- Complex structure: {email, phone, zoom}, keep as JSONB
    status TEXT,
    processing_status TEXT DEFAULT 'pending',
    processing_method TEXT,
    processing_time REAL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (banana) REFERENCES cities(banana) ON DELETE CASCADE
);

-- Meeting topics: Normalized from meetings.topics (was JSON array)
-- Enables efficient topic filtering and indexing
CREATE TABLE IF NOT EXISTS meeting_topics (
    meeting_id TEXT NOT NULL,
    topic TEXT NOT NULL,
    FOREIGN KEY (meeting_id) REFERENCES meetings(id) ON DELETE CASCADE,
    PRIMARY KEY (meeting_id, topic)
);

-- City Matters: Canonical representation of legislative items
-- Matters-First Architecture: Each matter has ONE canonical summary
-- that is reused across all appearances (deduplication)
-- CRITICAL: id includes city_banana in hash to prevent cross-city collisions
CREATE TABLE IF NOT EXISTS city_matters (
    id TEXT PRIMARY KEY,  -- Composite hash: includes city_banana to prevent cross-city collisions
    banana TEXT NOT NULL,  -- Scopes matter to specific city
    matter_id TEXT,        -- Vendor-specific UUID (may be unstable)
    matter_file TEXT,      -- Stable public file number (e.g., "BL2025-1098")
    matter_type TEXT,
    title TEXT NOT NULL,
    sponsors JSONB,        -- Array of sponsor names, keep as JSONB
    canonical_summary TEXT,
    canonical_topics JSONB,  -- Will normalize to matter_topics table
    attachments JSONB,     -- Complex structure: [{url, title, pages}], keep as JSONB
    metadata JSONB,        -- Flexible field for vendor-specific data
    first_seen TIMESTAMP,
    last_seen TIMESTAMP,
    appearance_count INTEGER DEFAULT 1,
    status TEXT DEFAULT 'active',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (banana) REFERENCES cities(banana) ON DELETE CASCADE
);

-- Matter topics: Normalized from city_matters.canonical_topics
CREATE TABLE IF NOT EXISTS matter_topics (
    matter_id TEXT NOT NULL,
    topic TEXT NOT NULL,
    FOREIGN KEY (matter_id) REFERENCES city_matters(id) ON DELETE CASCADE,
    PRIMARY KEY (matter_id, topic)
);

-- Matter Appearances: Timeline tracking for matters across meetings
-- Junction table linking matters to meetings via agenda items
CREATE TABLE IF NOT EXISTS matter_appearances (
    id BIGSERIAL PRIMARY KEY,  -- PostgreSQL auto-increment
    matter_id TEXT NOT NULL,
    meeting_id TEXT NOT NULL,
    item_id TEXT NOT NULL,
    appeared_at TIMESTAMP NOT NULL,
    committee TEXT,
    action TEXT,
    vote_tally TEXT,
    sequence INTEGER,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (matter_id) REFERENCES city_matters(id) ON DELETE CASCADE,
    FOREIGN KEY (meeting_id) REFERENCES meetings(id) ON DELETE CASCADE,
    FOREIGN KEY (item_id) REFERENCES items(id) ON DELETE CASCADE,
    UNIQUE(matter_id, meeting_id, item_id)
);

-- Agenda items: Individual items within meetings
-- matter_id stores COMPOSITE HASHED ID matching city_matters.id
-- CRITICAL: matter_id references city_matters.id which includes city_banana
CREATE TABLE IF NOT EXISTS items (
    id TEXT PRIMARY KEY,
    meeting_id TEXT NOT NULL,
    title TEXT NOT NULL,
    sequence INTEGER NOT NULL,
    attachments JSONB,     -- Complex structure: [{url, title, pages}], keep as JSONB
    attachment_hash TEXT,
    matter_id TEXT,        -- References city_matters.id (includes city_banana in hash)
    matter_file TEXT,      -- Denormalized for query performance
    matter_type TEXT,
    agenda_number TEXT,
    sponsors JSONB,        -- Array of sponsor names
    summary TEXT,
    topics JSONB,          -- Will normalize to item_topics table
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (meeting_id) REFERENCES meetings(id) ON DELETE CASCADE,
    FOREIGN KEY (matter_id) REFERENCES city_matters(id) ON DELETE SET NULL
);

-- Item topics: Normalized from items.topics
CREATE TABLE IF NOT EXISTS item_topics (
    item_id TEXT NOT NULL,
    topic TEXT NOT NULL,
    FOREIGN KEY (item_id) REFERENCES items(id) ON DELETE CASCADE,
    PRIMARY KEY (item_id, topic)
);

-- Processing cache: Track PDF processing for cost optimization
CREATE TABLE IF NOT EXISTS cache (
    packet_url TEXT PRIMARY KEY,
    content_hash TEXT,
    processing_method TEXT,
    processing_time REAL,
    cache_hit_count INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_accessed TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Processing queue: Decoupled processing queue (agenda-first, item-level)
CREATE TABLE IF NOT EXISTS queue (
    id BIGSERIAL PRIMARY KEY,  -- PostgreSQL auto-increment
    source_url TEXT NOT NULL UNIQUE,
    meeting_id TEXT,
    banana TEXT,
    job_type TEXT,
    payload JSONB,  -- Was TEXT in SQLite, JSONB is native in PostgreSQL
    status TEXT DEFAULT 'pending' CHECK (status IN ('pending', 'processing', 'completed', 'failed', 'dead_letter')),
    priority INTEGER DEFAULT 0,
    retry_count INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    started_at TIMESTAMP,
    completed_at TIMESTAMP,
    failed_at TIMESTAMP,
    error_message TEXT,
    processing_metadata JSONB,  -- Was TEXT, now JSONB
    FOREIGN KEY (banana) REFERENCES cities(banana) ON DELETE CASCADE,
    FOREIGN KEY (meeting_id) REFERENCES meetings(id) ON DELETE CASCADE
);

-- Tenants table: B2B customers (Phase 5)
CREATE TABLE IF NOT EXISTS tenants (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    api_key TEXT UNIQUE NOT NULL,
    webhook_url TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Tenant coverage: Which cities each tenant tracks
CREATE TABLE IF NOT EXISTS tenant_coverage (
    tenant_id TEXT NOT NULL,
    banana TEXT NOT NULL,
    added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (tenant_id) REFERENCES tenants(id) ON DELETE CASCADE,
    FOREIGN KEY (banana) REFERENCES cities(banana) ON DELETE CASCADE,
    PRIMARY KEY (tenant_id, banana)
);

-- Tenant keywords: Topics tenants care about
CREATE TABLE IF NOT EXISTS tenant_keywords (
    tenant_id TEXT NOT NULL,
    keyword TEXT NOT NULL,
    added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (tenant_id) REFERENCES tenants(id) ON DELETE CASCADE,
    PRIMARY KEY (tenant_id, keyword)
);

-- Tracked items: Ordinances, proposals, etc. (Phase 6)
CREATE TABLE IF NOT EXISTS tracked_items (
    id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    item_type TEXT NOT NULL,
    title TEXT NOT NULL,
    description TEXT,
    banana TEXT NOT NULL,
    first_mentioned_meeting_id TEXT,
    first_seen TIMESTAMP,
    last_seen TIMESTAMP,
    status TEXT DEFAULT 'active',
    metadata JSONB,  -- Was TEXT, now JSONB
    FOREIGN KEY (tenant_id) REFERENCES tenants(id) ON DELETE CASCADE,
    FOREIGN KEY (banana) REFERENCES cities(banana) ON DELETE CASCADE
);

-- Tracked item meetings: Link tracked items to meetings
CREATE TABLE IF NOT EXISTS tracked_item_meetings (
    tracked_item_id TEXT NOT NULL,
    meeting_id TEXT NOT NULL,
    mentioned_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    excerpt TEXT,
    FOREIGN KEY (tracked_item_id) REFERENCES tracked_items(id) ON DELETE CASCADE,
    FOREIGN KEY (meeting_id) REFERENCES meetings(id) ON DELETE CASCADE,
    PRIMARY KEY (tracked_item_id, meeting_id)
);

-- User profiles: End-user accounts (Phase 2)
CREATE TABLE IF NOT EXISTS user_profiles (
    id TEXT PRIMARY KEY,
    email TEXT UNIQUE NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- User topic subscriptions: Topics users want alerts for (Phase 2)
CREATE TABLE IF NOT EXISTS user_topic_subscriptions (
    user_id TEXT NOT NULL,
    banana TEXT NOT NULL,
    topic TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES user_profiles(id) ON DELETE CASCADE,
    FOREIGN KEY (banana) REFERENCES cities(banana) ON DELETE CASCADE,
    PRIMARY KEY (user_id, banana, topic)
);

-- =======================
-- PERFORMANCE INDICES
-- =======================

-- Cities
CREATE INDEX IF NOT EXISTS idx_cities_vendor ON cities(vendor);
CREATE INDEX IF NOT EXISTS idx_cities_state ON cities(state);
CREATE INDEX IF NOT EXISTS idx_cities_status ON cities(status);

-- Zipcodes
CREATE INDEX IF NOT EXISTS idx_zipcodes_zipcode ON zipcodes(zipcode);

-- Meetings
CREATE INDEX IF NOT EXISTS idx_meetings_banana ON meetings(banana);
CREATE INDEX IF NOT EXISTS idx_meetings_date ON meetings(date);
CREATE INDEX IF NOT EXISTS idx_meetings_status ON meetings(processing_status);
CREATE INDEX IF NOT EXISTS idx_meetings_banana_date ON meetings(banana, date DESC);  -- Composite for city timeline queries

-- Meeting topics (new normalized table)
CREATE INDEX IF NOT EXISTS idx_meeting_topics_topic ON meeting_topics(topic);
CREATE INDEX IF NOT EXISTS idx_meeting_topics_meeting ON meeting_topics(meeting_id);

-- Items
CREATE INDEX IF NOT EXISTS idx_items_matter_file ON items(matter_file) WHERE matter_file IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_items_matter_id ON items(matter_id) WHERE matter_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_items_meeting_id ON items(meeting_id);
CREATE INDEX IF NOT EXISTS idx_items_matter_meeting ON items(matter_id, meeting_id) WHERE matter_id IS NOT NULL;

-- Item topics (new normalized table)
CREATE INDEX IF NOT EXISTS idx_item_topics_topic ON item_topics(topic);
CREATE INDEX IF NOT EXISTS idx_item_topics_item ON item_topics(item_id);

-- City Matters
CREATE INDEX IF NOT EXISTS idx_city_matters_banana ON city_matters(banana);
CREATE INDEX IF NOT EXISTS idx_city_matters_matter_file ON city_matters(matter_file);
CREATE INDEX IF NOT EXISTS idx_city_matters_first_seen ON city_matters(first_seen);
CREATE INDEX IF NOT EXISTS idx_city_matters_status ON city_matters(status);
CREATE INDEX IF NOT EXISTS idx_city_matters_banana_file ON city_matters(banana, matter_file) WHERE matter_file IS NOT NULL;  -- Composite for matter lookup

-- Matter topics (new normalized table)
CREATE INDEX IF NOT EXISTS idx_matter_topics_topic ON matter_topics(topic);
CREATE INDEX IF NOT EXISTS idx_matter_topics_matter ON matter_topics(matter_id);

-- Matter Appearances
CREATE INDEX IF NOT EXISTS idx_matter_appearances_matter ON matter_appearances(matter_id);
CREATE INDEX IF NOT EXISTS idx_matter_appearances_meeting ON matter_appearances(meeting_id);
CREATE INDEX IF NOT EXISTS idx_matter_appearances_item ON matter_appearances(item_id);
CREATE INDEX IF NOT EXISTS idx_matter_appearances_date ON matter_appearances(appeared_at);

-- Cache
CREATE INDEX IF NOT EXISTS idx_cache_hash ON cache(content_hash);

-- Queue
CREATE INDEX IF NOT EXISTS idx_queue_status ON queue(status);
CREATE INDEX IF NOT EXISTS idx_queue_city ON queue(banana);
-- Composite index for get_next_for_processing() query (covers status, priority, created_at)
CREATE INDEX IF NOT EXISTS idx_queue_processing ON queue(status, priority DESC, created_at ASC);

-- Tenant tables
CREATE INDEX IF NOT EXISTS idx_tenant_coverage_city ON tenant_coverage(banana);
CREATE INDEX IF NOT EXISTS idx_tracked_items_tenant ON tracked_items(tenant_id);
CREATE INDEX IF NOT EXISTS idx_tracked_items_city ON tracked_items(banana);
CREATE INDEX IF NOT EXISTS idx_tracked_items_status ON tracked_items(status);

-- User profiles
CREATE INDEX IF NOT EXISTS idx_user_profiles_email ON user_profiles(email);
CREATE INDEX IF NOT EXISTS idx_user_subscriptions_user ON user_topic_subscriptions(user_id);
CREATE INDEX IF NOT EXISTS idx_user_subscriptions_city ON user_topic_subscriptions(banana);
CREATE INDEX IF NOT EXISTS idx_user_subscriptions_topic ON user_topic_subscriptions(topic);

-- =======================
-- FULL-TEXT SEARCH (PostgreSQL GIN indexes)
-- =======================

-- Full-text search on meetings (title + summary)
CREATE INDEX IF NOT EXISTS idx_meetings_fts ON meetings
USING gin(to_tsvector('english', COALESCE(title, '') || ' ' || COALESCE(summary, '')));

-- Full-text search on items (title + summary)
CREATE INDEX IF NOT EXISTS idx_items_fts ON items
USING gin(to_tsvector('english', COALESCE(title, '') || ' ' || COALESCE(summary, '')));

-- Full-text search on city_matters (title + canonical_summary)
CREATE INDEX IF NOT EXISTS idx_city_matters_fts ON city_matters
USING gin(to_tsvector('english', COALESCE(title, '') || ' ' || COALESCE(canonical_summary, '')));

-- =======================
-- COMMENTS FOR CRITICAL CONSTRAINTS
-- =======================

COMMENT ON TABLE city_matters IS 'Matters-First Architecture: Each legislative matter has ONE canonical summary reused across all appearances. The id field includes city_banana in hash to prevent cross-city collisions (e.g., BL2025-1098 can exist in multiple cities).';

COMMENT ON COLUMN city_matters.id IS 'Composite hash including city_banana to prevent cross-city collisions. Generated via fallback hierarchy: matter_file (preferred) → matter_id (vendor UUID) → normalized_title (fallback).';

COMMENT ON TABLE matter_appearances IS 'Timeline tracking: Links matters to meetings via agenda items. Enables legislative timeline view showing matter evolution across meetings.';

COMMENT ON TABLE meeting_topics IS 'Normalized from meetings.topics JSON array. Enables efficient topic filtering and indexing.';

COMMENT ON TABLE item_topics IS 'Normalized from items.topics JSON array. Enables efficient topic filtering and indexing.';
