-- Add filter_reason column to items table
-- Stores why an item was skipped: 'procedural', 'ceremonial', 'administrative', or NULL
ALTER TABLE items ADD COLUMN IF NOT EXISTS filter_reason TEXT;
CREATE INDEX IF NOT EXISTS idx_items_filter_reason ON items(filter_reason) WHERE filter_reason IS NOT NULL;
