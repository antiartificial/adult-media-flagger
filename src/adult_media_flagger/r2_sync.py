from __future__ import annotations

import hashlib
import os
import sqlite3
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
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


def default_state_path(root: Path, prefix: str) -> Path:
    safe_prefix = prefix.strip("/").replace("/", "_") or "root"
    return root.parent / f".adult-flag-r2-upload-{safe_prefix}.sqlite"


def default_download_state_path(output_dir: Path, prefix: str) -> Path:
    safe_prefix = prefix.strip("/").replace("/", "_") or "root"
    return output_dir / f".adult-flag-r2-download-{safe_prefix}.sqlite"


class UploadState:
    def __init__(self, path: Path | None):
        self.path = path
        self.conn: sqlite3.Connection | None = None
        if path:
            path.parent.mkdir(parents=True, exist_ok=True)
            self.conn = sqlite3.connect(path)
            self.conn.row_factory = sqlite3.Row
            self.conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS uploads (
                  bucket TEXT NOT NULL,
                  object_key TEXT NOT NULL,
                  local_path TEXT NOT NULL,
                  size INTEGER NOT NULL,
                  mtime_ns INTEGER NOT NULL,
                  sha256 TEXT NOT NULL,
                  status TEXT NOT NULL,
                  error TEXT,
                  verified_remote INTEGER NOT NULL DEFAULT 0,
                  updated_at REAL NOT NULL,
                  PRIMARY KEY (bucket, object_key)
                );
                CREATE INDEX IF NOT EXISTS idx_uploads_status ON uploads(status);
                CREATE INDEX IF NOT EXISTS idx_uploads_local_path ON uploads(local_path);
                """
            )
            self.conn.commit()

    def close(self) -> None:
        if self.conn:
            self.conn.close()

    def get(self, bucket: str, key: str) -> dict | None:
        if not self.conn:
            return None
        row = self.conn.execute(
            "SELECT * FROM uploads WHERE bucket = ? AND object_key = ?",
            (bucket, key),
        ).fetchone()
        return dict(row) if row else None

    def record(
        self,
        bucket: str,
        key: str,
        path: Path,
        identity: dict,
        status: str,
        *,
        error: str | None = None,
        verified_remote: bool = False,
    ) -> None:
        if not self.conn:
            return
        self.conn.execute(
            """
            INSERT INTO uploads (
              bucket, object_key, local_path, size, mtime_ns, sha256,
              status, error, verified_remote, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(bucket, object_key) DO UPDATE SET
              local_path=excluded.local_path,
              size=excluded.size,
              mtime_ns=excluded.mtime_ns,
              sha256=excluded.sha256,
              status=excluded.status,
              error=excluded.error,
              verified_remote=excluded.verified_remote,
              updated_at=excluded.updated_at
            """,
            (
                bucket,
                key,
                str(path),
                identity["size"],
                identity["mtime_ns"],
                identity["sha256"],
                status,
                error,
                1 if verified_remote else 0,
                time.time(),
            ),
        )
        self.conn.commit()


def state_matches(record: dict | None, identity: dict) -> bool:
    if not record:
        return False
    return (
        record.get("size") == identity["size"]
        and record.get("mtime_ns") == identity["mtime_ns"]
        and record.get("sha256") == identity["sha256"]
        and record.get("status") == "uploaded"
    )


class DownloadState:
    def __init__(self, path: Path | None):
        self.path = path
        self.conn: sqlite3.Connection | None = None
        if path:
            path.parent.mkdir(parents=True, exist_ok=True)
            self.conn = sqlite3.connect(path)
            self.conn.row_factory = sqlite3.Row
            self.conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS downloads (
                  bucket TEXT NOT NULL,
                  object_key TEXT NOT NULL,
                  local_path TEXT NOT NULL,
                  size INTEGER NOT NULL,
                  etag TEXT,
                  last_modified TEXT,
                  status TEXT NOT NULL,
                  error TEXT,
                  updated_at REAL NOT NULL,
                  PRIMARY KEY (bucket, object_key)
                );
                CREATE INDEX IF NOT EXISTS idx_downloads_status ON downloads(status);
                CREATE INDEX IF NOT EXISTS idx_downloads_local_path ON downloads(local_path);
                """
            )
            self.conn.commit()

    def close(self) -> None:
        if self.conn:
            self.conn.close()

    def get(self, bucket: str, key: str) -> dict | None:
        if not self.conn:
            return None
        row = self.conn.execute(
            "SELECT * FROM downloads WHERE bucket = ? AND object_key = ?",
            (bucket, key),
        ).fetchone()
        return dict(row) if row else None

    def record(
        self,
        bucket: str,
        key: str,
        path: Path,
        identity: dict,
        status: str,
        *,
        error: str | None = None,
    ) -> None:
        if not self.conn:
            return
        self.conn.execute(
            """
            INSERT INTO downloads (
              bucket, object_key, local_path, size, etag,
              last_modified, status, error, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(bucket, object_key) DO UPDATE SET
              local_path=excluded.local_path,
              size=excluded.size,
              etag=excluded.etag,
              last_modified=excluded.last_modified,
              status=excluded.status,
              error=excluded.error,
              updated_at=excluded.updated_at
            """,
            (
                bucket,
                key,
                str(path),
                identity["size"],
                identity.get("etag"),
                identity.get("last_modified"),
                status,
                error,
                time.time(),
            ),
        )
        self.conn.commit()


def download_state_matches(record: dict | None, identity: dict, path: Path) -> bool:
    if not record or not path.exists():
        return False
    if path.stat().st_size != identity["size"]:
        return False
    return (
        record.get("size") == identity["size"]
        and record.get("etag") == identity.get("etag")
        and record.get("last_modified") == identity.get("last_modified")
        and record.get("status") == "downloaded"
    )


def remote_identity(item: dict) -> dict:
    last_modified = item.get("LastModified")
    return {
        "size": int(item.get("Size", 0)),
        "etag": item.get("ETag", "").strip('"') or None,
        "last_modified": last_modified.isoformat() if hasattr(last_modified, "isoformat") else str(last_modified or ""),
    }


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


def upload_one(client, path: Path, bucket: str, key: str, retries: int) -> tuple[bool, str | None]:
    try:
        retry(lambda: client.upload_file(str(path), bucket, key), retries, 1.0)
        return True, None
    except Exception as exc:
        return False, str(exc)


def download_one(client, bucket: str, key: str, dest: Path, retries: int) -> tuple[bool, str | None]:
    try:
        dest.parent.mkdir(parents=True, exist_ok=True)
        retry(lambda: client.download_file(bucket, key, str(dest)), retries, 1.0)
        return True, None
    except Exception as exc:
        return False, str(exc)


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
    state_path: Path | None = None,
    retries: int = 3,
    workers: int = 4,
    progress: Progress | None = None,
) -> SyncSummary:
    client = make_r2_client(endpoint_url)
    root = root.resolve()
    state_file = state_path or manifest_path or default_state_path(root, prefix)
    state = UploadState(state_file)
    files = list(iter_upload_files(root))

    uploaded = skipped = failed = bytes_uploaded = 0
    try:
        pending_uploads: list[tuple[int, Path, str, dict]] = []
        for index, path in enumerate(files, start=1):
            key = object_key(root, path.resolve(), prefix)
            identity = file_identity(path)

            if skip_existing and state_matches(state.get(bucket, key), identity):
                skipped += 1
                if progress:
                    progress("skip-state", path, index, len(files))
                continue

            if skip_existing and verify_remote and remote_object_matches(client, bucket, key, identity["size"]):
                state.record(bucket, key, path, identity, "uploaded", verified_remote=True)
                skipped += 1
                if progress:
                    progress("skip-remote", path, index, len(files))
                continue

            if dry_run:
                skipped += 1
                if progress:
                    progress("dry-run", path, index, len(files))
                continue

            pending_uploads.append((index, path, key, identity))

        if pending_uploads:
            worker_count = max(1, workers)
            with ThreadPoolExecutor(max_workers=worker_count) as executor:
                futures = {
                    executor.submit(upload_one, client, path, bucket, key, retries): (index, path, key, identity)
                    for index, path, key, identity in pending_uploads
                }
                for future in as_completed(futures):
                    index, path, key, identity = futures[future]
                    ok, error = future.result()
                    if ok:
                        state.record(bucket, key, path, identity, "uploaded")
                        uploaded += 1
                        bytes_uploaded += identity["size"]
                        if progress:
                            progress("upload", path, index, len(files))
                    else:
                        state.record(bucket, key, path, identity, "failed", error=error)
                        failed += 1
                        if progress:
                            progress("failed", path, index, len(files))
    finally:
        state.close()

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
    state_path: Path | None = None,
    retries: int = 3,
    workers: int = 4,
    progress: Progress | None = None,
) -> SyncSummary:
    client = make_r2_client(endpoint_url)
    clean_prefix = prefix.strip("/")
    paginator = client.get_paginator("list_objects_v2")
    output_dir = output_dir.resolve()
    state = DownloadState(state_path or default_download_state_path(output_dir, prefix))
    downloaded = skipped = failed = bytes_downloaded = planned = 0
    try:
        pending_downloads: list[tuple[int, str, Path, dict]] = []
        for page in paginator.paginate(Bucket=bucket, Prefix=clean_prefix):
            for item in page.get("Contents", []):
                key = item["Key"]
                if key.endswith("/"):
                    continue
                planned += 1
                rel = key[len(clean_prefix) :].lstrip("/") if clean_prefix else key
                dest = output_dir / rel
                identity = remote_identity(item)
                if skip_existing and download_state_matches(state.get(bucket, key), identity, dest):
                    skipped += 1
                    if progress:
                        progress("skip-state", dest, planned, 0)
                    continue
                if skip_existing and dest.exists() and dest.stat().st_size == identity["size"]:
                    state.record(bucket, key, dest, identity, "downloaded")
                    skipped += 1
                    if progress:
                        progress("skip-local", dest, planned, 0)
                    continue
                if dry_run:
                    skipped += 1
                    if progress:
                        progress("dry-run", key, planned, 0)
                    continue

                pending_downloads.append((planned, key, dest, identity))

        if pending_downloads:
            worker_count = max(1, workers)
            with ThreadPoolExecutor(max_workers=worker_count) as executor:
                futures = {
                    executor.submit(download_one, client, bucket, key, dest, retries): (index, key, dest, identity)
                    for index, key, dest, identity in pending_downloads
                }
                for future in as_completed(futures):
                    index, key, dest, identity = futures[future]
                    ok, error = future.result()
                    if ok:
                        state.record(bucket, key, dest, identity, "downloaded")
                        downloaded += 1
                        bytes_downloaded += identity["size"]
                        if progress:
                            progress("download", dest, index, planned)
                    else:
                        state.record(bucket, key, dest, identity, "failed", error=error)
                        failed += 1
                        if progress:
                            progress("failed", key, index, planned)
    finally:
        state.close()

    return SyncSummary(
        downloaded=downloaded,
        skipped=skipped,
        failed=failed,
        planned=planned,
        bytes_downloaded=bytes_downloaded,
    )
