.PHONY: build build-dev build-prod shell run smoke dev frontend-build check backend-check backend-test frontend-check test hooks-install clean help

.DEFAULT_GOAL := help

IMAGE ?= nanoscribe
BASE_IMAGE ?= nvidia/cuda:12.4.1-runtime-ubuntu22.04
HOST_PORT ?= 8000

help: ## Show this help
	@echo "NanoScribe Docker Commands"
	@echo ""
	@echo "Usage: make [target]"
	@echo ""
	@echo "  build           Build the dev image (default)"
	@echo "  build-dev       Build the dev image (with Node.js, pnpm, dev tools)"
	@echo "  build-prod      Build the production image (with built SPA)"
	@echo "  dev             Start dev environment with hot reload (builds frontend on first run)"
	@echo "  frontend-build  Build the frontend SPA inside the container"
	@echo "  shell           Open an interactive shell with GPU and caches mounted"
	@echo "  run             Run a one-shot readiness check"
	@echo "  smoke           Verify funasr and modelscope imports"
	@echo "  check           Run all quality checks (lint + tests) inside Docker"
	@echo "  backend-check   Run backend quality checks (ruff format, ruff check, ty check)"
	@echo "  backend-test    Run backend pytest suite inside Docker"
	@echo "  frontend-check  Run frontend quality checks (svelte-check, prettier)"
	@echo "  test            Run all tests (currently backend pytest)"
	@echo "  hooks-install   Install pre-commit hooks"
	@echo "  clean           Remove the built image"

build: build-dev

build-dev:
	docker build --target dev --build-arg BASE_IMAGE=$(BASE_IMAGE) -t $(IMAGE) .

build-prod:
	docker build --target production --build-arg BASE_IMAGE=$(BASE_IMAGE) -t $(IMAGE)-prod .

frontend-build:
	docker compose exec funasr bash -c "cd /app/frontend && pnpm install && pnpm build"

dev:
	docker compose up -d && echo "Dev server starting on http://localhost:$(HOST_PORT)"
	@if [ ! -d frontend/build ]; then \
		echo "Building frontend (first run)..."; \
		$(MAKE) frontend-build; \
		docker compose restart funasr; \
		echo "Frontend built — server restarted."; \
	fi

shell:
	docker compose run --rm funasr /bin/bash

run:
	docker run --rm --gpus all \
		-v $(HOME)/.cache/huggingface:/home/appuser/.cache/huggingface \
		-v $(HOME)/.cache/modelscope:/home/appuser/.cache/modelscope \
		-v $(CURDIR)/data:/app/data \
		$(IMAGE)

smoke:
	docker run --rm $(IMAGE) python -c "import funasr, modelscope; print('ok')"

check:
	@echo "=== Running all quality checks inside Docker ==="
	@$(MAKE) backend-check
	@$(MAKE) frontend-check
	@$(MAKE) test
	@echo "=== All quality checks passed ==="

backend-check:
	@echo "--- Backend: ruff format --check ---"
	docker compose exec funasr bash -c "cd /app/backend && ruff format --check ."
	@echo "--- Backend: ruff check ---"
	docker compose exec funasr bash -c "cd /app/backend && ruff check ."
	@echo "--- Backend: ty check ---"
	docker compose exec funasr bash -c "cd /app/backend && ty check ."

backend-test:
	@echo "--- Backend: pytest ---"
	docker compose exec funasr bash -c "cd /app/backend && pytest -q"

test: backend-test

frontend-check:
	@echo "--- Frontend: svelte-check ---"
	docker compose exec funasr bash -c "cd /app/frontend && pnpm check"
	@echo "--- Frontend: prettier format check ---"
	docker compose exec funasr bash -c "cd /app/frontend && pnpm format:check"

hooks-install:
	@echo "Installing pre-commit hooks..."
	@mkdir -p .git/hooks
	@cp scripts/pre-commit-hook.sh .git/hooks/pre-commit
	@chmod +x .git/hooks/pre-commit
	@echo "Pre-commit hook installed to .git/hooks/pre-commit"
	@echo "  - Trailing whitespace removal"
	@echo "  - End-of-file newline fix"
	@echo "  - Backend: ruff format --check, ruff check (Docker)"
	@echo "  - Frontend: prettier format:check (Docker)"

clean:
	docker compose down || true
	docker rmi $(IMAGE) || true
	docker rmi $(IMAGE)-prod || true
