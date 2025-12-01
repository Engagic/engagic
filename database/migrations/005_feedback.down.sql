-- Rollback: 005_feedback
-- Removes feedback loop tables and columns

DROP TABLE IF EXISTS userland.issues;
DROP TABLE IF EXISTS userland.ratings;

-- Remove quality score columns (preserves data loss warning)
ALTER TABLE items DROP COLUMN IF EXISTS quality_score;
ALTER TABLE items DROP COLUMN IF EXISTS rating_count;
ALTER TABLE city_matters DROP COLUMN IF EXISTS quality_score;
ALTER TABLE city_matters DROP COLUMN IF EXISTS rating_count;
