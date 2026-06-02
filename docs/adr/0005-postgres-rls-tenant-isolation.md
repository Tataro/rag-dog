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

## Implementation notes (learned while building 0002)

Two non-obvious facts make RLS work or silently fail, both discovered by the isolation test:

1. **The runtime connection must be a non-superuser, non-`BYPASSRLS` role.** `FORCE ROW LEVEL SECURITY` binds the table *owner* but never a superuser — and the default Docker `postgres` image makes `POSTGRES_USER` a superuser, which bypasses RLS entirely. So the app connects as a dedicated least-privilege role (`ragdog_app`, `NOSUPERUSER NOBYPASSRLS`, DML grants only), while migrations and admin/maintenance use the owner/superuser role. Two DSNs: `DATABASE_URL` (owner, migrations) and `APP_DATABASE_URL` (runtime). The 0002 migration creates the role idempotently; production provisions its password out-of-band.

2. **The policy predicate must be `NULLIF(current_setting('app.user_id', true), '')::uuid`.** A custom GUC reverts to an empty string (not `NULL`) after a transaction-local `set_config`, so on a pooled connection that previously served a request, an unset GUC yields `''` and a bare `::uuid` cast raises. `NULLIF(..., '')` maps the empty string back to `NULL`, preserving default-deny without an error.
