CREATE TABLE IF NOT EXISTS home_light_permissions (
    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    entity_id TEXT NOT NULL,
    enabled INTEGER NOT NULL DEFAULT 0 CHECK (enabled IN (0,1)),
    updated_utc TEXT NOT NULL,
    PRIMARY KEY (user_id, entity_id)
);

CREATE TABLE IF NOT EXISTS home_light_action_requests (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    entity_id TEXT NOT NULL,
    action TEXT NOT NULL CHECK (action IN ('turn_on','turn_off')),
    entity_name TEXT NOT NULL,
    before_state TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('pending','executing','completed','failed','expired')),
    created_utc TEXT NOT NULL,
    expires_utc TEXT NOT NULL,
    completed_utc TEXT
);

CREATE INDEX IF NOT EXISTS idx_home_light_actions_user_status
ON home_light_action_requests(user_id, status, created_utc DESC);
