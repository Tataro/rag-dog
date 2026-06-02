import uuid

import jwt
import pytest

from app.config import settings
from app.security.session import decode_session_token, issue_session_token


@pytest.fixture(autouse=True)
def _strong_secret(monkeypatch):
    # Use a 32+ byte secret so PyJWT doesn't emit InsecureKeyLengthWarning and we
    # exercise the code with a properly-sized key.
    monkeypatch.setattr(settings, "session_jwt_secret", "a" * 32)


def test_roundtrip_session_token():
    uid = uuid.uuid4()
    token = issue_session_token(uid)
    payload = decode_session_token(token)
    assert payload["sub"] == str(uid)


def test_tampered_token_rejected():
    uid = uuid.uuid4()
    token = issue_session_token(uid)
    with pytest.raises(jwt.PyJWTError):
        decode_session_token(token + "x")
