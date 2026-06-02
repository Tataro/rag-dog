import os
from pathlib import Path

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

# Temporary: only the four tables that exist in 0001_init.
# Restore the full list (add "allowed_emails", "users") once Task 4 adds those migrations.
_USER_TABLES = ["messages", "conversations", "chunks", "documents"]


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
