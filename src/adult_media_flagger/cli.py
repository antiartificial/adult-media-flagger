from __future__ import annotations

import argparse
import os
from pathlib import Path

try:
    from tqdm import tqdm
except Exception:
    def tqdm(iterable, **_kwargs):
        return iterable

from .config import LlavaSettings, Thresholds, VideoSettings
from .env import config_status, load_env_file
from .processor import process_unprocessed
from .r2_sync import download_prefix, upload_directory
from .scanner import scan_media
from .store import Store, write_jsonl


def main() -> None:
    parser = argparse.ArgumentParser(prog="adult-flag")
    parser.add_argument("--db", default="media_flags.sqlite", help="SQLite database path")
    parser.add_argument("--env-file", default=None, help="Path to .env file, default: ./.env")
    subparsers = parser.add_subparsers(dest="command", required=True)

    scan_parser = subparsers.add_parser("scan", help="Scan a directory into the processing DB")
    scan_parser.add_argument("input_dir", help="Directory containing downloaded media")

    process_parser = subparsers.add_parser("process", help="Run adult classifier and optional LLaVA pass")
    process_parser.add_argument("--limit", type=int, default=None)
    process_parser.add_argument("--safe-max", type=float, default=0.35)
    process_parser.add_argument("--adult-min", type=float, default=0.80)
    process_parser.add_argument("--video-frames", type=int, default=16)
    process_parser.add_argument(
        "--llava",
        choices=["off", "review", "flagged", "all"],
        default="review",
        help="When to send images/frames to Ollama LLaVA",
    )
    process_parser.add_argument("--llava-endpoint", default=None)
    process_parser.add_argument("--llava-model", default=None)

    export_parser = subparsers.add_parser("export", help="Export DB rows as JSONL")
    export_parser.add_argument("output", help="Output .jsonl path")

    upload_parser = subparsers.add_parser("r2-upload", help="Upload a local directory to Cloudflare R2")
    upload_parser.add_argument("input_dir")
    upload_parser.add_argument("--bucket", default=None)
    upload_parser.add_argument("--prefix", default=None)
    upload_parser.add_argument("--endpoint-url", default=None)

    download_parser = subparsers.add_parser("r2-download", help="Download a Cloudflare R2 prefix")
    download_parser.add_argument("output_dir")
    download_parser.add_argument("--bucket", default=None)
    download_parser.add_argument("--prefix", default=None)
    download_parser.add_argument("--endpoint-url", default=None)

    subparsers.add_parser("config-check", help="Show loaded configuration without revealing secrets")

    args = parser.parse_args()
    env_loaded = load_env_file(args.env_file)

    if args.command == "config-check":
        if env_loaded:
            print(f"Loaded env file: {env_loaded}")
        else:
            print("Loaded env file: none")
        for key, value in config_status().items():
            print(f"{key}={value}")
        return

    if args.command == "r2-upload":
        bucket = require_value(args.bucket or os.environ.get("ADULT_FLAG_R2_BUCKET"), "bucket")
        prefix = args.prefix if args.prefix is not None else os.environ.get("ADULT_FLAG_R2_MEDIA_PREFIX", "")
        count = upload_directory(Path(args.input_dir), bucket, prefix, args.endpoint_url)
        print(f"Uploaded {count} files to r2://{bucket}/{prefix}")
        return
    if args.command == "r2-download":
        bucket = require_value(args.bucket or os.environ.get("ADULT_FLAG_R2_BUCKET"), "bucket")
        prefix = args.prefix if args.prefix is not None else os.environ.get("ADULT_FLAG_R2_MEDIA_PREFIX", "")
        count = download_prefix(Path(args.output_dir), bucket, prefix, args.endpoint_url)
        print(f"Downloaded {count} files from r2://{bucket}/{prefix}")
        return

    store = Store(Path(args.db))
    try:
        if args.command == "scan":
            scanned = 0
            for item in tqdm(scan_media(Path(args.input_dir)), desc="Scanning"):
                store.upsert_media(item)
                scanned += 1
            print(f"Scanned {scanned} media files into {args.db}")
        elif args.command == "process":
            count = process_unprocessed(
                store=store,
                thresholds=Thresholds(safe_max=args.safe_max, adult_min=args.adult_min),
                video_settings=VideoSettings(max_frames=args.video_frames),
                llava_settings=LlavaSettings(
                    endpoint=args.llava_endpoint or os.environ.get("OLLAMA_ENDPOINT", "http://localhost:11434/api/generate"),
                    model=args.llava_model or os.environ.get("OLLAMA_MODEL", "llava:13b"),
                ),
                llava_mode=args.llava,
                limit=args.limit,
            )
            print(f"Processed {count} media files")
        elif args.command == "export":
            write_jsonl(store.iter_results(), Path(args.output))
            print(f"Wrote {args.output}")
    finally:
        store.close()


def require_value(value: str | None, name: str) -> str:
    if not value:
        raise SystemExit(f"Missing {name}. Pass --{name} or set ADULT_FLAG_R2_BUCKET in .env")
    return value


if __name__ == "__main__":
    main()
