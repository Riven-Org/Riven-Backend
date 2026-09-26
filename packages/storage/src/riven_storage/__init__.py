"""Object storage for run logs and artifacts (ticket S01.4.3).

Services never write artifacts to local disk: bytes go to an S3-compatible bucket (MinIO
locally, S3 in the cloud) under an org-prefixed key, and users download them through
short-lived presigned URLs.
"""

import asyncio
import re
from typing import Any

import boto3
from botocore.config import Config
from pydantic_settings import BaseSettings, SettingsConfigDict

_UNSAFE = re.compile(r"[^A-Za-z0-9._-]")


class StorageSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="RIVEN_S3_", extra="ignore")

    endpoint_url: str | None = "http://localhost:9000"
    region: str = "us-east-1"
    bucket: str = "riven-artifacts"
    access_key: str = "riven"
    secret_key: str = "riven-dev-secret"


def artifact_key(org_id: str, run_id: str, name: str) -> str:
    """Org-prefixed object key; the org prefix keeps tenants apart in the bucket."""
    parts = (org_id, run_id, name)
    if any(not p or p in {".", ".."} for p in parts):
        raise ValueError("org_id, run_id and name must be non-empty path segments")
    return "/".join(_UNSAFE.sub("_", p) for p in parts)


class ObjectStore:
    """Async facade over an S3-compatible bucket (boto3 calls run in a thread)."""

    def __init__(self, settings: StorageSettings | None = None, client: Any = None) -> None:
        self.settings = settings or StorageSettings()
        self._client = client or boto3.client(
            "s3",
            endpoint_url=self.settings.endpoint_url,
            region_name=self.settings.region,
            aws_access_key_id=self.settings.access_key,
            aws_secret_access_key=self.settings.secret_key,
            config=Config(signature_version="s3v4"),
        )

    @property
    def bucket(self) -> str:
        return self.settings.bucket

    async def ensure_bucket(self) -> None:
        existing = await asyncio.to_thread(self._client.list_buckets)
        if not any(b["Name"] == self.bucket for b in existing.get("Buckets", [])):
            await asyncio.to_thread(self._client.create_bucket, Bucket=self.bucket)

    async def put(self, key: str, data: bytes, content_type: str) -> int:
        await asyncio.to_thread(
            self._client.put_object,
            Bucket=self.bucket,
            Key=key,
            Body=data,
            ContentType=content_type,
        )
        return len(data)

    async def get(self, key: str) -> bytes:
        response = await asyncio.to_thread(self._client.get_object, Bucket=self.bucket, Key=key)
        body: bytes = await asyncio.to_thread(response["Body"].read)
        return body

    def presigned_download_url(self, key: str, *, expires_in: int = 900) -> str:
        """A time-limited GET URL; the caller must have checked the user may see this run."""
        url: str = self._client.generate_presigned_url(
            "get_object", Params={"Bucket": self.bucket, "Key": key}, ExpiresIn=expires_in
        )
        return url


__all__ = ["ObjectStore", "StorageSettings", "artifact_key"]
