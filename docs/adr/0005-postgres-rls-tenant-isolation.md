# 0005 — Postgres Row-Level Security for tenant isolation

**Status**: Accepted
**Date**: 2026-06-02

## Context

[0004](0004-multi-user-production-pivot.md) makes rag-dog multi-user with private per-User Documents and Conversations. The worst failure this app can have is one User's Documents surfacing in another User's answers — and it would happen *silently*, on a retrieval path that happy-path tests don't exercise. We must decide where the `user_id` boundary is enforced.

- **Application-level filtering** — every query carries `WHERE user_id = :me`. Simple, but isolation is only as good as the one developer who remembers the clause on every query forever. A single missed `WHERE`, or a `JOIN` that drops it, leaks across tenants invisibly.
- **Postgres Row-Level Security** — the database enforces scoping via policies; the app sets the current User per transaction. A forgotten clause cannot leak, because the DB itself refuses to return other Users' rows.

## Decision

Enforce isolation with **Postgres RLS** on `documents`, `chunks`, `conversations`, `messages`, and any future User-owned table. Policies key off a per-transaction GUC (`app.user_id`) set from the authenticated session. Application code may still add filters for clarity, but correctness does not depend on it.

## Consequences

- A cross-tenant leak now requires actively disabling a database policy, not merely forgetting a line of code.
- The backend must reliably `SET LOCAL app.user_id` inside each request's transaction, and never reuse a pooled connection across Users mid-transaction. This is the one operational discipline RLS demands.
- Admin/maintenance jobs that legitimately span Users run under a role with `BYPASSRLS`, explicitly and narrowly — never the request-path role.
- Retrieval is now always a *filtered* vector query; the index implications are handled in the amendment to [0002](0002-dense-only-retrieval.md).
