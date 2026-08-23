CREATE TABLE IF NOT EXISTS gmail_automation_rules (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    sender TEXT NOT NULL,
    action TEXT NOT NULL CHECK (action IN ('permanent_delete')),
    status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'active', 'rejected', 'paused')),
    match_existing INTEGER NOT NULL DEFAULT 1 CHECK (match_existing IN (0, 1)),
    validation_match_count INTEGER NOT NULL DEFAULT 0 CHECK (validation_match_count >= 0),
    validation_note TEXT NOT NULL,
    created_source TEXT NOT NULL,
    created_utc TEXT NOT NULL,
    decided_utc TEXT,
    last_run_utc TEXT,
    deleted_count INTEGER NOT NULL DEFAULT 0 CHECK (deleted_count >= 0),
    UNIQUE (user_id, sender, action)
);
