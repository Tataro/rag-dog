"""Background ingestion: parse → chunk → embed → store.

Idempotent at the document level: if the document is already `ready` it returns immediately.
Failures land the document in `failed` with a human-readable error string.
"""
import logging
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID

from sqlalchemy import select

from ..db import SessionLocal
from ..models import Chunk as ChunkModel
from ..models import Document
from ..retrieval.embed import embed_texts
from .chunk import chunk_blocks
from .parse import parse

log = logging.getLogger(__name__)


async def run(document_id: UUID) -> None:
    async with SessionLocal() as session:
        doc = await session.get(Document, document_id)
        if doc is None:
            log.warning("ingest: document %s missing", document_id)
            return
        if doc.status == "ready":
            return
        doc.status = "processing"
        doc.error = None
        await session.commit()

        try:
            blocks = parse(Path(doc.storage_path), doc.mime_type)
            if not blocks:
                raise ValueError("no extractable text in document")

            chunks = chunk_blocks(blocks)
            if not chunks:
                raise ValueError("chunking produced no chunks")

            embeddings = await embed_texts([c.text for c in chunks])
            if len(embeddings) != len(chunks):
                raise ValueError(
                    f"embedding count mismatch: {len(embeddings)} vs {len(chunks)} chunks"
                )

            session.add_all(
                ChunkModel(
                    document_id=doc.id,
                    chunk_index=i,
                    text=c.text,
                    page=c.page,
                    section=c.section,
                    token_count=c.token_count,
                    embedding=emb,
                )
                for i, (c, emb) in enumerate(zip(chunks, embeddings, strict=True))
            )

            doc.page_count = max((b.page or 0 for b in blocks), default=0) or None
            doc.status = "ready"
            doc.indexed_at = datetime.now(timezone.utc)
            await session.commit()
            log.info("ingest: %s ready (%d chunks)", doc.filename, len(chunks))

        except Exception as exc:
            await session.rollback()
            # Re-fetch in the rolled-back session to update status.
            doc = await session.get(Document, document_id)
            if doc is not None:
                doc.status = "failed"
                doc.error = f"{type(exc).__name__}: {exc}"
                await session.commit()
            log.exception("ingest: failed for %s", document_id)
