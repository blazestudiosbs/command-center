CREATE TABLE calendar_change_requests_new (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    action TEXT NOT NULL CHECK (action IN ('create', 'edit', 'delete')),
    event_id TEXT,
    event_etag TEXT,
    payload_json TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('pending', 'executing', 'completed', 'failed', 'expired')),
    created_utc TEXT NOT NULL,
    expires_utc TEXT NOT NULL,
    completed_utc TEXT
);

INSERT INTO calendar_change_requests_new
SELECT * FROM calendar_change_requests;

DROP TABLE calendar_change_requests;
ALTER TABLE calendar_change_requests_new RENAME TO calendar_change_requests;

CREATE INDEX idx_calendar_changes_user_status
ON calendar_change_requests(user_id, status, created_utc DESC);
