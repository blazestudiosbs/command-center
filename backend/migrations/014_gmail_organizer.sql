CREATE TABLE IF NOT EXISTS gmail_organizer_settings (
    user_id TEXT PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
    enabled INTEGER NOT NULL DEFAULT 0 CHECK (enabled IN (0, 1)),
    poll_interval_seconds INTEGER NOT NULL DEFAULT 300 CHECK (poll_interval_seconds BETWEEN 60 AND 3600),
    enabled_utc TEXT,
    updated_utc TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS gmail_organizer_processed (
    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    message_id TEXT NOT NULL,
    category TEXT NOT NULL,
    labels_json TEXT NOT NULL,
    processed_utc TEXT NOT NULL,
    PRIMARY KEY (user_id, message_id)
);
