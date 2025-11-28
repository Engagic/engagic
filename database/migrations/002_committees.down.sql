-- Migration 002 DOWN: Remove Committee Tracking
--
-- Rolls back: committees, committee_members tables
-- Reverts: matter_appearances columns (committee_id, vote_outcome, vote_tally)
--
-- WARNING: This will delete all committee data. Cannot be undone.

-- ============================================================
-- DROP INDICES
-- ============================================================
DROP INDEX IF EXISTS idx_committees_banana;
DROP INDEX IF EXISTS idx_committees_name;
DROP INDEX IF EXISTS idx_committees_status;
DROP INDEX IF EXISTS idx_committees_fts;
DROP INDEX IF EXISTS idx_committee_members_committee;
DROP INDEX IF EXISTS idx_committee_members_member;
DROP INDEX IF EXISTS idx_committee_members_active;
DROP INDEX IF EXISTS idx_committee_members_dates;
DROP INDEX IF EXISTS idx_matter_appearances_committee_id;
DROP INDEX IF EXISTS idx_matter_appearances_outcome;

-- ============================================================
-- REVERT MATTER_APPEARANCES
-- ============================================================
-- Drop FK constraint first
ALTER TABLE matter_appearances DROP CONSTRAINT IF EXISTS fk_matter_appearances_committee;

-- Drop added columns
ALTER TABLE matter_appearances DROP COLUMN IF EXISTS committee_id;
ALTER TABLE matter_appearances DROP COLUMN IF EXISTS vote_outcome;
ALTER TABLE matter_appearances DROP COLUMN IF EXISTS vote_tally;

-- Restore original vote_tally as TEXT (if needed for backward compat)
-- ALTER TABLE matter_appearances ADD COLUMN vote_tally TEXT;

-- ============================================================
-- DROP TABLES (order matters for FK constraints)
-- ============================================================
DROP TABLE IF EXISTS committee_members;
DROP TABLE IF EXISTS committees;
