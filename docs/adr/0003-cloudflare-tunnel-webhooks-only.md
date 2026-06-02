# 0003 — Cloudflare Tunnel exposes only webhook paths

**Status**: Superseded by [0004](0004-multi-user-production-pivot.md)
**Date**: 2026-05-21

## Context

Line's Messaging API requires webhooks — it does not support long polling. Telegram supports both, but webhooks give the same model on both bots. So we need a public URL pointing at the local FastAPI service running on the M4.

The FastAPI service also serves the web UI's HTTP API on `/api/*`. The web UI has no authentication (single-user POC). If we expose the whole FastAPI through the tunnel, anyone who guesses the random `*.trycloudflare.com` URL can upload files and query our documents.

## Decision

Configure the Cloudflare Tunnel **ingress to forward only `/webhook/telegram` and `/webhook/line`** to `localhost:8000`. All other paths return 404 at the tunnel edge.

The web UI (Next.js) and the `/api/*` endpoints stay reachable only on `localhost`.

In addition, every webhook handler **verifies the platform signature** before processing:

- Telegram: `X-Telegram-Bot-Api-Secret-Token` matches our configured secret.
- Line: `X-Line-Signature` HMAC-SHA256 matches.

And we **allowlist** the user's own Telegram chat IDs and Line user IDs; messages from anyone else are dropped silently.

## Consequences

- The web UI cannot be used from a phone or a different machine. Adding remote web access is a real auth project, deferred until the POC has proved its worth.
- A leaked tunnel URL is not enough to do anything — the attacker also needs the Telegram secret token or Line channel secret, plus an allowlisted chat ID.
- Tunnel ingress config lives in `ops/cloudflared/config.yml`; changing what is publicly reachable is a one-file edit.
