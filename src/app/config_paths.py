"""Application config paths resolved from project root."""

from __future__ import annotations

from pathlib import Path


def project_root() -> Path:
    """Return repository root directory."""
    return Path(__file__).resolve().parents[2]


def resolve_config_path(relative_path: str) -> str:
    """Resolve a config file path relative to project root."""
    return str(project_root() / relative_path)


API_CONFIG_PATHS: tuple[str, ...] = (resolve_config_path("config/api.yaml"),)
WORKER_CONFIG_PATHS: tuple[str, ...] = (resolve_config_path("config/worker.yaml"),)

