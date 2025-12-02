-- Rollback Migration 003: Outcome Tracking
--
-- Reverses outcome tracking changes.
-- Note: Data in new columns will be lost.

-- Remove vote_outcome column
ALTER TABLE matter_appearances DROP COLUMN IF EXISTS vote_outcome;

-- Convert vote_tally back to TEXT
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'matter_appearances'
        AND column_name = 'vote_tally'
        AND data_type = 'jsonb'
    ) THEN
        ALTER TABLE matter_appearances DROP COLUMN vote_tally;
        ALTER TABLE matter_appearances ADD COLUMN vote_tally TEXT;
    END IF;
END $$;

-- Remove final_vote_date column
ALTER TABLE city_matters DROP COLUMN IF EXISTS final_vote_date;

-- Remove status constraint (revert to no constraint)
ALTER TABLE city_matters DROP CONSTRAINT IF EXISTS city_matters_status_check;
