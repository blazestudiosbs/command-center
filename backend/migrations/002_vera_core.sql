CREATE TABLE IF NOT EXISTS conversations (
    id TEXT PRIMARY KEY,
    owner_user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    title TEXT NOT NULL DEFAULT 'New conversation',
    archived INTEGER NOT NULL DEFAULT 0 CHECK (archived IN (0, 1)),
    created_utc TEXT NOT NULL,
    updated_utc TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_conversations_owner_updated
    ON conversations(owner_user_id, updated_utc DESC);

CREATE TABLE IF NOT EXISTS messages (
    id TEXT PRIMARY KEY,
    conversation_id TEXT NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    role TEXT NOT NULL CHECK (role IN ('user', 'assistant', 'system')),
    content TEXT NOT NULL,
    sequence INTEGER NOT NULL CHECK (sequence > 0),
    client_message_id TEXT,
    status TEXT NOT NULL DEFAULT 'complete'
        CHECK (status IN ('pending', 'complete', 'failed')),
    model TEXT,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    created_utc TEXT NOT NULL,
    UNIQUE(conversation_id, sequence),
    UNIQUE(conversation_id, client_message_id)
);

CREATE INDEX IF NOT EXISTS idx_messages_conversation_sequence
    ON messages(conversation_id, sequence);

CREATE TABLE IF NOT EXISTS control_state (
    id TEXT PRIMARY KEY CHECK (id = 'global'),
    mode TEXT NOT NULL CHECK (mode IN ('active', 'paused', 'emergency_stop')),
    changed_by_user_id TEXT REFERENCES users(id) ON DELETE SET NULL,
    reason TEXT NOT NULL DEFAULT '',
    version INTEGER NOT NULL DEFAULT 1 CHECK (version > 0),
    changed_utc TEXT NOT NULL
);

INSERT OR IGNORE INTO control_state (id, mode, reason, version, changed_utc)
VALUES ('global', 'active', 'Initial state', 1, strftime('%Y-%m-%dT%H:%M:%fZ', 'now'));

CREATE TABLE IF NOT EXISTS permissions (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    domain TEXT NOT NULL,
    capability TEXT NOT NULL,
    effect TEXT NOT NULL CHECK (effect IN ('allow', 'deny', 'approval_required')),
    created_utc TEXT NOT NULL,
    updated_utc TEXT NOT NULL,
    UNIQUE(user_id, domain, capability)
);

CREATE TABLE IF NOT EXISTS audit_events (
    id TEXT PRIMARY KEY,
    actor_user_id TEXT REFERENCES users(id) ON DELETE SET NULL,
    action TEXT NOT NULL,
    resource_type TEXT NOT NULL,
    resource_id TEXT,
    outcome TEXT NOT NULL CHECK (outcome IN ('allowed', 'denied', 'succeeded', 'failed')),
    request_id TEXT,
    details_json TEXT NOT NULL DEFAULT '{}',
    created_utc TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_audit_events_created
    ON audit_events(created_utc DESC);
CREATE INDEX IF NOT EXISTS idx_audit_events_resource
    ON audit_events(resource_type, resource_id, created_utc DESC);

CREATE TRIGGER IF NOT EXISTS audit_events_no_update
BEFORE UPDATE ON audit_events
BEGIN
    SELECT RAISE(ABORT, 'audit events are append-only');
END;

CREATE TRIGGER IF NOT EXISTS audit_events_no_delete
BEFORE DELETE ON audit_events
BEGIN
    SELECT RAISE(ABORT, 'audit events are append-only');
END;
