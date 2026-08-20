CREATE TABLE IF NOT EXISTS budget_ledger (
    id TEXT PRIMARY KEY,
    mode TEXT NOT NULL CHECK (mode IN ('simulation', 'live')),
    domain TEXT NOT NULL,
    model TEXT NOT NULL,
    input_tokens INTEGER NOT NULL CHECK (input_tokens >= 0),
    output_tokens INTEGER NOT NULL CHECK (output_tokens >= 0),
    estimated_cost_usd REAL NOT NULL CHECK (estimated_cost_usd >= 0),
    actual_cost_usd REAL CHECK (actual_cost_usd IS NULL OR actual_cost_usd >= 0),
    decision TEXT NOT NULL CHECK (decision IN ('allow', 'block')),
    reason TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('simulated', 'completed', 'failed')),
    created_utc TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_budget_ledger_created
    ON budget_ledger(created_utc DESC);
CREATE INDEX IF NOT EXISTS idx_budget_ledger_mode_created
    ON budget_ledger(mode, created_utc DESC);
