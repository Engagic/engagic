-- Scans now cover every Census sheet (cities, counties, townships, school
-- districts), not just special districts; the table name follows.
ALTER TABLE district_scans RENAME TO census_unit_scans;
ALTER INDEX IF EXISTS idx_district_scans_passed RENAME TO idx_census_unit_scans_passed;

-- Which jurisdiction a Census unit is. It lives on the unit, not the scan: a
-- unit engagic already covers (matched by name) is linked without ever being
-- probed, and a unit onboarded from a scan gets the same link. One place
-- answers "is this government covered?".
ALTER TABLE census_government_units
    ADD COLUMN IF NOT EXISTS banana TEXT REFERENCES jurisdictions (banana) ON UPDATE CASCADE ON DELETE SET NULL,
    ADD COLUMN IF NOT EXISTS match_method TEXT;    -- name | onboarded
CREATE INDEX IF NOT EXISTS idx_census_units_banana ON census_government_units (banana);

UPDATE census_government_units u SET banana = s.banana, match_method = 'onboarded'
FROM census_unit_scans s WHERE s.census_id = u.census_id AND s.banana IS NOT NULL;
ALTER TABLE census_unit_scans DROP COLUMN banana;
