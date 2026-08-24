CREATE TABLE IF NOT EXISTS managed_servers (
    id TEXT PRIMARY KEY,
    owner_user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    hostname TEXT NOT NULL,
    token_hash TEXT NOT NULL UNIQUE,
    enabled INTEGER NOT NULL DEFAULT 1 CHECK (enabled IN (0,1)),
    created_utc TEXT NOT NULL,
    updated_utc TEXT NOT NULL,
    last_seen_utc TEXT,
    agent_version TEXT,
    status_json TEXT
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_managed_servers_owner_hostname
ON managed_servers(owner_user_id, hostname);
