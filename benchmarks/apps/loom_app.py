"""Loom benchmark FastAPI app entrypoint."""

from __future__ import annotations

import os

from loom.rest.fastapi.auto import create_app as create_loom_app


def _config_paths_from_env() -> tuple[str, ...]:
    raw = os.getenv("BENCH_LOOM_CONFIG", "benchmarks/config/loom/base.yaml")
    paths = tuple(path.strip() for path in raw.split(",") if path.strip())
    if not paths:
        raise RuntimeError("BENCH_LOOM_CONFIG must contain at least one config path")
    return paths


app = create_loom_app(*_config_paths_from_env())
