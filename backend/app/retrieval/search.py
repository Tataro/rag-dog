"""Top-k dense retrieval against the pgvector HNSW index."""
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import settings
from ..models import Chunk, Document


@dataclass(slots=True)
class Hit:
    chunk_id: UUID
    document_id: UUID
    filename: str
    page: int | None
    section: str | None
    text: str
    distance: float


async def search(session: AsyncSession, query_embedding: list[float], k: int | None = None) -> list[Hit]:
    limit = k or settings.retrieval_top_k
    distance = Chunk.embedding.cosine_distance(query_embedding).label("distance")
    stmt = (
        select(
            Chunk.id,
            Chunk.document_id,
            Document.filename,
            Chunk.page,
            Chunk.section,
            Chunk.text,
            distance,
        )
        .join(Document, Document.id == Chunk.document_id)
        .where(Document.status == "ready")
        .order_by(distance)
        .limit(limit)
    )
    rows = (await session.execute(stmt)).all()
    return [
        Hit(
            chunk_id=row.id,
            document_id=row.document_id,
            filename=row.filename,
            page=row.page,
            section=row.section,
            text=row.text,
            distance=float(row.distance),
        )
        for row in rows
    ]
