.DEFAULT_GOAL := help
BACKEND := backend

.PHONY: help install run lint format typecheck test clean

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-12s\033[0m %s\n", $$1, $$2}'

install: ## Install backend dependencies (including dev tools) via uv
	uv sync --project $(BACKEND)
	uv run --project $(BACKEND) pre-commit install --config ../.pre-commit-config.yaml

run: ## Run the backend dev server
	uv run --project $(BACKEND) uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

lint: ## Lint the backend with Ruff
	uv run --project $(BACKEND) ruff check .

format: ## Format the backend with Ruff + Black
	uv run --project $(BACKEND) ruff format .
	uv run --project $(BACKEND) black .

typecheck: ## Run static type checks with MyPy
	uv run --project $(BACKEND) mypy .

test: ## Run the backend test suite with coverage
	uv run --project $(BACKEND) pytest

clean: ## Remove caches, build artifacts, and virtual environments
	rm -rf $(BACKEND)/.venv $(BACKEND)/.pytest_cache $(BACKEND)/.mypy_cache \
		$(BACKEND)/.ruff_cache $(BACKEND)/.coverage $(BACKEND)/htmlcov \
		$(BACKEND)/dist $(BACKEND)/build
	find . -type d -name "__pycache__" -exec rm -rf {} +
