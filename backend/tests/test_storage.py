import boto3
import pytest
from botocore.exceptions import ClientError
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
    with pytest.raises(ClientError):
        await storage.get_bytes(key)


@pytest.mark.asyncio
async def test_ensure_bucket_is_idempotent():
    with mock_aws():
        await storage.ensure_bucket()
        await storage.ensure_bucket()  # second call must not raise
