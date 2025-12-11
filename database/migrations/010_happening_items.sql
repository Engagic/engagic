-- Migration: happening_items
-- Purpose: Store Claude Code's analysis of important upcoming items
-- Run autonomously via cron, surfaced in "Happening This Week" frontend section

CREATE TABLE happening_items (
    id SERIAL PRIMARY KEY,
    banana TEXT NOT NULL REFERENCES cities(banana) ON DELETE CASCADE,
    item_id TEXT NOT NULL,
    meeting_id TEXT NOT NULL,
    meeting_date TIMESTAMP NOT NULL,
    rank INTEGER NOT NULL,
    reason TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT NOW(),
    expires_at TIMESTAMP NOT NULL,
    UNIQUE(banana, item_id)
);

-- Index for efficient lookups by city with active items
CREATE INDEX idx_happening_banana_expires ON happening_items(banana, expires_at);

-- Index for cleanup of expired items
CREATE INDEX idx_happening_expires ON happening_items(expires_at);

COMMENT ON TABLE happening_items IS 'Claude Code analyzed rankings of important upcoming agenda items';
COMMENT ON COLUMN happening_items.reason IS 'One-sentence explanation of why this item matters';
COMMENT ON COLUMN happening_items.expires_at IS 'Usually meeting_date + 1 day, for automatic cleanup';
