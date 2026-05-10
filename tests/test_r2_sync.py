from pathlib import Path

from adult_media_flagger.r2_sync import (
    DownloadState,
    UploadState,
    default_download_state_path,
    default_state_path,
    download_state_matches,
    object_key,
    state_matches,
)


def test_object_key_with_prefix():
    root = Path("/tmp/media")
    path = Path("/tmp/media/sub/file.jpg")
    assert object_key(root, path, "twitter-media") == "twitter-media/sub/file.jpg"


def test_object_key_without_prefix():
    root = Path("/tmp/media")
    path = Path("/tmp/media/sub/file.jpg")
    assert object_key(root, path, "") == "sub/file.jpg"


def test_default_state_path_is_outside_root():
    root = Path("/tmp/media")
    state = default_state_path(root, "twitter/media")
    assert state == Path("/tmp/.adult-flag-r2-upload-twitter_media.sqlite")


def test_default_download_state_path_is_inside_download_dir():
    root = Path("/tmp/downloaded-media")
    state = default_download_state_path(root, "twitter/media")
    assert state == Path("/tmp/downloaded-media/.adult-flag-r2-download-twitter_media.sqlite")


def test_upload_state_upserts_latest_record(tmp_path):
    identity = {"size": 1, "mtime_ns": 2, "sha256": "x"}
    state = UploadState(tmp_path / "state.sqlite")
    try:
        state.record("bucket", "key", tmp_path / "file.jpg", identity, "failed", error="boom")
        state.record("bucket", "key", tmp_path / "file.jpg", identity, "uploaded")
        assert state.get("bucket", "key")["status"] == "uploaded"
        assert state.get("bucket", "key")["error"] is None
    finally:
        state.close()


def test_state_matches_identity():
    identity = {"size": 1, "mtime_ns": 2, "sha256": "x"}
    assert state_matches({"status": "uploaded", **identity}, identity)
    assert not state_matches({"status": "failed", **identity}, identity)


def test_download_state_upserts_latest_record(tmp_path):
    identity = {"size": 1, "etag": "abc", "last_modified": "2026-05-04T00:00:00+00:00"}
    state = DownloadState(tmp_path / "state.sqlite")
    try:
        state.record("bucket", "key", tmp_path / "file.jpg", identity, "failed", error="boom")
        state.record("bucket", "key", tmp_path / "file.jpg", identity, "downloaded")
        assert state.get("bucket", "key")["status"] == "downloaded"
        assert state.get("bucket", "key")["error"] is None
    finally:
        state.close()


def test_download_state_matches_remote_identity_and_local_size(tmp_path):
    path = tmp_path / "file.jpg"
    path.write_bytes(b"x")
    identity = {"size": 1, "etag": "abc", "last_modified": "2026-05-04T00:00:00+00:00"}
    assert download_state_matches({"status": "downloaded", **identity}, identity, path)
    assert not download_state_matches({"status": "failed", **identity}, identity, path)
