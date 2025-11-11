-- Migration 002: Add Matter Tracking Fields
-- Enables tracking legislative items (bills, resolutions) across meetings
-- Foundation for Intelligence Layer: tracked items, deduplication, timeline view

-- Add matter tracking columns to items table
ALTER TABLE items ADD COLUMN matter_id TEXT;
ALTER TABLE items ADD COLUMN matter_file TEXT;
ALTER TABLE items ADD COLUMN agenda_number TEXT;

-- Create indices for efficient matter lookups
CREATE INDEX idx_items_matter_file ON items(matter_file) WHERE matter_file IS NOT NULL;
CREATE INDEX idx_items_matter_id ON items(matter_id) WHERE matter_id IS NOT NULL;

-- Migration notes:
-- - matter_id: Vendor-specific legislative ID (Legistar: EventItemMatterId)
-- - matter_file: City-wide bill number (e.g., "BL2025-1005", "RS2025-1591")
-- - agenda_number: Position on agenda (e.g., "E1", "K. 87", "A.")
--
-- Future: city_matters table will deduplicate summaries for same matter_file
-- appearing across multiple meetings (Planning, Finance, Council, etc.)
