CREATE TABLE IF NOT EXISTS infrastructure_agent_settings (
    id TEXT PRIMARY KEY CHECK (id = 'global'),
    security_updates_enabled INTEGER NOT NULL DEFAULT 1 CHECK (security_updates_enabled IN (0, 1)),
    health_checks_enabled INTEGER NOT NULL DEFAULT 1 CHECK (health_checks_enabled IN (0, 1)),
    automatic_reboot INTEGER NOT NULL DEFAULT 0 CHECK (automatic_reboot = 0),
    timezone TEXT NOT NULL DEFAULT 'America/Detroit',
    schedule TEXT NOT NULL DEFAULT 'Monday 03:00',
    updated_utc TEXT NOT NULL
);

INSERT OR IGNORE INTO infrastructure_agent_settings
    (id, security_updates_enabled, health_checks_enabled, automatic_reboot, timezone, schedule, updated_utc)
VALUES ('global', 1, 1, 0, 'America/Detroit', 'Monday 03:00', strftime('%Y-%m-%dT%H:%M:%fZ', 'now'));

CREATE TABLE IF NOT EXISTS infrastructure_agent_alert_state (
    id TEXT PRIMARY KEY CHECK (id = 'global'),
    issue_signature TEXT NOT NULL,
    updated_utc TEXT NOT NULL
);
