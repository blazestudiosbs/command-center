CREATE TABLE IF NOT EXISTS agent_permissions (
    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    agent_id TEXT NOT NULL,
    capability TEXT NOT NULL,
    enabled INTEGER NOT NULL CHECK (enabled IN (0, 1)),
    updated_utc TEXT NOT NULL,
    PRIMARY KEY (user_id, agent_id, capability)
);
