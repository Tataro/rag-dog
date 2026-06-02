# MinIO Object Storage Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move uploaded Document files off the local disk (`uploads/`) into self-hosted, S3-compatible object storage (MinIO), with per-User ownership enforced on every download — so the raw file blobs are as isolated as the RLS-protected metadata.

**Architecture:** A small `app/storage.py` wraps an S3 client (boto3, pointed at MinIO via `endpoint_url`); object keys are `"{user_id}/{document_id}{ext}"`. Uploads stream the bytes to MinIO and store the object key in `Document.storage_path`. Ingestion downloads the object to a temp file to parse it. A new ownership-checked endpoint streams the file back through the authenticated API (MinIO stays private — no public presigned URLs). Tests use `moto` to mock S3 in-process, mirroring how the suite uses a real Postgres but keeping object storage hermetic.

**Tech Stack:** Python 3.12, FastAPI, async SQLAlchemy, Postgres+pgvector (from Plan 1), **MinIO** (S3-compatible), **boto3** (sync client wrapped in `run_in_threadpool`), **moto** (test mock). Builds on Plan 1: `user_id` ownership, `get_current_user`, `get_user_session`, RLS.

> **Decision references:** ADR 0004 (MinIO chosen, S3 API keeps a cloud move a config change). This plan supersedes the local-disk `uploads/` approach in the README/0001-era layout.

> **Prerequisite:** Plan 1 is merged to `main` (it is). Work on a new branch `feat/minio-storage`.

---

## Task 1: Dependencies, config, and MinIO service

**Files:**
- Modify: `backend/pyproject.toml` (add `boto3`; dev `moto[s3]`)
- Modify: `backend/app/config.py` (S3 settings)
- Modify: `docker-compose.yml` (minio service)
- Modify: `.env.example` (S3 vars)
- Modify: `backend/tests/conftest.py` (set S3 test env)
- Test: `backend/tests/test_config.py` (extend)

- [x] **Step 1: Add dependencies**

In `backend/pyproject.toml` add to `dependencies`:
```toml
    "boto3>=1.35.0",
```
Add to `[dependency-groups].dev`:
```toml
    "moto[s3]>=5.0.0",
```
Run: `cd backend && uv sync`

- [x] **Step 2: Add the MinIO service to `docker-compose.yml`**

Add under `services:` (alongside `postgres`):
```yaml
  minio:
    image: minio/minio:latest
    container_name: ragdog-minio
    restart: unless-stopped
    command: server /data --console-address ":9001"
    environment:
      MINIO_ROOT_USER: ${S3_ACCESS_KEY:-ragdog}
      MINIO_ROOT_PASSWORD: ${S3_SECRET_KEY:-ragdog-secret}
    ports:
      - "${S3_PORT:-9000}:9000"
      - "${S3_CONSOLE_PORT:-9001}:9001"
    volumes:
      - miniodata:/data
    healthcheck:
      test: ["CMD", "mc", "ready", "local"]
      interval: 5s
      timeout: 5s
      retries: 10
```
And add `miniodata:` under the top-level `volumes:` block (next to `pgdata:`/`ollama:`).

- [x] **Step 3: Write the failing config test**

Append to `backend/tests/test_config.py`:
```python
def test_s3_settings_have_expected_fields():
    s = Settings(
        s3_endpoint_url="http://localhost:9000",
        s3_bucket="docs",
        s3_access_key="k",
        s3_secret_key="v",
    )
    assert s.s3_endpoint_url == "http://localhost:9000"
    assert s.s3_bucket == "docs"
    assert s.s3_region == "us-east-1"  # default
```

- [x] **Step 4: Run it to verify it fails**

Run: `cd backend && uv run pytest tests/test_config.py::test_s3_settings_have_expected_fields -v`
Expected: FAIL (`Settings` has no `s3_endpoint_url`).

- [x] **Step 5: Add S3 settings**

In `backend/app/config.py`, add fields near the database settings:
```python
    # Object storage (MinIO / S3-compatible) for uploaded Document files.
    s3_endpoint_url: str = "http://localhost:9000"
    s3_region: str = "us-east-1"
    s3_access_key: str = "ragdog"
    s3_secret_key: str = "ragdog-secret"
    s3_bucket: str = "ragdog-documents"
```

- [x] **Step 6: Set S3 env for tests**

In `backend/tests/conftest.py`, add to the `os.environ.setdefault(...)` block (with the other test env, before app imports):
```python
os.environ.setdefault("S3_ENDPOINT_URL", "http://localhost:9000")
os.environ.setdefault("S3_BUCKET", "ragdog-documents-test")
os.environ.setdefault("S3_ACCESS_KEY", "testing")
os.environ.setdefault("S3_SECRET_KEY", "testing")
os.environ.setdefault("AWS_DEFAULT_REGION", "us-east-1")
```
(`moto` reads standard AWS env; setting dummy creds avoids accidental real-AWS calls.)

- [x] **Step 7: Document the vars in `.env.example`**

Add a section to `.env.example`:
```bash
# --- Object storage (MinIO / S3-compatible) ---
S3_ENDPOINT_URL=http://localhost:9000
S3_REGION=us-east-1
S3_ACCESS_KEY=ragdog
S3_SECRET_KEY=ragdog-secret
S3_BUCKET=ragdog-documents
# Ports for the docker minio service (optional overrides)
S3_PORT=9000
S3_CONSOLE_PORT=9001
```

- [x] **Step 8: Run it to verify pass + start MinIO**

Run: `cd backend && uv run pytest tests/test_config.py -v` → PASS.
Run: `docker compose up -d minio` and confirm `docker ps` shows `ragdog-minio` healthy. (Dev only; tests use moto, not this container.)

- [x] **Step 9: Commit**

```bash
git add backend/pyproject.toml backend/uv.lock backend/app/config.py backend/tests/conftest.py backend/tests/test_config.py docker-compose.yml .env.example
git commit -m "feat(storage): add boto3/moto deps, S3 config, and MinIO service"
```

---

## Task 2: The storage module

**Files:**
- Create: `backend/app/storage.py`
- Test: `backend/tests/test_storage.py`

- [x] **Step 1: Write the failing test (moto-mocked S3)**

Create `backend/tests/test_storage.py`:
```python
import boto3
import pytest
from moto import mock_aws

from app import storage
from app.config import settings


@pytest.fixture(autouse=True)
def _clean_tables():  # storage tests don't touch Postgres
    yield


@pytest.fixture
def s3():
    with mock_aws():
        boto3.client("s3", region_name=settings.s3_region).create_bucket(Bucket=settings.s3_bucket)
        yield


@pytest.mark.asyncio
async def test_put_get_delete_roundtrip(s3):
    key = "user-1/doc-1.txt"
    await storage.put_object(key, b"hello world", "text/plain")
    assert await storage.get_bytes(key) == b"hello world"
    await storage.delete_object(key)
    with pytest.raises(Exception):
        await storage.get_bytes(key)


@pytest.mark.asyncio
async def test_ensure_bucket_is_idempotent():
    with mock_aws():
        await storage.ensure_bucket()
        await storage.ensure_bucket()  # second call must not raise
        assert await storage.get_bytes  # attribute exists (smoke)
```

- [x] **Step 2: Run it to verify it fails**

Run: `cd backend && uv run pytest tests/test_storage.py -v`
Expected: FAIL (`app.storage` does not exist).

- [x] **Step 3: Implement the storage module**

Create `backend/app/storage.py`:
```python
"""S3-compatible object storage (MinIO) for uploaded Document files.

A fresh boto3 client is created per call: client creation is cheap, it keeps the
sync boto3 calls confined to the threadpool, and it lets `moto` patch botocore in
tests (a module-level client created at import time would not be mocked).
"""
import boto3
from botocore.config import Config
from fastapi.concurrency import run_in_threadpool

from .config import settings


def _client():
    return boto3.client(
        "s3",
        endpoint_url=settings.s3_endpoint_url,
        region_name=settings.s3_region,
        aws_access_key_id=settings.s3_access_key,
        aws_secret_access_key=settings.s3_secret_key,
        config=Config(signature_version="s3v4", s3={"addressing_style": "path"}),
    )


def object_key(user_id, document_id, ext: str) -> str:
    """Storage key for a Document. user_id prefix keeps each User's blobs grouped."""
    return f"{user_id}/{document_id}{ext}"


async def ensure_bucket() -> None:
    def _ensure():
        client = _client()
        existing = {b["Name"] for b in client.list_buckets().get("Buckets", [])}
        if settings.s3_bucket not in existing:
            client.create_bucket(Bucket=settings.s3_bucket)

    await run_in_threadpool(_ensure)


async def put_object(key: str, data: bytes, content_type: str) -> None:
    def _put():
        _client().put_object(
            Bucket=settings.s3_bucket, Key=key, Body=data, ContentType=content_type
        )

    await run_in_threadpool(_put)


async def get_bytes(key: str) -> bytes:
    def _get():
        resp = _client().get_object(Bucket=settings.s3_bucket, Key=key)
        return resp["Body"].read()

    return await run_in_threadpool(_get)


async def delete_object(key: str) -> None:
    def _del():
        _client().delete_object(Bucket=settings.s3_bucket, Key=key)

    await run_in_threadpool(_del)
```

- [x] **Step 4: Run it to verify pass**

Run: `cd backend && uv run pytest tests/test_storage.py -v`
Expected: PASS (2 passed).

- [x] **Step 5: Commit**

```bash
git add backend/app/storage.py backend/tests/test_storage.py
git commit -m "feat(storage): S3 object storage module (put/get/delete/ensure_bucket)"
```

---

## Task 3: Upload and delete go to MinIO

**Files:**
- Modify: `backend/app/api/documents.py` (upload → put_object; delete → delete_object; key scheme)
- Test: `backend/tests/test_documents_api.py` (extend with S3 mock)

- [x] **Step 1: Add an S3 fixture and extend the documents test**

In `backend/tests/test_documents_api.py`, add the moto fixture and assert the object lands in storage. Add at the top (after imports):
```python
import boto3
from moto import mock_aws

from app import storage
from app.config import settings


@pytest.fixture
def s3(monkeypatch):
    with mock_aws():
        boto3.client("s3", region_name=settings.s3_region).create_bucket(Bucket=settings.s3_bucket)
        yield
```
Then change `test_upload_then_list_is_user_scoped` to take the `s3` fixture and, after the successful upload, assert the object exists:
```python
@pytest.mark.asyncio
async def test_upload_then_list_is_user_scoped(client, fake_google, monkeypatch, s3):
    from app.api import documents as docs_api
    monkeypatch.setattr(docs_api.BackgroundTasks, "add_task", lambda *a, **k: None)

    t1 = await _token(client, "boss@example.com")
    up = await client.post(
        "/api/documents",
        files={"file": ("a.md", io.BytesIO(b"# hello"), "text/markdown")},
        headers={"Authorization": f"Bearer {t1}"},
    )
    assert up.status_code == 201
    key = up.json()["id"]  # storage key starts with "<user_id>/" but we only have doc id here
    # Object is retrievable via the storage layer (proves it was uploaded, not written to disk):
    stored = await storage.get_bytes(_object_key_for(up.json()))
    assert stored == b"# hello"

    # ... (rest of the cross-user assertions unchanged)
```
Add this helper near the top of the test file:
```python
def _object_key_for(doc_json: dict) -> str:
    # mirrors storage.object_key(user_id, doc_id, ext); the API returns filename + id
    import os
    ext = os.path.splitext(doc_json["filename"])[1]
    # user_id isn't in DocumentOut, so reconstruct from the stored storage_path instead:
    return doc_json["storage_path"]
```
> NOTE: This requires `storage_path` to be exposed on `DocumentOut`. If you prefer NOT to expose the key, instead assert via `boto3` listing: `objs = boto3.client("s3", region_name=settings.s3_region).list_objects_v2(Bucket=settings.s3_bucket).get("Contents", [])` and assert exactly one object whose key ends with `a.md`'s extension. Use the listing approach to avoid leaking the key in the API response.

Use the listing approach (do not expose `storage_path`):
```python
    listed = boto3.client("s3", region_name=settings.s3_region).list_objects_v2(
        Bucket=settings.s3_bucket
    ).get("Contents", [])
    assert len(listed) == 1
    assert listed[0]["Key"].endswith(".md")
    body = await storage.get_bytes(listed[0]["Key"])
    assert body == b"# hello"
```

- [x] **Step 2: Run it to verify it fails**

Run: `cd backend && uv run pytest tests/test_documents_api.py -v`
Expected: FAIL (upload still writes to disk; no object in S3).

- [x] **Step 3: Rewrite the upload + delete handlers to use storage**

In `backend/app/api/documents.py`:
- Remove the `shutil` import and the `from ..config import settings` usage for `upload_dir`; add `from .. import storage` and keep `from ..config import settings` only if still used (it is not after this change — remove it if unused; ruff will tell you).
- Replace the file-writing block in `upload_document`:
```python
    doc_id = uuid4()
    ext = "." + filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
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
```
(`ext` is computed once now; the earlier extension-check block that derives `ext` for validation stays — reuse the same `ext` variable, don't recompute differently.)
- Replace the disk-deletion block in `delete_document` with:
```python
    await storage.delete_object(doc.storage_path)
    await session.delete(doc)
    # get_user_session commits at teardown.
```
Remove the now-unused `from pathlib import Path` local import and the `OSError` try/except.

- [x] **Step 4: Run it to verify pass**

Run: `cd backend && uv run pytest tests/test_documents_api.py -v` → PASS.

- [x] **Step 5: Commit**

```bash
git add backend/app/api/documents.py backend/tests/test_documents_api.py
git commit -m "feat(storage): upload and delete Documents via MinIO, keyed by user"
```

---

## Task 4: Ingestion reads from MinIO

**Files:**
- Modify: `backend/app/ingestion/pipeline.py` (download object to a temp file before parsing)
- Test: `backend/tests/test_ingestion_storage.py`

- [x] **Step 1: Write the failing test**

Create `backend/tests/test_ingestion_storage.py`:
```python
import uuid

import boto3
import pytest
from moto import mock_aws
from sqlalchemy import text

from app import storage
from app.config import settings
from app.db import SessionLocal, user_session
from app.ingestion import pipeline


@pytest.fixture
def s3():
    with mock_aws():
        boto3.client("s3", region_name=settings.s3_region).create_bucket(Bucket=settings.s3_bucket)
        yield


async def _seed_user_and_doc(key: str) -> tuple[uuid.UUID, uuid.UUID]:
    uid, did = uuid.uuid4(), uuid.uuid4()
    async with SessionLocal() as s:
        await s.execute(text("INSERT INTO users (id, email) VALUES (:id, :e)"),
                        {"id": uid, "e": f"{uid}@example.com"})
        await s.commit()
    async with user_session(uid) as s:
        await s.execute(
            text("""INSERT INTO documents (id, user_id, filename, mime_type, size_bytes,
                    storage_path, status) VALUES (:id, :uid, 'a.txt', 'text/plain', 5, :key, 'uploading')"""),
            {"id": did, "uid": str(uid), "key": key},
        )
    return uid, did


@pytest.mark.asyncio
async def test_ingestion_pulls_file_from_storage(s3, monkeypatch):
    async def _fake_embed(texts):
        return [[0.0] * settings.embedding_dim for _ in texts]
    monkeypatch.setattr(pipeline, "embed_texts", _fake_embed)

    key = "u/a.txt"
    await storage.put_object(key, b"hello world this is a document", "text/plain")
    uid, did = await _seed_user_and_doc(key)

    await pipeline.run(did, uid)

    async with user_session(uid) as s:
        status = (await s.execute(text("SELECT status FROM documents WHERE id = :id"), {"id": did})).scalar_one()
        nchunks = (await s.execute(text("SELECT count(*) FROM chunks WHERE document_id = :id"), {"id": did})).scalar_one()
    assert status == "ready"
    assert nchunks >= 1
```

- [x] **Step 2: Run it to verify it fails**

Run: `cd backend && uv run pytest tests/test_ingestion_storage.py -v`
Expected: FAIL (ingestion still reads `doc.storage_path` as a filesystem path; the key `u/a.txt` is not a real file).

- [x] **Step 3: Update ingestion to download from storage**

In `backend/app/ingestion/pipeline.py`, change Phase 1 to also capture the key, and download to a temp file before parsing. Replace the parse section:
```python
import os
import tempfile

from .. import storage
```
In `run`, after Phase 1 captures `storage_path, mime_type, filename`, replace `blocks = parse(Path(storage_path), mime_type)` with:
```python
        data = await storage.get_bytes(storage_path)
        ext = os.path.splitext(storage_path)[1]
        with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as tmp:
            tmp.write(data)
            tmp_path = Path(tmp.name)
        try:
            blocks = parse(tmp_path, mime_type)
        finally:
            tmp_path.unlink(missing_ok=True)
```
(Keep the rest of Phase 1/2 unchanged. `Path` is already imported.)

- [x] **Step 4: Run it to verify pass**

Run: `cd backend && uv run pytest tests/test_ingestion_storage.py -v` → PASS.

- [x] **Step 5: Commit**

```bash
git add backend/app/ingestion/pipeline.py backend/tests/test_ingestion_storage.py
git commit -m "feat(storage): ingestion downloads source file from MinIO to parse"
```

---

## Task 5: Ownership-checked download endpoint

**Files:**
- Modify: `backend/app/api/documents.py` (add `GET /{document_id}/file`)
- Test: `backend/tests/test_documents_api.py` (download is user-scoped)

- [x] **Step 1: Add the failing test**

Append to `backend/tests/test_documents_api.py`:
```python
@pytest.mark.asyncio
async def test_download_is_owner_only(client, fake_google, monkeypatch, s3):
    from app.api import documents as docs_api
    monkeypatch.setattr(docs_api.BackgroundTasks, "add_task", lambda *a, **k: None)

    t1 = await _token(client, "boss@example.com")
    up = await client.post(
        "/api/documents",
        files={"file": ("a.md", io.BytesIO(b"# secret"), "text/markdown")},
        headers={"Authorization": f"Bearer {t1}"},
    )
    doc_id = up.json()["id"]

    # Owner can download.
    mine = await client.get(f"/api/documents/{doc_id}/file", headers={"Authorization": f"Bearer {t1}"})
    assert mine.status_code == 200
    assert mine.content == b"# secret"

    # Another user cannot (RLS hides the row → 404).
    from sqlalchemy import text as _text

    from app.db import SessionLocal as _SL
    async with _SL() as s:
        await s.execute(_text("INSERT INTO allowed_emails (email) VALUES ('m@example.com')"))
        await s.commit()
    t2 = await _token(client, "m@example.com")
    theirs = await client.get(f"/api/documents/{doc_id}/file", headers={"Authorization": f"Bearer {t2}"})
    assert theirs.status_code == 404
```

- [x] **Step 2: Run it to verify it fails**

Run: `cd backend && uv run pytest tests/test_documents_api.py::test_download_is_owner_only -v`
Expected: FAIL (no `/file` route → 404 for owner too, or 405).

- [x] **Step 3: Add the download endpoint**

In `backend/app/api/documents.py`, add imports `import io` and `from fastapi.responses import StreamingResponse`, then add:
```python
@router.get("/{document_id}/file")
async def download_document(
    document_id: UUID, session: AsyncSession = Depends(get_user_session)
) -> StreamingResponse:
    doc = await session.get(Document, document_id)
    if doc is None:  # RLS hides other users' documents.
        raise HTTPException(status_code=404, detail="document not found")
    data = await storage.get_bytes(doc.storage_path)
    return StreamingResponse(
        io.BytesIO(data),
        media_type=doc.mime_type,
        headers={"Content-Disposition": f'inline; filename="{doc.filename}"'},
    )
```
The file is streamed through the authenticated, RLS-scoped endpoint, so MinIO stays private (no public presigned URLs) and a non-owner gets a 404 because RLS makes the row invisible.

- [x] **Step 4: Run it to verify pass**

Run: `cd backend && uv run pytest tests/test_documents_api.py -v` → PASS (all).

- [x] **Step 5: Commit**

```bash
git add backend/app/api/documents.py backend/tests/test_documents_api.py
git commit -m "feat(storage): ownership-checked Document download endpoint"
```

---

## Task 6: Bucket bootstrap on startup, and cleanup

**Files:**
- Modify: `backend/app/main.py` (ensure bucket in lifespan)
- Modify: `README.md` (storage note) and remove the now-dead `upload_dir` config if unused
- Test: full suite + ruff

- [x] **Step 1: Ensure the bucket exists at startup**

In `backend/app/main.py`'s `lifespan`, before `yield`, add:
```python
    from . import storage

    await storage.ensure_bucket()
    log.info("object storage ready (bucket=%s)", settings.s3_bucket)
```
(`settings` is already imported in main.py.)

- [x] **Step 2: Remove the dead local-upload config**

`app/config.py` still has `upload_dir: Path = Path("./uploads")` and a `settings.upload_dir.mkdir(...)` at import. Grep for remaining uses:
```bash
cd backend && grep -rn "upload_dir" app/
```
If the only references are the field + the `mkdir` line, remove BOTH (documents.py no longer uses local disk). If anything else uses it, leave it and note why. Remove `UPLOAD_DIR` from `.env.example`.

- [x] **Step 3: Update the README storage line**

In `README.md`, change the layout note `uploads/        Original document files (gitignored)` to note files now live in MinIO, and update the "Stack" list to mention MinIO for document storage. Keep it to one or two lines.

- [x] **Step 4: Full suite + lint**

Run:
```bash
cd backend && uv run pytest -q
uv run ruff check .
```
Expected: all pass; ruff clean. Fix any unused-import (F401) fallout from removing `shutil`/`upload_dir`/`Path` usages.

- [x] **Step 5: Commit**

```bash
git add backend/app/main.py backend/app/config.py .env.example README.md
git commit -m "feat(storage): ensure MinIO bucket on startup; drop local uploads dir"
```

---

## Self-Review (completed during planning)

**Spec coverage:** files leave local disk for MinIO (Tasks 3, 6), keyed per user (Task 2/3); ingestion reads from MinIO (Task 4); downloads are ownership-checked via RLS + a streaming endpoint (Task 5); bucket auto-provisions (Task 6); S3 API (boto3) keeps a later cloud-S3 move a config-only change (ADR 0004). Tests use moto so the suite stays hermetic and fast.

**Placeholder scan:** no TBD/TODO; every code step has complete code and exact commands. The one judgement call (how to assert the object exists without leaking the key) is resolved explicitly in Task 3 Step 1 (use S3 listing, do not expose `storage_path`).

**Type/name consistency:** `storage.object_key`, `put_object`, `get_bytes`, `delete_object`, `ensure_bucket` are used identically across documents.py, ingestion/pipeline.py, main.py, and the tests. `storage_path` continues to hold the object key (same column, new meaning). `run_ingestion(doc.id, user.id)` signature unchanged from Plan 1.

**Known limitations (documented, not hidden):**
- Streaming downloads through the API uses backend bandwidth and reads the whole object into memory — fine for personal-corpus PDFs/markdown; switch to presigned URLs or ranged streaming if large media ever lands here. (Recorded as the trade-off vs. keeping MinIO private.)
- `ensure_bucket` on startup needs the MinIO credentials to have bucket-create rights; in a locked-down prod, pre-create the bucket and the call becomes a no-op (it lists first).
