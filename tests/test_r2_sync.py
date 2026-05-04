from pathlib import Path

from adult_media_flagger.r2_sync import (
    default_manifest_path,
    load_manifest,
    manifest_matches,
    object_key,
)


def test_object_key_with_prefix():
    root = Path("/tmp/media")
    path = Path("/tmp/media/sub/file.jpg")
    assert object_key(root, path, "twitter-media") == "twitter-media/sub/file.jpg"


def test_object_key_without_prefix():
    root = Path("/tmp/media")
    path = Path("/tmp/media/sub/file.jpg")
    assert object_key(root, path, "") == "sub/file.jpg"


def test_default_manifest_path_is_outside_root():
    root = Path("/tmp/media")
    manifest = default_manifest_path(root, "twitter/media")
    assert manifest == Path("/tmp/.adult-flag-r2-upload-twitter_media.jsonl")


def test_load_manifest_keeps_latest_record(tmp_path):
    manifest = tmp_path / "manifest.jsonl"
    manifest.write_text(
        '{"key":"a","status":"failed"}\n'
        '{"key":"a","status":"uploaded","size":1,"mtime_ns":2,"sha256":"x"}\n',
        encoding="utf-8",
    )
    assert load_manifest(manifest)["a"]["status"] == "uploaded"


def test_manifest_matches_identity():
    identity = {"size": 1, "mtime_ns": 2, "sha256": "x"}
    assert manifest_matches({"status": "uploaded", **identity}, identity)
    assert not manifest_matches({"status": "failed", **identity}, identity)

