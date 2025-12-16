-- Migration 017: Add FK constraints for userland tables
-- Fixes integrity gaps identified in post-mortem hardening review

-- Step 1: Clean up orphaned used_magic_links (user deleted but token record remains)
DELETE FROM userland.used_magic_links
WHERE user_id NOT IN (SELECT id FROM userland.users);

-- Step 2: Add FK constraint to used_magic_links
ALTER TABLE userland.used_magic_links
ADD CONSTRAINT fk_used_magic_links_user
FOREIGN KEY (user_id) REFERENCES userland.users(id) ON DELETE CASCADE;

-- Step 3: Clean up orphaned tracked_items.first_mentioned_meeting_id
UPDATE tracked_items
SET first_mentioned_meeting_id = NULL
WHERE first_mentioned_meeting_id IS NOT NULL
  AND first_mentioned_meeting_id NOT IN (SELECT id FROM meetings);

-- Step 4: Add FK constraint to tracked_items
ALTER TABLE tracked_items
ADD CONSTRAINT fk_tracked_items_first_meeting
FOREIGN KEY (first_mentioned_meeting_id) REFERENCES meetings(id) ON DELETE SET NULL;
