from __future__ import annotations

import argparse
import shutil
import sqlite3
from datetime import datetime
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", required=True)
    parser.add_argument("--backup", default=None)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    db_path = Path(args.db)
    backup_path = Path(args.backup) if args.backup else db_path.with_suffix(f".backup-{timestamp()}.sqlite")

    if not db_path.exists():
        raise SystemExit(f"DB not found: {db_path}")

    if not args.dry_run:
        shutil.copy2(db_path, backup_path)

    conn = sqlite3.connect(db_path)
    try:
        missing = conn.execute(
            """
            SELECT id, path
            FROM media_items
            WHERE path IS NOT NULL
            ORDER BY id
            """
        ).fetchall()
        missing = [(media_id, path) for media_id, path in missing if not Path(path).exists()]

        if not args.dry_run and missing:
            ids = [media_id for media_id, _ in missing]
            placeholders = ",".join("?" for _ in ids)
            conn.execute(f"DELETE FROM adult_results WHERE media_id IN ({placeholders})", ids)
            conn.execute(f"DELETE FROM media_items WHERE id IN ({placeholders})", ids)
            conn.commit()

        remaining_media = conn.execute("SELECT count(*) FROM media_items").fetchone()[0]
        remaining_results = conn.execute("SELECT count(*) FROM adult_results").fetchone()[0]
    finally:
        conn.close()

    print(f"db={db_path}")
    print(f"dry_run={args.dry_run}")
    print(f"backup={backup_path if not args.dry_run else 'not-created'}")
    print(f"missing_rows={len(missing)}")
    print(f"remaining_media_items={remaining_media}")
    print(f"remaining_adult_results={remaining_results}")
    for _, path in missing[:10]:
        print(f"missing_sample={path}")


def timestamp() -> str:
    return datetime.now().strftime("%Y%m%d-%H%M%S")


if __name__ == "__main__":
    main()
