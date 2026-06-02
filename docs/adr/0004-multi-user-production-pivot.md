# 0004 — Pivot to multi-user, self-hosted production (supersedes 0003)

**Status**: Accepted
**Date**: 2026-06-02

## Context

The POC proved out as single-user and local-first on a MacBook M4 (see 0001–0003). The owner now wants a product: a mobile app — alongside the existing web UI — where many people log in and keep their *own* private Documents and Conversations.

This breaks the assumption behind ADR 0003: that the only client is `localhost`, so the API needs no auth. It also outgrows the Mac as a host. We have to decide who runs inference, who may have an account, and how clients reach the backend.

## Decision

Pivot rag-dog from a single-user local POC to a **multi-user, self-hosted production service**.

- **Multi-user with strict per-User isolation.** Every Document, Chunk, and Conversation belongs to exactly one User.
- **Closed access (invite / admin allowlist).** A User exists only after an Admin allowlists their email — no open signup. This is the successor to 0003's chat-ID allowlist, and it protects scarce GPU time.
- **Google sign-in, verified by us.** Native Google Sign-In (mobile) and Google Identity Services (web) yield a Google ID token; the backend verifies it against Google's JWKS, upserts the User, and issues our *own* session JWT. No third-party auth provider — Users live in our Postgres.
- **The backend becomes a public, authenticated HTTPS API**, replacing 0003's "tunnel exposes webhooks only, web API is localhost-only." **0003 is superseded.**
- **Inference stays self-hosted on the owner's GPU servers** (not the Mac). Ollama is retained at the owner's request; "hundreds" means registered Users at low concurrency, which Ollama can serve. The backend calls generation through an **OpenAI-compatible client** so the serving layer can be swapped (e.g. vLLM) without code change if concurrency ever grows.
- **Original files move off local disk (`uploads/`) to self-hosted, S3-compatible object storage (MinIO)**, keyed by owner and served only through ownership-checked endpoints. The S3 API keeps a later move to cloud storage a config change.
- **Telegram and Line bots are descoped** for this launch — they need a Google↔chat-ID account-linking design. Web + mobile ship first.

## Consequences

- The tunnel ingress from 0003 is retired for the web path; only TLS termination plus the authenticated API remain. Bot account-linking is deferred, not abandoned.
- Isolation *enforcement* and per-User *retrieval* are their own decisions: see [0005](0005-postgres-rls-tenant-isolation.md) (RLS) and the amendment to [0002](0002-dense-only-retrieval.md).
- Mobile client choice: see [0006](0006-react-native-expo-mobile.md).
- The README's "single-user, local-first" framing and the `uploads/`-on-disk layout no longer hold and need rewriting.
