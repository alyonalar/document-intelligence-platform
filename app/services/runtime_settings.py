import json
from pathlib import Path

from app.core.config import settings

RUNTIME_SETTINGS_PATH = Path(settings.upload_dir).parent / "runtime_settings.json"


def read_runtime_settings() -> dict:
    if not RUNTIME_SETTINGS_PATH.exists():
        return {}
    try:
        return json.loads(RUNTIME_SETTINGS_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def write_runtime_settings(values: dict) -> None:
    RUNTIME_SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
    RUNTIME_SETTINGS_PATH.write_text(json.dumps(values, indent=2), encoding="utf-8")


def semantic_search_enabled() -> bool:
    values = read_runtime_settings()
    if isinstance(values.get("semantic_search_enabled"), bool):
        return values["semantic_search_enabled"]
    return settings.semantic_search_enabled


def set_semantic_search_enabled(enabled: bool) -> None:
    values = read_runtime_settings()
    values["semantic_search_enabled"] = enabled
    write_runtime_settings(values)


def semantic_search_configured() -> bool:
    return bool(settings.openai_api_key and settings.chroma_dir)
