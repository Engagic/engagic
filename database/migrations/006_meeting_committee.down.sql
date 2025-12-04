-- Migration 006 DOWN: Remove committee_id from meetings table

-- Drop index
DROP INDEX IF EXISTS idx_meetings_committee;

-- Drop foreign key constraint
ALTER TABLE meetings DROP CONSTRAINT IF EXISTS fk_meetings_committee;

-- Drop column
ALTER TABLE meetings DROP COLUMN IF EXISTS committee_id;
