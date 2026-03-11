"""ASGI entrypoint for dummy-loom using Loom YAML bootstrap."""

from __future__ import annotations

from fastapi import FastAPI

from loom.rest.fastapi.auto import create_app as create_boot_app

from app.config_paths import API_CONFIG_PATHS


def create_app() -> FastAPI:
    """Create the API app from one or more config files."""
    return create_boot_app(*API_CONFIG_PATHS)


app = create_app()
