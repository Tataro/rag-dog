"""End-to-end query: resolve conversation → rewrite → embed → retrieve → generate → persist."""
import logging
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import settings
from ..models import Conversation, Message
from ..retrieval.embed import embed_text
from ..retrieval.rewrite import rewrite
from ..retrieval.search import Hit, search
from ..schemas import Citation
from .llm import chat
from .prompt import SYSTEM, build_user_prompt, cited_markers

log = logging.getLogger(__name__)


@dataclass(slots=True)
class QueryResult:
    answer: str
    citations: list[Citation]
    conversation_id: UUID


async def answer_query(
    session: AsyncSession, *, channel: str, external_id: str, text: str
) -> QueryResult:
    convo = await _resolve_conversation(session, channel, external_id)
    history = await _load_history(session, convo.id)

    rewritten = await rewrite(history, text) if history else text
    log.info("query: channel=%s rewrite=%r", channel, rewritten)

    embedding = await embed_text(rewritten)
    hits = await search(session, embedding)

    messages = [{"role": "system", "content": SYSTEM}]
    messages.extend(history[-settings.history_turns * 2 :])
    messages.append({"role": "user", "content": build_user_prompt(text, hits)})

    answer = await chat(messages, temperature=0.2)
    citations = _build_citations(answer, hits)

    session.add(Message(conversation_id=convo.id, role="user", content=text))
    session.add(
        Message(
            conversation_id=convo.id,
            role="assistant",
            content=answer,
            citations=[c.model_dump(mode="json") for c in citations] if citations else None,
        )
    )
    await session.commit()

    return QueryResult(answer=answer, citations=citations, conversation_id=convo.id)


async def _resolve_conversation(session: AsyncSession, channel: str, external_id: str) -> Conversation:
    stmt = select(Conversation).where(
        Conversation.channel == channel, Conversation.external_id == external_id
    )
    convo = (await session.execute(stmt)).scalar_one_or_none()
    if convo is None:
        convo = Conversation(channel=channel, external_id=external_id)
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
