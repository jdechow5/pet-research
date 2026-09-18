"""Configuration loading. The protocol lives in config/search.json so it can
be changed without touching code."""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CONFIG_PATH = PROJECT_ROOT / "config" / "search.json"


class Config:
    def __init__(self, data: dict[str, Any], path: Path | None = None):
        self._data = data
        self.path = path

    @classmethod
    def load(cls, path: str | Path | None = None) -> "Config":
        target = Path(path) if path else DEFAULT_CONFIG_PATH
        if not target.exists():
            raise FileNotFoundError(
                f"Config not found at {target}. Expected config/search.json."
            )
        data = json.loads(target.read_text())
        local = target.with_name(target.stem + ".local.json")
        if local.exists():
            data = deep_merge(data, json.loads(local.read_text()))
        return cls(data, target)

    def get(self, dotted: str, default: Any = None) -> Any:
        node: Any = self._data
        for part in dotted.split("."):
            if not isinstance(node, dict) or part not in node:
                return default
            node = node[part]
        return copy.deepcopy(node)

    def require(self, dotted: str) -> Any:
        value = self.get(dotted, _MISSING)
        if value is _MISSING:
            raise KeyError(f"Missing required config key: {dotted}")
        return value

    @property
    def raw(self) -> dict[str, Any]:
        return copy.deepcopy(self._data)


_MISSING = object()


def deep_merge(base: dict, override: dict) -> dict:
    out = copy.deepcopy(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = deep_merge(out[key], value)
        else:
            out[key] = copy.deepcopy(value)
    return out
