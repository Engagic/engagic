-- Migration 019: Rename cities to jurisdictions
-- Adds support for counties, utility boards, transit authorities, and any
-- public entity that publishes agendas.
--
-- Three changes:
-- 1. Rename table cities -> jurisdictions
-- 2. Add type column (TEXT, no CHECK -- validate in application layer)
-- 3. Rename county -> county_banana, add self-referencing FK

-- Step 1: Rename the table
ALTER TABLE cities RENAME TO jurisdictions;

-- Step 2: Add type column. All existing rows are cities.
ALTER TABLE jurisdictions ADD COLUMN type TEXT NOT NULL DEFAULT 'city';

-- Step 3: Rename county -> county_banana
ALTER TABLE jurisdictions RENAME COLUMN county TO county_banana;

-- Step 4: Add self-referencing FK for county_banana
-- The one existing value ('Cook') is a name, not a banana. NULL it out first.
UPDATE jurisdictions SET county_banana = NULL WHERE county_banana IS NOT NULL;
ALTER TABLE jurisdictions ADD CONSTRAINT jurisdictions_county_banana_fkey
    FOREIGN KEY (county_banana) REFERENCES jurisdictions(banana) ON DELETE SET NULL;

-- Step 5: Add index on type for filtered queries
CREATE INDEX idx_jurisdictions_type ON jurisdictions(type);

-- Step 6: Rename inherited indexes for clarity
ALTER INDEX cities_pkey RENAME TO jurisdictions_pkey;
ALTER INDEX cities_name_state_key RENAME TO jurisdictions_name_state_key;
ALTER INDEX idx_cities_geom RENAME TO idx_jurisdictions_geom;
ALTER INDEX idx_cities_population RENAME TO idx_jurisdictions_population;
ALTER INDEX idx_cities_state RENAME TO idx_jurisdictions_state;
ALTER INDEX idx_cities_status RENAME TO idx_jurisdictions_status;
ALTER INDEX idx_cities_vendor RENAME TO idx_jurisdictions_vendor;

-- Step 7: The unique constraint on (name, state) needs revisiting.
-- "Alameda" city and "Alameda County" can coexist: different names.
-- But if two entities have the same name and state (unlikely with the
-- collision convention), the banana PK already prevents duplicates.
-- Keep the constraint for now -- it's a useful safety net.

-- FK constraints from child tables automatically follow the table rename.
-- No need to drop/recreate them.

-- Record migration
INSERT INTO schema_migrations (version, name) VALUES ('019', 'jurisdictions');
