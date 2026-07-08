"""Object storage (MinIO / S3) for uploaded papers.

boto3 is sync — every call is wrapped in ``asyncio.to_thread`` so the event
loop never blocks. Stored URLs use the ``s3://bucket/key`` form; only this
module knows how to resolve them.
"""

from __future__ import annotations

import asyncio
from functools import lru_cache
from typing import Any

from vyakhya.core.config import get_settings
from vyakhya.core.logging import get_logger

log = get_logger(__name__)


@lru_cache
def _client() -> Any:  # boto3 S3 client (cached — thread-safe for our usage)
    import boto3

    settings = get_settings()
    return boto3.client(
        "s3",
        endpoint_url=settings.s3_endpoint,
        aws_access_key_id=settings.s3_access_key,
        aws_secret_access_key=settings.s3_secret_key,
        region_name="us-east-1",
    )


def _ensure_bucket_sync(bucket: str) -> None:
    client = _client()
    try:
        client.head_bucket(Bucket=bucket)
    except Exception:  # noqa: BLE001 - missing bucket (404) or fresh MinIO
        client.create_bucket(Bucket=bucket)
        log.info("created bucket %s", bucket)
    # Anonymous read for figures/ + audio/ so scene <img>/<audio> URLs are
    # stable (no presign expiry) — they're embedded in compositions and
    # rendered headlessly.
    import json

    policy = {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Effect": "Allow",
                "Principal": {"AWS": ["*"]},
                "Action": ["s3:GetObject"],
                "Resource": [
                    f"arn:aws:s3:::{bucket}/figures/*",
                    f"arn:aws:s3:::{bucket}/audio/*",
                ],
            }
        ],
    }
    try:
        client.put_bucket_policy(Bucket=bucket, Policy=json.dumps(policy))
    except Exception as exc:  # noqa: BLE001 - policy is best-effort
        log.warning("could not set bucket policy: %s", exc)


async def put_paper(project_id: str, data: bytes, content_type: str = "application/pdf") -> str:
    """Store the uploaded paper; returns its s3:// URL."""
    bucket = get_settings().s3_bucket
    key = f"papers/{project_id}.pdf"

    def _put() -> None:
        _ensure_bucket_sync(bucket)
        _client().put_object(Bucket=bucket, Key=key, Body=data, ContentType=content_type)

    await asyncio.to_thread(_put)
    log.info("paper stored s3://%s/%s (%d bytes)", bucket, key, len(data))
    return f"s3://{bucket}/{key}"


async def put_figure(project_id: str, index: int, data: bytes) -> str:
    """Store a cropped figure PNG; returns its stable browser-reachable URL
    (figures/ has anonymous read via the bucket policy)."""
    settings = get_settings()
    bucket = settings.s3_bucket
    key = f"figures/{project_id}/fig{index}.png"

    def _put() -> None:
        _ensure_bucket_sync(bucket)
        _client().put_object(Bucket=bucket, Key=key, Body=data, ContentType="image/png")

    await asyncio.to_thread(_put)
    return f"{settings.s3_public_endpoint}/{bucket}/{key}"


async def put_audio(project_id: str, index: int, data: bytes, ext: str = "mp3") -> str:
    """Store a narration clip; returns its stable browser-reachable URL
    (audio/ has anonymous read via the bucket policy)."""
    settings = get_settings()
    bucket = settings.s3_bucket
    key = f"audio/{project_id}/scene{index}.{ext}"

    content_type = "audio/mpeg" if ext == "mp3" else f"audio/{ext}"

    def _put() -> None:
        _ensure_bucket_sync(bucket)
        _client().put_object(Bucket=bucket, Key=key, Body=data, ContentType=content_type)

    await asyncio.to_thread(_put)
    return f"{settings.s3_public_endpoint}/{bucket}/{key}"


async def presign_paper_url(url: str, expires: int = 24 * 3600) -> str:
    """Presigned browser-reachable GET URL for an ``s3://`` paper object."""
    if not url.startswith("s3://"):
        return url
    bucket, _, key = url.removeprefix("s3://").partition("/")
    settings = get_settings()

    def _sign() -> str:
        import boto3

        public = boto3.client(
            "s3",
            endpoint_url=settings.s3_public_endpoint,
            aws_access_key_id=settings.s3_access_key,
            aws_secret_access_key=settings.s3_secret_key,
            region_name="us-east-1",
        )
        return public.generate_presigned_url(
            "get_object", Params={"Bucket": bucket, "Key": key}, ExpiresIn=expires
        )

    return await asyncio.to_thread(_sign)


async def get_object(url: str) -> bytes:
    """Fetch an ``s3://bucket/key`` URL's bytes."""
    if not url.startswith("s3://"):
        raise ValueError(f"not an s3 URL: {url}")
    bucket, _, key = url.removeprefix("s3://").partition("/")

    def _get() -> bytes:
        return _client().get_object(Bucket=bucket, Key=key)["Body"].read()

    return await asyncio.to_thread(_get)


async def delete_object(url: str) -> None:
    """Best-effort delete of an ``s3://bucket/key`` object."""
    if not url.startswith("s3://"):
        return
    bucket, _, key = url.removeprefix("s3://").partition("/")
    try:
        await asyncio.to_thread(lambda: _client().delete_object(Bucket=bucket, Key=key))
    except Exception as exc:  # noqa: BLE001 - deletion is best-effort
        log.warning("failed to delete %s: %s", url, exc)
