-- Migration: Add PostGIS geometry column to cities table
-- Run with: psql -U engagic -d engagic -f database/migrations/008_city_geometry.sql

-- Enable PostGIS extension (idempotent)
CREATE EXTENSION IF NOT EXISTS postgis;

-- Add geometry column for city boundaries
-- MultiPolygon: some Census places have discontiguous boundaries
-- SRID 4326: WGS84 lat/lng coordinate system
ALTER TABLE cities ADD COLUMN IF NOT EXISTS geom geometry(MultiPolygon, 4326);

-- Spatial index for efficient bounding box queries
CREATE INDEX IF NOT EXISTS idx_cities_geom ON cities USING GIST (geom);

-- Verify
SELECT
    column_name,
    udt_name,
    is_nullable
FROM information_schema.columns
WHERE table_name = 'cities' AND column_name = 'geom';
