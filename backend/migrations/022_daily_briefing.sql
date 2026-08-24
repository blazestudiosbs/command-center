CREATE TABLE IF NOT EXISTS daily_briefing_settings (
    user_id TEXT PRIMARY KEY,
    enabled INTEGER NOT NULL DEFAULT 0 CHECK (enabled IN (0,1)),
    delivery_time TEXT NOT NULL DEFAULT '07:00',
    timezone TEXT NOT NULL DEFAULT 'America/Detroit',
    include_calendar INTEGER NOT NULL DEFAULT 1 CHECK (include_calendar IN (0,1)),
    include_gmail INTEGER NOT NULL DEFAULT 1 CHECK (include_gmail IN (0,1)),
    include_infrastructure INTEGER NOT NULL DEFAULT 1 CHECK (include_infrastructure IN (0,1)),
    include_backups INTEGER NOT NULL DEFAULT 1 CHECK (include_backups IN (0,1)),
    include_approvals INTEGER NOT NULL DEFAULT 1 CHECK (include_approvals IN (0,1)),
    last_sent_local_date TEXT,
    last_attempt_local_date TEXT,
    updated_utc TEXT NOT NULL
);

INSERT OR IGNORE INTO daily_briefing_settings
    (user_id,enabled,delivery_time,timezone,updated_utc)
VALUES ('owner',0,'07:00','America/Detroit',strftime('%Y-%m-%dT%H:%M:%fZ','now'));

CREATE TABLE IF NOT EXISTS daily_briefing_runs (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    mode TEXT NOT NULL CHECK (mode IN ('preview','manual','scheduled')),
    status TEXT NOT NULL CHECK (status IN ('generated','sent','failed','skipped')),
    summary_json TEXT NOT NULL,
    created_utc TEXT NOT NULL,
    sent_utc TEXT
);

CREATE INDEX IF NOT EXISTS idx_daily_briefing_runs_user_created
ON daily_briefing_runs(user_id, created_utc DESC);
