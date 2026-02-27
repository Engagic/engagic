-- Remove filter_reason column from items table
DROP INDEX IF EXISTS idx_items_filter_reason;
ALTER TABLE items DROP COLUMN IF EXISTS filter_reason;
