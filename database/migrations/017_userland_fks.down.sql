-- Rollback migration 017: Remove FK constraints

ALTER TABLE userland.used_magic_links
DROP CONSTRAINT IF EXISTS fk_used_magic_links_user;

ALTER TABLE tracked_items
DROP CONSTRAINT IF EXISTS fk_tracked_items_first_meeting;
