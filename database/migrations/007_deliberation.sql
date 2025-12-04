-- Migration: 007_deliberation
-- Deliberation feature: comments, votes, opinion clustering

-- Deliberation sessions linked to matters
CREATE TABLE IF NOT EXISTS deliberations (
    id TEXT PRIMARY KEY,                    -- "delib_{matter_id}_{short_hash}"
    matter_id TEXT NOT NULL REFERENCES city_matters(id) ON DELETE CASCADE,
    banana TEXT NOT NULL,
    topic TEXT,                             -- Optional override of matter title
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    closed_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_delib_matter ON deliberations(matter_id);
CREATE INDEX IF NOT EXISTS idx_delib_banana ON deliberations(banana);

-- Track participant numbers per deliberation (for pseudonyms)
CREATE TABLE IF NOT EXISTS deliberation_participants (
    deliberation_id TEXT NOT NULL REFERENCES deliberations(id) ON DELETE CASCADE,
    user_id TEXT NOT NULL REFERENCES userland.users(id) ON DELETE CASCADE,
    participant_number INTEGER NOT NULL,
    joined_at TIMESTAMPTZ DEFAULT NOW(),
    PRIMARY KEY (deliberation_id, user_id)
);

-- User-submitted comments
CREATE TABLE IF NOT EXISTS deliberation_comments (
    id SERIAL PRIMARY KEY,
    deliberation_id TEXT NOT NULL REFERENCES deliberations(id) ON DELETE CASCADE,
    user_id TEXT NOT NULL REFERENCES userland.users(id) ON DELETE CASCADE,
    participant_number INTEGER NOT NULL,    -- Pseudonym: "Participant 1", "Participant 2"
    txt TEXT NOT NULL,
    mod_status INTEGER DEFAULT 0,           -- 0=pending, 1=approved, -1=hidden
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_delib_comments_delib ON deliberation_comments(deliberation_id);
CREATE INDEX IF NOT EXISTS idx_delib_comments_mod ON deliberation_comments(deliberation_id, mod_status);
-- Prevent duplicate comments from same user
CREATE UNIQUE INDEX IF NOT EXISTS idx_delib_comments_unique
    ON deliberation_comments(deliberation_id, user_id, txt);

-- Track trusted participants (have had comments approved before)
-- Trust is global, not per-deliberation
CREATE TABLE IF NOT EXISTS userland.deliberation_trusted_users (
    user_id TEXT PRIMARY KEY REFERENCES userland.users(id) ON DELETE CASCADE,
    first_approved_at TIMESTAMPTZ DEFAULT NOW()
);

-- Votes on comments
CREATE TABLE IF NOT EXISTS deliberation_votes (
    comment_id INTEGER NOT NULL REFERENCES deliberation_comments(id) ON DELETE CASCADE,
    user_id TEXT NOT NULL REFERENCES userland.users(id) ON DELETE CASCADE,
    vote SMALLINT NOT NULL CHECK (vote IN (-1, 0, 1)),  -- -1=disagree, 0=pass, 1=agree
    created_at TIMESTAMPTZ DEFAULT NOW(),
    PRIMARY KEY (comment_id, user_id)
);

CREATE INDEX IF NOT EXISTS idx_delib_votes_comment ON deliberation_votes(comment_id);

-- Cached clustering results
CREATE TABLE IF NOT EXISTS deliberation_results (
    deliberation_id TEXT PRIMARY KEY REFERENCES deliberations(id) ON DELETE CASCADE,
    n_participants INTEGER NOT NULL,
    n_comments INTEGER NOT NULL,
    k INTEGER NOT NULL,                     -- Number of clusters
    positions JSONB,                        -- [[x,y], ...] per participant
    clusters JSONB,                         -- {user_id: cluster_id}
    cluster_centers JSONB,                  -- [[x,y], ...] per cluster
    consensus JSONB,                        -- {comment_id: score}
    group_votes JSONB,                      -- Per-cluster vote tallies
    computed_at TIMESTAMPTZ DEFAULT NOW()
);
