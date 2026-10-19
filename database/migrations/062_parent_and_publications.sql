-- Every public body is a jurisdictions row; parent_banana says who it belongs
-- to: the one government that created or controls it (a state board's state,
-- a city department's city, a grand jury's court). It is ownership, not
-- geography: TCEQ acts on Houston but belongs to Texas, and where a body acts
-- is already geom/state/county_banana. A city's council and its executive
-- agencies are siblings under the city's row, never one under the other.
-- Interstate compacts, nonprofit grid operators and independent districts have
-- no parent.
ALTER TABLE jurisdictions
    ADD COLUMN IF NOT EXISTS parent_banana TEXT REFERENCES jurisdictions (banana) ON UPDATE CASCADE ON DELETE SET NULL;
CREATE INDEX IF NOT EXISTS idx_jurisdictions_parent ON jurisdictions (parent_banana) WHERE parent_banana IS NOT NULL;

-- What a publications listing says about a document. A meeting attachment
-- takes its title and date from its item; a report on an agency's own page has
-- nothing else to carry them. Stored as the listing printed them: published_on
-- is NULL when the listing names no date, never a fetch or Last-Modified time.
ALTER TABLE document_source
    ADD COLUMN IF NOT EXISTS title TEXT,
    ADD COLUMN IF NOT EXISTS published_on DATE;

-- State governments, as parents for the state bodies already onboarded. They
-- publish no meetings of their own here (vendor 'none' is skipped by sync).
INSERT INTO jurisdictions (banana, name, state, vendor, slug, type) VALUES
    ('californiaCA', 'State of California', 'CA', 'none', 'none', 'state'),
    ('coloradoCO', 'State of Colorado', 'CO', 'none', 'none', 'state'),
    ('iowaIA', 'State of Iowa', 'IA', 'none', 'none', 'state'),
    ('minnesotaMN', 'State of Minnesota', 'MN', 'none', 'none', 'state'),
    ('northcarolinaNC', 'State of North Carolina', 'NC', 'none', 'none', 'state'),
    ('oregonOR', 'State of Oregon', 'OR', 'none', 'none', 'state'),
    ('texasTX', 'State of Texas', 'TX', 'none', 'none', 'state'),
    ('virginiaVA', 'Commonwealth of Virginia', 'VA', 'none', 'none', 'state'),
    ('washingtonWA', 'State of Washington', 'WA', 'none', 'none', 'state')
ON CONFLICT (banana) DO NOTHING;

UPDATE jurisdictions j SET parent_banana = p.parent
FROM (VALUES
    ('energycommissionCA', 'californiaCA'),
    ('deltastewardshipcouncilCA', 'californiaCA'),
    ('statewaterboardCA', 'californiaCA'),
    ('centralcoastwaterboardCA', 'californiaCA'),
    ('centralvalleywaterboardCA', 'californiaCA'),
    ('coloradoriverwaterboardCA', 'californiaCA'),
    ('lahontanwaterboardCA', 'californiaCA'),
    ('losangeleswaterboardCA', 'californiaCA'),
    ('northcoastwaterboardCA', 'californiaCA'),
    ('sandiegowaterboardCA', 'californiaCA'),
    ('sanfranciscobaywaterboardCA', 'californiaCA'),
    ('santaanawaterboardCA', 'californiaCA'),
    ('cwcbCO', 'coloradoCO'),
    ('opportunityiowaIA', 'iowaIA'),
    ('minnesotapucMN', 'minnesotaMN'),
    ('nc911boardNC', 'northcarolinaNC'),
    ('ncrecNC', 'northcarolinaNC'),
    ('oregonpucOR', 'oregonOR'),
    ('tceqTX', 'texasTX'),
    ('puctTX', 'texasTX'),
    ('virginiaairboardVA', 'virginiaVA'),
    ('virginiajailsboardVA', 'virginiaVA'),
    ('virginiaenergyVA', 'virginiaVA'),
    ('virginiawastemanagementboardVA', 'virginiaVA'),
    ('virginiaboardofconservationandrecreationVA', 'virginiaVA'),
    ('virginiadepartmentofforestryVA', 'virginiaVA'),
    ('virginiawildlifeboardVA', 'virginiaVA'),
    ('vmrcVA', 'virginiaVA'),
    ('virginiaboardofhealthVA', 'virginiaVA'),
    ('ctbvirginiaVA', 'virginiaVA'),
    ('virginiasafetyandhealthcodesboardVA', 'virginiaVA'),
    ('virginiawaterboardVA', 'virginiaVA'),
    ('utcWA', 'washingtonWA')
) AS p (banana, parent)
WHERE j.banana = p.banana AND j.parent_banana IS NULL;
