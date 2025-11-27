-- Rollback Migration 001: Council Members and Sponsorships
--
-- WARNING: This will drop all council member and sponsorship data.
-- The sponsors JSONB arrays in city_matters will be preserved.

-- Drop indices first
DROP INDEX IF EXISTS idx_council_members_fts;
DROP INDEX IF EXISTS idx_sponsorships_primary;
DROP INDEX IF EXISTS idx_sponsorships_matter;
DROP INDEX IF EXISTS idx_sponsorships_member;
DROP INDEX IF EXISTS idx_council_members_banana_status;
DROP INDEX IF EXISTS idx_council_members_status;
DROP INDEX IF EXISTS idx_council_members_normalized;
DROP INDEX IF EXISTS idx_council_members_banana;

-- Drop tables (sponsorships first due to FK)
DROP TABLE IF EXISTS sponsorships;
DROP TABLE IF EXISTS council_members;
