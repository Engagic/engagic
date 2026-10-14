ALTER TABLE census_unit_scans ADD COLUMN IF NOT EXISTS banana TEXT REFERENCES jurisdictions (banana) ON UPDATE CASCADE ON DELETE SET NULL;
UPDATE census_unit_scans s SET banana = u.banana FROM census_government_units u
WHERE u.census_id = s.census_id AND u.match_method = 'onboarded';
DROP INDEX IF EXISTS idx_census_units_banana;
ALTER TABLE census_government_units DROP COLUMN IF EXISTS match_method, DROP COLUMN IF EXISTS banana;
ALTER INDEX IF EXISTS idx_census_unit_scans_passed RENAME TO idx_district_scans_passed;
ALTER TABLE census_unit_scans RENAME TO district_scans;
