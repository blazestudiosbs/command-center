# Vera Alexa Relay

Cloudflare Worker that verifies Amazon Alexa custom-skill requests, translates them to Vera's private relay contract, and returns Alexa speech responses.

Required Worker secrets:

- `ALEXA_SKILL_ID`
- `COMMAND_CENTER_URL`
- `RELAY_SECRET`

Command Center remains behind an outbound-only Cloudflare Tunnel. The tunnel hostname must route only `/api/alexa/relay`; the signed gateway still rejects requests without a current HMAC signature.
