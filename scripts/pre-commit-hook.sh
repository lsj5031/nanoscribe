#!/bin/bash
# NanoScribe pre-commit hook
# Runs file hygiene and Docker-backed quality checks.
# Installed by: make hooks-install
set -e

echo "=== Pre-commit: file hygiene ==="

# Remove trailing whitespace from staged files
git diff --cached --name-only --diff-filter=ACM | while read -r f; do
  if [ -f "$f" ] && ! [[ "$f" =~ \.(png|jpg|jpeg|gif|ico|webp)$ ]]; then
    sed -i 's/[[:space:]]*$//' "$f"
  fi
done

# Ensure newline at end of file
git diff --cached --name-only --diff-filter=ACM | while read -r f; do
  if [ -f "$f" ] && [ -s "$f" ] && ! [[ "$f" =~ \.(png|jpg|jpeg|gif|ico|webp)$ ]] && [ "$(tail -c 1 "$f" | wc -l)" -eq 0 ]; then
    echo "" >> "$f"
  fi
done

# Re-stage any modified files
git diff --cached --name-only --diff-filter=ACM | xargs -r git add

echo "=== Pre-commit: backend checks (Docker) ==="
# Use `exec` if the dev container is already running (much faster), otherwise
# fall back to `run --rm` so the hook still works on a clean checkout.
if docker compose ps --status running --services 2>/dev/null | grep -q '^funasr$'; then
  DC="docker compose exec -T funasr"
else
  DC="docker compose run --rm -T funasr"
fi

$DC bash -c "cd /app/backend && ruff format --check . && ruff check ."

echo "=== Pre-commit: frontend checks (Docker) ==="
$DC bash -c "cd /app/frontend && pnpm format:check"

echo "=== Pre-commit checks passed ==="
