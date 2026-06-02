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
