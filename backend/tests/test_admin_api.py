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
