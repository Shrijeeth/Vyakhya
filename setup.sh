#!/usr/bin/env bash
# Vyakhya self-host setup wizard.
# Generates the encryption key, writes .env, and brings up the stack.
# Idempotent: re-run to upgrade. Use --headless to skip prompts (CI/servers).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

HEADLESS=false
[[ "${1:-}" == "--headless" ]] && HEADLESS=true

say() { printf "\033[1;34m▶ %s\033[0m\n" "$1"; }
warn() { printf "\033[1;33m! %s\033[0m\n" "$1"; }

# 1. Prereqs
command -v docker >/dev/null 2>&1 || { warn "Docker is required. Install Docker and re-run."; exit 1; }

# 2. .env — create if missing (never overwrite an existing one)
if [[ -f .env ]]; then
  say ".env already exists — keeping it."
else
  say "Creating .env from .env.example"
  cp .env.example .env

  # Generate a strong random encryption key (used to encrypt provider keys at rest).
  KEY="$(openssl rand -base64 32 2>/dev/null || head -c 32 /dev/urandom | base64)"
  # portable in-place sed (macOS + GNU)
  if sed --version >/dev/null 2>&1; then
    sed -i "s|^VYAKHYA_ENCRYPTION_KEY=.*|VYAKHYA_ENCRYPTION_KEY=${KEY}|" .env
  else
    sed -i '' "s|^VYAKHYA_ENCRYPTION_KEY=.*|VYAKHYA_ENCRYPTION_KEY=${KEY}|" .env
  fi
  chmod 600 .env
  warn "Wrote VYAKHYA_ENCRYPTION_KEY to .env (chmod 600). Back this file up and NEVER commit it."
fi

# 3. Bring up the stack
say "Starting services (docker compose up -d)…"
docker compose up -d --build

# 4. Migrations (placeholder — wire to real migration tool)
# docker compose exec -T api <migrate command>

WEB_PORT="$(grep -E '^WEB_PORT=' .env | cut -d= -f2 || echo 5173)"
say "Vyakhya is starting."
echo ""
echo "  → Open:   http://localhost:${WEB_PORT:-5173}"
echo "  → Next:   add your model provider API keys in the Model Config UI, then upload a PDF."
echo ""
