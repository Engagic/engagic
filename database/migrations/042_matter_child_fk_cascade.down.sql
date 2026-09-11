ALTER TABLE matter_topics DROP CONSTRAINT IF EXISTS matter_topics_matter_id_fkey;
ALTER TABLE matter_topics ADD CONSTRAINT matter_topics_matter_id_fkey
    FOREIGN KEY (matter_id) REFERENCES city_matters(id) ON DELETE SET NULL;
ALTER TABLE sponsorships DROP CONSTRAINT IF EXISTS sponsorships_matter_id_fkey;
ALTER TABLE sponsorships ADD CONSTRAINT sponsorships_matter_id_fkey
    FOREIGN KEY (matter_id) REFERENCES city_matters(id) ON DELETE SET NULL;
ALTER TABLE votes DROP CONSTRAINT IF EXISTS votes_matter_id_fkey;
ALTER TABLE votes ADD CONSTRAINT votes_matter_id_fkey
    FOREIGN KEY (matter_id) REFERENCES city_matters(id) ON DELETE SET NULL;
ALTER TABLE matter_appearances DROP CONSTRAINT IF EXISTS matter_appearances_matter_id_fkey;
ALTER TABLE matter_appearances ADD CONSTRAINT matter_appearances_matter_id_fkey
    FOREIGN KEY (matter_id) REFERENCES city_matters(id) ON DELETE SET NULL;
ALTER TABLE deliberations DROP CONSTRAINT IF EXISTS deliberations_matter_id_fkey;
ALTER TABLE deliberations ADD CONSTRAINT deliberations_matter_id_fkey
    FOREIGN KEY (matter_id) REFERENCES city_matters(id) ON DELETE SET NULL;
