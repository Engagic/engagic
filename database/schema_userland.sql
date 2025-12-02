-- Userland Database Schema for PostgreSQL
-- User authentication, alerts, and notification system
--
-- Uses 'userland' schema namespace for logical separation from main engagic tables
-- All tables use JSONB for structured data (cities, criteria, matched_criteria)

-- Create userland schema if it doesn't exist
CREATE SCHEMA IF NOT EXISTS userland;

-- ============================================================
-- USERS TABLE
-- ============================================================
-- User accounts for authentication and alert subscriptions
CREATE TABLE IF NOT EXISTS userland.users (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    email TEXT UNIQUE NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_login TIMESTAMP
);

-- Index for email lookups during login
CREATE INDEX IF NOT EXISTS idx_userland_users_email ON userland.users(email);

-- ============================================================
-- ALERTS TABLE
-- ============================================================
-- User-configured alerts for meeting/item notifications
CREATE TABLE IF NOT EXISTS userland.alerts (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    name TEXT NOT NULL,
    cities JSONB NOT NULL,  -- JSON array of city bananas: ["paloaltoCA", "mountainviewCA"]
    criteria JSONB NOT NULL,  -- JSON object: {"keywords": ["housing", "zoning"]}
    frequency TEXT DEFAULT 'weekly' CHECK (frequency IN ('weekly', 'daily')),
    active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES userland.users(id) ON DELETE CASCADE
);

-- Indexes for common queries
CREATE INDEX IF NOT EXISTS idx_userland_alerts_user ON userland.alerts(user_id);
CREATE INDEX IF NOT EXISTS idx_userland_alerts_active ON userland.alerts(active);
CREATE INDEX IF NOT EXISTS idx_userland_alerts_frequency ON userland.alerts(frequency) WHERE active = TRUE;

-- GIN index for keyword searches in criteria JSONB
CREATE INDEX IF NOT EXISTS idx_userland_alerts_criteria ON userland.alerts USING GIN (criteria);

-- ============================================================
-- ALERT MATCHES TABLE
-- ============================================================
-- Matched meetings/items that triggered user alerts
CREATE TABLE IF NOT EXISTS userland.alert_matches (
    id TEXT PRIMARY KEY,
    alert_id TEXT NOT NULL,
    meeting_id TEXT NOT NULL,  -- References public.meetings(id) - no FK for cross-schema simplicity
    item_id TEXT,  -- References public.items(id) - NULL for meeting-level matches
    match_type TEXT NOT NULL CHECK (match_type IN ('keyword', 'matter')),
    confidence REAL NOT NULL CHECK (confidence >= 0 AND confidence <= 1),
    matched_criteria JSONB NOT NULL,  -- JSON object with match details
    notified BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (alert_id) REFERENCES userland.alerts(id) ON DELETE CASCADE
);

-- Indexes for common queries
CREATE INDEX IF NOT EXISTS idx_userland_matches_alert ON userland.alert_matches(alert_id);
CREATE INDEX IF NOT EXISTS idx_userland_matches_meeting ON userland.alert_matches(meeting_id);
CREATE INDEX IF NOT EXISTS idx_userland_matches_item ON userland.alert_matches(item_id) WHERE item_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_userland_matches_notified ON userland.alert_matches(notified) WHERE notified = FALSE;
CREATE INDEX IF NOT EXISTS idx_userland_matches_created ON userland.alert_matches(created_at);

-- ============================================================
-- USED MAGIC LINKS TABLE
-- ============================================================
-- Security: Prevent replay attacks on magic link tokens
-- Stores hashed tokens that have been used (single-use enforcement)
CREATE TABLE IF NOT EXISTS userland.used_magic_links (
    token_hash TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    used_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    expires_at TIMESTAMP NOT NULL
);

-- Index for cleanup job (delete expired tokens)
CREATE INDEX IF NOT EXISTS idx_userland_magic_links_expires ON userland.used_magic_links(expires_at);

-- ============================================================
-- CITY REQUESTS TABLE
-- ============================================================
-- Track unknown cities that users request via their watchlists
-- Helps prioritize which cities to add based on user demand
CREATE TABLE IF NOT EXISTS userland.city_requests (
    city_banana TEXT PRIMARY KEY,
    request_count INTEGER DEFAULT 1,
    first_requested TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_requested TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    status TEXT DEFAULT 'pending' CHECK (status IN ('pending', 'added', 'rejected')),
    notes TEXT
);

-- Index for pending requests lookup
CREATE INDEX IF NOT EXISTS idx_city_requests_status
    ON userland.city_requests(status) WHERE status = 'pending';

-- ============================================================
-- COMMENTS
-- ============================================================
-- Table purposes for documentation
COMMENT ON SCHEMA userland IS 'User authentication and alert notification system';
COMMENT ON TABLE userland.users IS 'User accounts with email-based authentication';
COMMENT ON TABLE userland.alerts IS 'User-configured alerts for meeting/agenda item notifications';
COMMENT ON TABLE userland.alert_matches IS 'Matched meetings/items that triggered user alerts';
COMMENT ON TABLE userland.used_magic_links IS 'Security table to prevent magic link replay attacks';
COMMENT ON TABLE userland.city_requests IS 'Unknown cities requested by users - tracks demand for coverage expansion';

-- Column-level comments for clarity
COMMENT ON COLUMN userland.alerts.cities IS 'JSONB array of city bananas to monitor (e.g., ["paloaltoCA"])';
COMMENT ON COLUMN userland.alerts.criteria IS 'JSONB object with matching criteria (e.g., {"keywords": ["housing"]})';
COMMENT ON COLUMN userland.alert_matches.confidence IS 'Match confidence score 0.0-1.0 (1.0 = exact match)';
COMMENT ON COLUMN userland.alert_matches.matched_criteria IS 'JSONB object with match details for user display';

-- ============================================================
-- ENGAGEMENT TABLES (Closed Loop Phase 2)
-- ============================================================
-- User engagement tracking: watches, activity, trending

-- User watches (matters, meetings, topics, cities, council members)
CREATE TABLE IF NOT EXISTS userland.watches (
    id BIGSERIAL PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES userland.users(id) ON DELETE CASCADE,
    entity_type TEXT NOT NULL CHECK (
        entity_type IN ('matter', 'meeting', 'topic', 'city', 'council_member')
    ),
    entity_id TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(user_id, entity_type, entity_id)
);

CREATE INDEX IF NOT EXISTS idx_userland_watches_entity ON userland.watches(entity_type, entity_id);
CREATE INDEX IF NOT EXISTS idx_userland_watches_user ON userland.watches(user_id);

-- Activity log (views, watches, searches, shares)
CREATE TABLE IF NOT EXISTS userland.activity_log (
    id BIGSERIAL PRIMARY KEY,
    user_id TEXT,                    -- NULL for anonymous
    session_id TEXT,                 -- For anonymous tracking
    action TEXT NOT NULL CHECK (
        action IN ('view', 'watch', 'unwatch', 'search', 'share', 'rate', 'report')
    ),
    entity_type TEXT NOT NULL,
    entity_id TEXT,
    metadata JSONB,                  -- Search query, referrer, etc.
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_userland_activity_entity ON userland.activity_log(entity_type, entity_id);
CREATE INDEX IF NOT EXISTS idx_userland_activity_time ON userland.activity_log(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_userland_activity_user ON userland.activity_log(user_id) WHERE user_id IS NOT NULL;

-- Trending matters (materialized view, refresh every 15 min)
CREATE MATERIALIZED VIEW IF NOT EXISTS userland.trending_matters AS
SELECT
    entity_id AS matter_id,
    COUNT(*) AS engagement,
    COUNT(DISTINCT COALESCE(user_id, session_id)) AS unique_users
FROM userland.activity_log
WHERE entity_type = 'matter'
  AND created_at > NOW() - INTERVAL '7 days'
GROUP BY entity_id
ORDER BY engagement DESC
LIMIT 100;

CREATE UNIQUE INDEX IF NOT EXISTS idx_userland_trending_matters ON userland.trending_matters(matter_id);

-- ============================================================
-- FEEDBACK TABLES (Closed Loop Phase 3)
-- ============================================================
-- User feedback: ratings, issue reports, quality signals

-- Summary ratings (1-5 stars)
CREATE TABLE IF NOT EXISTS userland.ratings (
    id BIGSERIAL PRIMARY KEY,
    user_id TEXT,                    -- NULL for anonymous
    session_id TEXT,                 -- For anonymous rating
    entity_type TEXT NOT NULL CHECK (entity_type IN ('item', 'meeting', 'matter')),
    entity_id TEXT NOT NULL,
    rating SMALLINT NOT NULL CHECK (rating BETWEEN 1 AND 5),
    created_at TIMESTAMP DEFAULT NOW(),
    -- One rating per user/session per entity
    CONSTRAINT ratings_unique_user UNIQUE(user_id, entity_type, entity_id),
    CONSTRAINT ratings_unique_session CHECK (
        (user_id IS NOT NULL) OR (session_id IS NOT NULL)
    )
);

CREATE INDEX IF NOT EXISTS idx_userland_ratings_entity ON userland.ratings(entity_type, entity_id);
CREATE INDEX IF NOT EXISTS idx_userland_ratings_user ON userland.ratings(user_id) WHERE user_id IS NOT NULL;

-- Issue reports
CREATE TABLE IF NOT EXISTS userland.issues (
    id BIGSERIAL PRIMARY KEY,
    user_id TEXT,
    session_id TEXT,
    entity_type TEXT NOT NULL,
    entity_id TEXT NOT NULL,
    issue_type TEXT NOT NULL CHECK (
        issue_type IN ('inaccurate', 'incomplete', 'misleading', 'offensive', 'other')
    ),
    description TEXT NOT NULL,
    status TEXT DEFAULT 'open' CHECK (status IN ('open', 'resolved', 'dismissed')),
    admin_notes TEXT,
    created_at TIMESTAMP DEFAULT NOW(),
    resolved_at TIMESTAMP,
    CONSTRAINT issues_has_reporter CHECK (
        (user_id IS NOT NULL) OR (session_id IS NOT NULL)
    )
);

CREATE INDEX IF NOT EXISTS idx_userland_issues_status ON userland.issues(status);
CREATE INDEX IF NOT EXISTS idx_userland_issues_entity ON userland.issues(entity_type, entity_id);

-- Comments for engagement/feedback tables
COMMENT ON TABLE userland.watches IS 'User watchlist for entities (matters, meetings, topics, cities, council members)';
COMMENT ON TABLE userland.activity_log IS 'User activity tracking for analytics and trending calculations';
COMMENT ON TABLE userland.ratings IS 'User ratings (1-5 stars) for items, meetings, and matters';
COMMENT ON TABLE userland.issues IS 'User-reported issues (inaccurate, incomplete, etc.) for admin review';
