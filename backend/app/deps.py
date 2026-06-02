from collections.abc import AsyncIterator
from uuid import UUID

import jwt
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from .db import SessionLocal, user_session
from .models import User
from .security.session import decode_session_token

_bearer = HTTPBearer(auto_error=False)


async def get_current_user(
    creds: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> User:
    if creds is None:
        raise HTTPException(status_code=401, detail="missing bearer token")
    try:
        payload = decode_session_token(creds.credentials)
        user_id = UUID(payload["sub"])
    except (jwt.PyJWTError, KeyError, ValueError) as exc:
        raise HTTPException(status_code=401, detail="invalid token") from exc

    # users table has no RLS — read it on a plain session.
    async with SessionLocal() as session:
        user = await session.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=401, detail="user no longer exists")
    return user


async def get_current_admin(user: User = Depends(get_current_user)) -> User:
    if not user.is_admin:
        raise HTTPException(status_code=403, detail="admin only")
    return user


async def get_user_session(
    user: User = Depends(get_current_user),
) -> AsyncIterator[AsyncSession]:
    """RLS-scoped session for endpoints that touch user-owned tables."""
    async with user_session(user.id) as session:
        yield session
