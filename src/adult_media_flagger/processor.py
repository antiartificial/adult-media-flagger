from __future__ import annotations

from pathlib import Path

from .adult_detector import OpenNsfw2Detector
from .config import LlavaSettings, Thresholds, VideoSettings
from .llava import LlavaClient, final_decision_from_llava
from .store import Store
from .video_frames import cleanup_sampled_frames, sample_video_frames


def process_unprocessed(
    store: Store,
    thresholds: Thresholds,
    video_settings: VideoSettings,
    llava_settings: LlavaSettings,
    llava_mode: str,
    limit: int | None = None,
) -> int:
    detector = OpenNsfw2Detector()
    llava_client = LlavaClient(llava_settings) if llava_mode != "off" else None
    processed = 0

    for row in store.iter_unprocessed(limit):
        path = Path(row["path"])
        try:
            if row["media_type"] == "image":
                score = detector.score_image(path)
                decision = thresholds.decision_for_score(score)
                llava_json, llava_error = maybe_review_with_llava(path, decision, llava_mode, llava_client)
                final_decision = final_decision_from_llava(decision, llava_json)
                store.save_result(
                    media_id=row["id"],
                    detector=detector.name,
                    score=score,
                    decision=decision,
                    final_decision=final_decision,
                    llava_json=llava_json,
                    llava_error=llava_error,
                )
            else:
                process_video_row(store, row, detector, thresholds, video_settings, llava_mode, llava_client)
            processed += 1
        except Exception as exc:
            store.save_result(
                media_id=row["id"],
                detector=detector.name,
                score=None,
                decision="error",
                final_decision="error",
                error=str(exc),
            )
            processed += 1

    return processed


def process_video_row(
    store: Store,
    row,
    detector: OpenNsfw2Detector,
    thresholds: Thresholds,
    video_settings: VideoSettings,
    llava_mode: str,
    llava_client: LlavaClient | None,
) -> None:
    frames = sample_video_frames(Path(row["path"]), video_settings)
    frame_results: list[dict] = []
    llava_json = None
    llava_error = None

    try:
        for timestamp, frame_path in frames:
            score = detector.score_image(frame_path)
            frame_results.append(
                {
                    "timestamp": round(timestamp, 3),
                    "score": score,
                    "decision": thresholds.decision_for_score(score),
                }
            )
        max_score = max((item["score"] for item in frame_results), default=None)
        decision = thresholds.decision_for_score(max_score)

        if frames:
            review_frame = max(zip(frame_results, frames), key=lambda pair: pair[0]["score"])[1][1]
            llava_json, llava_error = maybe_review_with_llava(review_frame, decision, llava_mode, llava_client)
        final_decision = final_decision_from_llava(decision, llava_json)
        store.save_result(
            media_id=row["id"],
            detector=detector.name,
            score=max_score,
            decision=decision,
            final_decision=final_decision,
            sampled_frames=len(frame_results),
            frame_results=frame_results,
            llava_json=llava_json,
            llava_error=llava_error,
        )
    finally:
        cleanup_sampled_frames(frames)


def maybe_review_with_llava(
    path: Path,
    classifier_decision: str,
    llava_mode: str,
    llava_client: LlavaClient | None,
) -> tuple[dict | None, str | None]:
    if llava_client is None:
        return None, None
    if llava_mode == "review" and classifier_decision != "review":
        return None, None
    if llava_mode == "flagged" and classifier_decision not in {"review", "adult_likely"}:
        return None, None
    if llava_mode not in {"review", "flagged", "all"}:
        return None, None

    try:
        return llava_client.review_image(path), None
    except Exception as exc:
        return None, str(exc)

