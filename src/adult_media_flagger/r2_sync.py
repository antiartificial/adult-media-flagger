from __future__ import annotations

import os
from pathlib import Path
from typing import Iterable


class R2Unavailable(RuntimeError):
    pass


def make_r2_client(endpoint_url: str | None = None):
    try:
        import boto3
    except Exception as exc:
        raise R2Unavailable("boto3 is not installed. Install with: pip install 'adult-media-flagger[r2]'") from exc

    endpoint = endpoint_url or os.environ.get("R2_ENDPOINT_URL")
    if not endpoint:
        raise R2Unavailable("Set R2_ENDPOINT_URL or pass --endpoint-url")

    return boto3.client(
        "s3",
        endpoint_url=endpoint,
        region_name="auto",
        aws_access_key_id=os.environ.get("AWS_ACCESS_KEY_ID"),
        aws_secret_access_key=os.environ.get("AWS_SECRET_ACCESS_KEY"),
        aws_session_token=os.environ.get("AWS_SESSION_TOKEN") or None,
    )


def iter_upload_files(root: Path) -> Iterable[Path]:
    for path in sorted(root.rglob("*")):
        if path.is_file():
            yield path


def object_key(root: Path, path: Path, prefix: str) -> str:
    rel = path.relative_to(root).as_posix()
    clean_prefix = prefix.strip("/")
    return f"{clean_prefix}/{rel}" if clean_prefix else rel


def upload_directory(root: Path, bucket: str, prefix: str, endpoint_url: str | None = None) -> int:
    client = make_r2_client(endpoint_url)
    count = 0
    for path in iter_upload_files(root):
        client.upload_file(str(path), bucket, object_key(root, path, prefix))
        count += 1
    return count


def download_prefix(output_dir: Path, bucket: str, prefix: str, endpoint_url: str | None = None) -> int:
    client = make_r2_client(endpoint_url)
    clean_prefix = prefix.strip("/")
    paginator = client.get_paginator("list_objects_v2")
    count = 0
    for page in paginator.paginate(Bucket=bucket, Prefix=clean_prefix):
        for item in page.get("Contents", []):
            key = item["Key"]
            if key.endswith("/"):
                continue
            rel = key[len(clean_prefix) :].lstrip("/") if clean_prefix else key
            dest = output_dir / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            client.download_file(bucket, key, str(dest))
            count += 1
    return count
