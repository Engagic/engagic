-- Census of Governments units and what engagic learned probing their websites.
-- The Census list is the denominator for "every government body": a district
-- that is absent here was never looked at, one with a scan row was. Scans used
-- to live in a session scratchpad jsonl; the probe of ~11k district homepages
-- and the parse verdicts are too expensive to redo on every rerun, and the
-- next sweep (or the next Census vintage) resumes from these rows.
-- census_id is the Census's identity for its own row, never a jurisdiction
-- key: a unit becomes a jurisdiction through the selfhosted registry and the
-- banana, and district_scans.banana records that link once it exists.
CREATE TABLE IF NOT EXISTS census_government_units (
    census_id TEXT PRIMARY KEY,                 -- CENSUS_ID_PID6: present and unique on every row
    census_gidid TEXT,                          -- CENSUS_ID_GIDID: absent for 36 units new in 2022
    vintage INTEGER NOT NULL,                   -- Census of Governments year (2022)
    sheet TEXT NOT NULL,                        -- general | special | school | dependent_school
    unit_name TEXT NOT NULL,
    unit_type TEXT,                             -- UNIT_TYPE, FUNCTION_NAME or school level, verbatim
    state TEXT,                                 -- null on some inactive units
    city TEXT,
    county_area TEXT,
    fips_state TEXT,
    fips_county TEXT,
    web_address TEXT,                           -- verbatim, often a bare host
    web_host TEXT,                              -- lowercased host without www., for ownership checks
    population INTEGER,
    is_active BOOLEAN,
    loaded_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_census_units_state ON census_government_units (state);
CREATE INDEX IF NOT EXISTS idx_census_units_host ON census_government_units (web_host);

CREATE TABLE IF NOT EXISTS district_scans (
    census_id TEXT PRIMARY KEY REFERENCES census_government_units (census_id) ON DELETE CASCADE,
    -- Homepage probe: one fetch, which agenda vendors and meeting pages it links.
    probe_version INTEGER NOT NULL,
    probed_at TIMESTAMP NOT NULL,
    url TEXT NOT NULL,
    http_status INTEGER,
    final_url TEXT,
    error TEXT,
    vendors JSONB,                              -- {vendor: slug-or-true}
    meeting_links JSONB,                        -- candidate meeting/agenda pages
    -- Discovery: the selfhosted adapter's index parse of those pages.
    discovery_version INTEGER,
    tested_at TIMESTAMP,
    discovery_passed BOOLEAN,
    discovery_page TEXT,                        -- the page a registry entry is built from
    discovery_pages JSONB,                      -- per-page metrics and errors
    registry_slug TEXT,                         -- selfhosted_sites.json key once written
    banana TEXT REFERENCES jurisdictions (banana) ON UPDATE CASCADE ON DELETE SET NULL
);
CREATE INDEX IF NOT EXISTS idx_district_scans_passed ON district_scans (discovery_passed) WHERE discovery_passed;
