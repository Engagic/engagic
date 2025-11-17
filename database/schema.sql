-- Engagic Unified Database Schema
-- Last Updated: 2025-11-15

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
CREATE TABLE IF NOT EXISTS meetings (
    id TEXT PRIMARY KEY,
    banana TEXT NOT NULL,
    title TEXT NOT NULL,
    date TIMESTAMP,
    agenda_url TEXT,
    packet_url TEXT,
    summary TEXT,
    participation TEXT,
    status TEXT,
    topics TEXT,
    processing_status TEXT DEFAULT 'pending',
    processing_method TEXT,
    processing_time REAL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (banana) REFERENCES cities(banana) ON DELETE CASCADE
);

-- City Matters: Canonical representation of legislative items
-- Matters-First Architecture: Each matter has ONE canonical summary
-- that is reused across all appearances (deduplication)
CREATE TABLE IF NOT EXISTS city_matters (
    id TEXT PRIMARY KEY,
    banana TEXT NOT NULL,
    matter_id TEXT,
    matter_file TEXT,
    matter_type TEXT,
    title TEXT NOT NULL,
    sponsors TEXT,
    canonical_summary TEXT,
    canonical_topics TEXT,
    attachments TEXT,
    metadata TEXT,
    first_seen TIMESTAMP,
    last_seen TIMESTAMP,
    appearance_count INTEGER DEFAULT 1,
    status TEXT DEFAULT 'active',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (banana) REFERENCES cities(banana) ON DELETE CASCADE
);

-- Matter Appearances: Timeline tracking for matters across meetings
-- Junction table linking matters to meetings via agenda items
CREATE TABLE IF NOT EXISTS matter_appearances (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
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
CREATE TABLE IF NOT EXISTS items (
    id TEXT PRIMARY KEY,
    meeting_id TEXT NOT NULL,
    title TEXT NOT NULL,
    sequence INTEGER NOT NULL,
    attachments TEXT,
    attachment_hash TEXT,
    matter_id TEXT,
    matter_file TEXT,
    matter_type TEXT,
    agenda_number TEXT,
    sponsors TEXT,
    summary TEXT,
    topics TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (meeting_id) REFERENCES meetings(id) ON DELETE CASCADE,
    FOREIGN KEY (matter_id) REFERENCES city_matters(id) ON DELETE SET NULL
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
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_url TEXT NOT NULL UNIQUE,
    meeting_id TEXT,
    banana TEXT,
    job_type TEXT,
    payload TEXT,
    status TEXT DEFAULT 'pending' CHECK (status IN ('pending', 'processing', 'completed', 'failed', 'dead_letter')),
    priority INTEGER DEFAULT 0,
    retry_count INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    started_at TIMESTAMP,
    completed_at TIMESTAMP,
    failed_at TIMESTAMP,
    error_message TEXT,
    processing_metadata TEXT,
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
    metadata TEXT,
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

-- Performance indices
CREATE INDEX IF NOT EXISTS idx_cities_vendor ON cities(vendor);
CREATE INDEX IF NOT EXISTS idx_cities_state ON cities(state);
CREATE INDEX IF NOT EXISTS idx_cities_status ON cities(status);
CREATE INDEX IF NOT EXISTS idx_zipcodes_zipcode ON zipcodes(zipcode);
CREATE INDEX IF NOT EXISTS idx_meetings_banana ON meetings(banana);
CREATE INDEX IF NOT EXISTS idx_meetings_date ON meetings(date);
CREATE INDEX IF NOT EXISTS idx_meetings_status ON meetings(processing_status);
CREATE INDEX IF NOT EXISTS idx_items_matter_file ON items(matter_file) WHERE matter_file IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_items_matter_id ON items(matter_id) WHERE matter_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_items_meeting_id ON items(meeting_id);
CREATE INDEX IF NOT EXISTS idx_items_matter_meeting ON items(matter_id, meeting_id) WHERE matter_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_city_matters_banana ON city_matters(banana);
CREATE INDEX IF NOT EXISTS idx_city_matters_matter_file ON city_matters(matter_file);
CREATE INDEX IF NOT EXISTS idx_city_matters_first_seen ON city_matters(first_seen);
CREATE INDEX IF NOT EXISTS idx_city_matters_status ON city_matters(status);
CREATE INDEX IF NOT EXISTS idx_matter_appearances_matter ON matter_appearances(matter_id);
CREATE INDEX IF NOT EXISTS idx_matter_appearances_meeting ON matter_appearances(meeting_id);
CREATE INDEX IF NOT EXISTS idx_matter_appearances_item ON matter_appearances(item_id);
CREATE INDEX IF NOT EXISTS idx_matter_appearances_date ON matter_appearances(appeared_at);
CREATE INDEX IF NOT EXISTS idx_cache_hash ON cache(content_hash);
CREATE INDEX IF NOT EXISTS idx_queue_status ON queue(status);
CREATE INDEX IF NOT EXISTS idx_queue_priority ON queue(priority DESC);
CREATE INDEX IF NOT EXISTS idx_queue_city ON queue(banana);
CREATE INDEX IF NOT EXISTS idx_tenant_coverage_city ON tenant_coverage(banana);
CREATE INDEX IF NOT EXISTS idx_tracked_items_tenant ON tracked_items(tenant_id);
CREATE INDEX IF NOT EXISTS idx_tracked_items_city ON tracked_items(banana);
CREATE INDEX IF NOT EXISTS idx_tracked_items_status ON tracked_items(status);
CREATE INDEX IF NOT EXISTS idx_user_profiles_email ON user_profiles(email);
CREATE INDEX IF NOT EXISTS idx_user_subscriptions_user ON user_topic_subscriptions(user_id);
CREATE INDEX IF NOT EXISTS idx_user_subscriptions_city ON user_topic_subscriptions(banana);
CREATE INDEX IF NOT EXISTS idx_user_subscriptions_topic ON user_topic_subscriptions(topic);
