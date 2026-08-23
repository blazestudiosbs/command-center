CREATE TABLE IF NOT EXISTS calendar_change_requests (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    action TEXT NOT NULL CHECK (action IN ('create', 'edit')),
    event_id TEXT,
    event_etag TEXT,
    payload_json TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('pending', 'executing', 'completed', 'failed', 'expired')),
    created_utc TEXT NOT NULL,
    expires_utc TEXT NOT NULL,
    completed_utc TEXT
);

CREATE INDEX IF NOT EXISTS idx_calendar_changes_user_status
ON calendar_change_requests(user_id, status, created_utc DESC);
