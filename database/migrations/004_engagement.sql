-- Migration: 004_engagement
-- Phase 2: Engagement Mechanics - watches, activity log, trending
-- Depends on: userland schema existing

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

CREATE INDEX IF NOT EXISTS watches_entity_idx ON userland.watches(entity_type, entity_id);
CREATE INDEX IF NOT EXISTS watches_user_idx ON userland.watches(user_id);

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

CREATE INDEX IF NOT EXISTS activity_log_entity_idx ON userland.activity_log(entity_type, entity_id);
CREATE INDEX IF NOT EXISTS activity_log_time_idx ON userland.activity_log(created_at DESC);
CREATE INDEX IF NOT EXISTS activity_log_user_idx ON userland.activity_log(user_id) WHERE user_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS activity_log_session_idx ON userland.activity_log(session_id) WHERE session_id IS NOT NULL;

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

CREATE UNIQUE INDEX IF NOT EXISTS trending_matters_idx ON userland.trending_matters(matter_id);
