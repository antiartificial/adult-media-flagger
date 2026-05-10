from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

from .config import VideoSettings


class FfmpegUnavailable(RuntimeError):
    pass


def tool_command(name: str) -> str:
    env_name = f"ADULT_FLAG_{name.upper()}"
    configured = os.environ.get(env_name)
    if configured:
        configured_path = Path(configured)
        if configured_path.exists():
            return str(configured_path)
        raise FfmpegUnavailable(f"{env_name} points to missing file: {configured}")

    found = shutil.which(name)
    if found is None:
        raise FfmpegUnavailable(f"{name} was not found on PATH")
    return found


def video_duration_seconds(path: Path) -> float | None:
    ffprobe = tool_command("ffprobe")
    cmd = [
        ffprobe,
        "-v",
        "error",
        "-show_entries",
        "format=duration",
        "-of",
        "json",
        str(path),
    ]
    proc = subprocess.run(cmd, check=True, capture_output=True, text=True)
    data = json.loads(proc.stdout)
    duration = data.get("format", {}).get("duration")
    return float(duration) if duration else None


def sample_video_frames(path: Path, settings: VideoSettings) -> list[tuple[float, Path]]:
    ffmpeg = tool_command("ffmpeg")
    duration = video_duration_seconds(path)
    if not duration or duration <= 0:
        return []

    count = max(1, settings.max_frames)
    if duration / count < settings.min_seconds_between_frames:
        count = max(1, int(duration // settings.min_seconds_between_frames) or 1)
    timestamps = evenly_spaced_timestamps(duration, count)

    temp_dir = Path(tempfile.mkdtemp(prefix="adult-flag-frames-"))
    frames: list[tuple[float, Path]] = []
    for index, timestamp in enumerate(timestamps):
        output = temp_dir / f"frame-{index:04d}-{timestamp:.2f}.jpg"
        extract_video_frame(ffmpeg, path, timestamp, output, settings)
        if output.exists():
            frames.append((timestamp, output))
    return frames


def extract_video_frame(ffmpeg: str, path: Path, timestamp: float, output: Path, settings: VideoSettings) -> None:
    cmd = [
        ffmpeg,
        "-hide_banner",
        "-loglevel",
        "error",
        "-ss",
        f"{timestamp:.3f}",
        "-i",
        str(path),
        "-frames:v",
        "1",
        "-q:v",
        str(31 - max(2, min(settings.jpeg_quality, 95)) // 4),
        "-y",
        str(output),
    ]
    try:
        subprocess.run(cmd, check=True)
        return
    except subprocess.CalledProcessError:
        output.unlink(missing_ok=True)

    # Some videos fail FFmpeg's MJPEG encoder on Windows. PNG avoids that encoder
    # path and gives Pillow/opennsfw2 a lossless image to score.
    fallback_output = output.with_suffix(".png")
    fallback_cmd = [
        ffmpeg,
        "-hide_banner",
        "-loglevel",
        "error",
        "-ss",
        f"{timestamp:.3f}",
        "-i",
        str(path),
        "-frames:v",
        "1",
        "-f",
        "image2",
        "-vcodec",
        "png",
        "-vf",
        "format=rgba",
        "-update",
        "1",
        "-y",
        str(fallback_output),
    ]
    subprocess.run(fallback_cmd, check=True)
    if not fallback_output.exists():
        raise RuntimeError(f"ffmpeg fallback did not write frame: {fallback_output}")
    fallback_output.replace(output)


def cleanup_sampled_frames(frames: list[tuple[float, Path]]) -> None:
    if not frames:
        return
    temp_dir = frames[0][1].parent
    shutil.rmtree(temp_dir, ignore_errors=True)


def evenly_spaced_timestamps(duration: float, count: int) -> list[float]:
    if count <= 1:
        return [max(0.0, duration / 2)]
    margin = min(1.0, duration * 0.05)
    start = margin
    end = max(start, duration - margin)
    step = (end - start) / (count - 1)
    return [start + i * step for i in range(count)]

