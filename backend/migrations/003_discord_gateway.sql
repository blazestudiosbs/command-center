CREATE TABLE IF NOT EXISTS conversation_bindings (
    id TEXT PRIMARY KEY,
    conversation_id TEXT NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    provider TEXT NOT NULL CHECK (provider IN ('discord')),
    external_scope_id TEXT NOT NULL,
    external_channel_id TEXT NOT NULL,
    external_user_id TEXT,
    created_utc TEXT NOT NULL,
    updated_utc TEXT NOT NULL,
    UNIQUE(provider, external_scope_id, external_channel_id)
);

CREATE INDEX IF NOT EXISTS idx_conversation_bindings_conversation
    ON conversation_bindings(conversation_id);
