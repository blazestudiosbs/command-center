CREATE TABLE IF NOT EXISTS alexa_voice_sessions (
    session_id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    conversation_id TEXT NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    created_utc TEXT NOT NULL,
    updated_utc TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_alexa_voice_sessions_user_updated
ON alexa_voice_sessions(user_id, updated_utc DESC);
