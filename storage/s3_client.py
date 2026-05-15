"""Загрузка фото анкет в S3-совместимое хранилище (MinIO)."""

from __future__ import annotations

import os
import uuid
from typing import Optional

import aioboto3
from botocore.exceptions import ClientError
from dotenv import load_dotenv

load_dotenv()

S3_ENDPOINT = os.getenv("S3_ENDPOINT", "http://localhost:9000")
S3_ACCESS_KEY = os.getenv("S3_ACCESS_KEY", "minio")
S3_SECRET_KEY = os.getenv("S3_SECRET_KEY", "minio123")
S3_BUCKET = os.getenv("S3_BUCKET", "dating-photos")
S3_REGION = os.getenv("S3_REGION", "us-east-1")
S3_PUBLIC_BASE = os.getenv("S3_PUBLIC_BASE", f"{S3_ENDPOINT.rstrip('/')}/{S3_BUCKET}")


class S3Storage:
    def __init__(self):
        self._session = aioboto3.Session()

    async def ensure_bucket(self) -> None:
        async with self._session.client(
            "s3",
            endpoint_url=S3_ENDPOINT,
            aws_access_key_id=S3_ACCESS_KEY,
            aws_secret_access_key=S3_SECRET_KEY,
            region_name=S3_REGION,
        ) as client:
            try:
                await client.head_bucket(Bucket=S3_BUCKET)
            except ClientError:
                await client.create_bucket(Bucket=S3_BUCKET)

    async def upload_bytes(
        self,
        data: bytes,
        *,
        content_type: str = "image/jpeg",
        prefix: str = "profiles",
    ) -> str:
        key = f"{prefix}/{uuid.uuid4().hex}.jpg"
        async with self._session.client(
            "s3",
            endpoint_url=S3_ENDPOINT,
            aws_access_key_id=S3_ACCESS_KEY,
            aws_secret_access_key=S3_SECRET_KEY,
            region_name=S3_REGION,
        ) as client:
            await client.put_object(
                Bucket=S3_BUCKET,
                Key=key,
                Body=data,
                ContentType=content_type,
            )
        return f"{S3_PUBLIC_BASE.rstrip('/')}/{key}"


_storage: Optional[S3Storage] = None


def get_s3_storage() -> S3Storage:
    global _storage
    if _storage is None:
        _storage = S3Storage()
    return _storage
