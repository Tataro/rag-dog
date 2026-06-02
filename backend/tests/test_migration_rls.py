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

    async with SessionLocal() as s:
        await s.execute(text("SELECT set_config('app.user_id', :uid, true)"), {"uid": str(u1)})
        await s.execute(
            text("""INSERT INTO documents (id, user_id, filename, mime_type, size_bytes,
                    storage_path, status) VALUES (:id, :uid, 'a.pdf', 'application/pdf', 1, 'x', 'ready')"""),
            {"id": uuid.uuid4(), "uid": str(u1)},
        )
        await s.commit()

    async with SessionLocal() as s:
        await s.execute(text("SELECT set_config('app.user_id', :uid, true)"), {"uid": str(u2)})
        assert (await s.execute(text("SELECT count(*) FROM documents"))).scalar_one() == 0
    async with SessionLocal() as s:
        await s.execute(text("SELECT set_config('app.user_id', :uid, true)"), {"uid": str(u1)})
        assert (await s.execute(text("SELECT count(*) FROM documents"))).scalar_one() == 1


@pytest.mark.asyncio
async def test_rls_default_denies_without_guc():
    async with SessionLocal() as s:
        assert (await s.execute(text("SELECT count(*) FROM documents"))).scalar_one() == 0
