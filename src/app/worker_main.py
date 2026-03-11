"""Celery worker entrypoint for dummy-loom."""

from __future__ import annotations

from loom.celery.auto import create_app as create_worker_app

from app.config_paths import WORKER_CONFIG_PATHS


celery_app = create_worker_app(*WORKER_CONFIG_PATHS)
