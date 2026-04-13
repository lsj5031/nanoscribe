.PHONY: build build-dev build-prod shell run smoke dev check backend-check frontend-check hooks-install clean help

.DEFAULT_GOAL := help

IMAGE ?= funasr
BASE_IMAGE ?= glm-asr-glm-asr:latest
HOST_PORT ?= 8000

help:
	@echo "NanoScribe Docker Commands"
	@echo ""
	@echo "Usage: make [target]"
	@echo ""
	@echo "  build           Build the dev image (default)"
	@echo "  build-dev       Build the dev image (with Node.js, pnpm, dev tools)"
	@echo "  build-prod      Build the production image (with built SPA)"
	@echo "  dev             Start dev environment with hot reload"
	@echo "  shell           Open an interactive shell with GPU and caches mounted"
	@echo "  run             Run a one-shot readiness check"
	@echo "  smoke           Verify funasr and modelscope imports"
	@echo "  check           Run all quality checks inside Docker"
	@echo "  backend-check   Run backend quality checks (ruff, ty)"
	@echo "  frontend-check  Run frontend quality checks (svelte-check, prettier)"
	@echo "  hooks-install   Install pre-commit hooks"
	@echo "  clean           Remove the built image"

build: build-dev

build-dev:
	docker build --target dev --build-arg BASE_IMAGE=$(BASE_IMAGE) -t $(IMAGE) .

build-prod:
	docker build --target production --build-arg BASE_IMAGE=$(BASE_IMAGE) -t $(IMAGE)-prod .

dev:
	docker compose up -d && echo "Dev server starting on http://localhost:$(HOST_PORT)"

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
	docker compose exec funasr bash -c "cd /app/backend && ruff format --check . && ruff check . && ty check . && cd /app/frontend && pnpm check && pnpm format:check"

backend-check:
	docker compose exec funasr bash -c "cd /app/backend && ruff format --check . && ruff check . && ty check ."

frontend-check:
	docker compose exec funasr bash -c "cd /app/frontend && pnpm check && pnpm format:check"

hooks-install:
	@echo "Installing pre-commit hooks..."
	@if [ ! -d .git/hooks ]; then mkdir -p .git/hooks; fi
	@cat > .git/hooks/pre-commit << 'HOOK'
#!/bin/bash
set -e
echo "Running pre-commit checks..."
docker compose exec funasr bash -c "cd /app/backend && ruff format --check . && ruff check ."
echo "Pre-commit checks passed."
HOOK
	@chmod +x .git/hooks/pre-commit
	@echo "Pre-commit hook installed."

clean:
	docker compose down || true
	docker rmi $(IMAGE) || true
	docker rmi $(IMAGE)-prod || true
