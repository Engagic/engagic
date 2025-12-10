-- Migration: Add population column to cities table
-- Run with: psql -U engagic -d engagic -f database/migrations/009_city_population.sql

ALTER TABLE cities ADD COLUMN IF NOT EXISTS population INTEGER;

-- Index for sorting/filtering by population
CREATE INDEX IF NOT EXISTS idx_cities_population ON cities (population DESC NULLS LAST);

-- Verify
SELECT column_name, data_type, is_nullable
FROM information_schema.columns
WHERE table_name = 'cities' AND column_name = 'population';
