-- Migration 001: Council Members, Sponsorships, and Votes
--
-- Normalizes sponsor data from city_matters.sponsors JSONB array
-- into proper relational tables for tracking elected officials.
-- Also tracks voting patterns per member per meeting.
--
-- Tables created:
--   council_members: Elected officials registry per city
--   sponsorships: Links council members to matters they sponsor
--   votes: Records individual votes per member per matter per meeting
--
-- Design decisions:
--   - ID includes city_banana hash to prevent cross-city collisions
--   - normalized_name enables fuzzy matching across vendor variations
--   - status tracks active/former officials
--   - Votes are per-meeting (same matter can be voted multiple times)
--   - Preserves existing sponsors JSONB for backward compatibility

-- ============================================================
-- COUNCIL MEMBERS TABLE
-- ============================================================
-- Elected officials registry - one row per official per city
CREATE TABLE IF NOT EXISTS council_members (
    id TEXT PRIMARY KEY,  -- Hash of (banana + normalized_name) for cross-city safety
    banana TEXT NOT NULL,
    name TEXT NOT NULL,  -- Display name as extracted from vendor
    normalized_name TEXT NOT NULL,  -- Lowercase, trimmed for matching
    title TEXT,  -- Role: "Council Member", "Mayor", "Alderman", etc.
    district TEXT,  -- Ward/district number if applicable
    status TEXT DEFAULT 'active' CHECK (status IN ('active', 'former', 'unknown')),
    first_seen TIMESTAMP,  -- First appearance (sponsor or vote)
    last_seen TIMESTAMP,  -- Most recent activity
    sponsorship_count INTEGER DEFAULT 0,  -- Denormalized for quick stats
    vote_count INTEGER DEFAULT 0,  -- Denormalized count of votes cast
    metadata JSONB,  -- Vendor-specific fields (photo_url, party, etc.)
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (banana) REFERENCES cities(banana) ON DELETE CASCADE,
    UNIQUE(banana, normalized_name)
);

-- ============================================================
-- SPONSORSHIPS TABLE
-- ============================================================
-- Links council members to matters they sponsor
-- Normalizes city_matters.sponsors JSONB array
CREATE TABLE IF NOT EXISTS sponsorships (
    id BIGSERIAL PRIMARY KEY,
    council_member_id TEXT NOT NULL,
    matter_id TEXT NOT NULL,
    is_primary BOOLEAN DEFAULT FALSE,  -- Primary sponsor vs co-sponsor
    sponsor_order INTEGER,  -- Order in sponsor list (1 = first listed)
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (council_member_id) REFERENCES council_members(id) ON DELETE CASCADE,
    FOREIGN KEY (matter_id) REFERENCES city_matters(id) ON DELETE CASCADE,
    UNIQUE(council_member_id, matter_id)
);

-- ============================================================
-- VOTES TABLE
-- ============================================================
-- Records individual votes per member per matter per meeting
-- Same matter may be voted on in multiple meetings (readings, amendments)
CREATE TABLE IF NOT EXISTS votes (
    id BIGSERIAL PRIMARY KEY,
    council_member_id TEXT NOT NULL,
    matter_id TEXT NOT NULL,
    meeting_id TEXT NOT NULL,  -- Critical: same matter voted multiple times
    vote TEXT NOT NULL CHECK (vote IN ('yes', 'no', 'abstain', 'absent', 'present', 'recused', 'not_voting')),
    vote_date TIMESTAMP,  -- Date of vote (usually meeting date)
    sequence INTEGER,  -- Order in roll call if available
    metadata JSONB,  -- Vendor-specific (motion_id, voice_vote, etc.)
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (council_member_id) REFERENCES council_members(id) ON DELETE CASCADE,
    FOREIGN KEY (matter_id) REFERENCES city_matters(id) ON DELETE CASCADE,
    FOREIGN KEY (meeting_id) REFERENCES meetings(id) ON DELETE CASCADE,
    UNIQUE(council_member_id, matter_id, meeting_id)  -- One vote per member per matter per meeting
);

-- ============================================================
-- PERFORMANCE INDICES
-- ============================================================

-- Council members lookups
CREATE INDEX IF NOT EXISTS idx_council_members_banana ON council_members(banana);
CREATE INDEX IF NOT EXISTS idx_council_members_normalized ON council_members(normalized_name);
CREATE INDEX IF NOT EXISTS idx_council_members_status ON council_members(status);
CREATE INDEX IF NOT EXISTS idx_council_members_banana_status ON council_members(banana, status);

-- Sponsorships lookups
CREATE INDEX IF NOT EXISTS idx_sponsorships_member ON sponsorships(council_member_id);
CREATE INDEX IF NOT EXISTS idx_sponsorships_matter ON sponsorships(matter_id);
CREATE INDEX IF NOT EXISTS idx_sponsorships_primary ON sponsorships(is_primary) WHERE is_primary = TRUE;

-- Votes lookups
CREATE INDEX IF NOT EXISTS idx_votes_member ON votes(council_member_id);
CREATE INDEX IF NOT EXISTS idx_votes_matter ON votes(matter_id);
CREATE INDEX IF NOT EXISTS idx_votes_meeting ON votes(meeting_id);
CREATE INDEX IF NOT EXISTS idx_votes_member_date ON votes(council_member_id, vote_date DESC);
CREATE INDEX IF NOT EXISTS idx_votes_value ON votes(vote);  -- For filtering by yes/no/abstain

-- Full-text search on council member names
CREATE INDEX IF NOT EXISTS idx_council_members_fts ON council_members
USING gin(to_tsvector('english', name));

-- ============================================================
-- COMMENTS
-- ============================================================
COMMENT ON TABLE council_members IS 'Elected officials registry. ID includes city_banana to prevent cross-city collisions. Normalized from city_matters.sponsors JSONB.';
COMMENT ON COLUMN council_members.normalized_name IS 'Lowercase, trimmed name for matching. Handles vendor variations like "John Smith" vs "JOHN SMITH" vs "Smith, John".';
COMMENT ON COLUMN council_members.sponsorship_count IS 'Denormalized count for quick stats. Updated via trigger or application code.';
COMMENT ON TABLE sponsorships IS 'Links council members to matters they sponsor. Normalizes city_matters.sponsors JSONB array.';
COMMENT ON COLUMN sponsorships.is_primary IS 'TRUE if listed first in sponsor list (primary sponsor). FALSE for co-sponsors.';
COMMENT ON TABLE votes IS 'Individual voting records per member per matter per meeting. Same matter may be voted on multiple times across meetings.';
COMMENT ON COLUMN votes.vote IS 'Vote value: yes, no, abstain, absent, present, recused, not_voting. Varies by vendor.';
COMMENT ON COLUMN votes.meeting_id IS 'Critical for tracking same matter across readings/amendments. FK to meetings.';
