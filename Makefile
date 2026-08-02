.DEFAULT_GOAL := help
BACKEND := backend

BACKING := redis qdrant
DEV     := docker compose -f docker-compose.yml -f docker-compose.dev.yml
PROD    := docker compose -f docker-compose.yml -f docker-compose.prod.yml

.PHONY: help install run worker lint format typecheck test clean \
	services-up services-down services-status services-logs services-reset \
	up-dev up-prod down logs ps reset

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

# --- Full containerized stack (Stage 8) -------------------------------------

up-dev: ## Start the whole stack in development mode (source mounted, hot reload)
	$(DEV) up -d --build --wait

up-prod: ## Start the whole stack production-like (immutable images, no mounts)
	$(PROD) up -d --build --wait

down: ## Stop the whole stack (named volumes, and therefore data, are kept)
	docker compose down

ps: ## Show the status and health of every service
	docker compose ps

logs: ## Tail logs from every service
	docker compose logs -f

reset: ## DESTRUCTIVE: stop the stack and delete ALL data (vectors, Redis, uploads, models)
	docker compose down --volumes

# --- Backing services only (host-based development) -------------------------
# For running the API and worker on the host with `make run` / `make worker`
# while Redis and Qdrant stay in Docker. Uses the dev overlay because that is
# what publishes 6379/6333 to the host for a host-run backend to reach.

services-up: ## Start only Qdrant + Redis (for host-run API/worker) and wait for health
	$(DEV) up -d --wait $(BACKING)

services-down: ## Stop Qdrant + Redis (named volumes, and therefore data, are kept)
	docker compose down

services-status: ## Show the status and health of the backing services
	docker compose ps $(BACKING)

services-logs: ## Tail the backing-service logs
	docker compose logs -f $(BACKING)

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
