import pytest
from sqlalchemy import text

from app.api import auth as auth_api
from app.generation import pipeline as gen_pipeline
from app.db import SessionLocal


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


async def _login(client, email: str) -> dict:
    token = (await client.post("/api/auth/google", json={"id_token": email})).json()["session_token"]
    return {"Authorization": f"Bearer {token}"}


async def _allow(email: str) -> None:
    async with SessionLocal() as s:
        await s.execute(text("INSERT INTO allowed_emails (email) VALUES (:e)"), {"e": email})
        await s.commit()


@pytest.mark.asyncio
async def test_list_empty_for_new_user(client, fake_google):
    h = await _login(client, "boss@example.com")
    resp = await client.get("/api/conversations", headers=h)
    assert resp.status_code == 200
    assert resp.json() == []


@pytest.mark.asyncio
async def test_list_returns_preview_after_query(client, fake_google, fake_llm):
    h = await _login(client, "boss@example.com")
    await client.post("/api/query", json={"text": "what is rls"}, headers=h)
    body = (await client.get("/api/conversations", headers=h)).json()
    assert len(body) == 1
    assert body[0]["preview"] == "what is rls"
    assert body[0]["last_message_at"]
    assert body[0]["created_at"]


@pytest.mark.asyncio
async def test_list_ordered_by_last_activity(client, fake_google, fake_llm):
    h = await _login(client, "boss@example.com")
    a = (await client.post("/api/query", json={"text": "first"}, headers=h)).json()["conversation_id"]
    b = (await client.post("/api/query", json={"text": "second"}, headers=h)).json()["conversation_id"]
    # Continue A so it becomes the most-recently-active conversation.
    await client.post("/api/query", json={"text": "again", "conversation_id": a}, headers=h)
    body = (await client.get("/api/conversations", headers=h)).json()
    assert [c["id"] for c in body] == [a, b]


@pytest.mark.asyncio
async def test_detail_returns_messages_in_order(client, fake_google, fake_llm):
    h = await _login(client, "boss@example.com")
    cid = (await client.post("/api/query", json={"text": "hello"}, headers=h)).json()["conversation_id"]
    body = (await client.get(f"/api/conversations/{cid}", headers=h)).json()
    assert body["id"] == cid
    assert [m["role"] for m in body["messages"]] == ["user", "assistant"]
    assert body["messages"][0]["content"] == "hello"
    assert body["messages"][1]["content"] == "answer with no citation"
    assert body["messages"][1]["citations"] is None


@pytest.mark.asyncio
async def test_list_preview_truncated_to_80(client, fake_google, fake_llm):
    h = await _login(client, "boss@example.com")
    long_text = "x" * 100
    await client.post("/api/query", json={"text": long_text}, headers=h)
    body = (await client.get("/api/conversations", headers=h)).json()
    preview = body[0]["preview"]
    assert len(preview) == 80
    assert preview.endswith("…")
    assert preview[:-1] == "x" * 79


@pytest.mark.asyncio
async def test_other_user_cannot_read_conversation(client, fake_google, fake_llm):
    h1 = await _login(client, "boss@example.com")
    cid = (await client.post("/api/query", json={"text": "hi"}, headers=h1)).json()["conversation_id"]
    await _allow("m@example.com")
    h2 = await _login(client, "m@example.com")
    assert (await client.get(f"/api/conversations/{cid}", headers=h2)).status_code == 404
    assert (await client.get("/api/conversations", headers=h2)).json() == []
