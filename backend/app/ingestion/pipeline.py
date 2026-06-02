"""Background ingestion: parse → chunk → embed → store. Owner-scoped for RLS.

The owner id is passed in by the upload endpoint because a background task has no
request/user context. Each DB phase runs in its own short transaction with
app.user_id set; the slow parse/embed work happens outside any transaction.
"""
import logging
import os
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

from .. import storage
from ..db import user_session
from ..models import Chunk as ChunkModel
from ..models import Document
from ..retrieval.embed import embed_texts
from .chunk import chunk_blocks
from .parse import parse

log = logging.getLogger(__name__)


async def run(document_id: UUID, owner_id: UUID) -> None:
    # Phase 1: mark processing.
    async with user_session(owner_id) as session:
        doc = await session.get(Document, document_id)
        if doc is None:
            log.warning("ingest: document %s missing", document_id)
            return
        if doc.status == "ready":
            return
        doc.status = "processing"
        doc.error = None
        storage_path, mime_type, filename = doc.storage_path, doc.mime_type, doc.filename

    try:
        data = await storage.get_bytes(storage_path)
        ext = os.path.splitext(storage_path)[1]
        # mkstemp so tmp_path is bound before any write — a failed write then can't
        # leak the file (the finally below always runs). Close the fd before parse
        # reads the path (some platforms can't reopen an still-open temp file).
        fd, tmp_name = tempfile.mkstemp(suffix=ext)
        tmp_path = Path(tmp_name)
        try:
            with os.fdopen(fd, "wb") as f:
                f.write(data)
            blocks = parse(tmp_path, mime_type)
        finally:
            tmp_path.unlink(missing_ok=True)
        if not blocks:
            raise ValueError("no extractable text in document")
        chunks = chunk_blocks(blocks)
        if not chunks:
            raise ValueError("chunking produced no chunks")
        embeddings = await embed_texts([c.text for c in chunks])
        if len(embeddings) != len(chunks):
            raise ValueError(f"embedding count mismatch: {len(embeddings)} vs {len(chunks)} chunks")

        # Phase 2: persist chunks + mark ready.
        async with user_session(owner_id) as session:
            doc = await session.get(Document, document_id)
            session.add_all(
                ChunkModel(
                    document_id=doc.id,
                    user_id=owner_id,
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
            doc.indexed_at = datetime.now(UTC)
        log.info("ingest: %s ready (%d chunks)", filename, len(chunks))

    except Exception as exc:
        async with user_session(owner_id) as session:
            doc = await session.get(Document, document_id)
            if doc is not None:
                doc.status = "failed"
                doc.error = f"{type(exc).__name__}: {exc}"
        log.exception("ingest: failed for %s", document_id)
