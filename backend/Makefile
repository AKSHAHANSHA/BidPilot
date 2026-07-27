# BidPilot UAE backend command runner.
#
# GNU make is not installed on every developer machine; `make.ps1` in this directory
# exposes the same target names for Windows PowerShell (./make.ps1 check).

ifeq ($(OS),Windows_NT)
	VENV_BIN := .venv/Scripts
else
	VENV_BIN := .venv/bin
endif

PY := $(VENV_BIN)/python
PYTEST := $(PY) -m pytest
UNIT := -m "not integration"

.DEFAULT_GOAL := help
.PHONY: help venv install dev api worker migrate revision downgrade seed lint format \
        typecheck test test-integration test-all eval eval-live openapi check up down logs \
        demo-reset clean

help: ## List available targets
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
		| awk 'BEGIN {FS = ":.*?## "}; {printf "  %-18s %s\n", $$1, $$2}'

venv: ## Create the virtual environment with Python 3.12
	python3.12 -m venv .venv || py -3.12 -m venv .venv

install: ## Install the backend with development dependencies
	$(PY) -m pip install --upgrade pip
	$(PY) -m pip install -e ".[dev]"

up: ## Start PostgreSQL and Redis
	docker compose up -d postgres redis

down: ## Stop containers (volumes are preserved)
	docker compose down

logs: ## Follow container logs
	docker compose logs -f

dev: up migrate api ## Start dependencies, migrate, then run the API

api: ## Run the API with autoreload
	$(PY) -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000

worker: ## Run the background analysis worker
	$(PY) -m dramatiq app.workers.main

migrate: ## Apply all migrations
	$(PY) -m alembic upgrade head

revision: ## Autogenerate a migration: make revision m="add users"
	$(PY) -m alembic revision --autogenerate -m "$(m)"

downgrade: ## Roll back one migration
	$(PY) -m alembic downgrade -1

seed: ## Load the fictional demo company, evidence, and projects
	$(PY) scripts/seed_demo.py

lint: ## Ruff lint
	$(PY) -m ruff check .

format: ## Apply Ruff formatting
	$(PY) -m ruff format .

format-check: ## Verify formatting without writing
	$(PY) -m ruff format --check .

typecheck: ## mypy
	$(PY) -m mypy app

test: ## Unit and API tests (no external services required)
	$(PYTEST) $(UNIT)

test-integration: ## Tests requiring PostgreSQL and Redis
	$(PYTEST) -m integration

test-all: ## Every test
	$(PYTEST)

eval: ## Run the gold-set evaluation (mocked, zero cost); writes eval/reports/*.{json,csv}
	$(PY) scripts/evaluate_pipeline.py

eval-live: ## Run the gold-set evaluation against the real OpenAI provider (costs money, capped)
	$(PY) scripts/evaluate_pipeline.py --live --max-cost 1.00

openapi: ## Export artifacts/openapi.json
	$(PY) scripts/export_openapi.py

check: format-check lint typecheck test ## Everything CI enforces on every commit

demo-reset: ## Clear the demo user's tenders/analyses and re-seed the company
	$(PY) scripts/demo_reset.py

clean: ## Remove caches and build artifacts
	rm -rf .pytest_cache .mypy_cache .ruff_cache htmlcov .coverage
