import os
from pathlib import Path

# Must run before any `app.*` import so pydantic-settings reads the test values.
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://ragdog:ragdog@localhost:5432/ragdog_test")
os.environ.setdefault("APP_DATABASE_URL", "postgresql+asyncpg://ragdog_app:ragdog_app@localhost:5432/ragdog_test")
os.environ.setdefault("SESSION_JWT_SECRET", "test-secret")
os.environ.setdefault("GOOGLE_CLIENT_IDS", "test-client.apps.googleusercontent.com")
os.environ.setdefault("BOOTSTRAP_ADMIN_EMAILS", "boss@example.com")
os.environ.setdefault("S3_ENDPOINT_URL", "http://localhost:9000")
os.environ.setdefault("S3_BUCKET", "ragdog-documents-test")
os.environ.setdefault("S3_ACCESS_KEY", "testing")
os.environ.setdefault("S3_SECRET_KEY", "testing")
os.environ.setdefault("AWS_DEFAULT_REGION", "us-east-1")

import pytest
import pytest_asyncio
from alembic.config import Config
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from alembic import command
from app.db import SessionLocal
from app.main import app

_USER_TABLES = ["messages", "conversations", "chunks", "documents", "allowed_emails", "users"]

# Cleanup runs as the admin/owner role: the app role (ragdog_app) is subject to RLS
# and cannot TRUNCATE, and a DELETE under default-deny RLS would remove nothing.
_admin_engine = create_async_engine(os.environ["DATABASE_URL"])


@pytest.fixture(scope="session", autouse=True)
def _migrate():
    # Anchor both the ini and the script location absolutely so the harness works
    # regardless of pytest's CWD (both are CWD-relative in alembic.ini otherwise).
    backend_dir = Path(__file__).parent.parent
    cfg = Config(str(backend_dir / "alembic.ini"))
    cfg.set_main_option("script_location", str(backend_dir / "alembic"))
    command.upgrade(cfg, "head")
    yield


@pytest_asyncio.fixture(autouse=True)
async def _clean_tables():
    async with _admin_engine.begin() as conn:
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
