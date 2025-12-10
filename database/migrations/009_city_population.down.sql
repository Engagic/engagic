-- Rollback: Remove population column from cities table

DROP INDEX IF EXISTS idx_cities_population;
ALTER TABLE cities DROP COLUMN IF EXISTS population;
