CREATE TABLE IF NOT EXISTS users (
    id TEXT PRIMARY KEY,
    username TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    role TEXT NOT NULL CHECK (role IN ('owner')),
    active INTEGER NOT NULL DEFAULT 1 CHECK (active IN (0, 1)),
    created_utc TEXT NOT NULL,
    updated_utc TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS sessions (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    token_hash TEXT NOT NULL UNIQUE,
    csrf_token TEXT NOT NULL,
    created_utc TEXT NOT NULL,
    expires_utc TEXT NOT NULL,
    last_seen_utc TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_sessions_token_hash
    ON sessions(token_hash);
CREATE INDEX IF NOT EXISTS idx_sessions_expires_utc
    ON sessions(expires_utc);
