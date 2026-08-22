CREATE TABLE IF NOT EXISTS monitoring_notification_settings (
    id TEXT PRIMARY KEY CHECK (id = 'global'),
    alerts_enabled INTEGER NOT NULL CHECK (alerts_enabled IN (0, 1)),
    cooldown_seconds INTEGER NOT NULL CHECK (cooldown_seconds BETWEEN 0 AND 86400),
    updated_utc TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS monitoring_service_notification_preferences (
    container_name TEXT PRIMARY KEY,
    outage_alerts_enabled INTEGER NOT NULL CHECK (outage_alerts_enabled IN (0, 1)),
    recovery_alerts_enabled INTEGER NOT NULL CHECK (recovery_alerts_enabled IN (0, 1)),
    updated_utc TEXT NOT NULL
);
