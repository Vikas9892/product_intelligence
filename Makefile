.DEFAULT_GOAL := help
BACKEND := backend

.PHONY: help install run worker lint format typecheck test clean \
	services-up services-down services-status services-logs services-reset

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-16s\033[0m %s\n", $$1, $$2}'

install: ## Install backend dependencies (including dev tools) via uv
	uv sync --directory $(BACKEND)
	# --project (not --directory): pre-commit must run with cwd at the repo
	# root, where .pre-commit-config.yaml actually lives, so it can find
	# it via default discovery. --project only selects backend's venv for
	# the `pre-commit` binary; it does not change the working directory.
	uv run --project $(BACKEND) pre-commit install

run: ## Run the backend dev server
	uv run --directory $(BACKEND) uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

worker: ## Run the async pipeline worker pool (needs services-up)
	uv run --directory $(BACKEND) python scripts/run_workers.py

services-up: ## Start Qdrant + Redis (Docker) and wait until both are healthy
	docker compose up -d --wait

services-down: ## Stop Qdrant + Redis (named volumes, and therefore data, are kept)
	docker compose down

services-status: ## Show the status and health of the backing services
	docker compose ps

services-logs: ## Tail the backing-service logs
	docker compose logs -f

services-reset: ## DESTRUCTIVE: stop the services and delete all vector/Redis data
	docker compose down --volumes

lint: ## Lint the backend with Ruff
	uv run --directory $(BACKEND) ruff check .

format: ## Format the backend with Ruff + Black
	uv run --directory $(BACKEND) ruff format .
	uv run --directory $(BACKEND) black .

typecheck: ## Run static type checks with MyPy
	uv run --directory $(BACKEND) mypy .

test: ## Run the backend test suite with coverage
	uv run --directory $(BACKEND) pytest

clean: ## Remove caches, build artifacts, and virtual environments
	rm -rf $(BACKEND)/.venv $(BACKEND)/.pytest_cache $(BACKEND)/.mypy_cache \
		$(BACKEND)/.ruff_cache $(BACKEND)/.coverage $(BACKEND)/htmlcov \
		$(BACKEND)/dist $(BACKEND)/build
	find . -type d -name "__pycache__" -exec rm -rf {} +
