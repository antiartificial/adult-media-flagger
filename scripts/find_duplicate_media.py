from __future__ import annotations

import argparse
import csv
import hashlib
import os
import sys
from collections import defaultdict
from pathlib import Path


STATE_FILE_NAMES = {
    ".adult-flag-r2-download-twitter-media.sqlite",
    ".adult-flag-r2-download-twitter-media.sqlite-journal",
    ".adult-flag-r2-download-twitter-media.sqlite-wal",
    ".adult-flag-r2-download-twitter-media.sqlite-shm",
}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--media-dir", required=True)
    parser.add_argument("--output-csv", required=True)
    parser.add_argument("--summary-path", required=True)
    parser.add_argument("--deletion-csv", default=None)
    parser.add_argument("--delete-local", action="store_true")
    parser.add_argument("--delete-r2", action="store_true")
    parser.add_argument("--r2-prefix", default="twitter-media")
    parser.add_argument("--keep-strategy", choices=["first", "shortest-name"], default="first")
    args = parser.parse_args()

    media_dir = Path(args.media_dir)
    output_csv = Path(args.output_csv)
    summary_path = Path(args.summary_path)
    deletion_csv = Path(args.deletion_csv) if args.deletion_csv else output_csv.with_name("duplicate-media-deletions.csv")

    files_by_size: dict[int, list[Path]] = defaultdict(list)
    for path in media_dir.rglob("*"):
        if not path.is_file() or path.name in STATE_FILE_NAMES:
            continue
        files_by_size[path.stat().st_size].append(path)

    candidate_groups = {size: paths for size, paths in files_by_size.items() if len(paths) > 1}
    hash_groups: dict[str, list[Path]] = defaultdict(list)
    candidate_files = sum(len(paths) for paths in candidate_groups.values())

    hashed = 0
    for paths in candidate_groups.values():
        for path in paths:
            hashed += 1
            if hashed % 1000 == 0:
                print(f"hashed={hashed}/{candidate_files}")
            hash_groups[sha256_file(path)].append(path)

    duplicate_groups = [(digest, paths) for digest, paths in hash_groups.items() if len(paths) > 1]
    duplicate_groups.sort(key=lambda item: (-item[1][0].stat().st_size * (len(item[1]) - 1), str(item[1][0])))
    deletion_plan = build_deletion_plan(duplicate_groups, media_dir, args.r2_prefix, args.keep_strategy)

    output_csv.parent.mkdir(parents=True, exist_ok=True)
    with output_csv.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["group_id", "sha256", "size_bytes", "duplicate_count", "wasted_bytes", "action", "r2_key", "path"])
        for group_id, (digest, paths) in enumerate(duplicate_groups, start=1):
            size = paths[0].stat().st_size
            wasted = size * (len(paths) - 1)
            keep_path = choose_keep_path(paths, args.keep_strategy)
            for path in sorted(paths):
                action = "keep" if path == keep_path else "delete"
                writer.writerow([group_id, digest, size, len(paths), wasted, action, r2_key_for_path(path, media_dir, args.r2_prefix), str(path)])

    write_deletion_csv(deletion_csv, deletion_plan)

    local_deleted = 0
    local_delete_errors = 0
    r2_deleted = 0
    r2_delete_errors = 0
    if args.delete_local:
        local_deleted, local_delete_errors = delete_local_files(deletion_plan)
        write_deletion_csv(deletion_csv, deletion_plan)
    if args.delete_r2:
        r2_deleted, r2_delete_errors = delete_r2_objects(deletion_plan)
        write_deletion_csv(deletion_csv, deletion_plan)

    total_files = sum(len(paths) for paths in files_by_size.values())
    duplicate_files = sum(len(paths) for _, paths in duplicate_groups)
    duplicate_extra_files = sum(len(paths) - 1 for _, paths in duplicate_groups)
    wasted_bytes = sum(paths[0].stat().st_size * (len(paths) - 1) for _, paths in duplicate_groups)

    lines = [
        f"media_dir={media_dir}",
        f"total_files={total_files}",
        f"candidate_same_size_files={candidate_files}",
        f"duplicate_groups={len(duplicate_groups)}",
        f"duplicate_files={duplicate_files}",
        f"duplicate_extra_files={duplicate_extra_files}",
        f"wasted_bytes={wasted_bytes}",
        f"wasted_gib={wasted_bytes / (1024 ** 3):.3f}",
        f"csv={output_csv}",
        f"deletion_csv={deletion_csv}",
        f"delete_local_requested={args.delete_local}",
        f"local_deleted={local_deleted}",
        f"local_delete_errors={local_delete_errors}",
        f"delete_r2_requested={args.delete_r2}",
        f"r2_deleted={r2_deleted}",
        f"r2_delete_errors={r2_delete_errors}",
    ]
    summary_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))


def sha256_file(path: Path, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(chunk_size), b""):
            digest.update(chunk)
    return digest.hexdigest()


def choose_keep_path(paths: list[Path], strategy: str) -> Path:
    sorted_paths = sorted(paths)
    if strategy == "shortest-name":
        return sorted(sorted_paths, key=lambda path: (len(path.name), path.name))[0]
    return sorted_paths[0]


def r2_key_for_path(path: Path, media_dir: Path, prefix: str) -> str:
    rel = path.relative_to(media_dir).as_posix()
    clean_prefix = prefix.strip("/")
    return f"{clean_prefix}/{rel}" if clean_prefix else rel


def build_deletion_plan(
    duplicate_groups: list[tuple[str, list[Path]]],
    media_dir: Path,
    prefix: str,
    keep_strategy: str,
) -> list[dict[str, str | int]]:
    plan: list[dict[str, str | int]] = []
    for group_id, (digest, paths) in enumerate(duplicate_groups, start=1):
        keep_path = choose_keep_path(paths, keep_strategy)
        size = keep_path.stat().st_size
        for path in sorted(paths):
            if path == keep_path:
                continue
            plan.append(
                {
                    "group_id": group_id,
                    "sha256": digest,
                    "size_bytes": size,
                    "keep_path": str(keep_path),
                    "delete_path": str(path),
                    "r2_key": r2_key_for_path(path, media_dir, prefix),
                    "local_status": "planned",
                    "r2_status": "planned",
                    "error": "",
                }
            )
    return plan


def write_deletion_csv(path: Path, plan: list[dict[str, str | int]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    columns = [
        "group_id",
        "sha256",
        "size_bytes",
        "keep_path",
        "delete_path",
        "r2_key",
        "local_status",
        "r2_status",
        "error",
    ]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        for row in plan:
            writer.writerow(row)


def delete_local_files(plan: list[dict[str, str | int]]) -> tuple[int, int]:
    deleted = 0
    errors = 0
    for row in plan:
        path = Path(str(row["delete_path"]))
        try:
            if path.exists():
                path.unlink()
            row["local_status"] = "deleted"
            deleted += 1
        except Exception as exc:
            row["local_status"] = "error"
            row["error"] = append_error(str(row.get("error", "")), f"local: {exc}")
            errors += 1
    return deleted, errors


def delete_r2_objects(plan: list[dict[str, str | int]]) -> tuple[int, int]:
    repo_root = Path(__file__).resolve().parents[1]
    src_path = repo_root / "src"
    if str(src_path) not in sys.path:
        sys.path.insert(0, str(src_path))

    from adult_media_flagger.env import load_env_file
    from adult_media_flagger.r2_sync import make_r2_client

    load_env_file()
    bucket = os.environ.get("ADULT_FLAG_R2_BUCKET")
    if not bucket:
        raise SystemExit("ADULT_FLAG_R2_BUCKET is required for --delete-r2")

    client = make_r2_client()
    deleted = 0
    errors = 0
    for row in plan:
        key = str(row["r2_key"])
        try:
            client.delete_object(Bucket=bucket, Key=key)
            row["r2_status"] = "deleted"
            deleted += 1
        except Exception as exc:
            row["r2_status"] = "error"
            row["error"] = append_error(str(row.get("error", "")), f"r2: {exc}")
            errors += 1
    return deleted, errors


def append_error(existing: str, new_error: str) -> str:
    return f"{existing}; {new_error}" if existing else new_error


if __name__ == "__main__":
    main()
