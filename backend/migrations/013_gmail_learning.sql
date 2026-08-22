CREATE TABLE IF NOT EXISTS gmail_classification_rules (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    match_type TEXT NOT NULL CHECK (match_type IN ('sender', 'domain')),
    match_value TEXT NOT NULL,
    category TEXT NOT NULL,
    source TEXT NOT NULL CHECK (source IN ('user', 'cloud_suggestion')),
    approved INTEGER NOT NULL CHECK (approved IN (0, 1)),
    created_utc TEXT NOT NULL,
    updated_utc TEXT NOT NULL,
    UNIQUE (user_id, match_type, match_value)
);

CREATE TABLE IF NOT EXISTS gmail_learning_settings (
    user_id TEXT PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
    cloud_review_enabled INTEGER NOT NULL DEFAULT 0 CHECK (cloud_review_enabled IN (0, 1)),
    monthly_budget_usd REAL NOT NULL DEFAULT 0.25 CHECK (monthly_budget_usd >= 0),
    weekly_message_limit INTEGER NOT NULL DEFAULT 20 CHECK (weekly_message_limit BETWEEN 0 AND 100),
    include_message_bodies INTEGER NOT NULL DEFAULT 0 CHECK (include_message_bodies IN (0, 1)),
    updated_utc TEXT NOT NULL
);
