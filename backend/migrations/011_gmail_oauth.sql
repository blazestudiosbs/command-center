CREATE TABLE IF NOT EXISTS gmail_connections (
    user_id TEXT PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
    email_address TEXT NOT NULL,
    encrypted_refresh_token TEXT NOT NULL,
    scopes_json TEXT NOT NULL,
    connected_utc TEXT NOT NULL,
    updated_utc TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS gmail_oauth_states (
    state TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    expires_utc TEXT NOT NULL,
    created_utc TEXT NOT NULL
);
