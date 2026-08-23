CREATE TABLE IF NOT EXISTS backup_agent_settings (
    id TEXT PRIMARY KEY CHECK (id = 'global'),
    enabled INTEGER NOT NULL DEFAULT 1 CHECK (enabled IN (0, 1)),
    destination TEXT NOT NULL DEFAULT '/mnt/media/backups/command-center',
    schedule TEXT NOT NULL DEFAULT 'Daily 02:30',
    timezone TEXT NOT NULL DEFAULT 'America/Detroit',
    daily_retention INTEGER NOT NULL DEFAULT 14 CHECK (daily_retention BETWEEN 1 AND 90),
    weekly_retention INTEGER NOT NULL DEFAULT 8 CHECK (weekly_retention BETWEEN 1 AND 52),
    updated_utc TEXT NOT NULL
);

INSERT OR IGNORE INTO backup_agent_settings
    (id, enabled, destination, schedule, timezone, daily_retention, weekly_retention, updated_utc)
VALUES ('global', 1, '/mnt/media/backups/command-center', 'Daily 02:30', 'America/Detroit', 14, 8,
        strftime('%Y-%m-%dT%H:%M:%fZ', 'now'));

CREATE TABLE IF NOT EXISTS backup_agent_alert_state (
    id TEXT PRIMARY KEY CHECK (id = 'global'),
    status_signature TEXT NOT NULL,
    updated_utc TEXT NOT NULL
);
