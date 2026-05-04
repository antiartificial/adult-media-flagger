from __future__ import annotations

import json
import sqlite3
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from .scanner import MediaItem


SCHEMA = """
CREATE TABLE IF NOT EXISTS media_items (
  id INTEGER PRIMARY KEY,
  path TEXT NOT NULL UNIQUE,
  sha256 TEXT NOT NULL,
  media_type TEXT NOT NULL,
  mime_type TEXT,
  size_bytes INTEGER NOT NULL,
  width INTEGER,
  height INTEGER,
  metadata_path TEXT,
  source_metadata TEXT,
  scanned_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_media_sha256 ON media_items(sha256);
CREATE INDEX IF NOT EXISTS idx_media_type ON media_items(media_type);

CREATE TABLE IF NOT EXISTS adult_results (
  media_id INTEGER PRIMARY KEY,
  detector TEXT NOT NULL,
  score REAL,
  decision TEXT NOT NULL,
  sampled_frames INTEGER NOT NULL DEFAULT 0,
  frame_results TEXT,
  llava_json TEXT,
  llava_error TEXT,
  final_decision TEXT NOT NULL,
  error TEXT,
  processed_at TEXT NOT NULL,
  FOREIGN KEY(media_id) REFERENCES media_items(id)
);
"""


class Store:
    def __init__(self, path: Path):
        self.path = path
        self.conn = sqlite3.connect(path)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(SCHEMA)
        self.conn.commit()

    def close(self) -> None:
        self.conn.close()

    def upsert_media(self, item: MediaItem) -> int:
        now = utc_now()
        self.conn.execute(
            """
            INSERT INTO media_items (
              path, sha256, media_type, mime_type, size_bytes, width, height,
              metadata_path, source_metadata, scanned_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(path) DO UPDATE SET
              sha256=excluded.sha256,
              media_type=excluded.media_type,
              mime_type=excluded.mime_type,
              size_bytes=excluded.size_bytes,
              width=excluded.width,
              height=excluded.height,
              metadata_path=excluded.metadata_path,
              source_metadata=excluded.source_metadata,
              scanned_at=excluded.scanned_at
            """,
            (
                str(item.path),
                item.sha256,
                item.media_type,
                item.mime_type,
                item.size_bytes,
                item.width,
                item.height,
                str(item.metadata_path) if item.metadata_path else None,
                item.source_metadata,
                now,
            ),
        )
        self.conn.commit()
        row = self.conn.execute("SELECT id FROM media_items WHERE path = ?", (str(item.path),)).fetchone()
        return int(row["id"])

    def iter_unprocessed(self, limit: int | None = None) -> Iterable[sqlite3.Row]:
        query = """
            SELECT m.*
            FROM media_items m
            LEFT JOIN adult_results r ON r.media_id = m.id
            WHERE r.media_id IS NULL
            ORDER BY m.id
        """
        if limit is not None:
            query += " LIMIT ?"
            return self.conn.execute(query, (limit,))
        return self.conn.execute(query)

    def iter_results(self) -> Iterable[sqlite3.Row]:
        return self.conn.execute(
            """
            SELECT m.*, r.detector, r.score, r.decision, r.sampled_frames,
                   r.frame_results, r.llava_json, r.llava_error,
                   r.final_decision, r.error, r.processed_at
            FROM media_items m
            LEFT JOIN adult_results r ON r.media_id = m.id
            ORDER BY m.id
            """
        )

    def save_result(
        self,
        media_id: int,
        detector: str,
        score: float | None,
        decision: str,
        final_decision: str,
        sampled_frames: int = 0,
        frame_results: list[dict[str, Any]] | None = None,
        llava_json: dict[str, Any] | None = None,
        llava_error: str | None = None,
        error: str | None = None,
    ) -> None:
        self.conn.execute(
            """
            INSERT INTO adult_results (
              media_id, detector, score, decision, sampled_frames, frame_results,
              llava_json, llava_error, final_decision, error, processed_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(media_id) DO UPDATE SET
              detector=excluded.detector,
              score=excluded.score,
              decision=excluded.decision,
              sampled_frames=excluded.sampled_frames,
              frame_results=excluded.frame_results,
              llava_json=excluded.llava_json,
              llava_error=excluded.llava_error,
              final_decision=excluded.final_decision,
              error=excluded.error,
              processed_at=excluded.processed_at
            """,
            (
                media_id,
                detector,
                score,
                decision,
                sampled_frames,
                json.dumps(frame_results or [], ensure_ascii=False),
                json.dumps(llava_json, ensure_ascii=False) if llava_json else None,
                llava_error,
                final_decision,
                error,
                utc_now(),
            ),
        )
        self.conn.commit()


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    out = dict(row)
    for key in ("frame_results", "llava_json", "source_metadata"):
        if out.get(key):
            try:
                out[key] = json.loads(out[key])
            except Exception:
                pass
    return out


def write_jsonl(rows: Iterable[sqlite3.Row], output: Path) -> None:
    with output.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row_to_dict(row), ensure_ascii=False) + "\n")

