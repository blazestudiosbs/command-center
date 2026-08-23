CREATE TABLE IF NOT EXISTS release_approvals (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    branch TEXT NOT NULL,
    expected_head TEXT NOT NULL,
    snapshot_hash TEXT NOT NULL,
    files_json TEXT NOT NULL,
    commit_message TEXT NOT NULL,
    deploy_requested INTEGER NOT NULL CHECK (deploy_requested IN (0, 1)),
    status TEXT NOT NULL CHECK (status IN ('pending', 'executing', 'completed', 'failed', 'expired')),
    created_utc TEXT NOT NULL,
    expires_utc TEXT NOT NULL,
    completed_utc TEXT,
    commit_hash TEXT,
    error TEXT
);

CREATE INDEX IF NOT EXISTS idx_release_approvals_user_status
ON release_approvals(user_id, status, created_utc DESC);
