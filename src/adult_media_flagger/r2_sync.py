from __future__ import annotations

import hashlib
import json
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable


class R2Unavailable(RuntimeError):
    pass


@dataclass(frozen=True)
class SyncSummary:
    uploaded: int = 0
    downloaded: int = 0
    skipped: int = 0
    failed: int = 0
    planned: int = 0
    bytes_uploaded: int = 0
    bytes_downloaded: int = 0


Progress = Callable[[str, Path | str, int, int], None]


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


def sha256_file(path: Path, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(chunk_size), b""):
            digest.update(chunk)
    return digest.hexdigest()


def file_identity(path: Path) -> dict:
    stat = path.stat()
    return {
        "size": stat.st_size,
        "mtime_ns": stat.st_mtime_ns,
        "sha256": sha256_file(path),
    }


def default_manifest_path(root: Path, prefix: str) -> Path:
    safe_prefix = prefix.strip("/").replace("/", "_") or "root"
    return root.parent / f".adult-flag-r2-upload-{safe_prefix}.jsonl"


def load_manifest(path: Path | None) -> dict[str, dict]:
    if not path or not path.exists():
        return {}
    records: dict[str, dict] = {}
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
            key = record.get("key")
            if key:
                records[key] = record
    return records


def append_manifest(path: Path | None, record: dict) -> None:
    if not path:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, sort_keys=True) + "\n")


def manifest_matches(record: dict | None, identity: dict) -> bool:
    if not record:
        return False
    return (
        record.get("size") == identity["size"]
        and record.get("mtime_ns") == identity["mtime_ns"]
        and record.get("sha256") == identity["sha256"]
        and record.get("status") == "uploaded"
    )


def remote_object_matches(client, bucket: str, key: str, size: int) -> bool:
    try:
        response = client.head_object(Bucket=bucket, Key=key)
    except Exception:
        return False
    return int(response.get("ContentLength", -1)) == size


def retry(operation: Callable[[], None], attempts: int, delay_seconds: float) -> None:
    last_exc: Exception | None = None
    for attempt in range(max(1, attempts)):
        try:
            operation()
            return
        except Exception as exc:
            last_exc = exc
            if attempt + 1 < attempts:
                time.sleep(delay_seconds * (2**attempt))
    if last_exc:
        raise last_exc


def upload_directory(
    root: Path,
    bucket: str,
    prefix: str,
    endpoint_url: str | None = None,
    *,
    dry_run: bool = False,
    skip_existing: bool = True,
    verify_remote: bool = False,
    manifest_path: Path | None = None,
    retries: int = 3,
    progress: Progress | None = None,
) -> SyncSummary:
    client = make_r2_client(endpoint_url)
    root = root.resolve()
    manifest = manifest_path or default_manifest_path(root, prefix)
    manifest_records = load_manifest(manifest)
    files = list(iter_upload_files(root))
    summary = SyncSummary(planned=len(files))

    uploaded = skipped = failed = bytes_uploaded = 0
    for index, path in enumerate(files, start=1):
        key = object_key(root, path.resolve(), prefix)
        identity = file_identity(path)

        if skip_existing and manifest_matches(manifest_records.get(key), identity):
            skipped += 1
            if progress:
                progress("skip-manifest", path, index, len(files))
            continue

        if skip_existing and verify_remote and remote_object_matches(client, bucket, key, identity["size"]):
            append_manifest(
                manifest,
                {
                    "status": "uploaded",
                    "bucket": bucket,
                    "key": key,
                    "path": str(path),
                    **identity,
                    "verified_remote": True,
                    "uploaded_at": time.time(),
                },
            )
            skipped += 1
            if progress:
                progress("skip-remote", path, index, len(files))
            continue

        if dry_run:
            skipped += 1
            if progress:
                progress("dry-run", path, index, len(files))
            continue

        try:
            retry(lambda: client.upload_file(str(path), bucket, key), retries, 1.0)
            append_manifest(
                manifest,
                {
                    "status": "uploaded",
                    "bucket": bucket,
                    "key": key,
                    "path": str(path),
                    **identity,
                    "uploaded_at": time.time(),
                },
            )
            uploaded += 1
            bytes_uploaded += identity["size"]
            if progress:
                progress("upload", path, index, len(files))
        except Exception as exc:
            append_manifest(
                manifest,
                {
                    "status": "failed",
                    "bucket": bucket,
                    "key": key,
                    "path": str(path),
                    **identity,
                    "error": str(exc),
                    "failed_at": time.time(),
                },
            )
            failed += 1
            if progress:
                progress("failed", path, index, len(files))

    return SyncSummary(
        uploaded=uploaded,
        skipped=skipped,
        failed=failed,
        planned=len(files),
        bytes_uploaded=bytes_uploaded,
    )


def download_prefix(
    output_dir: Path,
    bucket: str,
    prefix: str,
    endpoint_url: str | None = None,
    *,
    skip_existing: bool = True,
    dry_run: bool = False,
    retries: int = 3,
    progress: Progress | None = None,
) -> SyncSummary:
    client = make_r2_client(endpoint_url)
    clean_prefix = prefix.strip("/")
    paginator = client.get_paginator("list_objects_v2")
    downloaded = skipped = failed = bytes_downloaded = planned = 0
    for page in paginator.paginate(Bucket=bucket, Prefix=clean_prefix):
        for item in page.get("Contents", []):
            key = item["Key"]
            if key.endswith("/"):
                continue
            planned += 1
            rel = key[len(clean_prefix) :].lstrip("/") if clean_prefix else key
            dest = output_dir / rel
            size = int(item.get("Size", 0))
            if skip_existing and dest.exists() and dest.stat().st_size == size:
                skipped += 1
                if progress:
                    progress("skip-local", dest, planned, 0)
                continue
            if dry_run:
                skipped += 1
                if progress:
                    progress("dry-run", key, planned, 0)
                continue
            dest.parent.mkdir(parents=True, exist_ok=True)
            try:
                retry(lambda: client.download_file(bucket, key, str(dest)), retries, 1.0)
                downloaded += 1
                bytes_downloaded += size
                if progress:
                    progress("download", dest, planned, 0)
            except Exception:
                failed += 1
                if progress:
                    progress("failed", key, planned, 0)
    return SyncSummary(
        downloaded=downloaded,
        skipped=skipped,
        failed=failed,
        planned=planned,
        bytes_downloaded=bytes_downloaded,
    )
