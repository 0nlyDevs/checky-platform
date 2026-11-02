"""S3-compatible object storage (Neon Object Storage in this project).

The bucket is private: the browser uploads and downloads through short-lived presigned URLs
issued here, so files never pass through the API.

    url = presign_upload("sources/<ws>/<id>.pdf", "application/pdf")
    url = presign_download("sources/<ws>/<id>.pdf")
"""

import asyncio
import time
from functools import lru_cache
from typing import Any

import boto3
from botocore.config import Config

from app.core.config import get_settings

UPLOAD_SECONDS = 10 * 60
DOWNLOAD_SECONDS = 60 * 60


def configured() -> bool:
    s = get_settings()
    return bool(s.storage_endpoint and s.storage_access_key_id and s.storage_secret_access_key)


@lru_cache
def _client(endpoint: str, region: str, key_id: str, secret: str):
    return boto3.client(
        "s3",
        endpoint_url=endpoint,
        region_name=region,
        aws_access_key_id=key_id,
        aws_secret_access_key=secret,
        # Neon Object Storage only supports path-style addressing.
        config=Config(
            s3={"addressing_style": "path"},
            signature_version="s3v4",
            connect_timeout=5,
            read_timeout=10,
            retries={"max_attempts": 2},
        ),
    )


def client():
    s = get_settings()
    return _client(
        s.storage_endpoint, s.storage_region, s.storage_access_key_id, s.storage_secret_access_key
    )


def presign_upload(key: str, content_type: str, expires: int = UPLOAD_SECONDS) -> str:
    """URL the browser PUTs the file to, with the same Content-Type header."""
    return client().generate_presigned_url(
        "put_object",
        Params={"Bucket": get_settings().storage_bucket, "Key": key, "ContentType": content_type},
        ExpiresIn=expires,
    )


def presign_download(key: str, filename: str | None = None, expires: int = DOWNLOAD_SECONDS) -> str:
    params = {"Bucket": get_settings().storage_bucket, "Key": key}
    if filename:
        # Opens in the browser under its original name instead of the storage key.
        safe = filename.replace('"', "")
        params["ResponseContentDisposition"] = f'inline; filename="{safe}"'
    return client().generate_presigned_url("get_object", Params=params, ExpiresIn=expires)


async def head(key: str) -> dict[str, Any] | None:
    """Size and type of an object, or None when it is not there."""
    try:
        r = await asyncio.to_thread(
            client().head_object, Bucket=get_settings().storage_bucket, Key=key
        )
    except Exception:  # noqa: BLE001 - missing or unreadable is the same answer here
        return None
    return {"size": r.get("ContentLength", 0), "content_type": r.get("ContentType")}


async def read(key: str) -> bytes:
    r = await asyncio.to_thread(client().get_object, Bucket=get_settings().storage_bucket, Key=key)
    return await asyncio.to_thread(r["Body"].read)


async def write(key: str, body: bytes, content_type: str) -> None:
    """Store a file the API made itself (a video's keyframe, a blurred copy)."""
    await asyncio.to_thread(
        client().put_object,
        Bucket=get_settings().storage_bucket,
        Key=key,
        Body=body,
        ContentType=content_type,
    )


async def delete(key: str) -> None:
    await asyncio.to_thread(client().delete_object, Bucket=get_settings().storage_bucket, Key=key)


async def check() -> dict[str, Any]:
    """Up when the bucket answers a HEAD with our credential."""
    if not configured():
        return {"status": "not_configured"}
    started = time.monotonic()
    try:
        bucket = get_settings().storage_bucket
        await asyncio.to_thread(client().head_bucket, Bucket=bucket)
        status, detail = "up", None
    except Exception as e:  # noqa: BLE001 - any failure means storage is down
        status, detail = "down", type(e).__name__
    latency = int((time.monotonic() - started) * 1000)
    return {"status": status, "latency_ms": latency, "detail": detail}
