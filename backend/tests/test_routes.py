import pytest

from app.main import app


# Pure route-table introspection — no DB needed, so suppress the autouse async
# cleanup fixture (mirrors tests/test_models.py).
@pytest.fixture(autouse=True)
def _clean_tables():
    yield


def test_bot_webhooks_are_gone():
    paths = {r.path for r in app.routes}
    assert not any(p.startswith("/webhook/") for p in paths)


def test_core_api_present():
    paths = {r.path for r in app.routes}
    assert "/api/auth/google" in paths
    assert "/api/admin/allowlist" in paths
