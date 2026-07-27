"""S3-compatible object storage for deployment (Supabase Storage, MinIO, AWS S3, …).

boto3 is synchronous, so every call runs in a worker thread (`asyncio.to_thread`) exactly as the
local adapter does — a slow upload never blocks the event loop. The bucket is private: objects are
written with no ACL and the adapter never generates public or pre-signed URLs. Files are served
only through authenticated backend endpoints, which read bytes through `read()`.

Timeouts and bounded retries come from a botocore `Config`, so a flaky network fails predictably
instead of hanging. Keys are the same opaque, application-generated strings the local adapter uses
(`{user_id}/{tender_id}/{uuid}.pdf`), which are valid S3 object keys as-is.
"""

from __future__ import annotations

import asyncio
from typing import Any

from app.core.config import S3Config
from app.core.logging import get_logger

logger = get_logger(__name__)


def _build_client(config: S3Config) -> Any:
    """Create a boto3 S3 client. Imported lazily so the dependency is only needed for S3."""
    import boto3
    from botocore.config import Config as BotoConfig

    boto_config = BotoConfig(
        connect_timeout=config.connect_timeout,
        read_timeout=config.read_timeout,
        retries={"max_attempts": config.max_attempts, "mode": "adaptive"},
        signature_version="s3v4",
        # Path-style addressing works with Supabase Storage and MinIO, where virtual-host
        # style buckets are not available.
        s3={"addressing_style": "path"},
    )
    return boto3.client(
        "s3",
        endpoint_url=config.endpoint_url,
        region_name=config.region,
        aws_access_key_id=config.access_key_id,
        aws_secret_access_key=config.secret_access_key,
        config=boto_config,
    )


def _is_not_found(error: Any) -> bool:
    """True when a botocore ClientError means the object/key is absent."""
    from botocore.exceptions import ClientError

    if not isinstance(error, ClientError):
        return False
    code = error.response.get("Error", {}).get("Code", "")
    status = error.response.get("ResponseMetadata", {}).get("HTTPStatusCode")
    return code in {"NoSuchKey", "NoSuchBucket", "404", "NotFound"} or status == 404


class S3Storage:
    """S3-compatible implementation of the `StorageBackend` protocol.

    `client` may be injected for tests; in production it is built lazily from `config` on first
    use and reused (boto3 clients are safe to share across threads).
    """

    def __init__(self, config: S3Config, *, client: Any | None = None) -> None:
        self._config = config
        self._client = client

    def _get_client(self) -> Any:
        if self._client is None:
            self._client = _build_client(self._config)
        return self._client

    async def save(self, key: str, content: bytes) -> None:
        client = self._get_client()

        def _put() -> None:
            client.put_object(
                Bucket=self._config.bucket_name,
                Key=key,
                Body=content,
                ContentType="application/pdf",
            )

        await asyncio.to_thread(_put)

    async def read(self, key: str) -> bytes:
        client = self._get_client()

        def _get() -> bytes:
            from botocore.exceptions import ClientError

            try:
                response = client.get_object(Bucket=self._config.bucket_name, Key=key)
                return response["Body"].read()  # type: ignore[no-any-return]
            except ClientError as exc:
                if _is_not_found(exc):
                    raise FileNotFoundError(key) from exc
                raise

        return await asyncio.to_thread(_get)

    async def delete(self, key: str) -> bool:
        client = self._get_client()

        def _delete() -> bool:
            from botocore.exceptions import ClientError

            # head_object first so a missing key reports False, matching the local adapter and
            # the protocol contract. delete_object alone is a 204 even when the key is absent.
            try:
                client.head_object(Bucket=self._config.bucket_name, Key=key)
            except ClientError as exc:
                if _is_not_found(exc):
                    return False
                raise
            client.delete_object(Bucket=self._config.bucket_name, Key=key)
            return True

        return await asyncio.to_thread(_delete)

    async def exists(self, key: str) -> bool:
        client = self._get_client()

        def _head() -> bool:
            from botocore.exceptions import ClientError

            try:
                client.head_object(Bucket=self._config.bucket_name, Key=key)
                return True
            except ClientError as exc:
                if _is_not_found(exc):
                    return False
                raise

        return await asyncio.to_thread(_head)
