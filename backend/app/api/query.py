from fastapi import APIRouter, Depends

from ..deps import get_current_user
from ..generation.pipeline import answer_query
from ..models import User
from ..schemas import QueryRequest, QueryResponse

router = APIRouter()


@router.post("", response_model=QueryResponse)
async def post_query(
    body: QueryRequest, user: User = Depends(get_current_user)
) -> QueryResponse:
    result = await answer_query(
        user_id=user.id, conversation_id=body.conversation_id, text=body.text
    )
    return QueryResponse(
        answer=result.answer,
        citations=result.citations,
        conversation_id=result.conversation_id,
    )
