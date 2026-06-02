from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import settings
from ..db import get_session
from ..deps import get_current_user
from ..models import AllowedEmail, User
from ..schemas import GoogleLoginRequest, LoginResponse, UserOut
from ..security.google import GoogleAuthError, verify_google_id_token
from ..security.session import issue_session_token

router = APIRouter()


class EmailNotAllowed(Exception):
    """Raised when a verified Google email is neither bootstrap nor allowlisted."""


async def _provision_user(session: AsyncSession, info: dict) -> User:
    email = info["email"].lower()
    existing = (
        await session.execute(select(User).where(User.email == email))
    ).scalar_one_or_none()
    if existing is not None:
        return existing

    is_bootstrap = email in settings.bootstrap_admin_set
    allowlisted = (
        await session.execute(select(AllowedEmail).where(AllowedEmail.email == email))
    ).scalar_one_or_none() is not None

    if not (is_bootstrap or allowlisted):
        raise EmailNotAllowed(email)

    user = User(
        email=email,
        name=info.get("name"),
        picture=info.get("picture"),
        is_admin=is_bootstrap,
    )
    session.add(user)
    await session.flush()
    return user


@router.post("/google", response_model=LoginResponse)
async def google_login(
    body: GoogleLoginRequest, session: AsyncSession = Depends(get_session)
) -> LoginResponse:
    try:
        info = await verify_google_id_token(body.id_token)
    except GoogleAuthError as exc:
        raise HTTPException(status_code=401, detail="invalid Google token") from exc

    try:
        user = await _provision_user(session, info)
    except EmailNotAllowed as exc:
        raise HTTPException(status_code=403, detail="email is not allowlisted") from exc
    await session.commit()
    await session.refresh(user)

    return LoginResponse(session_token=issue_session_token(user.id), user=UserOut.model_validate(user))


@router.get("/me", response_model=UserOut)
async def me(user: User = Depends(get_current_user)) -> User:
    return user
