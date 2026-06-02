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
