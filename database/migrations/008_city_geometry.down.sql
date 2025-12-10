-- Rollback: Remove geometry column from cities table

DROP INDEX IF EXISTS idx_cities_geom;
ALTER TABLE cities DROP COLUMN IF EXISTS geom;

-- Note: PostGIS extension left in place (may be used elsewhere)
