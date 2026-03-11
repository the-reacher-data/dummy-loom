SHELL := /bin/bash
UV ?= uv
COMPOSE ?= docker compose
PYTHON ?= 3.12
DATABASE_URL ?= postgresql+asyncpg://store:store@localhost:5432/store
ALEMBIC_DATABASE_URL ?= postgresql+psycopg://store:store@localhost:5432/store

ifneq (,$(wildcard ./.env.local))
include .env.local
export
endif

ifneq (,$(wildcard ./.env))
include .env
export
endif

.PHONY: help setup sync install lock migrate revision run run-dev test coverage coverage-badge check build up down recreate rebuild destroy restart logs ps clean benchmark benchmark-isolated-up benchmark-isolated benchmark-isolated-down

help:
	@echo "Targets:"
	@echo "  make setup                 - Create local virtual environment"
	@echo "  make sync                  - Sync dependencies with uv (dev group)"
	@echo "  make install               - Alias of sync"
	@echo "  make lock                  - Generate/refresh uv.lock"
	@echo "  make migrate               - Apply Alembic migrations (compose service)"
	@echo "  make revision              - Create Alembic revision (MSG=...)"
	@echo "  make run                   - Run store API"
	@echo "  make run-dev               - Run store API with auto reload"
	@echo "  make test                  - Run tests"
	@echo "  make coverage              - Run tests with coverage and export coverage.xml"
	@echo "  make coverage-badge        - Generate local badge at docs/images/coverage.svg"
	@echo "  make benchmark             - Run local loom vs fastapi benchmark (process mode)"
	@echo "  make benchmark-isolated-up - Start isolated benchmark stack"
	@echo "  make benchmark-isolated    - Run benchmark against isolated stack"
	@echo "  make benchmark-isolated-down - Stop isolated benchmark stack"
	@echo "  make check                 - Run ruff + mypy + tests"
	@echo "  make build                 - Build docker images"
	@echo "  make up                    - Start compose stack in background (without migrate)"
	@echo "  make down                  - Stop compose stack"
	@echo "  make recreate              - Recreate compose stack"
	@echo "  make rebuild               - Rebuild from zero and run migrate"
	@echo "  make destroy               - Drop volumes, rebuild all, and stream logs"
	@echo "  make restart               - Restart compose stack"
	@echo "  make logs                  - Follow compose logs"
	@echo "  make ps                    - List compose services"
	@echo "  make clean                 - Remove local artifacts"

setup:
	$(UV) venv --python $(PYTHON)

sync: setup
	$(UV) sync --group dev

install: sync

lock:
	$(UV) lock

migrate:
	$(COMPOSE) run --rm migrate

revision:
	@if [ -z "$(MSG)" ]; then echo "Usage: make revision MSG='your message'"; exit 1; fi
	DATABASE_URL=$(DATABASE_URL) ALEMBIC_DATABASE_URL=$(ALEMBIC_DATABASE_URL) $(UV) run alembic revision --autogenerate -m "$(MSG)"

run:
	DATABASE_URL=$(DATABASE_URL) $(UV) run uvicorn app.main:app --host 0.0.0.0 --port 8000

run-dev:
	DATABASE_URL=$(DATABASE_URL) $(UV) run uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

test:
	DATABASE_URL=$(DATABASE_URL) ALEMBIC_DATABASE_URL=$(ALEMBIC_DATABASE_URL) $(UV) run pytest -q

coverage:
	DATABASE_URL=$(DATABASE_URL) ALEMBIC_DATABASE_URL=$(ALEMBIC_DATABASE_URL) $(UV) run pytest --cov=src/app --cov-report=term-missing --cov-report=xml:coverage.xml

coverage-badge: coverage
	mkdir -p docs/images
	$(UV) run python scripts/gen_coverage_badge.py --input coverage.xml --output docs/images/coverage.svg

benchmark:
	$(UV) run python benchmarks/scripts/run_benchmark.py

benchmark-isolated-up:
	docker compose -f docker-compose.benchmark.yml up -d --build

benchmark-isolated:
	$(UV) run python benchmarks/scripts/run_benchmark_external.py

benchmark-isolated-down:
	docker compose -f docker-compose.benchmark.yml down --remove-orphans

check:
	$(UV) run ruff check src tests
	$(UV) run mypy src
	$(MAKE) test

build:
	$(COMPOSE) build

up:
	$(COMPOSE) up -d --build

down:
	$(COMPOSE) down --remove-orphans

recreate:
	$(COMPOSE) down --remove-orphans
	$(COMPOSE) up -d --build --force-recreate

rebuild:
	$(COMPOSE) down -v --remove-orphans
	$(COMPOSE) build --no-cache
	$(COMPOSE) up -d --force-recreate
	$(MAKE) migrate

destroy:
	$(COMPOSE) down -v --remove-orphans
	$(COMPOSE) build --no-cache
	$(COMPOSE) up -d --force-recreate
	$(COMPOSE) logs -f

restart: down up

logs:
	$(COMPOSE) logs -f

ps:
	$(COMPOSE) ps

clean:
	rm -rf .venv .pytest_cache store.db .coverage coverage.xml docs/images/coverage.svg
