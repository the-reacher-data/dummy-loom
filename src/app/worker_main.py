"""Celery worker entrypoint for dummy-loom."""

from __future__ import annotations

from typing import Any

import msgspec
from omegaconf import DictConfig

from loom.core.backend.sqlalchemy import compile_all, reset_registry
from loom.celery.bootstrap import bootstrap_worker
from loom.core.config.loader import section
from loom.core.di.container import LoomContainer
from loom.core.di.scope import Scope
from loom.core.repository.sqlalchemy.repository import RepositorySQLAlchemy
from loom.core.repository.sqlalchemy.session_manager import SessionManager

from app.manifest import CALLBACKS, JOBS, MODELS
from app.runtime_config import worker_config_paths


class _WorkerDbConfig(msgspec.Struct, kw_only=True):
    """Subset of worker DB settings used for repository bindings."""

    url: str
    echo: bool = False
    pool_pre_ping: bool = True


def _register_worker_repositories(container: LoomContainer) -> None:
    """Register SQLAlchemy repositories used by job markers."""
    reset_registry()
    compile_all(*MODELS)

    raw = container.resolve(DictConfig)
    db_cfg = section(raw, "database", _WorkerDbConfig)
    session_manager = SessionManager(
        db_cfg.url,
        echo=db_cfg.echo,
        pool_pre_ping=db_cfg.pool_pre_ping,
    )

    container.register(SessionManager, lambda: session_manager, scope=Scope.APPLICATION)

    for model in MODELS:
        repository: Any = RepositorySQLAlchemy(session_manager=session_manager, model=model)
        token = type(f"_{model.__name__}WorkerRepositoryToken", (), {})
        container.register(token, lambda repository=repository: repository, scope=Scope.APPLICATION)
        container.register_repo(model, token)


_worker_bootstrap = bootstrap_worker(
    *worker_config_paths(),
    jobs=tuple(JOBS),
    callbacks=tuple(CALLBACKS),
    modules=(_register_worker_repositories,),
)

celery_app = _worker_bootstrap.celery_app
