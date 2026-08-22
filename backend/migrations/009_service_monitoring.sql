CREATE TABLE IF NOT EXISTS service_monitor_state (
    container_name TEXT PRIMARY KEY,
    display_name TEXT NOT NULL,
    status TEXT NOT NULL,
    detail TEXT,
    last_checked_utc TEXT NOT NULL,
    last_changed_utc TEXT NOT NULL,
    last_alerted_utc TEXT
);
