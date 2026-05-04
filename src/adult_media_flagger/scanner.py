from __future__ import annotations

import hashlib
import json
import mimetypes
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp", ".tif", ".tiff", ".heic"}
VIDEO_EXTENSIONS = {".mp4", ".mov", ".m4v", ".webm", ".mkv", ".avi"}


@dataclass(frozen=True)
class MediaItem:
    path: Path
    sha256: str
    media_type: str
    mime_type: str | None
    size_bytes: int
    width: int | None = None
    height: int | None = None
    metadata_path: Path | None = None
    source_metadata: str | None = None


def classify_path(path: Path) -> str | None:
    ext = path.suffix.lower()
    if ext in IMAGE_EXTENSIONS:
        return "image"
    if ext in VIDEO_EXTENSIONS:
        return "video"
    return None


def sha256_file(path: Path, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(chunk_size), b""):
            digest.update(chunk)
    return digest.hexdigest()


def image_dimensions(path: Path) -> tuple[int | None, int | None]:
    try:
        from PIL import Image

        with Image.open(path) as image:
            return image.size
    except Exception:
        return None, None


def find_sidecar_metadata(path: Path) -> tuple[Path | None, str | None]:
    candidates = [
        path.with_suffix(path.suffix + ".json"),
        path.with_suffix(".json"),
        path.parent / f"{path.stem}.metadata.json",
    ]
    for candidate in candidates:
        if candidate.exists() and candidate.is_file():
            try:
                parsed = json.loads(candidate.read_text(encoding="utf-8"))
                return candidate, json.dumps(parsed, ensure_ascii=False, sort_keys=True)
            except Exception:
                return candidate, candidate.read_text(encoding="utf-8", errors="replace")
    return None, None


def scan_media(root: Path) -> Iterable[MediaItem]:
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        media_type = classify_path(path)
        if media_type is None:
            continue

        width, height = image_dimensions(path) if media_type == "image" else (None, None)
        metadata_path, source_metadata = find_sidecar_metadata(path)
        yield MediaItem(
            path=path.resolve(),
            sha256=sha256_file(path),
            media_type=media_type,
            mime_type=mimetypes.guess_type(path.name)[0],
            size_bytes=path.stat().st_size,
            width=width,
            height=height,
            metadata_path=metadata_path.resolve() if metadata_path else None,
            source_metadata=source_metadata,
        )
