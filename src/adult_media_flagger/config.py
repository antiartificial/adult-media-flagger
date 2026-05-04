from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Thresholds:
    safe_max: float = 0.35
    adult_min: float = 0.80

    def decision_for_score(self, score: float | None) -> str:
        if score is None:
            return "error"
        if score < self.safe_max:
            return "safe"
        if score >= self.adult_min:
            return "adult_likely"
        return "review"


@dataclass(frozen=True)
class VideoSettings:
    max_frames: int = 16
    min_seconds_between_frames: float = 2.0
    jpeg_quality: int = 88


@dataclass(frozen=True)
class LlavaSettings:
    endpoint: str = "http://localhost:11434/api/generate"
    model: str = "llava:13b"
    timeout_seconds: int = 120

