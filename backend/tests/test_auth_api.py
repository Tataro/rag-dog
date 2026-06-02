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
