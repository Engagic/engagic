-- Migration 006: Add committee_id to meetings table
-- Enables Meeting -> Committee navigation (meetings are occurrences of committees)
-- Run on: VPS PostgreSQL

-- Add committee_id column to meetings table
ALTER TABLE meetings ADD COLUMN IF NOT EXISTS committee_id TEXT;

-- Add foreign key constraint
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.table_constraints
        WHERE constraint_name = 'fk_meetings_committee'
    ) THEN
        ALTER TABLE meetings ADD CONSTRAINT fk_meetings_committee
            FOREIGN KEY (committee_id) REFERENCES committees(id) ON DELETE SET NULL;
    END IF;
END $$;

-- Create index for efficient committee-based queries
CREATE INDEX IF NOT EXISTS idx_meetings_committee ON meetings(committee_id);

-- Add column comment
COMMENT ON COLUMN meetings.committee_id IS 'FK to committees table. Enables meeting → committee navigation. A meeting is an occurrence of a committee.';

-- =======================
-- BACKFILL: Populate committee_id for existing meetings
-- =======================
-- Strategy: For each meeting, find the most common committee_id among its item appearances
-- This is more reliable than parsing meeting titles

UPDATE meetings m
SET committee_id = subq.committee_id
FROM (
    SELECT
        ma.meeting_id,
        ma.committee_id,
        ROW_NUMBER() OVER (
            PARTITION BY ma.meeting_id
            ORDER BY COUNT(*) DESC
        ) as rn
    FROM matter_appearances ma
    WHERE ma.committee_id IS NOT NULL
    GROUP BY ma.meeting_id, ma.committee_id
) subq
WHERE m.id = subq.meeting_id
  AND subq.rn = 1
  AND m.committee_id IS NULL;

-- Log result
DO $$
DECLARE
    updated_count INTEGER;
BEGIN
    SELECT COUNT(*) INTO updated_count
    FROM meetings
    WHERE committee_id IS NOT NULL;

    RAISE NOTICE 'Migration 006: % meetings now have committee_id', updated_count;
END $$;
