CREATE TABLE IF NOT EXISTS routing_decisions (
    id TEXT PRIMARY KEY,
    mode TEXT NOT NULL CHECK (mode = 'simulation'),
    domain TEXT NOT NULL,
    local_model TEXT NOT NULL,
    local_available INTEGER NOT NULL CHECK (local_available IN (0, 1)),
    local_confidence REAL NOT NULL CHECK (local_confidence >= 0 AND local_confidence <= 1),
    local_threshold REAL NOT NULL CHECK (local_threshold >= 0 AND local_threshold <= 1),
    input_tokens INTEGER NOT NULL CHECK (input_tokens >= 0),
    max_output_tokens INTEGER NOT NULL CHECK (max_output_tokens >= 0),
    cloud_model TEXT NOT NULL,
    estimated_cloud_cost_usd REAL NOT NULL CHECK (estimated_cloud_cost_usd >= 0),
    decision TEXT NOT NULL CHECK (
        decision IN ('local', 'would_escalate', 'approval_required', 'local_fallback', 'blocked')
    ),
    selected_provider TEXT CHECK (selected_provider IN ('local', 'openai')),
    selected_model TEXT,
    policy_effect TEXT,
    reason TEXT NOT NULL,
    cloud_call_made INTEGER NOT NULL DEFAULT 0 CHECK (cloud_call_made = 0),
    created_utc TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_routing_decisions_created
    ON routing_decisions(created_utc DESC);
CREATE INDEX IF NOT EXISTS idx_routing_decisions_domain_created
    ON routing_decisions(domain, created_utc DESC);
