"""Our own HS256 session tokens, issued after Google sign-in is verified."""
import time
from uuid import UUID

import jwt

from ..config import settings


def issue_session_token(user_id: UUID) -> str:
    now = int(time.time())
    payload = {
        "sub": str(user_id),
        "iat": now,
        "exp": now + settings.session_jwt_ttl_seconds,
    }
    return jwt.encode(payload, settings.session_jwt_secret, algorithm="HS256")


def decode_session_token(token: str) -> dict:
    """Returns the payload, or raises jwt.PyJWTError on invalid/expired token."""
    return jwt.decode(token, settings.session_jwt_secret, algorithms=["HS256"])
