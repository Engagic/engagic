-- Fix JSONB Data Migration Issue
--
-- Problem: Migration script stored JSON as TEXT strings in JSONB columns
-- Solution: Re-cast all JSONB columns from TEXT strings to proper JSONB
--
-- Run on VPS:
--   psql engagic -f scripts/fix_jsonb_data.sql
--
-- Expected: ~7,000-8,000 rows updated across 3 tables
-- Duration: ~1-2 seconds

BEGIN;

-- 1. Fix meetings.participation (JSONB object)
-- Current: '{"phone": "...", "email": "...", ...}' (TEXT string)
-- Target:  {"phone": "...", "email": "...", ...} (JSONB object)
UPDATE meetings
SET participation = participation::jsonb
WHERE participation IS NOT NULL
  AND jsonb_typeof(participation) IS NULL;  -- Only update if not already JSONB

-- 2. Fix agenda_items.attachments (JSONB array)
-- Current: '[{"url": "...", "title": "...", ...}, ...]' (TEXT string)
-- Target:  [{"url": "...", "title": "...", ...}, ...] (JSONB array)
UPDATE agenda_items
SET attachments = attachments::jsonb
WHERE attachments IS NOT NULL
  AND jsonb_typeof(attachments) IS NULL;

-- 3. Fix agenda_items.sponsors (JSONB array)
-- Current: '["Council Member Smith", "Mayor Jones"]' (TEXT string)
-- Target:  ["Council Member Smith", "Mayor Jones"] (JSONB array)
UPDATE agenda_items
SET sponsors = sponsors::jsonb
WHERE sponsors IS NOT NULL
  AND jsonb_typeof(sponsors) IS NULL;

-- 4. Fix city_matters.attachments (JSONB array)
UPDATE city_matters
SET attachments = attachments::jsonb
WHERE attachments IS NOT NULL
  AND jsonb_typeof(attachments) IS NULL;

-- 5. Fix city_matters.sponsors (JSONB array)
UPDATE city_matters
SET sponsors = sponsors::jsonb
WHERE sponsors IS NOT NULL
  AND jsonb_typeof(sponsors) IS NULL;

-- 6. Fix city_matters.metadata (JSONB object)
UPDATE city_matters
SET metadata = metadata::jsonb
WHERE metadata IS NOT NULL
  AND jsonb_typeof(metadata) IS NULL;

-- 7. Fix queue.payload (JSONB object)
UPDATE queue
SET payload = payload::jsonb
WHERE payload IS NOT NULL
  AND jsonb_typeof(payload) IS NULL;

-- 8. Fix queue.processing_metadata (JSONB object)
UPDATE queue
SET processing_metadata = processing_metadata::jsonb
WHERE processing_metadata IS NOT NULL
  AND jsonb_typeof(processing_metadata) IS NULL;

COMMIT;

-- Verification queries (run after commit)
-- Should return 0 if all data is properly JSONB now:
SELECT 'meetings.participation' as table_column,
       COUNT(*) as text_strings_remaining
FROM meetings
WHERE participation IS NOT NULL
  AND jsonb_typeof(participation) IS NULL;

SELECT 'agenda_items.attachments' as table_column,
       COUNT(*) as text_strings_remaining
FROM agenda_items
WHERE attachments IS NOT NULL
  AND jsonb_typeof(attachments) IS NULL;

SELECT 'agenda_items.sponsors' as table_column,
       COUNT(*) as text_strings_remaining
FROM agenda_items
WHERE sponsors IS NOT NULL
  AND jsonb_typeof(sponsors) IS NULL;

-- Summary
SELECT 'Fix complete!' as status,
       (SELECT COUNT(*) FROM meetings WHERE participation IS NOT NULL) as meetings_with_participation,
       (SELECT COUNT(*) FROM agenda_items WHERE attachments IS NOT NULL) as items_with_attachments,
       (SELECT COUNT(*) FROM agenda_items WHERE sponsors IS NOT NULL) as items_with_sponsors;
