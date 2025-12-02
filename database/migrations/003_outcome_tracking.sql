-- Migration 003: Outcome Tracking
--
-- Closes the loop from "item discussed" to "item resolved."
-- Enables tracking of vote outcomes on matters across meetings.
--
-- Changes:
--   1. Add CHECK constraint to city_matters.status for valid dispositions
--   2. Add final_vote_date column for when matter reached final disposition
--   3. Add vote_outcome column to matter_appearances for per-meeting outcomes
--   4. Convert vote_tally to JSONB for structured storage
--
-- Design decisions:
--   - Status enum covers all common legislative outcomes
--   - vote_outcome on matter_appearances enables per-meeting tracking
--   - vote_tally as JSONB allows {yes: N, no: N, abstain: N, absent: N}
--   - final_vote_date tracks when matter reached terminal state

-- ============================================================
-- CITY_MATTERS STATUS ENUM
-- ============================================================
-- Expand from just 'active' to full disposition tracking

ALTER TABLE city_matters
    DROP CONSTRAINT IF EXISTS city_matters_status_check;

ALTER TABLE city_matters
    ADD CONSTRAINT city_matters_status_check
    CHECK (status IN (
        'active',      -- Still in progress
        'passed',      -- Approved/adopted
        'failed',      -- Rejected/defeated
        'tabled',      -- Postponed indefinitely
        'withdrawn',   -- Removed by sponsor
        'referred',    -- Sent to committee
        'amended',     -- Modified and passed
        'vetoed',      -- Executive veto
        'enacted'      -- Signed into law/ordinance
    ));

-- ============================================================
-- FINAL VOTE DATE
-- ============================================================
-- Track when matter reached terminal disposition

ALTER TABLE city_matters
    ADD COLUMN IF NOT EXISTS final_vote_date TIMESTAMP;

CREATE INDEX IF NOT EXISTS idx_city_matters_final_vote
    ON city_matters(final_vote_date)
    WHERE final_vote_date IS NOT NULL;

-- ============================================================
-- MATTER_APPEARANCES OUTCOME TRACKING
-- ============================================================
-- Per-meeting vote outcome and tally

-- Add vote_outcome column for per-meeting result
ALTER TABLE matter_appearances
    ADD COLUMN IF NOT EXISTS vote_outcome TEXT
    CHECK (vote_outcome IS NULL OR vote_outcome IN (
        'passed', 'failed', 'tabled', 'withdrawn', 'referred', 'amended', 'unknown', 'no_vote'
    ));

-- Convert vote_tally from TEXT to JSONB if needed
-- (Check if already JSONB - PostgreSQL will error on type mismatch)
DO $$
BEGIN
    -- Only alter if currently TEXT
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'matter_appearances'
        AND column_name = 'vote_tally'
        AND data_type = 'text'
    ) THEN
        -- Drop the column and recreate as JSONB
        ALTER TABLE matter_appearances DROP COLUMN vote_tally;
        ALTER TABLE matter_appearances ADD COLUMN vote_tally JSONB;
    END IF;
END $$;

-- Index for filtering by outcome
CREATE INDEX IF NOT EXISTS idx_matter_appearances_outcome
    ON matter_appearances(vote_outcome)
    WHERE vote_outcome IS NOT NULL;

-- ============================================================
-- COMMENTS
-- ============================================================

COMMENT ON COLUMN city_matters.status IS 'Legislative disposition: active (in progress), passed, failed, tabled, withdrawn, referred, amended, vetoed, enacted';
COMMENT ON COLUMN city_matters.final_vote_date IS 'Date when matter reached terminal disposition (passed/failed/etc)';
COMMENT ON COLUMN matter_appearances.vote_outcome IS 'Per-meeting vote result: passed, failed, tabled, withdrawn, referred, amended, unknown, no_vote';
COMMENT ON COLUMN matter_appearances.vote_tally IS 'Vote counts as JSONB: {yes: N, no: N, abstain: N, absent: N}';
