"""S3-compatible storage adapter, driven by an in-memory fake S3 client.

No live Supabase/AWS credentials and no network — the fake reproduces the botocore surface the
adapter uses (put/get/head/delete_object) and raises a real `ClientError` for a missing key, so
the adapter's not-found handling is exercised exactly as it would be against a real endpoint.
"""

from __future__ import annotations

import pytest
from botocore.exceptions import ClientError

from app.core.config import S3Config
from app.storage.s3 import S3Storage


def _not_found() -> ClientError:
    return ClientError(
        {
            "Error": {"Code": "NoSuchKey", "Message": "not found"},
            "ResponseMetadata": {"HTTPStatusCode": 404},
        },
        "GetObject",
    )


class _Body:
    def __init__(self, data: bytes) -> None:
        self._data = data

    def read(self) -> bytes:
        return self._data


class FakeS3Client:
    """Minimal in-memory stand-in for a boto3 S3 client."""

    def __init__(self) -> None:
        self.store: dict[tuple[str, str], bytes] = {}
        self.calls: list[str] = []

    def put_object(self, *, Bucket: str, Key: str, Body: bytes, ContentType: str) -> dict:
        self.calls.append("put")
        assert ContentType == "application/pdf"
        self.store[(Bucket, Key)] = Body
        return {}

    def get_object(self, *, Bucket: str, Key: str) -> dict:
        self.calls.append("get")
        if (Bucket, Key) not in self.store:
            raise _not_found()
        return {"Body": _Body(self.store[(Bucket, Key)])}

    def head_object(self, *, Bucket: str, Key: str) -> dict:
        self.calls.append("head")
        if (Bucket, Key) not in self.store:
            raise _not_found()
        return {"ContentLength": len(self.store[(Bucket, Key)])}

    def delete_object(self, *, Bucket: str, Key: str) -> dict:
        self.calls.append("delete")
        self.store.pop((Bucket, Key), None)
        return {}


def _config() -> S3Config:
    return S3Config(
        endpoint_url="https://example.storage/s3",
        region="us-east-1",
        access_key_id="key",
        secret_access_key="secret",
        bucket_name="bidpilot",
        connect_timeout=10,
        read_timeout=60,
        max_attempts=4,
    )


def _storage() -> tuple[S3Storage, FakeS3Client]:
    client = FakeS3Client()
    return S3Storage(_config(), client=client), client


async def test_save_then_read_roundtrips() -> None:
    storage, _ = _storage()
    key = "user-1/tender-1/abc.pdf"
    await storage.save(key, b"%PDF-1.7 fake")
    assert await storage.read(key) == b"%PDF-1.7 fake"


async def test_save_uses_the_opaque_key_verbatim() -> None:
    storage, client = _storage()
    key = "user-1/tender-1/abc.pdf"
    await storage.save(key, b"data")
    assert ("bidpilot", key) in client.store


async def test_read_missing_key_raises_file_not_found() -> None:
    storage, _ = _storage()
    with pytest.raises(FileNotFoundError):
        await storage.read("nope/missing.pdf")


async def test_exists_reflects_presence() -> None:
    storage, _ = _storage()
    key = "user-1/tender-1/abc.pdf"
    assert await storage.exists(key) is False
    await storage.save(key, b"data")
    assert await storage.exists(key) is True


async def test_delete_returns_true_when_present_false_when_absent() -> None:
    storage, _ = _storage()
    key = "user-1/tender-1/abc.pdf"
    await storage.save(key, b"data")
    assert await storage.delete(key) is True
    assert await storage.delete(key) is False  # already gone
    assert await storage.exists(key) is False


async def test_unexpected_client_error_propagates() -> None:
    """A non-404 error is a real fault and must not be swallowed as 'absent'."""
    storage, client = _storage()

    def _boom(**_: object) -> dict:
        raise ClientError(
            {
                "Error": {"Code": "AccessDenied", "Message": "denied"},
                "ResponseMetadata": {"HTTPStatusCode": 403},
            },
            "GetObject",
        )

    client.get_object = _boom  # type: ignore[method-assign]
    with pytest.raises(ClientError):
        await storage.read("user-1/tender-1/abc.pdf")
