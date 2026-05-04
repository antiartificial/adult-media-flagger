from __future__ import annotations

from pathlib import Path


class DetectorUnavailable(RuntimeError):
    pass


class OpenNsfw2Detector:
    name = "opennsfw2"

    def __init__(self) -> None:
        try:
            import opennsfw2 as n2
        except Exception as exc:
            raise DetectorUnavailable(
                "opennsfw2 is not installed. Install with: pip install 'adult-media-flagger[ml]'"
            ) from exc
        self._n2 = n2

    def score_image(self, path: Path) -> float:
        # opennsfw2 returns a probability-like NSFW score for the image.
        return float(self._n2.predict_image(str(path)))

