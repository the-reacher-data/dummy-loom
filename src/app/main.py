"""ASGI entrypoint for dummy-loom using Loom YAML bootstrap."""

from __future__ import annotations

from fastapi import FastAPI

from loom.rest.fastapi.auto import create_app as create_boot_app

from app.runtime_config import api_config_paths


def create_app() -> FastAPI:
    """Create the API app from one or more config files."""
    return create_boot_app(*api_config_paths())


app = create_app()
