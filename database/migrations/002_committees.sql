-- Migration 002: Committee Tracking
--
-- Enables tracking of:
--   - Committee registry (Planning Commission, Budget Committee, etc.)
--   - Committee roster (which council members serve on which committees)
--   - Historical assignments (joined_at, left_at for time-aware queries)
--   - Committee-level vote analysis ("Committee X voted 5-2")
--   - Vote outcomes per matter appearance (passed, failed, tabled, etc.)
--
-- Design decisions:
--   - committees.id = {banana}_comm_{hash(normalized_name)} for cross-city safety
--   - committee_members tracks assignments with time bounds
--   - Preserves matter_appearances.committee TEXT for backward compat
--   - Adds committee_id FK for relational queries
--   - vote_outcome and vote_tally enable "passed/failed" tracking per committee
--
-- Depends on: 001_council_members.sql (council_members table)

-- ============================================================
-- COMMITTEES TABLE
-- ============================================================
-- Registry of legislative bodies per city
CREATE TABLE IF NOT EXISTS committees (
    id TEXT PRIMARY KEY,  -- {banana}_comm_{16-char-hash}
    banana TEXT NOT NULL,
    name TEXT NOT NULL,  -- "Planning Commission", "Budget Committee", "City Council"
    normalized_name TEXT NOT NULL,  -- Lowercase for matching
    description TEXT,
    status TEXT DEFAULT 'active' CHECK (status IN ('active', 'inactive', 'unknown')),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (banana) REFERENCES cities(banana) ON DELETE CASCADE,
    UNIQUE(banana, normalized_name)
);

-- ============================================================
-- COMMITTEE MEMBERS TABLE
-- ============================================================
-- Tracks which council members serve on which committees
-- Historical tracking via joined_at/left_at enables time-aware queries
-- (e.g., "who was on Planning Commission when matter X was voted?")
CREATE TABLE IF NOT EXISTS committee_members (
    id BIGSERIAL PRIMARY KEY,
    committee_id TEXT NOT NULL,
    council_member_id TEXT NOT NULL,
    role TEXT,  -- "Chair", "Vice-Chair", "Member"
    joined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    left_at TIMESTAMP,  -- NULL = currently serving
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (committee_id) REFERENCES committees(id) ON DELETE CASCADE,
    FOREIGN KEY (council_member_id) REFERENCES council_members(id) ON DELETE CASCADE,
    -- Allow re-joining: unique per assignment period
    UNIQUE(committee_id, council_member_id, joined_at)
);

-- ============================================================
-- ENHANCE MATTER_APPEARANCES
-- ============================================================
-- Add committee_id FK for relational queries (keep TEXT committee for backward compat)
-- Add vote_outcome and vote_tally for committee-level pass/fail tracking

-- committee_id: Links to committees table for relational queries
ALTER TABLE matter_appearances ADD COLUMN IF NOT EXISTS committee_id TEXT;
ALTER TABLE matter_appearances DROP CONSTRAINT IF EXISTS fk_matter_appearances_committee;
ALTER TABLE matter_appearances ADD CONSTRAINT fk_matter_appearances_committee
    FOREIGN KEY (committee_id) REFERENCES committees(id) ON DELETE SET NULL;

-- vote_outcome: Result of committee vote on this matter at this meeting
-- Common outcomes: passed (adopted/approved), failed (rejected), tabled (deferred),
-- withdrawn, referred (to another committee), amended (modified and passed)
ALTER TABLE matter_appearances ADD COLUMN IF NOT EXISTS vote_outcome TEXT
    CHECK (vote_outcome IS NULL OR vote_outcome IN ('passed', 'failed', 'tabled', 'withdrawn', 'referred', 'amended', 'unknown'));

-- vote_tally: JSON summary of vote counts for this matter at this meeting
-- Example: {"yes": 7, "no": 2, "abstain": 1, "absent": 1}
-- Note: This replaces the existing TEXT vote_tally column with JSONB
ALTER TABLE matter_appearances DROP COLUMN IF EXISTS vote_tally;
ALTER TABLE matter_appearances ADD COLUMN vote_tally JSONB;

-- ============================================================
-- PERFORMANCE INDICES
-- ============================================================

-- Committees lookups
CREATE INDEX IF NOT EXISTS idx_committees_banana ON committees(banana);
CREATE INDEX IF NOT EXISTS idx_committees_name ON committees(normalized_name);
CREATE INDEX IF NOT EXISTS idx_committees_status ON committees(status);

-- Committee members lookups
CREATE INDEX IF NOT EXISTS idx_committee_members_committee ON committee_members(committee_id);
CREATE INDEX IF NOT EXISTS idx_committee_members_member ON committee_members(council_member_id);
-- Active members only (left_at IS NULL)
CREATE INDEX IF NOT EXISTS idx_committee_members_active ON committee_members(committee_id)
    WHERE left_at IS NULL;
-- Historical queries by date range
CREATE INDEX IF NOT EXISTS idx_committee_members_dates ON committee_members(joined_at, left_at);

-- Matter appearances by committee and outcome
CREATE INDEX IF NOT EXISTS idx_matter_appearances_committee_id ON matter_appearances(committee_id);
CREATE INDEX IF NOT EXISTS idx_matter_appearances_outcome ON matter_appearances(vote_outcome);

-- Full-text search on committee names
CREATE INDEX IF NOT EXISTS idx_committees_fts ON committees
USING gin(to_tsvector('english', name));

-- ============================================================
-- COMMENTS
-- ============================================================
COMMENT ON TABLE committees IS 'Committee registry per city. ID includes city_banana to prevent cross-city collisions. Enables committee-level vote analysis.';
COMMENT ON TABLE committee_members IS 'Tracks council member committee assignments. left_at NULL means currently serving. Historical tracking enables time-aware queries.';
COMMENT ON COLUMN matter_appearances.committee_id IS 'FK to committees table. Enables "how did Committee X vote" queries. TEXT committee field preserved for backward compat.';
COMMENT ON COLUMN matter_appearances.vote_outcome IS 'Result of committee vote: passed, failed, tabled, withdrawn, referred, amended, unknown.';
COMMENT ON COLUMN matter_appearances.vote_tally IS 'JSON vote counts: {"yes": N, "no": N, "abstain": N, "absent": N}. Populated from votes table.';
