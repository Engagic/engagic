-- Migration 015: Clean up orphaned item references after ID generation standardization
--
-- CONTEXT:
-- Item ID generation was centralized in database/id_generation.py. All adapters now
-- return vendor_item_id instead of generating final item IDs. The orchestrator
-- (meeting_sync.py) handles ID generation using generate_item_id().
--
-- This migration cleans up any orphaned references that may exist from previous
-- sync operations with inconsistent ID generation.
--
-- NOTE: This migration does NOT change existing item IDs. New syncs will generate
-- new IDs using the centralized function, which may result in duplicates until
-- old items expire or are cleaned up.

-- Step 1: Clean orphaned happening_items (items that no longer exist)
DELETE FROM happening_items h
WHERE NOT EXISTS (SELECT 1 FROM items i WHERE i.id = h.item_id);

-- Step 2: Clean orphaned happening_items (meetings that no longer exist)
DELETE FROM happening_items h
WHERE NOT EXISTS (SELECT 1 FROM meetings m WHERE m.id = h.meeting_id);

-- Step 3: Clean orphaned matter_appearances (items that no longer exist)
DELETE FROM matter_appearances ma
WHERE NOT EXISTS (SELECT 1 FROM items i WHERE i.id = ma.item_id);

-- Step 4: Clean orphaned matter_appearances (meetings that no longer exist)
DELETE FROM matter_appearances ma
WHERE NOT EXISTS (SELECT 1 FROM meetings m WHERE m.id = ma.meeting_id);

-- Step 5: Clean orphaned matter_appearances (matters that no longer exist)
DELETE FROM matter_appearances ma
WHERE NOT EXISTS (SELECT 1 FROM city_matters cm WHERE cm.id = ma.matter_id);

-- Step 6: Log orphan counts for diagnostics (run before DELETE to see scope)
-- Run manually: SELECT COUNT(*) FROM happening_items h WHERE NOT EXISTS (SELECT 1 FROM items i WHERE i.id = h.item_id);
