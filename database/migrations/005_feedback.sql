-- Migration: 005_feedback
-- Phase 3: User Feedback Loop - ratings, issues, quality scores
-- Depends on: userland schema existing

-- Summary ratings (1-5 stars)
CREATE TABLE IF NOT EXISTS userland.ratings (
    id BIGSERIAL PRIMARY KEY,
    user_id TEXT,                    -- NULL for anonymous
    session_id TEXT,                 -- For anonymous rating
    entity_type TEXT NOT NULL CHECK (entity_type IN ('item', 'meeting', 'matter')),
    entity_id TEXT NOT NULL,
    rating SMALLINT NOT NULL CHECK (rating BETWEEN 1 AND 5),
    created_at TIMESTAMP DEFAULT NOW(),
    -- One rating per user per entity (authenticated)
    CONSTRAINT ratings_unique_user UNIQUE(user_id, entity_type, entity_id),
    -- Require either user_id or session_id
    CONSTRAINT ratings_has_identity CHECK (
        (user_id IS NOT NULL) OR (session_id IS NOT NULL)
    )
);

-- One rating per session per entity (anonymous) - partial unique index
CREATE UNIQUE INDEX IF NOT EXISTS ratings_unique_session_idx
    ON userland.ratings(session_id, entity_type, entity_id)
    WHERE user_id IS NULL AND session_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS ratings_entity_idx ON userland.ratings(entity_type, entity_id);
CREATE INDEX IF NOT EXISTS ratings_user_idx ON userland.ratings(user_id) WHERE user_id IS NOT NULL;

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

CREATE INDEX IF NOT EXISTS issues_status_idx ON userland.issues(status);
CREATE INDEX IF NOT EXISTS issues_entity_idx ON userland.issues(entity_type, entity_id);

-- Denormalized quality scores on items table
ALTER TABLE items ADD COLUMN IF NOT EXISTS quality_score REAL;
ALTER TABLE items ADD COLUMN IF NOT EXISTS rating_count INTEGER DEFAULT 0;

-- Denormalized quality scores on city_matters table
ALTER TABLE city_matters ADD COLUMN IF NOT EXISTS quality_score REAL;
ALTER TABLE city_matters ADD COLUMN IF NOT EXISTS rating_count INTEGER DEFAULT 0;
