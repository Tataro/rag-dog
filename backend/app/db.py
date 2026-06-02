from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from .config import settings

# Runtime queries go through the least-privilege app role so RLS applies. Migrations
# and admin tooling use settings.database_url (the owner/superuser role) instead.
engine = create_async_engine(settings.app_database_url, echo=False, pool_pre_ping=True)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


class Base(DeclarativeBase):
    pass


async def get_session() -> AsyncIterator[AsyncSession]:
    async with SessionLocal() as session:
        yield session


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
