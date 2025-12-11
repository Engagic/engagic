-- Rollback FTS optimization

-- Drop the new indexes
DROP INDEX IF EXISTS idx_meetings_search_vector;
DROP INDEX IF EXISTS idx_items_search_vector;
DROP INDEX IF EXISTS idx_city_matters_search_vector;
DROP INDEX IF EXISTS idx_meetings_banana_date_covering;
DROP INDEX IF EXISTS idx_items_meeting_sequence;
DROP INDEX IF EXISTS idx_city_matters_banana_last_seen;

-- Drop the generated columns
ALTER TABLE meetings DROP COLUMN IF EXISTS search_vector;
ALTER TABLE items DROP COLUMN IF EXISTS search_vector;
ALTER TABLE city_matters DROP COLUMN IF EXISTS search_vector;
