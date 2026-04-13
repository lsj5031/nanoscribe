#!/bin/bash
set -euo pipefail

echo "=== NanoScribe Environment Init ==="

# Install frontend dependencies if needed
if [ ! -d "/app/frontend/node_modules" ]; then
  echo "Installing frontend dependencies..."
  cd /app/frontend && pnpm install
fi

# Install backend dependencies if needed
if [ ! -f "/app/backend/.installed" ]; then
  echo "Installing backend dependencies..."
  cd /app/backend && pip install -e ".[dev]" && touch .installed
fi

# Run database migrations
echo "Running database migrations..."
cd /app/backend && python -m app.db.migrate

echo "=== Init complete ==="
