-- 042: make the child tables of city_matters actually deletable.
-- Live FKs from matter_topics, sponsorships, votes, matter_appearances and
-- deliberations onto city_matters were ON DELETE SET NULL against NOT NULL
-- columns, so deleting any matter with children failed outright while the
-- schema file documented CASCADE. A child row without its matter has no
-- meaning; the documented rule is the right one. items keeps SET NULL: an
-- agenda item outlives the aggregate it was linked to.
-- Scripts that move children between matters (relink_vendor_keyed_items,
-- migrate_matter_ids) copy first and delete the emptied parent last, so
-- cascade only ever removes rows already carried over.

ALTER TABLE matter_topics DROP CONSTRAINT IF EXISTS matter_topics_matter_id_fkey;
ALTER TABLE matter_topics ADD CONSTRAINT matter_topics_matter_id_fkey
    FOREIGN KEY (matter_id) REFERENCES city_matters(id) ON DELETE CASCADE;

ALTER TABLE sponsorships DROP CONSTRAINT IF EXISTS sponsorships_matter_id_fkey;
ALTER TABLE sponsorships ADD CONSTRAINT sponsorships_matter_id_fkey
    FOREIGN KEY (matter_id) REFERENCES city_matters(id) ON DELETE CASCADE;

ALTER TABLE votes DROP CONSTRAINT IF EXISTS votes_matter_id_fkey;
ALTER TABLE votes ADD CONSTRAINT votes_matter_id_fkey
    FOREIGN KEY (matter_id) REFERENCES city_matters(id) ON DELETE CASCADE;

ALTER TABLE matter_appearances DROP CONSTRAINT IF EXISTS matter_appearances_matter_id_fkey;
ALTER TABLE matter_appearances ADD CONSTRAINT matter_appearances_matter_id_fkey
    FOREIGN KEY (matter_id) REFERENCES city_matters(id) ON DELETE CASCADE;

ALTER TABLE deliberations DROP CONSTRAINT IF EXISTS deliberations_matter_id_fkey;
ALTER TABLE deliberations ADD CONSTRAINT deliberations_matter_id_fkey
    FOREIGN KEY (matter_id) REFERENCES city_matters(id) ON DELETE CASCADE;
