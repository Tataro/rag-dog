# Backend Multi-User Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn the single-user rag-dog backend into a multi-user service where each authenticated user (Google sign-in, closed allowlist) has database-enforced isolation of their Documents, Chunks, Conversations, and Messages.

**Architecture:** A new `users` + `allowed_emails` schema; Google ID tokens verified server-side and exchanged for our own HS256 session JWT; per-User data isolation enforced by **Postgres Row-Level Security** (FORCE RLS + policies keyed off a per-transaction `app.user_id` GUC), not by application `WHERE` clauses. Every request that touches user-owned data runs inside a short transaction that first sets `app.user_id`. Background ingestion is handed the owner id explicitly. Telegram/Line bots are descoped.

**Tech Stack:** Python 3.12, FastAPI, async SQLAlchemy 2 + asyncpg, Alembic, Postgres 16 + pgvector, `google-auth` (ID-token verification), `PyJWT` (session tokens), pytest + pytest-asyncio + httpx (tests run against a real Postgres test DB — RLS cannot be tested on SQLite).

> **Decision references:** ADR 0004 (multi-user pivot), ADR 0005 (RLS), ADR 0002 amendment (per-user retrieval). Glossary terms: User, Admin, Document, Chunk, Conversation, Channel.

> **⚠️ Destructive step, called out deliberately:** Task 4's migration **deletes all existing `documents`/`chunks`/`conversations`/`messages` rows** before adding the `NOT NULL user_id` columns. The POC's data is disposable test data with no owner; there is no sane user to backfill it to. If a reviewer's DB contains data worth keeping, stop and reconsider before running this migration.

---

## Prerequisites (one-time, manual)

Before Task 2, create the Postgres test database the harness uses:

```bash
# From a shell with psql access to the same Postgres in docker-compose:
createdb -h localhost -U ragdog ragdog_test   # password: ragdog
# or: docker exec -it ragdog-postgres createdb -U ragdog ragdog_test
```

The test harness applies migrations to this DB automatically; it never touches the dev DB.

---

## Task 1: Dependencies, config, and pinned pgvector image

**Files:**
- Modify: `backend/pyproject.toml:6-20` (add deps) and `:22-27` (dev deps)
- Modify: `backend/app/config.py:29-49` (add auth settings + helpers)
- Modify: `docker-compose.yml:3` (pin pgvector ≥ 0.8)
- Test: `backend/tests/test_config.py`

- [ ] **Step 1: Add runtime + dev dependencies**

In `backend/pyproject.toml`, add to `dependencies`:

```toml
    "google-auth>=2.35.0",
    "pyjwt>=2.9.0",
```

Add to `[dependency-groups].dev`:

```toml
    "pytest-asyncio>=0.24.0",
    "anyio>=4.6.0",
```

(`pytest-asyncio` is already present; ensure `anyio` is there for `httpx` ASGI transport.) Then run:

```bash
cd backend && uv sync
```

- [ ] **Step 2: Pin the pgvector image to a version that has iterative scans**

In `docker-compose.yml`, change line 3 from:

```yaml
    image: pgvector/pgvector:pg16
```

to:

```yaml
    image: pgvector/pgvector:0.8.0-pg16
```

(ADR 0002 amendment: iterative index scans require pgvector ≥ 0.8; the floating `:pg16` tag does not guarantee the version.)

- [ ] **Step 3: Write the failing config test**

Create `backend/tests/test_config.py`:

```python
from app.config import Settings


def test_google_client_ids_parsed_as_list():
    s = Settings(google_client_ids="web.apps.googleusercontent.com, mobile.apps.googleusercontent.com")
    assert s.google_client_id_list == [
        "web.apps.googleusercontent.com",
        "mobile.apps.googleusercontent.com",
    ]


def test_bootstrap_admins_lowercased_set():
    s = Settings(bootstrap_admin_emails="Boss@Example.com")
    assert s.bootstrap_admin_set == {"boss@example.com"}
```

- [ ] **Step 4: Run it to verify it fails**

Run: `cd backend && uv run pytest tests/test_config.py -v`
Expected: FAIL with `AttributeError` (no `google_client_id_list` / `bootstrap_admin_set`).

- [ ] **Step 5: Add the settings + helpers**

In `backend/app/config.py`, add fields after line 37 (`cors_origins`):

```python
    google_client_ids: str = ""  # comma-separated OAuth client IDs (web + mobile) accepted as token audience
    session_jwt_secret: str = "dev-insecure-change-me"
    session_jwt_ttl_seconds: int = 60 * 60 * 24 * 30  # 30 days
    bootstrap_admin_emails: str = ""  # comma-separated; implicitly allowed + admin on first login
```

Add properties alongside the existing ones (after line 49):

```python
    @property
    def google_client_id_list(self) -> list[str]:
        return [x.strip() for x in self.google_client_ids.split(",") if x.strip()]

    @property
    def bootstrap_admin_set(self) -> set[str]:
        return {x.strip().lower() for x in self.bootstrap_admin_emails.split(",") if x.strip()}
```

- [ ] **Step 6: Run it to verify it passes**

Run: `cd backend && uv run pytest tests/test_config.py -v`
Expected: PASS (2 passed).

- [ ] **Step 7: Commit**

```bash
git add backend/pyproject.toml backend/uv.lock backend/app/config.py backend/tests/test_config.py docker-compose.yml
git commit -m "feat(backend): add auth deps and config, pin pgvector 0.8"
```

---

## Task 2: Test harness against a real Postgres

**Files:**
- Create: `backend/tests/conftest.py`
- Test: `backend/tests/test_harness.py`

- [ ] **Step 1: Write the conftest**

Create `backend/tests/conftest.py`. It points the app at the test DB **before** importing app modules, applies migrations once per session, and truncates between tests.

```python
import os

# Must run before any `app.*` import so pydantic-settings reads the test values.
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://ragdog:ragdog@localhost:5432/ragdog_test")
os.environ.setdefault("SESSION_JWT_SECRET", "test-secret")
os.environ.setdefault("GOOGLE_CLIENT_IDS", "test-client.apps.googleusercontent.com")
os.environ.setdefault("BOOTSTRAP_ADMIN_EMAILS", "boss@example.com")

import pytest
import pytest_asyncio
from alembic import command
from alembic.config import Config
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text

from app.db import SessionLocal, engine
from app.main import app

_USER_TABLES = ["messages", "conversations", "chunks", "documents", "allowed_emails", "users"]


@pytest.fixture(scope="session", autouse=True)
def _migrate():
    cfg = Config("alembic.ini")
    command.upgrade(cfg, "head")
    yield


@pytest_asyncio.fixture(autouse=True)
async def _clean_tables():
    async with engine.begin() as conn:
        await conn.execute(text("TRUNCATE " + ", ".join(_USER_TABLES) + " RESTART IDENTITY CASCADE"))
    yield


@pytest_asyncio.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest_asyncio.fixture
async def session():
    async with SessionLocal() as s:
        yield s
```

- [ ] **Step 2: Write a harness smoke test**

Create `backend/tests/test_harness.py`:

```python
import pytest


@pytest.mark.asyncio
async def test_health_ok(client):
    resp = await client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}
```

- [ ] **Step 3: Run it to verify it fails or errors meaningfully**

Run: `cd backend && uv run pytest tests/test_harness.py -v`
Expected at this point: PASS (health route already exists and migrations only create the 0001 schema). If it errors with a connection failure, the `ragdog_test` DB was not created — see Prerequisites.

- [ ] **Step 4: Confirm the truncate fixture tolerates the not-yet-existing tables**

`users`/`allowed_emails` don't exist until Task 4. Until then, adjust `_USER_TABLES` to only the existing four for this commit:

```python
_USER_TABLES = ["messages", "conversations", "chunks", "documents"]
```

(We restore `users`/`allowed_emails` in Task 4, Step 6.)

- [ ] **Step 5: Run again to verify pass**

Run: `cd backend && uv run pytest tests/test_harness.py -v`
Expected: PASS (1 passed).

- [ ] **Step 6: Commit**

```bash
git add backend/tests/conftest.py backend/tests/test_harness.py
git commit -m "test(backend): add Postgres-backed async test harness"
```

---

## Task 3: User and ownership models

**Files:**
- Modify: `backend/app/models.py` (add `User`, `AllowedEmail`; add `user_id` to `Document`, `Chunk`, `Conversation`, `Message`; relax Conversation constraint)
- Test: `backend/tests/test_models.py`

- [ ] **Step 1: Write the failing model test**

Create `backend/tests/test_models.py`:

```python
from app.models import AllowedEmail, Chunk, Conversation, Document, Message, User


def test_user_model_columns():
    cols = set(User.__table__.columns.keys())
    assert {"id", "email", "name", "picture", "is_admin", "created_at"} <= cols


def test_ownership_columns_present():
    for model in (Document, Chunk, Conversation, Message):
        assert "user_id" in model.__table__.columns, f"{model.__name__} missing user_id"


def test_allowed_email_pk_is_email():
    assert AllowedEmail.__table__.primary_key.columns.keys() == ["email"]
```

- [ ] **Step 2: Run it to verify it fails**

Run: `cd backend && uv run pytest tests/test_models.py -v`
Expected: FAIL with `ImportError` (no `User`/`AllowedEmail`).

- [ ] **Step 3: Add the models and ownership columns**

In `backend/app/models.py`, add these classes (after the imports, before `Document`):

```python
class User(Base):
    __tablename__ = "users"

    id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=uuid4)
    email: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    name: Mapped[str | None] = mapped_column(Text, nullable=True)
    picture: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_admin: Mapped[bool] = mapped_column(default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class AllowedEmail(Base):
    __tablename__ = "allowed_emails"

    email: Mapped[str] = mapped_column(Text, primary_key=True)
    added_by: Mapped[UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
```

You'll need `Boolean` import behavior — `Mapped[bool]` maps automatically, no extra import. Add `from sqlalchemy import Boolean` is **not** required.

Add `user_id` to each owned model. In `Document` (after line 27 `id`):

```python
    user_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
```

In `Chunk` (after its `id`):

```python
    user_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
```

In `Conversation` (after its `id`), and **remove** the `UniqueConstraint("channel", "external_id", ...)` from `__table_args__` (conversations are now User-owned, not keyed by channel+external_id), making `external_id` nullable:

```python
    user_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
```

Change `external_id` to nullable:

```python
    external_id: Mapped[str | None] = mapped_column(Text, nullable=True)
```

And change `__table_args__` to:

```python
    __table_args__ = (Index("conversations_user_time", "user_id", "created_at"),)
```

In `Message` (after its `id`):

```python
    user_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
```

- [ ] **Step 4: Run it to verify it passes**

Run: `cd backend && uv run pytest tests/test_models.py -v`
Expected: PASS (3 passed).

- [ ] **Step 5: Commit**

```bash
git add backend/app/models.py backend/tests/test_models.py
git commit -m "feat(backend): add User/AllowedEmail models and user_id ownership"
```

---

## Task 4: Migration — schema, data wipe, and RLS policies

> **Implementation delta (found during execution — RLS would otherwise be silently bypassed):**
> 1. The app must connect as a **non-superuser** role or `FORCE` RLS does nothing (the Docker `postgres` superuser bypasses it). The 0002 migration also creates a least-privilege `ragdog_app` role (idempotent) with DML grants; `app/config.py` gains `app_database_url` and `app/db.py`'s engine uses it, while migrations/admin keep `database_url`. `conftest.py` sets `APP_DATABASE_URL` and truncates via a separate admin engine. See ADR 0005 "Implementation notes."
> 2. The policy predicate must be `user_id = NULLIF(current_setting('app.user_id', true), '')::uuid` (a custom GUC reverts to `''`, not NULL, after a transaction-local set on a pooled connection; `''::uuid` raises).
> 3. `pyproject.toml` sets `asyncio_default_fixture_loop_scope = "session"` / `asyncio_default_test_loop_scope = "session"` so the async engine pools stay bound to one loop across tests.

**Files:**
- Create: `backend/alembic/versions/0002_multi_user_rls.py`
- Modify: `backend/tests/conftest.py:` (restore full `_USER_TABLES`)
- Test: `backend/tests/test_migration_rls.py`

- [ ] **Step 1: Write the migration**

Create `backend/alembic/versions/0002_multi_user_rls.py`:

```python
"""multi-user: users, ownership columns, and RLS

Revision ID: 0002_multi_user_rls
Revises: 0001_init
Create Date: 2026-06-02
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0002_multi_user_rls"
down_revision: Union[str, None] = "0001_init"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_OWNED = ["documents", "chunks", "conversations", "messages"]


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("email", sa.Text(), nullable=False, unique=True),
        sa.Column("name", sa.Text(), nullable=True),
        sa.Column("picture", sa.Text(), nullable=True),
        sa.Column("is_admin", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_table(
        "allowed_emails",
        sa.Column("email", sa.Text(), primary_key=True),
        sa.Column("added_by", sa.dialects.postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )

    # ⚠️ Disposable POC data has no owner; wipe before adding NOT NULL user_id.
    op.execute("DELETE FROM messages")
    op.execute("DELETE FROM conversations")
    op.execute("DELETE FROM chunks")
    op.execute("DELETE FROM documents")

    for tbl in _OWNED:
        op.add_column(
            tbl,
            sa.Column("user_id", sa.dialects.postgresql.UUID(as_uuid=True),
                      sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        )
        op.create_index(f"{tbl}_user_id_idx", tbl, ["user_id"])

    # Conversations are no longer keyed by (channel, external_id).
    op.drop_constraint("uq_conversations_channel_external", "conversations", type_="unique")
    op.alter_column("conversations", "external_id", nullable=True)
    op.create_index("conversations_user_time", "conversations", ["user_id", "created_at"])

    # RLS: force it even for the table owner, default-deny when app.user_id is unset.
    for tbl in _OWNED:
        op.execute(f"ALTER TABLE {tbl} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {tbl} FORCE ROW LEVEL SECURITY")
        op.execute(
            f"""
            CREATE POLICY {tbl}_isolation ON {tbl}
            USING (user_id = current_setting('app.user_id', true)::uuid)
            WITH CHECK (user_id = current_setting('app.user_id', true)::uuid)
            """
        )


def downgrade() -> None:
    for tbl in _OWNED:
        op.execute(f"DROP POLICY IF EXISTS {tbl}_isolation ON {tbl}")
        op.execute(f"ALTER TABLE {tbl} NO FORCE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {tbl} DISABLE ROW LEVEL SECURITY")
    op.drop_index("conversations_user_time", table_name="conversations")
    op.alter_column("conversations", "external_id", nullable=False)
    op.create_unique_constraint(
        "uq_conversations_channel_external", "conversations", ["channel", "external_id"]
    )
    for tbl in _OWNED:
        op.drop_index(f"{tbl}_user_id_idx", table_name=tbl)
        op.drop_column(tbl, "user_id")
    op.drop_table("allowed_emails")
    op.drop_table("users")
```

- [ ] **Step 2: Restore the full truncate list in conftest**

In `backend/tests/conftest.py`, change `_USER_TABLES` back to:

```python
_USER_TABLES = ["messages", "conversations", "chunks", "documents", "allowed_emails", "users"]
```

- [ ] **Step 3: Write the RLS isolation test (raw SQL, no app layer yet)**

Create `backend/tests/test_migration_rls.py`:

```python
import uuid

import pytest
from sqlalchemy import text

from app.db import SessionLocal


async def _make_user(s, email):
    uid = uuid.uuid4()
    await s.execute(text("INSERT INTO users (id, email) VALUES (:id, :email)"),
                    {"id": uid, "email": email})
    return uid


@pytest.mark.asyncio
async def test_rls_blocks_cross_user_reads():
    async with SessionLocal() as s:
        u1 = await _make_user(s, "a@example.com")
        u2 = await _make_user(s, "b@example.com")
        await s.commit()

    # u1 inserts a document under its own GUC.
    async with SessionLocal() as s:
        await s.execute(text("SELECT set_config('app.user_id', :uid, true)"), {"uid": str(u1)})
        await s.execute(
            text("""INSERT INTO documents (id, user_id, filename, mime_type, size_bytes,
                    storage_path, status) VALUES (:id, :uid, 'a.pdf', 'application/pdf', 1, 'x', 'ready')"""),
            {"id": uuid.uuid4(), "uid": str(u1)},
        )
        await s.commit()

    # u2 must see zero documents; u1 must see one.
    async with SessionLocal() as s:
        await s.execute(text("SELECT set_config('app.user_id', :uid, true)"), {"uid": str(u2)})
        assert (await s.execute(text("SELECT count(*) FROM documents"))).scalar_one() == 0
    async with SessionLocal() as s:
        await s.execute(text("SELECT set_config('app.user_id', :uid, true)"), {"uid": str(u1)})
        assert (await s.execute(text("SELECT count(*) FROM documents"))).scalar_one() == 1


@pytest.mark.asyncio
async def test_rls_default_denies_without_guc():
    async with SessionLocal() as s:
        # No app.user_id set → current_setting(...,true) is NULL → no rows visible.
        assert (await s.execute(text("SELECT count(*) FROM documents"))).scalar_one() == 0
```

- [ ] **Step 4: Run to verify the migration applies and isolation holds**

Run: `cd backend && uv run pytest tests/test_migration_rls.py -v`
Expected: PASS (2 passed). The session-scoped `_migrate` fixture applies `0002` to the test DB. If migration errors, read the Alembic traceback before proceeding.

- [ ] **Step 5: Apply the migration to the dev DB**

Run: `cd backend && uv run alembic upgrade head`
Expected: `Running upgrade 0001_init -> 0002_multi_user_rls`.

- [ ] **Step 6: Commit**

```bash
git add backend/alembic/versions/0002_multi_user_rls.py backend/tests/conftest.py backend/tests/test_migration_rls.py
git commit -m "feat(backend): migration for users, ownership, and FORCE RLS policies"
```

---

## Task 5: Google ID-token verification and session JWT

**Files:**
- Create: `backend/app/security/google.py`
- Create: `backend/app/security/session.py`
- Test: `backend/tests/test_session_token.py`

- [ ] **Step 1: Write the session-token test**

Create `backend/tests/test_session_token.py`:

```python
import uuid

import pytest

from app.security.session import decode_session_token, issue_session_token


def test_roundtrip_session_token():
    uid = uuid.uuid4()
    token = issue_session_token(uid)
    payload = decode_session_token(token)
    assert payload["sub"] == str(uid)


def test_tampered_token_rejected():
    uid = uuid.uuid4()
    token = issue_session_token(uid)
    with pytest.raises(Exception):
        decode_session_token(token + "x")
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd backend && uv run pytest tests/test_session_token.py -v`
Expected: FAIL with `ModuleNotFoundError: app.security.session`.

- [ ] **Step 3: Implement the session-token module**

Create `backend/app/security/session.py`:

```python
"""Our own HS256 session tokens, issued after Google sign-in is verified."""
import time
from uuid import UUID

import jwt

from ..config import settings


def issue_session_token(user_id: UUID) -> str:
    now = int(time.time())
    payload = {
        "sub": str(user_id),
        "iat": now,
        "exp": now + settings.session_jwt_ttl_seconds,
    }
    return jwt.encode(payload, settings.session_jwt_secret, algorithm="HS256")


def decode_session_token(token: str) -> dict:
    """Returns the payload, or raises jwt.PyJWTError on invalid/expired token."""
    return jwt.decode(token, settings.session_jwt_secret, algorithms=["HS256"])
```

- [ ] **Step 4: Implement the Google verification module**

Create `backend/app/security/google.py`:

```python
"""Verify Google ID tokens (from native mobile sign-in and web GIS)."""
from fastapi.concurrency import run_in_threadpool
from google.auth.transport import requests as google_requests
from google.oauth2 import id_token

from ..config import settings

_request = google_requests.Request()


class GoogleAuthError(Exception):
    pass


async def verify_google_id_token(token: str) -> dict:
    """Return the verified claims dict, or raise GoogleAuthError.

    google-auth validates the signature, issuer, and expiry. We additionally
    check the audience against our configured client IDs (web + mobile) and
    require a verified email.
    """
    def _verify() -> dict:
        return id_token.verify_oauth2_token(token, _request)

    try:
        info = await run_in_threadpool(_verify)
    except Exception as exc:  # ValueError from google-auth on any failure
        raise GoogleAuthError(str(exc)) from exc

    if info.get("aud") not in settings.google_client_id_list:
        raise GoogleAuthError("token audience not in allowed client IDs")
    if not info.get("email_verified"):
        raise GoogleAuthError("email not verified by Google")
    if not info.get("email"):
        raise GoogleAuthError("token has no email claim")
    return info
```

- [ ] **Step 5: Run the session-token test to verify pass**

Run: `cd backend && uv run pytest tests/test_session_token.py -v`
Expected: PASS (2 passed). (`google.py` is exercised in Task 7 via a mocked verifier; it does network I/O so it isn't unit-tested directly here.)

- [ ] **Step 6: Commit**

```bash
git add backend/app/security/google.py backend/app/security/session.py backend/tests/test_session_token.py
git commit -m "feat(backend): Google ID-token verification and session JWT"
```

---

## Task 6: Auth dependencies and the RLS-bound session

**Files:**
- Modify: `backend/app/db.py` (add `user_session` context manager)
- Create: `backend/app/deps.py` (`get_current_user`, `get_current_admin`, `get_user_session`)
- Test: `backend/tests/test_deps.py`

- [ ] **Step 1: Add the `user_session` context manager**

In `backend/app/db.py`, append:

```python
from contextlib import asynccontextmanager
from uuid import UUID

from sqlalchemy import text


@asynccontextmanager
async def user_session(user_id: UUID):
    """A short transaction with app.user_id set, so RLS policies apply.

    Use for any access to user-owned tables. Keep the body short — do not hold
    this open across slow network calls (LLM/embeddings); see generation/ingestion
    for the split-transaction pattern.
    """
    async with SessionLocal() as session:
        await session.execute(
            text("SELECT set_config('app.user_id', :uid, true)"), {"uid": str(user_id)}
        )
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
```

- [ ] **Step 2: Write the deps test**

Create `backend/tests/test_deps.py`:

```python
import uuid

import pytest
from sqlalchemy import text

from app.db import SessionLocal
from app.deps import get_current_user
from app.security.session import issue_session_token


async def _seed_user(is_admin=False):
    uid = uuid.uuid4()
    async with SessionLocal() as s:
        await s.execute(
            text("INSERT INTO users (id, email, is_admin) VALUES (:id, :e, :a)"),
            {"id": uid, "e": f"{uid}@example.com", "a": is_admin},
        )
        await s.commit()
    return uid


@pytest.mark.asyncio
async def test_protected_route_requires_token(client):
    resp = await client.get("/api/auth/me")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_me_returns_current_user(client):
    uid = await _seed_user()
    token = issue_session_token(uid)
    resp = await client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    assert resp.json()["id"] == str(uid)
```

(This test depends on the `/api/auth/me` route added in Task 7; it will fail until then. That's intentional TDD ordering — run it red now, green after Task 7.)

- [ ] **Step 3: Run to verify it fails**

Run: `cd backend && uv run pytest tests/test_deps.py -v`
Expected: FAIL — `get_current_user` import error (and route 404 once import is fixed).

- [ ] **Step 4: Implement the dependencies**

Create `backend/app/deps.py`:

```python
from collections.abc import AsyncIterator
from uuid import UUID

import jwt
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from .db import SessionLocal, user_session
from .models import User
from .security.session import decode_session_token

_bearer = HTTPBearer(auto_error=False)


async def get_current_user(
    creds: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> User:
    if creds is None:
        raise HTTPException(status_code=401, detail="missing bearer token")
    try:
        payload = decode_session_token(creds.credentials)
        user_id = UUID(payload["sub"])
    except (jwt.PyJWTError, KeyError, ValueError):
        raise HTTPException(status_code=401, detail="invalid token")

    # users table has no RLS — read it on a plain session.
    async with SessionLocal() as session:
        user = await session.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=401, detail="user no longer exists")
    return user


async def get_current_admin(user: User = Depends(get_current_user)) -> User:
    if not user.is_admin:
        raise HTTPException(status_code=403, detail="admin only")
    return user


async def get_user_session(
    user: User = Depends(get_current_user),
) -> AsyncIterator[AsyncSession]:
    """RLS-scoped session for endpoints that touch user-owned tables."""
    async with user_session(user.id) as session:
        yield session
```

- [ ] **Step 5: Leave the test red for now**

Run: `cd backend && uv run pytest tests/test_deps.py::test_protected_route_requires_token -v`
Expected: still FAIL (route 404) — `/api/auth/me` arrives in Task 7. The import error is gone, which is the win for this task.

- [ ] **Step 6: Commit**

```bash
git add backend/app/db.py backend/app/deps.py backend/tests/test_deps.py
git commit -m "feat(backend): auth dependencies and RLS-bound session"
```

---

## Task 7: Auth endpoints and user provisioning

**Files:**
- Create: `backend/app/api/auth.py`
- Modify: `backend/app/schemas.py` (add `UserOut`, `GoogleLoginRequest`, `LoginResponse`)
- Modify: `backend/app/main.py` (register router)
- Test: `backend/tests/test_auth_api.py`

- [ ] **Step 1: Add schemas**

In `backend/app/schemas.py`, append:

```python
class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    email: str
    name: str | None = None
    picture: str | None = None
    is_admin: bool


class GoogleLoginRequest(BaseModel):
    id_token: str = Field(min_length=1)


class LoginResponse(BaseModel):
    session_token: str
    user: UserOut
```

- [ ] **Step 2: Write the auth API test (with the Google verifier mocked)**

Create `backend/tests/test_auth_api.py`:

```python
import pytest

from app.api import auth as auth_api


@pytest.fixture
def fake_google(monkeypatch):
    async def _fake(token: str) -> dict:
        # token string encodes the email for the test
        return {"email": token, "email_verified": True, "name": "Test", "picture": None,
                "aud": "test-client.apps.googleusercontent.com"}

    monkeypatch.setattr(auth_api, "verify_google_id_token", _fake)


@pytest.mark.asyncio
async def test_bootstrap_admin_can_log_in(client, fake_google):
    resp = await client.post("/api/auth/google", json={"id_token": "boss@example.com"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["user"]["email"] == "boss@example.com"
    assert body["user"]["is_admin"] is True
    assert body["session_token"]


@pytest.mark.asyncio
async def test_non_allowlisted_rejected(client, fake_google):
    resp = await client.post("/api/auth/google", json={"id_token": "stranger@example.com"})
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_allowlisted_user_provisioned_as_non_admin(client, fake_google, session):
    from sqlalchemy import text
    await session.execute(text("INSERT INTO allowed_emails (email) VALUES ('member@example.com')"))
    await session.commit()
    resp = await client.post("/api/auth/google", json={"id_token": "member@example.com"})
    assert resp.status_code == 200
    assert resp.json()["user"]["is_admin"] is False


@pytest.mark.asyncio
async def test_me_after_login(client, fake_google):
    login = await client.post("/api/auth/google", json={"id_token": "boss@example.com"})
    token = login.json()["session_token"]
    me = await client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200
    assert me.json()["email"] == "boss@example.com"
```

- [ ] **Step 3: Run to verify it fails**

Run: `cd backend && uv run pytest tests/test_auth_api.py -v`
Expected: FAIL — `app.api.auth` does not exist.

- [ ] **Step 4: Implement the auth router + provisioning**

Create `backend/app/api/auth.py`:

```python
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import settings
from ..db import get_session
from ..deps import get_current_user
from ..models import AllowedEmail, User
from ..schemas import GoogleLoginRequest, LoginResponse, UserOut
from ..security.google import GoogleAuthError, verify_google_id_token
from ..security.session import issue_session_token

router = APIRouter()


async def _provision_user(session: AsyncSession, info: dict) -> User:
    email = info["email"].lower()
    existing = (
        await session.execute(select(User).where(User.email == email))
    ).scalar_one_or_none()
    if existing is not None:
        return existing

    is_bootstrap = email in settings.bootstrap_admin_set
    allowlisted = (
        await session.execute(select(AllowedEmail).where(AllowedEmail.email == email))
    ).scalar_one_or_none() is not None

    if not (is_bootstrap or allowlisted):
        raise PermissionError(email)

    user = User(
        email=email,
        name=info.get("name"),
        picture=info.get("picture"),
        is_admin=is_bootstrap,
    )
    session.add(user)
    await session.flush()
    return user


@router.post("/google", response_model=LoginResponse)
async def google_login(
    body: GoogleLoginRequest, session: AsyncSession = Depends(get_session)
) -> LoginResponse:
    try:
        info = await verify_google_id_token(body.id_token)
    except GoogleAuthError:
        raise HTTPException(status_code=401, detail="invalid Google token")

    try:
        user = await _provision_user(session, info)
    except PermissionError:
        raise HTTPException(status_code=403, detail="email is not allowlisted")
    await session.commit()
    await session.refresh(user)

    return LoginResponse(session_token=issue_session_token(user.id), user=UserOut.model_validate(user))


@router.get("/me", response_model=UserOut)
async def me(user: User = Depends(get_current_user)) -> User:
    return user
```

- [ ] **Step 5: Register the router**

In `backend/app/main.py`, add the import near the other api imports (line 7):

```python
from .api import auth, documents, query
```

And register it (after line 35, before the documents router):

```python
app.include_router(auth.router, prefix="/api/auth", tags=["auth"])
```

- [ ] **Step 6: Run the auth + deps tests to verify pass**

Run: `cd backend && uv run pytest tests/test_auth_api.py tests/test_deps.py -v`
Expected: PASS (all). The previously-red `test_deps.py` tests go green now.

- [ ] **Step 7: Commit**

```bash
git add backend/app/api/auth.py backend/app/schemas.py backend/app/main.py backend/tests/test_auth_api.py
git commit -m "feat(backend): Google login, user provisioning, /api/auth/me"
```

---

## Task 8: Scope the documents API to the user

**Files:**
- Modify: `backend/app/api/documents.py` (use `get_user_session` + `get_current_user`, set `user_id`, hand owner to ingestion, stop self-committing)
- Modify: `backend/app/ingestion/pipeline.py` (accept `owner_id`, split transactions, set chunk `user_id`)
- Test: `backend/tests/test_documents_api.py`

- [ ] **Step 1: Write the documents isolation test**

Create `backend/tests/test_documents_api.py`:

```python
import io

import pytest

from app.api import auth as auth_api


@pytest.fixture
def fake_google(monkeypatch):
    async def _fake(token: str) -> dict:
        return {"email": token, "email_verified": True, "name": None, "picture": None,
                "aud": "test-client.apps.googleusercontent.com"}
    monkeypatch.setattr(auth_api, "verify_google_id_token", _fake)


async def _token(client, email):
    # boss@example.com is bootstrap admin; for members, allowlist first.
    if email != "boss@example.com":
        await client.post("/api/auth/google", json={"id_token": "boss@example.com"})
    return (await client.post("/api/auth/google", json={"id_token": email})).json()["session_token"]


@pytest.mark.asyncio
async def test_upload_then_list_is_user_scoped(client, fake_google, monkeypatch):
    # Avoid running the real ingestion background task in this test.
    from app.api import documents as docs_api
    monkeypatch.setattr(docs_api.BackgroundTasks, "add_task", lambda *a, **k: None)

    t1 = await _token(client, "boss@example.com")
    up = await client.post(
        "/api/documents",
        files={"file": ("a.md", io.BytesIO(b"# hello"), "text/markdown")},
        headers={"Authorization": f"Bearer {t1}"},
    )
    assert up.status_code == 201

    # Allowlist + log in a second user; they must see no documents.
    from sqlalchemy import text
    from app.db import SessionLocal
    async with SessionLocal() as s:
        await s.execute(text("INSERT INTO allowed_emails (email) VALUES ('m@example.com')"))
        await s.commit()
    t2 = await _token(client, "m@example.com")
    mine = await client.get("/api/documents", headers={"Authorization": f"Bearer {t2}"})
    assert mine.status_code == 200
    assert mine.json() == []

    owner = await client.get("/api/documents", headers={"Authorization": f"Bearer {t1}"})
    assert len(owner.json()) == 1
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd backend && uv run pytest tests/test_documents_api.py -v`
Expected: FAIL — endpoints don't set `user_id` (insert violates NOT NULL) and/or aren't scoped.

- [ ] **Step 3: Rewrite the documents router**

Replace the body of `backend/app/api/documents.py` with:

```python
import mimetypes
import shutil
from uuid import UUID, uuid4

from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, UploadFile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import settings
from ..deps import get_current_user, get_user_session
from ..ingestion.pipeline import run as run_ingestion
from ..models import Document, User
from ..schemas import DocumentOut

router = APIRouter()

_ALLOWED_EXTS = {".pdf", ".md", ".markdown", ".txt", ".docx"}


@router.get("", response_model=list[DocumentOut])
async def list_documents(session: AsyncSession = Depends(get_user_session)) -> list[Document]:
    stmt = select(Document).order_by(Document.created_at.desc())
    return list((await session.execute(stmt)).scalars().all())


@router.get("/{document_id}", response_model=DocumentOut)
async def get_document(
    document_id: UUID, session: AsyncSession = Depends(get_user_session)
) -> Document:
    doc = await session.get(Document, document_id)
    if doc is None:  # RLS makes another user's doc indistinguishable from missing.
        raise HTTPException(status_code=404, detail="document not found")
    return doc


@router.post("", response_model=DocumentOut, status_code=201)
async def upload_document(
    background: BackgroundTasks,
    file: UploadFile = File(...),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_user_session),
) -> Document:
    filename = file.filename or "upload"
    ext = "." + filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if ext not in _ALLOWED_EXTS:
        raise HTTPException(
            status_code=415,
            detail=f"unsupported file type {ext!r}; allowed: {sorted(_ALLOWED_EXTS)}",
        )

    doc_id = uuid4()
    storage_path = settings.upload_dir / f"{doc_id}{ext}"
    with storage_path.open("wb") as f:
        shutil.copyfileobj(file.file, f)
    size = storage_path.stat().st_size
    mime = file.content_type or mimetypes.guess_type(filename)[0] or "application/octet-stream"

    doc = Document(
        id=doc_id,
        user_id=user.id,
        filename=filename,
        mime_type=mime,
        size_bytes=size,
        storage_path=str(storage_path),
        status="uploading",
    )
    session.add(doc)
    await session.flush()
    await session.refresh(doc)

    # Hand the owner id to the background task — it has no request/user context.
    background.add_task(run_ingestion, doc.id, user.id)
    return doc


@router.delete("/{document_id}", status_code=204)
async def delete_document(
    document_id: UUID, session: AsyncSession = Depends(get_user_session)
) -> None:
    doc = await session.get(Document, document_id)
    if doc is None:
        raise HTTPException(status_code=404, detail="document not found")
    try:
        from pathlib import Path

        p = Path(doc.storage_path)
        if p.exists():
            p.unlink()
    except OSError:
        pass
    await session.delete(doc)
    # get_user_session commits at teardown.
```

Note: the endpoints no longer call `session.commit()` — the `user_session` context manager (via `get_user_session`) commits on success and rolls back on error.

- [ ] **Step 4: Rewrite ingestion to be owner-scoped and split-transaction**

Replace `backend/app/ingestion/pipeline.py` with:

```python
"""Background ingestion: parse → chunk → embed → store. Owner-scoped for RLS.

The owner id is passed in by the upload endpoint because a background task has no
request/user context. Each DB phase runs in its own short transaction with
app.user_id set; the slow parse/embed work happens outside any transaction.
"""
import logging
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID

from ..db import user_session
from ..models import Chunk as ChunkModel
from ..models import Document
from ..retrieval.embed import embed_texts
from .chunk import chunk_blocks
from .parse import parse

log = logging.getLogger(__name__)


async def run(document_id: UUID, owner_id: UUID) -> None:
    # Phase 1: mark processing.
    async with user_session(owner_id) as session:
        doc = await session.get(Document, document_id)
        if doc is None:
            log.warning("ingest: document %s missing", document_id)
            return
        if doc.status == "ready":
            return
        doc.status = "processing"
        doc.error = None
        storage_path, mime_type, filename = doc.storage_path, doc.mime_type, doc.filename

    try:
        blocks = parse(Path(storage_path), mime_type)
        if not blocks:
            raise ValueError("no extractable text in document")
        chunks = chunk_blocks(blocks)
        if not chunks:
            raise ValueError("chunking produced no chunks")
        embeddings = await embed_texts([c.text for c in chunks])
        if len(embeddings) != len(chunks):
            raise ValueError(f"embedding count mismatch: {len(embeddings)} vs {len(chunks)} chunks")

        # Phase 2: persist chunks + mark ready.
        async with user_session(owner_id) as session:
            doc = await session.get(Document, document_id)
            session.add_all(
                ChunkModel(
                    document_id=doc.id,
                    user_id=owner_id,
                    chunk_index=i,
                    text=c.text,
                    page=c.page,
                    section=c.section,
                    token_count=c.token_count,
                    embedding=emb,
                )
                for i, (c, emb) in enumerate(zip(chunks, embeddings, strict=True))
            )
            doc.page_count = max((b.page or 0 for b in blocks), default=0) or None
            doc.status = "ready"
            doc.indexed_at = datetime.now(timezone.utc)
        log.info("ingest: %s ready (%d chunks)", filename, len(chunks))

    except Exception as exc:
        async with user_session(owner_id) as session:
            doc = await session.get(Document, document_id)
            if doc is not None:
                doc.status = "failed"
                doc.error = f"{type(exc).__name__}: {exc}"
        log.exception("ingest: failed for %s", document_id)
```

- [ ] **Step 5: Run the documents test to verify pass**

Run: `cd backend && uv run pytest tests/test_documents_api.py -v`
Expected: PASS (1 passed).

- [ ] **Step 6: Commit**

```bash
git add backend/app/api/documents.py backend/app/ingestion/pipeline.py backend/tests/test_documents_api.py
git commit -m "feat(backend): scope documents API and ingestion to owning user"
```

---

## Task 9: Scope the query/chat pipeline to the user

**Files:**
- Modify: `backend/app/schemas.py` (`QueryRequest`: drop `session_id`, add optional `conversation_id`)
- Modify: `backend/app/api/query.py` (auth + user-scoped, explicit conversation)
- Modify: `backend/app/generation/pipeline.py` (`answer_query` takes `user_id`/`conversation_id`, split transactions, owns conversations)
- Test: `backend/tests/test_query_api.py`

- [ ] **Step 1: Update the request schema**

In `backend/app/schemas.py`, replace `QueryRequest` with:

```python
class QueryRequest(BaseModel):
    text: str = Field(min_length=1, max_length=4000)
    conversation_id: UUID | None = None  # None starts a new conversation
```

- [ ] **Step 2: Write the query isolation test (LLM + embed mocked)**

Create `backend/tests/test_query_api.py`:

```python
import pytest

from app.api import auth as auth_api
from app.generation import pipeline as gen_pipeline


@pytest.fixture
def fake_google(monkeypatch):
    async def _fake(token: str) -> dict:
        return {"email": token, "email_verified": True, "name": None, "picture": None,
                "aud": "test-client.apps.googleusercontent.com"}
    monkeypatch.setattr(auth_api, "verify_google_id_token", _fake)


@pytest.fixture
def fake_llm(monkeypatch):
    async def _embed(text):
        return [0.0] * 1024
    async def _chat(messages, temperature=0.1):
        return "answer with no citation"
    monkeypatch.setattr(gen_pipeline, "embed_text", _embed)
    monkeypatch.setattr(gen_pipeline, "chat", _chat)


@pytest.mark.asyncio
async def test_query_creates_user_owned_conversation(client, fake_google, fake_llm):
    token = (await client.post("/api/auth/google", json={"id_token": "boss@example.com"})).json()["session_token"]
    resp = await client.post(
        "/api/query", json={"text": "hi"}, headers={"Authorization": f"Bearer {token}"}
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["answer"] == "answer with no citation"
    assert body["conversation_id"]


@pytest.mark.asyncio
async def test_cannot_query_into_another_users_conversation(client, fake_google, fake_llm):
    t1 = (await client.post("/api/auth/google", json={"id_token": "boss@example.com"})).json()["session_token"]
    first = await client.post("/api/query", json={"text": "hi"}, headers={"Authorization": f"Bearer {t1}"})
    convo_id = first.json()["conversation_id"]

    from sqlalchemy import text
    from app.db import SessionLocal
    async with SessionLocal() as s:
        await s.execute(text("INSERT INTO allowed_emails (email) VALUES ('m@example.com')"))
        await s.commit()
    t2 = (await client.post("/api/auth/google", json={"id_token": "m@example.com"})).json()["session_token"]

    resp = await client.post(
        "/api/query",
        json={"text": "steal", "conversation_id": convo_id},
        headers={"Authorization": f"Bearer {t2}"},
    )
    assert resp.status_code == 404
```

- [ ] **Step 3: Run to verify it fails**

Run: `cd backend && uv run pytest tests/test_query_api.py -v`
Expected: FAIL — `answer_query` signature and the route still use `channel`/`session_id`.

- [ ] **Step 4: Rewrite `answer_query`**

Replace `backend/app/generation/pipeline.py`'s `answer_query` and `_resolve_conversation` (lines 31–81) with:

```python
async def answer_query(
    *, user_id: UUID, conversation_id: UUID | None, text: str
) -> QueryResult:
    # Phase 1 (read): resolve/own the conversation, load history, retrieve.
    async with user_session(user_id) as session:
        convo = await _resolve_conversation(session, user_id, conversation_id)
        convo_id = convo.id
        history = await _load_history(session, convo_id)
        rewritten = await rewrite(history, text) if history else text
        log.info("query: user=%s rewrite=%r", user_id, rewritten)
        embedding = await embed_text(rewritten)
        hits = await search(session, embedding)

    sanitized_history = [
        {"role": m["role"], "content": _MARKER_RE.sub("", m["content"]).strip()}
        for m in history[-settings.history_turns * 2 :]
    ]
    messages = [{"role": "system", "content": SYSTEM}]
    messages.extend(sanitized_history)
    messages.append({"role": "user", "content": build_user_prompt(text, hits)})

    # LLM call happens outside any DB transaction.
    answer = await chat(messages, temperature=0.1)
    citations = _build_citations(answer, hits)

    # Phase 2 (write): persist the turn.
    async with user_session(user_id) as session:
        session.add(Message(conversation_id=convo_id, user_id=user_id, role="user", content=text))
        session.add(
            Message(
                conversation_id=convo_id,
                user_id=user_id,
                role="assistant",
                content=answer,
                citations=[c.model_dump(mode="json") for c in citations] if citations else None,
            )
        )
    return QueryResult(answer=answer, citations=citations, conversation_id=convo_id)


async def _resolve_conversation(
    session: AsyncSession, user_id: UUID, conversation_id: UUID | None
) -> Conversation:
    if conversation_id is not None:
        convo = await session.get(Conversation, conversation_id)
        if convo is None:  # RLS hides other users' conversations → 404 at the API.
            raise HTTPException(status_code=404, detail="conversation not found")
        return convo
    convo = Conversation(user_id=user_id, channel="web")
    session.add(convo)
    await session.flush()
    return convo
```

Update imports at the top of `backend/app/generation/pipeline.py`:

```python
from fastapi import HTTPException
from ..db import user_session
```

(`embed_text` and `search` are still imported as before; `session` arg removed from `answer_query`.)

- [ ] **Step 5: Rewrite the query route**

Replace `backend/app/api/query.py` with:

```python
from fastapi import APIRouter, Depends

from ..deps import get_current_user
from ..generation.pipeline import answer_query
from ..models import User
from ..schemas import QueryRequest, QueryResponse

router = APIRouter()


@router.post("", response_model=QueryResponse)
async def post_query(
    body: QueryRequest, user: User = Depends(get_current_user)
) -> QueryResponse:
    result = await answer_query(
        user_id=user.id, conversation_id=body.conversation_id, text=body.text
    )
    return QueryResponse(
        answer=result.answer,
        citations=result.citations,
        conversation_id=result.conversation_id,
    )
```

Note: the query route depends only on `get_current_user`, not `get_user_session`, because `answer_query` manages its own RLS-scoped transactions (so the LLM call isn't wrapped in a DB transaction).

- [ ] **Step 6: Run to verify pass**

Run: `cd backend && uv run pytest tests/test_query_api.py -v`
Expected: PASS (2 passed).

- [ ] **Step 7: Commit**

```bash
git add backend/app/schemas.py backend/app/api/query.py backend/app/generation/pipeline.py backend/tests/test_query_api.py
git commit -m "feat(backend): scope chat pipeline to user, explicit conversations"
```

---

## Task 10: Admin allowlist endpoints

**Files:**
- Create: `backend/app/api/admin.py`
- Modify: `backend/app/schemas.py` (`AllowedEmailOut`, `AddAllowedEmailRequest`)
- Modify: `backend/app/main.py` (register router)
- Test: `backend/tests/test_admin_api.py`

- [ ] **Step 1: Add schemas**

In `backend/app/schemas.py`, append:

```python
class AddAllowedEmailRequest(BaseModel):
    email: str = Field(min_length=3, max_length=320)


class AllowedEmailOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    email: str
    created_at: datetime
```

- [ ] **Step 2: Write the admin API test**

Create `backend/tests/test_admin_api.py`:

```python
import pytest

from app.api import auth as auth_api


@pytest.fixture
def fake_google(monkeypatch):
    async def _fake(token: str) -> dict:
        return {"email": token, "email_verified": True, "name": None, "picture": None,
                "aud": "test-client.apps.googleusercontent.com"}
    monkeypatch.setattr(auth_api, "verify_google_id_token", _fake)


async def _login(client, email):
    return (await client.post("/api/auth/google", json={"id_token": email})).json()["session_token"]


@pytest.mark.asyncio
async def test_admin_can_add_and_list_allowlist(client, fake_google):
    admin = await _login(client, "boss@example.com")  # bootstrap admin
    h = {"Authorization": f"Bearer {admin}"}
    add = await client.post("/api/admin/allowlist", json={"email": "New@Example.com"}, headers=h)
    assert add.status_code == 201
    listed = await client.get("/api/admin/allowlist", headers=h)
    assert "new@example.com" in [e["email"] for e in listed.json()]


@pytest.mark.asyncio
async def test_non_admin_forbidden(client, fake_google):
    admin = await _login(client, "boss@example.com")
    await client.post("/api/admin/allowlist", json={"email": "m@example.com"},
                      headers={"Authorization": f"Bearer {admin}"})
    member = await _login(client, "m@example.com")
    resp = await client.get("/api/admin/allowlist", headers={"Authorization": f"Bearer {member}"})
    assert resp.status_code == 403
```

- [ ] **Step 3: Run to verify it fails**

Run: `cd backend && uv run pytest tests/test_admin_api.py -v`
Expected: FAIL — `app.api.admin` does not exist.

- [ ] **Step 4: Implement the admin router**

Create `backend/app/api/admin.py`:

```python
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import get_session
from ..deps import get_current_admin
from ..models import AllowedEmail, User
from ..schemas import AddAllowedEmailRequest, AllowedEmailOut

router = APIRouter()


@router.get("/allowlist", response_model=list[AllowedEmailOut])
async def list_allowlist(
    _admin: User = Depends(get_current_admin),
    session: AsyncSession = Depends(get_session),
) -> list[AllowedEmail]:
    stmt = select(AllowedEmail).order_by(AllowedEmail.created_at.desc())
    return list((await session.execute(stmt)).scalars().all())


@router.post("/allowlist", response_model=AllowedEmailOut, status_code=201)
async def add_allowlist(
    body: AddAllowedEmailRequest,
    admin: User = Depends(get_current_admin),
    session: AsyncSession = Depends(get_session),
) -> AllowedEmail:
    email = body.email.strip().lower()
    existing = await session.get(AllowedEmail, email)
    if existing is not None:
        return existing
    entry = AllowedEmail(email=email, added_by=admin.id)
    session.add(entry)
    await session.commit()
    await session.refresh(entry)
    return entry


@router.delete("/allowlist/{email}", status_code=204)
async def remove_allowlist(
    email: str,
    _admin: User = Depends(get_current_admin),
    session: AsyncSession = Depends(get_session),
) -> None:
    entry = await session.get(AllowedEmail, email.strip().lower())
    if entry is None:
        raise HTTPException(status_code=404, detail="not on allowlist")
    await session.delete(entry)
    await session.commit()
```

(`allowed_emails`/`users` have no RLS, so admin routes use the plain `get_session`.)

- [ ] **Step 5: Register the router**

In `backend/app/main.py`, update the import line to:

```python
from .api import admin, auth, documents, query
```

And register (after the auth router):

```python
app.include_router(admin.router, prefix="/api/admin", tags=["admin"])
```

- [ ] **Step 6: Run to verify pass**

Run: `cd backend && uv run pytest tests/test_admin_api.py -v`
Expected: PASS (2 passed).

- [ ] **Step 7: Commit**

```bash
git add backend/app/api/admin.py backend/app/schemas.py backend/app/main.py backend/tests/test_admin_api.py
git commit -m "feat(backend): admin allowlist endpoints"
```

---

## Task 11: Descope bots and finalize CORS/wiring

**Files:**
- Modify: `backend/app/main.py` (remove telegram/line routers; enable credentials in CORS)
- Test: `backend/tests/test_routes.py`

- [ ] **Step 1: Write a route-surface test**

Create `backend/tests/test_routes.py`:

```python
import pytest

from app.main import app


def test_bot_webhooks_are_gone():
    paths = {r.path for r in app.routes}
    assert not any(p.startswith("/webhook/") for p in paths)


def test_core_api_present():
    paths = {r.path for r in app.routes}
    assert "/api/auth/google" in paths
    assert "/api/admin/allowlist" in paths
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd backend && uv run pytest tests/test_routes.py -v`
Expected: FAIL on `test_bot_webhooks_are_gone` (webhook routers still registered).

- [ ] **Step 3: Remove bot routers and fix CORS**

In `backend/app/main.py`:
- Delete the two channel imports (lines 8–9: `from .channels import line ...` and `... telegram ...`).
- Delete the two `app.include_router(...webhook...)` lines (38–39).
- Change `allow_credentials=False` to `allow_credentials=True` (the web app will send the bearer token; credentialed CORS is the correct posture for an authenticated API).

The final router block should read:

```python
app.include_router(auth.router, prefix="/api/auth", tags=["auth"])
app.include_router(admin.router, prefix="/api/admin", tags=["admin"])
app.include_router(documents.router, prefix="/api/documents", tags=["documents"])
app.include_router(query.router, prefix="/api/query", tags=["query"])
```

> The bot code (`app/channels/`, `app/security/verify.py`) stays on disk but unwired — it returns when account-linking is designed (ADR 0004). Do not delete it.

- [ ] **Step 4: Run to verify pass**

Run: `cd backend && uv run pytest tests/test_routes.py -v`
Expected: PASS (2 passed).

- [ ] **Step 5: Run the whole suite + lint**

Run: `cd backend && uv run pytest -v && uv run ruff check .`
Expected: all tests PASS; ruff clean.

- [ ] **Step 6: Commit**

```bash
git add backend/app/main.py backend/tests/test_routes.py
git commit -m "feat(backend): descope bot webhooks, enable credentialed CORS"
```

---

## Self-Review (completed during planning)

**Spec coverage** — every Plan-1 decision maps to a task: closed multi-user access (T7 provisioning + T10 allowlist), Google OIDC + self-issued session (T5, T7), RLS isolation with FORCE + default-deny (T4, proven in T4 + T8 + T9 tests), per-user ingestion without a request context (T8), per-user chat with conversation ownership (T9), bootstrap admin via config (T1 config + T7 logic), pgvector ≥0.8 pin (T1), bots descoped (T11). MinIO storage, web UI, and mobile are explicitly out of this plan (Plans 2–4).

**Placeholder scan** — no TBD/TODO; every code step contains complete code; every test step has real assertions and exact run commands.

**Type/name consistency** — `user_session` (db.py) used identically in deps/ingestion/generation; `get_user_session`/`get_current_user`/`get_current_admin` names consistent across deps and routers; `verify_google_id_token` patched by the same import path it's defined under (`app.api.auth.verify_google_id_token`, re-exported via the `from ... import` in `auth.py`) — tests monkeypatch `auth_api.verify_google_id_token`, which matches the name bound in that module; `answer_query` keyword args (`user_id`, `conversation_id`, `text`) match the call in `query.py`.

> **Known cost, documented not hidden:** holding `app.user_id` requires the GUC and the queries to share a transaction. We avoid wrapping the slow LLM/embedding calls in a DB transaction by splitting ingestion and chat into short read/write transactions (T8, T9). This is the intended pattern, not an oversight.
