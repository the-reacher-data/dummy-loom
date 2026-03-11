"""Alembic environment for dummy-loom."""

from __future__ import annotations

import os
import sys
from logging.config import fileConfig
from pathlib import Path

import msgspec
from alembic import context
from omegaconf import DictConfig
from sqlalchemy import engine_from_config, pool
from sqlalchemy.engine import URL, make_url

from loom.core.backend.sqlalchemy import compile_all, get_metadata, reset_registry
from loom.core.config.loader import load_config, section
from loom.core.discovery import ModulesDiscoveryEngine


class _AppConfig(msgspec.Struct, kw_only=True):
    code_path: str = "../src"
    discovery: dict = msgspec.field(default_factory=dict)


class _DatabaseConfig(msgspec.Struct, kw_only=True):
    url: str


config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)


def _project_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _load_runtime_config() -> DictConfig:
    return load_config(str(_project_root() / "config" / "api.yaml"))


def _resolve_database_url(raw: DictConfig) -> str:
    database = section(raw, "database", _DatabaseConfig)
    configured = os.getenv("ALEMBIC_DATABASE_URL") or database.url
    url: URL = make_url(configured)
    if url.drivername == "postgresql+asyncpg":
        url = url.set(drivername="postgresql+psycopg")
    return url.render_as_string(hide_password=False)


def _build_target_metadata(raw: DictConfig):
    app_cfg = section(raw, "app", _AppConfig)
    discovery = app_cfg.discovery
    if discovery.get("mode") != "modules":
        raise RuntimeError("Alembic requires discovery.mode=modules")

    code_path = Path(app_cfg.code_path)
    if not code_path.is_absolute():
        code_path = (_project_root() / code_path).resolve()
    code_path_str = str(code_path)
    if code_path_str not in sys.path:
        sys.path.insert(0, code_path_str)

    modules_cfg = discovery.get("modules", {})
    if not isinstance(modules_cfg, dict):
        raise RuntimeError("Alembic requires discovery.modules mapping")
    include = modules_cfg.get("include", [])
    if not isinstance(include, list):
        raise RuntimeError("Alembic requires discovery.modules.include list")
    modules = [str(value) for value in include]
    discovered = ModulesDiscoveryEngine(modules).discover()
    if not discovered.models:
        raise RuntimeError("No models discovered for Alembic metadata")

    reset_registry()
    compile_all(*discovered.models)
    return get_metadata()


raw_config = _load_runtime_config()
config.set_main_option("sqlalchemy.url", _resolve_database_url(raw_config))
target_metadata = _build_target_metadata(raw_config)


def run_migrations_offline() -> None:
    """Run migrations in offline mode."""
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in online mode."""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
