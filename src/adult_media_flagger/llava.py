from __future__ import annotations

import base64
import json
from pathlib import Path
from typing import Any

from .config import LlavaSettings


PROMPT = """You are reviewing media for local personal file organization.

Classify the image into one of:
- safe
- suggestive
- explicit
- unclear

Return JSON only:
{
  "classification": "safe|suggestive|explicit|unclear",
  "confidence": 0.0,
  "adult_indicators": [],
  "non_adult_context": [],
  "short_description": ""
}

Be literal. Do not infer identity, age, intent, or private traits. If uncertain, use "unclear".
"""


class LlavaClient:
    def __init__(self, settings: LlavaSettings):
        self.settings = settings

    def review_image(self, path: Path) -> dict[str, Any]:
        try:
            import requests
        except Exception as exc:
            raise RuntimeError("requests is not installed. Install the package dependencies first.") from exc

        image_b64 = base64.b64encode(path.read_bytes()).decode("ascii")
        payload = {
            "model": self.settings.model,
            "prompt": PROMPT,
            "images": [image_b64],
            "stream": False,
            "format": "json",
        }
        response = requests.post(
            self.settings.endpoint,
            json=payload,
            timeout=self.settings.timeout_seconds,
        )
        response.raise_for_status()
        data = response.json()
        text = data.get("response", "")
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            parsed = {"classification": "unclear", "confidence": 0.0, "raw_response": text}
        parsed["_model"] = self.settings.model
        return parsed


def final_decision_from_llava(classifier_decision: str, llava_json: dict[str, Any] | None) -> str:
    if not llava_json:
        return classifier_decision

    classification = str(llava_json.get("classification", "")).lower()
    if classification == "explicit":
        return "adult_likely"
    if classification == "suggestive":
        return "review"
    if classification == "safe" and classifier_decision == "review":
        return "safe"
    if classification == "unclear":
        return "review"
    return classifier_decision
