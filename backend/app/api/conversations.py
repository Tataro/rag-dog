from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..deps import get_user_session
from ..models import Conversation, Message
from ..schemas import ConversationDetail, ConversationOut, MessageOut

router = APIRouter()

_PREVIEW_LEN = 80


@router.get("", response_model=list[ConversationOut])
async def list_conversations(
    session: AsyncSession = Depends(get_user_session),
) -> list[ConversationOut]:
    # Correlated subqueries against the outer `conversations` row. RLS scopes both
    # tables to the current user, so no explicit user_id filter is needed here.
    last_at = (
        select(func.max(Message.created_at))
        .where(Message.conversation_id == Conversation.id)
        .scalar_subquery()
    )
    first_user_msg = (
        select(Message.content)
        .where(Message.conversation_id == Conversation.id, Message.role == "user")
        .order_by(Message.created_at.asc())
        .limit(1)
        .scalar_subquery()
    )
    stmt = (
        select(Conversation.id, Conversation.created_at, first_user_msg, last_at)
        .where(last_at.is_not(None))  # drop empty conversations (no messages)
        .order_by(last_at.desc())
    )
    rows = (await session.execute(stmt)).all()

    out: list[ConversationOut] = []
    for cid, created_at, preview, last_message_at in rows:
        preview = preview or ""
        if len(preview) > _PREVIEW_LEN:
            preview = preview[: _PREVIEW_LEN - 1] + "…"
        out.append(
            ConversationOut(
                id=cid,
                preview=preview,
                created_at=created_at,
                last_message_at=last_message_at,
            )
        )
    return out


@router.get("/{conversation_id}", response_model=ConversationDetail)
async def get_conversation(
    conversation_id: UUID,
    session: AsyncSession = Depends(get_user_session),
) -> ConversationDetail:
    # RLS hides other users' conversations → get() returns None → 404 (mirrors documents.py).
    convo = await session.get(Conversation, conversation_id)
    if convo is None:
        raise HTTPException(status_code=404, detail="conversation not found")

    stmt = (
        select(Message)
        .where(Message.conversation_id == conversation_id)
        .order_by(Message.created_at.asc())
    )
    messages = (await session.execute(stmt)).scalars().all()
    return ConversationDetail(
        id=convo.id,
        created_at=convo.created_at,
        messages=[MessageOut.model_validate(m) for m in messages],
    )
