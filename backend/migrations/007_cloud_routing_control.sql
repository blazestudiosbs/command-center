CREATE TABLE IF NOT EXISTS cloud_routing_state (
    id TEXT PRIMARY KEY CHECK (id = 'global'),
    enabled INTEGER NOT NULL DEFAULT 0 CHECK (enabled IN (0, 1)),
    changed_by_user_id TEXT REFERENCES users(id) ON DELETE SET NULL,
    reason TEXT NOT NULL DEFAULT '',
    version INTEGER NOT NULL DEFAULT 1 CHECK (version > 0),
    changed_utc TEXT NOT NULL
);

INSERT OR IGNORE INTO cloud_routing_state
    (id, enabled, reason, version, changed_utc)
VALUES
    ('global', 0, 'Cloud routing defaults to off', 1,
     strftime('%Y-%m-%dT%H:%M:%fZ', 'now'));
