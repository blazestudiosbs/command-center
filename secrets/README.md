# Runtime secrets

Secret values are created directly on Command Center and are never committed.
`discord_bot_token` is mounted read-only into the isolated Vera Discord service.

## Gmail OAuth

The Gmail connection is read-only and requires a Google OAuth Web application with this authorized redirect URI:

`https://command-center.tail6031ec.ts.net/api/gmail/oauth/callback`

Store the OAuth client secret in `secrets/gmail_client_secret`. Generate the database token-encryption key once with:

`openssl rand -base64 32 | tr '+/' '-_'`

Store that output in `secrets/vera_token_encryption_key`. Never rotate or delete this key while Gmail is connected, or Vera will be unable to decrypt the stored refresh token. The OAuth client ID is not secret and belongs in `.env` as `GMAIL_CLIENT_ID`.
