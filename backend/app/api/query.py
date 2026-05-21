from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import get_session
from ..generation.pipeline import answer_query
from ..schemas import QueryRequest, QueryResponse

router = APIRouter()


@router.post("", response_model=QueryResponse)
async def post_query(
    body: QueryRequest, session: AsyncSession = Depends(get_session)
) -> QueryResponse:
    result = await answer_query(
        session, channel="web", external_id=body.session_id, text=body.text
    )
    return QueryResponse(
        answer=result.answer,
        citations=result.citations,
        conversation_id=result.conversation_id,
    )
