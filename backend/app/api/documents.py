import io
import mimetypes
from urllib.parse import quote
from uuid import UUID, uuid4

from botocore.exceptions import ClientError
from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, UploadFile
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .. import storage
from ..deps import get_current_user, get_user_session
from ..ingestion.pipeline import run as run_ingestion
from ..models import Document, User
from ..schemas import DocumentOut

router = APIRouter()

_ALLOWED_EXTS = {".pdf", ".md", ".markdown", ".txt", ".docx"}


async def _get_doc_or_404(session: AsyncSession, document_id: UUID) -> Document:
    # RLS scopes the lookup to the current user, so another user's document is
    # indistinguishable from a missing one (both → 404).
    doc = await session.get(Document, document_id)
    if doc is None:
        raise HTTPException(status_code=404, detail="document not found")
    return doc


def _content_disposition(filename: str) -> str:
    """RFC 6266 / 5987-safe disposition: an escaped ASCII fallback plus a UTF-8
    `filename*` so non-ASCII names (e.g. Thai) and quotes don't break the header."""
    ascii_fallback = filename.encode("ascii", "replace").decode("ascii").replace("\\", "_").replace('"', "_")
    return f"inline; filename=\"{ascii_fallback}\"; filename*=UTF-8''{quote(filename)}"


@router.get("", response_model=list[DocumentOut])
async def list_documents(session: AsyncSession = Depends(get_user_session)) -> list[Document]:
    stmt = select(Document).order_by(Document.created_at.desc())
    return list((await session.execute(stmt)).scalars().all())


@router.get("/{document_id}", response_model=DocumentOut)
async def get_document(
    document_id: UUID, session: AsyncSession = Depends(get_user_session)
) -> Document:
    return await _get_doc_or_404(session, document_id)


@router.get("/{document_id}/file")
async def download_document(
    document_id: UUID, session: AsyncSession = Depends(get_user_session)
) -> StreamingResponse:
    doc = await _get_doc_or_404(session, document_id)
    try:
        data = await storage.get_bytes(doc.storage_path)
    except ClientError as exc:  # object vanished from storage (lifecycle/manual delete)
        raise HTTPException(status_code=404, detail="file not found in storage") from exc
    return StreamingResponse(
        io.BytesIO(data),
        media_type=doc.mime_type,
        headers={"Content-Disposition": _content_disposition(doc.filename)},
    )


@router.post("", response_model=DocumentOut, status_code=201)
async def upload_document(
    background: BackgroundTasks,
    file: UploadFile = File(...),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_user_session),
) -> Document:
    filename = file.filename or "upload"
    ext = "." + filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if ext not in _ALLOWED_EXTS:
        raise HTTPException(
            status_code=415,
            detail=f"unsupported file type {ext!r}; allowed: {sorted(_ALLOWED_EXTS)}",
        )

    doc_id = uuid4()
    data = await file.read()
    size = len(data)
    mime = file.content_type or mimetypes.guess_type(filename)[0] or "application/octet-stream"
    key = storage.object_key(user.id, doc_id, ext)
    await storage.put_object(key, data, mime)

    doc = Document(
        id=doc_id,
        user_id=user.id,
        filename=filename,
        mime_type=mime,
        size_bytes=size,
        storage_path=key,
        status="uploading",
    )
    session.add(doc)
    await session.flush()
    await session.refresh(doc)
    # Commit BEFORE scheduling ingestion: background tasks run after the response is
    # sent but before get_user_session's teardown commit, so the row must already be
    # committed or run_ingestion's fresh session won't see it (doc stuck "uploading").
    await session.commit()

    # Hand the owner id to the background task — it has no request/user context.
    background.add_task(run_ingestion, doc.id, user.id)
    return doc


@router.delete("/{document_id}", status_code=204)
async def delete_document(
    document_id: UUID, session: AsyncSession = Depends(get_user_session)
) -> None:
    doc = await _get_doc_or_404(session, document_id)
    await storage.delete_object(doc.storage_path)
    await session.delete(doc)
    # get_user_session commits at teardown.
