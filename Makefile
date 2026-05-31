# Brite Tech Lifestyle — developer task shortcuts (Unix / CI).
# Windows users: use ./tasks.ps1 <task> instead.

.DEFAULT_GOAL := help
.PHONY: help install install-dev test smoke run lint format clean

help:  ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
		| awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-12s\033[0m %s\n", $$1, $$2}'

install:  ## Install runtime dependencies
	pip install -r requirements.txt

install-dev:  ## Install runtime + dev dependencies
	pip install -r requirements-dev.txt

test:  ## Run the test suite
	pytest

smoke:  ## Run one post end-to-end in dry-run
	python -m scripts.smoke_test

run:  ## Start the scheduler worker
	python scheduler/cron.py

lint:  ## Lint with ruff
	ruff check .

format:  ## Auto-format with ruff
	ruff format .
	ruff check --fix .

clean:  ## Remove caches and generated artifacts
	rm -rf .pytest_cache .ruff_cache .mypy_cache
	find . -type d -name __pycache__ -prune -exec rm -rf {} +
