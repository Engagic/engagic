-- 041: give votes an item/motion grain, additively.
-- The original UNIQUE(council_member_id, matter_id, meeting_id) encodes the
-- vendor-API assumption of one roll call per matter per meeting. Minutes
-- routinely record several on one item (amend, then adopt; reconsider, then
-- adopt), and the roll-call parser must be able to store each one with a
-- byte-offset receipt. New columns default to the API shape (motion_index 0,
-- source 'api') so every existing writer keeps working unchanged.
--
-- Phase 1 (this file): columns + the finer unique index, old constraint kept.
-- Phase 2 (after every writer is restarted on code that targets the new
-- index): drop the old constraint so a second motion on the same matter can
-- be stored. Do not fold phase 2 in here: a running process on the old code
-- would fail its ON CONFLICT (council_member_id, matter_id, meeting_id).

ALTER TABLE votes ADD COLUMN IF NOT EXISTS item_id TEXT REFERENCES items(id) ON DELETE SET NULL;
ALTER TABLE votes ADD COLUMN IF NOT EXISTS motion_index SMALLINT NOT NULL DEFAULT 0;
ALTER TABLE votes ADD COLUMN IF NOT EXISTS motion_text TEXT;
ALTER TABLE votes ADD COLUMN IF NOT EXISTS source TEXT NOT NULL DEFAULT 'api'
    CHECK (source IN ('api', 'minutes'));
ALTER TABLE votes ADD COLUMN IF NOT EXISTS content_sha256 TEXT;
ALTER TABLE votes ADD COLUMN IF NOT EXISTS receipt JSONB;

CREATE UNIQUE INDEX IF NOT EXISTS uq_votes_member_matter_meeting_motion
    ON votes(council_member_id, matter_id, meeting_id, motion_index);
CREATE INDEX IF NOT EXISTS idx_votes_item ON votes(item_id) WHERE item_id IS NOT NULL;
