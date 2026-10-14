-- Which extractor versions' corpus text is readable, published by engagic for every
-- reader. Owned by corpus.store (EXTRACT_VERSION, COMPATIBLE_EXTRACT_VERSIONS): the
-- writer re-syncs these rows from its constants whenever it opens a pool with the corpus
-- on, so a version bump needs no edit in any other repo. Readers (motioncount) join this
-- table instead of keeping their own copy -- a copied list hid 58k v3 texts from them.
CREATE TABLE IF NOT EXISTS corpus_extract_versions (
    version TEXT PRIMARY KEY,
    readable BOOLEAN NOT NULL,
    is_current BOOLEAN NOT NULL DEFAULT FALSE,   -- the version new extractions are stamped with
    declared_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_corpus_extract_versions_current
    ON corpus_extract_versions (is_current) WHERE is_current;

INSERT INTO corpus_extract_versions (version, readable, is_current) VALUES
    ('1', TRUE, FALSE), ('2', TRUE, FALSE), ('3', TRUE, TRUE)
ON CONFLICT (version) DO NOTHING;
