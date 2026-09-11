-- 040: durable link from a meeting to its ingested minutes document(s).
-- scripts/ingest_minutes.py writes minutes bytes and text into the
-- content-addressed corpus (document_blob / document_source), but the only
-- way back to the meeting was document_source.source_identity ==
-- attachment_identity(meetings.minutes_url). That breaks the moment a vendor
-- moves the URL, and it cannot represent revisions: draft minutes are
-- replaced by approved minutes at the same URL with a different sha256.
-- One row per (meeting, content) keeps every revision; the newest
-- ingested_at is the current text for the roll-call parser.

CREATE TABLE IF NOT EXISTS minutes_documents (
    meeting_id TEXT NOT NULL REFERENCES meetings(id) ON DELETE CASCADE,
    content_sha256 TEXT NOT NULL REFERENCES document_blob(content_sha256) ON DELETE CASCADE,
    source_identity TEXT NOT NULL,
    ingested_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (meeting_id, content_sha256)
);

CREATE INDEX IF NOT EXISTS idx_minutes_documents_sha ON minutes_documents(content_sha256);
