-- Migration 015 rollback: No-op
-- Deleted orphan records cannot be restored (they were invalid references anyway)
-- This is a data cleanup migration, not a schema change

SELECT 'No rollback possible for orphan cleanup - this is expected' AS info;
