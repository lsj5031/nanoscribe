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

AUTOFIXED=0

# Run ruff format check. Exit codes: 0=ok, 1=would-reformat, >=2=error.
set +e
$DC bash -c "cd /app/backend && ruff format --check ."
rc=$?
set -e
if [ "$rc" -eq 0 ]; then
  $DC bash -c "cd /app/backend && ruff check ."
elif [ "$rc" -eq 1 ]; then
  echo "  Formatting issues found — auto-fixing with ruff format..."
  $DC bash -c "cd /app/backend && ruff format . && ruff check ."
  # Re-stage only staged Python files that may have been modified
  git diff --cached --name-only --diff-filter=ACM -- 'backend/*.py' ':(glob)backend/**/*.py' | xargs -r git add
  AUTOFIXED=1
else
  echo "ERROR: ruff format --check failed (exit $rc); aborting." >&2
  exit "$rc"
fi

echo "=== Pre-commit: frontend checks (Docker) ==="

# Run prettier check. Exit codes: 0=ok, 1=needs-format, >=2=error.
set +e
$DC bash -c "cd /app/frontend && pnpm format:check"
rc=$?
set -e
if [ "$rc" -eq 1 ]; then
  echo "  Formatting issues found — auto-fixing with prettier..."
  $DC bash -c "cd /app/frontend && npx prettier --write ."
  # Re-stage only staged frontend files that may have been modified
  git diff --cached --name-only --diff-filter=ACM -- 'frontend/*' ':(glob)frontend/**' | xargs -r git add
  AUTOFIXED=1
elif [ "$rc" -ne 0 ]; then
  echo "ERROR: pnpm format:check failed (exit $rc); aborting." >&2
  exit "$rc"
fi

if [ "$AUTOFIXED" -eq 1 ]; then
  echo ""
  echo "Pre-commit auto-formatted staged files and re-staged them."
  echo "Review the changes (git diff --cached) and re-run your commit."
  exit 1
fi

echo "=== Pre-commit checks passed ==="
