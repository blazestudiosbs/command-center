CREATE TABLE IF NOT EXISTS gmail_cloud_review_batches (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    status TEXT NOT NULL CHECK (status IN ('completed', 'failed')),
    message_count INTEGER NOT NULL CHECK (message_count >= 0),
    estimated_cost_usd REAL NOT NULL CHECK (estimated_cost_usd >= 0),
    actual_cost_usd REAL CHECK (actual_cost_usd IS NULL OR actual_cost_usd >= 0),
    error TEXT,
    created_utc TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS gmail_cloud_suggestions (
    id TEXT PRIMARY KEY,
    batch_id TEXT NOT NULL REFERENCES gmail_cloud_review_batches(id) ON DELETE CASCADE,
    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    sender TEXT NOT NULL,
    suggested_category TEXT NOT NULL,
    reason TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'approved', 'rejected')),
    created_utc TEXT NOT NULL,
    decided_utc TEXT
);

CREATE INDEX IF NOT EXISTS idx_gmail_cloud_suggestions_user_status
    ON gmail_cloud_suggestions(user_id, status, created_utc DESC);

INSERT OR IGNORE INTO domain_policies
    (domain, risk_level, allowed_models_json, cloud_allowed,
     approval_required, max_request_usd, created_utc, updated_utc)
VALUES
    ('gmail', 'high', '["local","gpt-4.1-mini"]', 1, 0, 0.025,
     strftime('%Y-%m-%dT%H:%M:%fZ', 'now'), strftime('%Y-%m-%dT%H:%M:%fZ', 'now'));
