import uuid

import pytest
from sqlalchemy import text

from app.db import SessionLocal
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
