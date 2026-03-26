-- Rollback migration 019: Revert jurisdictions back to cities

-- Drop the self-referencing FK
ALTER TABLE jurisdictions DROP CONSTRAINT IF EXISTS jurisdictions_county_banana_fkey;

-- Rename county_banana back to county
ALTER TABLE jurisdictions RENAME COLUMN county_banana TO county;

-- Drop the type column
ALTER TABLE jurisdictions DROP COLUMN IF EXISTS type;

-- Drop the type index
DROP INDEX IF EXISTS idx_jurisdictions_type;

-- Rename indexes back
ALTER INDEX jurisdictions_pkey RENAME TO cities_pkey;
ALTER INDEX jurisdictions_name_state_key RENAME TO cities_name_state_key;
ALTER INDEX idx_jurisdictions_geom RENAME TO idx_cities_geom;
ALTER INDEX idx_jurisdictions_population RENAME TO idx_cities_population;
ALTER INDEX idx_jurisdictions_state RENAME TO idx_cities_state;
ALTER INDEX idx_jurisdictions_status RENAME TO idx_cities_status;
ALTER INDEX idx_jurisdictions_vendor RENAME TO idx_cities_vendor;

-- Rename table back
ALTER TABLE jurisdictions RENAME TO cities;

-- Remove migration record
DELETE FROM schema_migrations WHERE version = '019';
