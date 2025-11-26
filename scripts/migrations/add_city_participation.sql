-- Migration: Add participation column to cities table
-- Run on VPS: psql -U engagic -d engagic -f add_city_participation.sql

-- Add participation JSONB column for city-level participation config
-- This stores official testimony/contact info that replaces meeting-level parsing
-- for cities with centralized processes (e.g., NYC)
ALTER TABLE cities ADD COLUMN IF NOT EXISTS participation JSONB;

-- Seed NYC participation data
UPDATE cities
SET participation = '{
  "testimony_url": "https://council.nyc.gov/testify/",
  "testimony_email": "testimony@council.nyc.gov",
  "process_url": "https://council.nyc.gov/testify/"
}'::jsonb
WHERE banana = 'newyorkNY';
