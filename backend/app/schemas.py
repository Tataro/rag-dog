from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class DocumentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    filename: str
    mime_type: str
    size_bytes: int
    status: str
    error: str | None = None
    page_count: int | None = None
    created_at: datetime
    indexed_at: datetime | None = None


class Citation(BaseModel):
    marker: int
    chunk_id: UUID
    document_id: UUID
    filename: str
    page: int | None = None
    section: str | None = None
    snippet: str


class QueryRequest(BaseModel):
    text: str = Field(min_length=1, max_length=4000)
    conversation_id: UUID | None = None  # None starts a new conversation


class QueryResponse(BaseModel):
    answer: str
    citations: list[Citation]
    conversation_id: UUID


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    email: str
    name: str | None = None
    picture: str | None = None
    is_admin: bool


class GoogleLoginRequest(BaseModel):
    id_token: str = Field(min_length=1)


class LoginResponse(BaseModel):
    session_token: str
    user: UserOut
