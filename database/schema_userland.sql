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
-- COMMENTS
-- ============================================================
-- Table purposes for documentation
COMMENT ON SCHEMA userland IS 'User authentication and alert notification system';
COMMENT ON TABLE userland.users IS 'User accounts with email-based authentication';
COMMENT ON TABLE userland.alerts IS 'User-configured alerts for meeting/agenda item notifications';
COMMENT ON TABLE userland.alert_matches IS 'Matched meetings/items that triggered user alerts';
COMMENT ON TABLE userland.used_magic_links IS 'Security table to prevent magic link replay attacks';

-- Column-level comments for clarity
COMMENT ON COLUMN userland.alerts.cities IS 'JSONB array of city bananas to monitor (e.g., ["paloaltoCA"])';
COMMENT ON COLUMN userland.alerts.criteria IS 'JSONB object with matching criteria (e.g., {"keywords": ["housing"]})';
COMMENT ON COLUMN userland.alert_matches.confidence IS 'Match confidence score 0.0-1.0 (1.0 = exact match)';
COMMENT ON COLUMN userland.alert_matches.matched_criteria IS 'JSONB object with match details for user display';
