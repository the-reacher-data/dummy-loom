"""Runtime configuration path helpers for API and worker entrypoints."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Iterable

_DEFAULT_API_CONFIGS: tuple[str, ...] = ("config/api.yaml",)
_DEFAULT_WORKER_CONFIGS: tuple[str, ...] = ("config/worker.yaml",)


def _project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _split_csv(raw: str) -> tuple[str, ...]:
    parts = tuple(part.strip() for part in raw.split(","))
    return tuple(part for part in parts if part)


def _resolve(paths: Iterable[str]) -> tuple[str, ...]:
    root = _project_root()
    resolved: list[str] = []
    for value in paths:
        candidate = Path(value)
        if not candidate.is_absolute():
            candidate = root / candidate
        resolved.append(str(candidate))
    return tuple(resolved)


def api_config_paths() -> tuple[str, ...]:
    """Return resolved config paths for API bootstrap."""
    raw = os.getenv("DUMMY_LOOM_CONFIGS", "")
    selected = _split_csv(raw) if raw.strip() else _DEFAULT_API_CONFIGS
    return _resolve(selected)


def worker_config_paths() -> tuple[str, ...]:
    """Return resolved config paths for worker bootstrap."""
    raw = os.getenv("DUMMY_LOOM_WORKER_CONFIGS", "")
    selected = _split_csv(raw) if raw.strip() else _DEFAULT_WORKER_CONFIGS
    return _resolve(selected)
