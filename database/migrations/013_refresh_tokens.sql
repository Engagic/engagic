-- Migration: 013_refresh_tokens
-- Server-side refresh token storage for revocation support
-- Enables logout, security revocation, and token rotation

CREATE TABLE IF NOT EXISTS userland.refresh_tokens (
    token_hash TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES userland.users(id) ON DELETE CASCADE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    expires_at TIMESTAMPTZ NOT NULL,
    revoked_at TIMESTAMPTZ,
    revoked_reason TEXT
);

CREATE INDEX IF NOT EXISTS idx_refresh_tokens_user ON userland.refresh_tokens(user_id);
CREATE INDEX IF NOT EXISTS idx_refresh_tokens_expires ON userland.refresh_tokens(expires_at);

COMMENT ON TABLE userland.refresh_tokens IS 'Server-side refresh token storage for revocation support';
COMMENT ON COLUMN userland.refresh_tokens.revoked_at IS 'NULL = active, set = revoked';
COMMENT ON COLUMN userland.refresh_tokens.revoked_reason IS 'logout, rotation, security, etc.';
