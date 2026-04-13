#!/bin/bash
# NanoScribe pre-commit hook
# Runs file hygiene and Docker-backed quality checks.
# Installed by: make hooks-install
set -e

echo "=== Pre-commit: file hygiene ==="

# Remove trailing whitespace from staged files
git diff --cached --name-only --diff-filter=ACM | while read -r f; do
  if [ -f "$f" ]; then
    sed -i 's/[[:space:]]*$//' "$f"
  fi
done

# Ensure newline at end of file
git diff --cached --name-only --diff-filter=ACM | while read -r f; do
  if [ -f "$f" ] && [ -s "$f" ] && [ "$(tail -c 1 "$f" | wc -l)" -eq 0 ]; then
    echo "" >> "$f"
  fi
done

# Re-stage any modified files
git diff --cached --name-only --diff-filter=ACM | xargs -r git add

echo "=== Pre-commit: backend checks (Docker) ==="
docker compose exec funasr bash -c "cd /app/backend && ruff format --check . && ruff check ."

echo "=== Pre-commit: frontend checks (Docker) ==="
docker compose exec funasr bash -c "cd /app/frontend && pnpm format:check"

echo "=== Pre-commit checks passed ==="
