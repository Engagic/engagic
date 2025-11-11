-- Migration 003: City Matters - Intelligence Layer Foundation
-- Track legislative items (bills, resolutions, ordinances) across their lifecycle
-- Enables: deduplication, timeline view, committee tracking, sponsor tracking

-- City Matters: Canonical representation of legislative items
CREATE TABLE IF NOT EXISTS city_matters (
    id TEXT PRIMARY KEY,                    -- banana_matterfile (e.g., "nashvilleTN_BL2025-1005")
    banana TEXT NOT NULL,                   -- City identifier
    matter_id TEXT,                         -- Vendor-specific ID (Legistar EventItemMatterId)
    matter_file TEXT NOT NULL,              -- Bill number (BL2025-1005, RS2025-1591)
    matter_type TEXT,                       -- Bill, Resolution, Ordinance, etc.
    title TEXT NOT NULL,                    -- Canonical title
    sponsors TEXT,                          -- JSON array of sponsor names
    canonical_summary TEXT,                 -- THE summary (deduplicated across meetings)
    canonical_topics TEXT,                  -- JSON array of topics
    first_seen TIMESTAMP NOT NULL,          -- First appearance in any meeting
    last_seen TIMESTAMP NOT NULL,           -- Most recent appearance
    appearance_count INTEGER DEFAULT 1,     -- How many times appeared
    status TEXT DEFAULT 'active',           -- active, passed, failed, withdrawn
    metadata TEXT,                          -- JSON: additional vendor-specific data
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (banana) REFERENCES cities(banana) ON DELETE CASCADE,
    UNIQUE(banana, matter_file)
);

-- Matter Appearances: Track each time a bill appears in a meeting
-- Enables timeline view and committee progression tracking
CREATE TABLE IF NOT EXISTS matter_appearances (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    matter_id TEXT NOT NULL,                -- FK to city_matters.id
    meeting_id TEXT NOT NULL,               -- FK to meetings.id
    item_id TEXT NOT NULL,                  -- FK to items.id
    appeared_at TIMESTAMP NOT NULL,         -- Meeting date
    committee TEXT,                         -- Which committee (from meeting title)
    action TEXT,                            -- Introduced, First Reading, Passed, etc.
    vote_tally TEXT,                        -- JSON: vote results if available
    sequence INTEGER,                       -- Order in meeting agenda
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (matter_id) REFERENCES city_matters(id) ON DELETE CASCADE,
    FOREIGN KEY (meeting_id) REFERENCES meetings(id) ON DELETE CASCADE,
    FOREIGN KEY (item_id) REFERENCES items(id) ON DELETE CASCADE,
    UNIQUE(matter_id, meeting_id, item_id)
);

-- Indices for efficient queries
CREATE INDEX idx_city_matters_banana ON city_matters(banana);
CREATE INDEX idx_city_matters_matter_file ON city_matters(matter_file);
CREATE INDEX idx_city_matters_first_seen ON city_matters(first_seen);
CREATE INDEX idx_city_matters_status ON city_matters(status);
CREATE INDEX idx_matter_appearances_matter ON matter_appearances(matter_id);
CREATE INDEX idx_matter_appearances_meeting ON matter_appearances(meeting_id);
CREATE INDEX idx_matter_appearances_date ON matter_appearances(appeared_at);

-- Use cases enabled:
-- 1. Timeline: SELECT * FROM matter_appearances WHERE matter_id = ? ORDER BY appeared_at
-- 2. Deduplication: Check canonical_summary before LLM processing
-- 3. Committee tracking: GROUP BY committee to see which committees handle what
-- 4. Sponsor analysis: Track which sponsors introduce what types of bills
-- 5. Intelligence Layer: Foundation for tracked items, alerts, and civic insights
