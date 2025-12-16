-- Migration 014: Add FK constraints to happening_items
-- Prevents orphaned happening_items when meetings/items are deleted

-- Step 1: Clean up any orphaned happening_items before adding constraints
-- This prevents FK violation errors during constraint creation
DELETE FROM happening_items h
WHERE NOT EXISTS (SELECT 1 FROM meetings m WHERE m.id = h.meeting_id)
   OR NOT EXISTS (SELECT 1 FROM items i WHERE i.id = h.item_id);

-- Step 2: Add FK constraint for meeting_id
-- ON DELETE CASCADE: When meeting deleted, happening_items auto-deleted
ALTER TABLE happening_items
ADD CONSTRAINT fk_happening_meeting
FOREIGN KEY (meeting_id) REFERENCES meetings(id) ON DELETE CASCADE;

-- Step 3: Add FK constraint for item_id
-- ON DELETE CASCADE: When item deleted, happening_items auto-deleted
ALTER TABLE happening_items
ADD CONSTRAINT fk_happening_item
FOREIGN KEY (item_id) REFERENCES items(id) ON DELETE CASCADE;

COMMENT ON CONSTRAINT fk_happening_meeting ON happening_items IS 'Ensures happening_items reference valid meetings';
COMMENT ON CONSTRAINT fk_happening_item ON happening_items IS 'Ensures happening_items reference valid items';
