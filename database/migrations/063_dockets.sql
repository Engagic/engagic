-- A docket is one proceeding in a commission's case system: a case number
-- under one body, with filings accumulating over months or years. It is the
-- docket system's container the way a meeting is an agenda's, and a filing is
-- its unit the way an item is a meeting's: a dated submission by one party,
-- carrying documents in the same attachments shape items use ([{url, name,
-- type}]). Originals live in the corpus under the same URLs, so
-- document_source joins to a filing exactly as it joins to an item.
-- Dockets are not meetings: they have no agenda, no body sitting on a date,
-- and nothing downstream that reads meetings should see them.
CREATE TABLE IF NOT EXISTS dockets (
    id TEXT PRIMARY KEY,                -- id_generation.generate_docket_id
    banana TEXT NOT NULL REFERENCES jurisdictions (banana) ON UPDATE CASCADE ON DELETE CASCADE,
    system TEXT NOT NULL,               -- data/docket_systems.json key (nydps, txpuc ...)
    case_key TEXT NOT NULL,             -- the system's own case identifier, as its URLs carry it
    docket_number TEXT,                 -- the number the commission prints, when the listing shows it
    title TEXT,                         -- the case caption, when the listing shows it
    url TEXT NOT NULL,                  -- the case page a person opens
    first_filed_on DATE,
    last_filed_on DATE,
    filing_count INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (system, case_key)
);
CREATE INDEX IF NOT EXISTS idx_dockets_banana ON dockets (banana, last_filed_on DESC);

CREATE TABLE IF NOT EXISTS docket_filings (
    id TEXT PRIMARY KEY,                -- id_generation.generate_docket_filing_id
    docket_id TEXT NOT NULL REFERENCES dockets (id) ON DELETE CASCADE,
    vendor_filing_id TEXT NOT NULL,     -- the system's identity for the filing
    sequence INTEGER NOT NULL,          -- position in filing order within the docket
    title TEXT NOT NULL,
    filing_type TEXT,                   -- as the system labels it (Testimony, Orders, ...)
    description TEXT,
    filer TEXT,
    filed_on DATE,
    attachments JSONB NOT NULL DEFAULT '[]',
    attachment_hash TEXT,               -- pipeline.utils.hash_attachments_fast
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (docket_id, vendor_filing_id)
);
CREATE INDEX IF NOT EXISTS idx_docket_filings_docket ON docket_filings (docket_id, sequence);
CREATE INDEX IF NOT EXISTS idx_docket_filings_filed ON docket_filings (filed_on);
