CREATE TABLE IF NOT EXISTS household_members (
    id TEXT PRIMARY KEY,
    user_id TEXT UNIQUE REFERENCES users(id) ON DELETE SET NULL,
    display_name TEXT NOT NULL,
    role TEXT NOT NULL CHECK (role IN ('owner','adult','child','guest')),
    status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active','disabled')),
    created_utc TEXT NOT NULL,
    updated_utc TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS household_voice_identities (
    id TEXT PRIMARY KEY,
    household_member_id TEXT NOT NULL REFERENCES household_members(id) ON DELETE CASCADE,
    provider TEXT NOT NULL,
    subject_hash TEXT NOT NULL,
    created_utc TEXT NOT NULL,
    updated_utc TEXT NOT NULL,
    UNIQUE(provider, subject_hash)
);

ALTER TABLE alexa_voice_sessions ADD COLUMN household_member_id TEXT
    REFERENCES household_members(id) ON DELETE CASCADE;

CREATE INDEX IF NOT EXISTS idx_household_voice_member
ON household_voice_identities(household_member_id, provider);
