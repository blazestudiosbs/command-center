INSERT OR IGNORE INTO domain_policies
    (domain, risk_level, allowed_models_json, cloud_allowed,
     approval_required, max_request_usd, created_utc, updated_utc)
VALUES
    ('conversation', 'medium', '["local","gpt-4.1-mini"]', 1, 0, 0.02,
     strftime('%Y-%m-%dT%H:%M:%fZ', 'now'), strftime('%Y-%m-%dT%H:%M:%fZ', 'now'));
