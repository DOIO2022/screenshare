import json
import os
from typing import Any

_APP_FOLDER = "LanShare"


def _settings_dir() -> str:
    base = os.environ.get("APPDATA") or os.path.expanduser("~")
    path = os.path.join(base, _APP_FOLDER)
    os.makedirs(path, exist_ok=True)
    return path


def settings_path() -> str:
    return os.path.join(_settings_dir(), "settings.json")


def load() -> dict[str, Any]:
    defaults = {
        "auto_share": False,
        "device_name": "",
        "port": 8765,
        "password": "",
        "allow_control": True,
        "stream_profile": "balanced",
    }
    path = settings_path()
    if not os.path.isfile(path):
        return defaults.copy()
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        merged = defaults.copy()
        merged.update({k: v for k, v in data.items() if k in defaults})
        return merged
    except (json.JSONDecodeError, OSError):
        return defaults.copy()


def save(data: dict[str, Any]) -> None:
    path = settings_path()
    current = load()
    current.update(data)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(current, f, ensure_ascii=False, indent=2)
