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
