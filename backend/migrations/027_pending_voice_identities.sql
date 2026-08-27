CREATE TABLE IF NOT EXISTS pending_household_voice_identities (
    id TEXT PRIMARY KEY,
    provider TEXT NOT NULL,
    subject_hash TEXT NOT NULL,
    first_seen_utc TEXT NOT NULL,
    last_seen_utc TEXT NOT NULL,
    seen_count INTEGER NOT NULL DEFAULT 1,
    UNIQUE(provider, subject_hash)
);

CREATE INDEX IF NOT EXISTS idx_pending_voice_last_seen
ON pending_household_voice_identities(last_seen_utc DESC);
