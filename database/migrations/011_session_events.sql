-- Session events for journey tracking
-- Events linked to IP hash (same as rate limiting uses)
-- Auto-cleanup: 7 day retention

CREATE TABLE session_events (
    id SERIAL PRIMARY KEY,
    ip_hash TEXT NOT NULL,
    event TEXT NOT NULL,
    url TEXT,
    properties JSONB,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Query by user (ip_hash) and time
CREATE INDEX idx_session_events_ip_hash ON session_events(ip_hash, created_at DESC);

-- Query recent events across all users
CREATE INDEX idx_session_events_created ON session_events(created_at DESC);

-- Cleanup function: delete events older than 7 days
CREATE OR REPLACE FUNCTION cleanup_old_session_events()
RETURNS INTEGER AS $$
DECLARE
    deleted_count INTEGER;
BEGIN
    DELETE FROM session_events WHERE created_at < NOW() - INTERVAL '7 days';
    GET DIAGNOSTICS deleted_count = ROW_COUNT;
    RETURN deleted_count;
END;
$$ LANGUAGE plpgsql;

COMMENT ON TABLE session_events IS 'Anonymous user journey events, linked by IP hash, 7-day retention';
