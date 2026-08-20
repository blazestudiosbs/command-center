CREATE TABLE IF NOT EXISTS domain_policies (
    domain TEXT PRIMARY KEY,
    risk_level TEXT NOT NULL CHECK (risk_level IN ('low', 'medium', 'high', 'critical')),
    allowed_models_json TEXT NOT NULL,
    cloud_allowed INTEGER NOT NULL CHECK (cloud_allowed IN (0, 1)),
    approval_required INTEGER NOT NULL CHECK (approval_required IN (0, 1)),
    max_request_usd REAL NOT NULL CHECK (max_request_usd >= 0),
    created_utc TEXT NOT NULL,
    updated_utc TEXT NOT NULL
);

INSERT OR IGNORE INTO domain_policies
    (domain, risk_level, allowed_models_json, cloud_allowed,
     approval_required, max_request_usd, created_utc, updated_utc)
VALUES
    ('general', 'medium', '["local","gpt-4.1-mini"]', 1, 0, 0.05,
     strftime('%Y-%m-%dT%H:%M:%fZ', 'now'), strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    ('home', 'low', '["local","gpt-4.1-mini"]', 1, 0, 0.02,
     strftime('%Y-%m-%dT%H:%M:%fZ', 'now'), strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    ('family', 'high', '["local"]', 0, 1, 0.00,
     strftime('%Y-%m-%dT%H:%M:%fZ', 'now'), strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    ('development', 'high', '["local","gpt-4.1-mini"]', 1, 1, 0.10,
     strftime('%Y-%m-%dT%H:%M:%fZ', 'now'), strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    ('security', 'critical', '["local","gpt-4.1-mini"]', 1, 1, 0.05,
     strftime('%Y-%m-%dT%H:%M:%fZ', 'now'), strftime('%Y-%m-%dT%H:%M:%fZ', 'now'));
