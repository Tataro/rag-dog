import mimetypes
import shutil
from uuid import UUID, uuid4

from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, UploadFile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import settings
from ..deps import get_current_user, get_user_session
from ..ingestion.pipeline import run as run_ingestion
from ..models import Document, User
from ..schemas import DocumentOut

router = APIRouter()

_ALLOWED_EXTS = {".pdf", ".md", ".markdown", ".txt", ".docx"}


@router.get("", response_model=list[DocumentOut])
async def list_documents(session: AsyncSession = Depends(get_user_session)) -> list[Document]:
    stmt = select(Document).order_by(Document.created_at.desc())
    return list((await session.execute(stmt)).scalars().all())


@router.get("/{document_id}", response_model=DocumentOut)
async def get_document(
    document_id: UUID, session: AsyncSession = Depends(get_user_session)
) -> Document:
    doc = await session.get(Document, document_id)
    if doc is None:  # RLS makes another user's doc indistinguishable from missing.
        raise HTTPException(status_code=404, detail="document not found")
    return doc


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
    storage_path = settings.upload_dir / f"{doc_id}{ext}"
    with storage_path.open("wb") as f:
        shutil.copyfileobj(file.file, f)
    size = storage_path.stat().st_size
    mime = file.content_type or mimetypes.guess_type(filename)[0] or "application/octet-stream"

    doc = Document(
        id=doc_id,
        user_id=user.id,
        filename=filename,
        mime_type=mime,
        size_bytes=size,
        storage_path=str(storage_path),
        status="uploading",
    )
    session.add(doc)
    await session.flush()
    await session.refresh(doc)

    # Hand the owner id to the background task — it has no request/user context.
    background.add_task(run_ingestion, doc.id, user.id)
    return doc


@router.delete("/{document_id}", status_code=204)
async def delete_document(
    document_id: UUID, session: AsyncSession = Depends(get_user_session)
) -> None:
    doc = await session.get(Document, document_id)
    if doc is None:
        raise HTTPException(status_code=404, detail="document not found")
    try:
        from pathlib import Path

        p = Path(doc.storage_path)
        if p.exists():
            p.unlink()
    except OSError:
        pass
    await session.delete(doc)
    # get_user_session commits at teardown.
