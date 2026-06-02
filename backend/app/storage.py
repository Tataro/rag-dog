"""S3-compatible object storage (MinIO) for uploaded Document files.

A fresh boto3 client is created per call: client creation is cheap, it keeps the
sync boto3 calls confined to the threadpool, and it lets `moto` patch botocore in
tests (a module-level client created at import time would not be mocked).
"""
import boto3
from botocore.config import Config
from botocore.exceptions import ClientError
from fastapi.concurrency import run_in_threadpool

from .config import settings

# Errors that mean "the bucket already exists and is ours" — benign on a concurrent
# multi-instance startup race (two processes both calling ensure_bucket).
_BUCKET_EXISTS_CODES = {"BucketAlreadyOwnedByYou", "BucketAlreadyExists"}


def _client():
    return boto3.client(
        "s3",
        endpoint_url=settings.s3_endpoint_url or None,
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
        if settings.s3_bucket in existing:
            return
        # AWS S3 (unlike MinIO) rejects create_bucket without a LocationConstraint
        # for any region other than us-east-1 — needed for the "portable to cloud
        # S3" goal (ADR 0004).
        kwargs: dict = {"Bucket": settings.s3_bucket}
        if settings.s3_region != "us-east-1":
            kwargs["CreateBucketConfiguration"] = {"LocationConstraint": settings.s3_region}
        try:
            client.create_bucket(**kwargs)
        except ClientError as exc:
            # Lost a startup race with another instance — that's fine.
            if exc.response.get("Error", {}).get("Code") not in _BUCKET_EXISTS_CODES:
                raise

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
