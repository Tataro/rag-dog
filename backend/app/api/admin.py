from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import get_session
from ..deps import get_current_admin
from ..models import AllowedEmail, User
from ..schemas import AddAllowedEmailRequest, AllowedEmailOut

router = APIRouter()


@router.get("/allowlist", response_model=list[AllowedEmailOut])
async def list_allowlist(
    _admin: User = Depends(get_current_admin),
    session: AsyncSession = Depends(get_session),
) -> list[AllowedEmail]:
    stmt = select(AllowedEmail).order_by(AllowedEmail.created_at.desc())
    return list((await session.execute(stmt)).scalars().all())


@router.post("/allowlist", response_model=AllowedEmailOut, status_code=201)
async def add_allowlist(
    body: AddAllowedEmailRequest,
    admin: User = Depends(get_current_admin),
    session: AsyncSession = Depends(get_session),
) -> AllowedEmail:
    email = body.email.strip().lower()
    existing = await session.get(AllowedEmail, email)
    if existing is not None:
        return existing
    entry = AllowedEmail(email=email, added_by=admin.id)
    session.add(entry)
    await session.commit()
    await session.refresh(entry)
    return entry


@router.delete("/allowlist/{email}", status_code=204)
async def remove_allowlist(
    email: str,
    _admin: User = Depends(get_current_admin),
    session: AsyncSession = Depends(get_session),
) -> None:
    entry = await session.get(AllowedEmail, email.strip().lower())
    if entry is None:
        raise HTTPException(status_code=404, detail="not on allowlist")
    await session.delete(entry)
    await session.commit()
