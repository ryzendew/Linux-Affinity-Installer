"""Manager settings, kept in the Manager subdirectory of the base directory.

The base directory itself cannot live here -- it is what tells us where here
is -- so that one pointer stays in ~/.config/AffinityLinuxManager/base_dir and
everything else lives with the rest of the manager's metadata.
"""

from __future__ import annotations

import json
from pathlib import Path

from . import registry


def path() -> Path:
    return registry.manager_dir() / "settings.json"


def _load() -> dict:
    try:
        data = json.loads(path().read_text())
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def get(key: str, default=None):
    return _load().get(key, default)


def set(key: str, value) -> None:  # noqa: A001 - reads better as settings.set
    data = _load()
    data[key] = value
    target = path()
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(data, indent=2) + "\n")
    tmp.replace(target)
