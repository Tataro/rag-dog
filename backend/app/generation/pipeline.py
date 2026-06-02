"""End-to-end query: resolve conversation → rewrite → embed → retrieve → generate → persist."""
import logging
import re
from dataclasses import dataclass
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import settings
from ..db import user_session
from ..models import Conversation, Message
from ..retrieval.embed import embed_text
from ..retrieval.rewrite import rewrite
from ..retrieval.search import Hit, search
from ..schemas import Citation
from .llm import chat
from .prompt import SYSTEM, build_user_prompt, cited_markers

_MARKER_RE = re.compile(r"\s*\[\d+\]")

log = logging.getLogger(__name__)


@dataclass(slots=True)
class QueryResult:
    answer: str
    citations: list[Citation]
    conversation_id: UUID


async def answer_query(
    *, user_id: UUID, conversation_id: UUID | None, text: str
) -> QueryResult:
    # Phase 1a (read): resolve/own the conversation and load history in a short tx.
    async with user_session(user_id) as session:
        convo = await _resolve_conversation(session, user_id, conversation_id)
        convo_id = convo.id
        history = await _load_history(session, convo_id)

    # Slow Ollama calls (rewrite + embed) happen OUTSIDE any DB transaction so we
    # don't hold a pooled connection idle across them (see user_session docstring).
    rewritten = await rewrite(history, text) if history else text
    log.info("query: user=%s rewrite=%r", user_id, rewritten)
    embedding = await embed_text(rewritten)

    # Phase 1b (read): vector search in its own short tx.
    async with user_session(user_id) as session:
        hits = await search(session, embedding)

    # Strip citation markers from prior assistant turns — they're noise for
    # generation context and encourage the model to mimic earlier answers.
    sanitized_history = [
        {"role": m["role"], "content": _MARKER_RE.sub("", m["content"]).strip()}
        for m in history[-settings.history_turns * 2 :]
    ]

    messages = [{"role": "system", "content": SYSTEM}]
    messages.extend(sanitized_history)
    messages.append({"role": "user", "content": build_user_prompt(text, hits)})

    # LLM call happens outside any DB transaction (temperature=0.1: prioritize
    # instruction following over creativity).
    answer = await chat(messages, temperature=0.1)
    citations = _build_citations(answer, hits)

    # Phase 2 (write): persist the turn.
    async with user_session(user_id) as session:
        session.add(Message(conversation_id=convo_id, user_id=user_id, role="user", content=text))
        session.add(
            Message(
                conversation_id=convo_id,
                user_id=user_id,
                role="assistant",
                content=answer,
                citations=[c.model_dump(mode="json") for c in citations] if citations else None,
            )
        )

    return QueryResult(answer=answer, citations=citations, conversation_id=convo_id)


async def _resolve_conversation(
    session: AsyncSession, user_id: UUID, conversation_id: UUID | None
) -> Conversation:
    if conversation_id is not None:
        convo = await session.get(Conversation, conversation_id)
        if convo is None:  # RLS hides other users' conversations → 404 at the API.
            raise HTTPException(status_code=404, detail="conversation not found")
        return convo
    convo = Conversation(user_id=user_id, channel="web")
    session.add(convo)
    await session.flush()
    return convo


async def _load_history(session: AsyncSession, conversation_id: UUID) -> list[dict]:
    limit = settings.history_turns * 2  # user+assistant per turn
    stmt = (
        select(Message)
        .where(Message.conversation_id == conversation_id)
        .order_by(Message.created_at.desc())
        .limit(limit)
    )
    rows = (await session.execute(stmt)).scalars().all()
    rows = list(reversed(rows))
    return [{"role": m.role, "content": m.content} for m in rows]


def _build_citations(answer: str, hits: list[Hit]) -> list[Citation]:
    markers = cited_markers(answer)
    if not markers:
        # Fall back to top-1 hit so the UI always has at least one source.
        markers = [1] if hits else []

    out: list[Citation] = []
    for n in markers[: settings.citations_limit]:
        if 1 <= n <= len(hits):
            h = hits[n - 1]
            snippet = h.text.strip().replace("\n", " ")
            if len(snippet) > 240:
                snippet = snippet[:237] + "…"
            out.append(
                Citation(
                    marker=n,
                    chunk_id=h.chunk_id,
                    document_id=h.document_id,
                    filename=h.filename,
                    page=h.page,
                    section=h.section,
                    snippet=snippet,
                )
            )
    return out
