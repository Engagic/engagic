-- Rollback Migration 014: Remove FK constraints from happening_items

ALTER TABLE happening_items DROP CONSTRAINT IF EXISTS fk_happening_meeting;
ALTER TABLE happening_items DROP CONSTRAINT IF EXISTS fk_happening_item;
