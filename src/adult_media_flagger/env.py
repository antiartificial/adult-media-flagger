from __future__ import annotations

import os
from pathlib import Path


DEFAULT_ENV_FILE = ".env"


def load_env_file(path: str | Path | None = None) -> Path | None:
    env_path = Path(path or os.environ.get("ADULT_FLAG_ENV", DEFAULT_ENV_FILE))
    if not env_path.exists():
        return None

    try:
        from dotenv import load_dotenv

        load_dotenv(env_path)
    except Exception:
        load_simple_env(env_path)
    return env_path


def load_simple_env(path: Path) -> None:
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip("'").strip('"')
        os.environ.setdefault(key, value)


def masked(value: str | None) -> str:
    if not value:
        return "missing"
    if len(value) <= 8:
        return "***"
    return f"{value[:4]}...{value[-4:]}"


def config_status() -> dict[str, str]:
    return {
        "R2_ENDPOINT_URL": os.environ.get("R2_ENDPOINT_URL") or "missing",
        "AWS_ACCESS_KEY_ID": masked(os.environ.get("AWS_ACCESS_KEY_ID")),
        "AWS_SECRET_ACCESS_KEY": masked(os.environ.get("AWS_SECRET_ACCESS_KEY")),
        "AWS_SESSION_TOKEN": masked(os.environ.get("AWS_SESSION_TOKEN")),
        "ADULT_FLAG_R2_BUCKET": os.environ.get("ADULT_FLAG_R2_BUCKET") or "missing",
        "ADULT_FLAG_R2_MEDIA_PREFIX": os.environ.get("ADULT_FLAG_R2_MEDIA_PREFIX") or "twitter-media",
        "ADULT_FLAG_R2_RESULTS_PREFIX": os.environ.get("ADULT_FLAG_R2_RESULTS_PREFIX") or "twitter-results",
        "OLLAMA_ENDPOINT": os.environ.get("OLLAMA_ENDPOINT") or "http://localhost:11434/api/generate",
        "OLLAMA_MODEL": os.environ.get("OLLAMA_MODEL") or "llava:13b",
    }
