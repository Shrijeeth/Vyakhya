#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# Vyakhya · व्याख्या — self-host setup wizard
#
# Interactive first-run installer: checks prerequisites, collects config,
# generates the encryption key, writes .env, and brings up the Docker stack.
#
#   ./setup.sh                 interactive wizard
#   ./setup.sh --headless      no prompts, use defaults (CI / servers)
#   ./setup.sh --reconfigure   re-run the wizard even if .env exists
#   ./setup.sh --no-up         configure only; do not start Docker
#   ./setup.sh -h | --help     show help
#
# Idempotent: re-run any time to upgrade the stack.
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

# ── Flags ────────────────────────────────────────────────────────────────────
HEADLESS=false
RECONFIGURE=false
DO_UP=true
for arg in "$@"; do
  case "$arg" in
    --headless)    HEADLESS=true ;;
    --reconfigure) RECONFIGURE=true ;;
    --no-up)       DO_UP=false ;;
    -h|--help)
      cat <<'USAGE'
Vyakhya · व्याख्या — self-host setup wizard

Interactive first-run installer: checks prerequisites, collects config,
generates the encryption key, writes .env, and brings up the Docker stack.

  ./setup.sh                 interactive wizard
  ./setup.sh --headless      no prompts, use defaults (CI / servers)
  ./setup.sh --reconfigure   re-run the wizard even if .env exists
  ./setup.sh --no-up         configure only; do not start Docker
  ./setup.sh -h | --help     show help

Idempotent: re-run any time to upgrade the stack.
USAGE
      exit 0 ;;
    *) printf 'Unknown option: %s (try --help)\n' "$arg" >&2; exit 2 ;;
  esac
done

# ── Colors (disabled when not a TTY) ─────────────────────────────────────────
if [[ -t 1 ]]; then
  BOLD=$'\033[1m'; DIM=$'\033[2m'; RESET=$'\033[0m'
  BLUE=$'\033[38;5;39m'; GREEN=$'\033[38;5;42m'; YELLOW=$'\033[38;5;214m'
  RED=$'\033[38;5;203m'; PURPLE=$'\033[38;5;135m'; GREY=$'\033[38;5;245m'
else
  BOLD=""; DIM=""; RESET=""; BLUE=""; GREEN=""; YELLOW=""; RED=""; PURPLE=""; GREY=""
fi

step() { printf '\n%s▶ %s%s\n' "$BOLD$BLUE" "$1" "$RESET"; }
ok()   { printf '  %s✓%s %s\n' "$GREEN" "$RESET" "$1"; }
info() { printf '  %s•%s %s\n' "$GREY" "$RESET" "$1"; }
warn() { printf '  %s!%s %s\n' "$YELLOW" "$RESET" "$1"; }
die()  { printf '\n%s✗ %s%s\n' "$RED$BOLD" "$1" "$RESET" >&2; exit 1; }

banner() {
  printf '%s' "$PURPLE$BOLD"
  cat <<'ART'

  ██╗   ██╗██╗   ██╗ █████╗ ██╗  ██╗██╗  ██╗██╗   ██╗ █████╗
  ██║   ██║╚██╗ ██╔╝██╔══██╗██║ ██╔╝██║  ██║╚██╗ ██╔╝██╔══██╗
  ██║   ██║ ╚████╔╝ ███████║█████╔╝ ███████║ ╚████╔╝ ███████║
  ╚██╗ ██╔╝  ╚██╔╝  ██╔══██║██╔═██╗ ██╔══██║  ╚██╔╝  ██╔══██║
   ╚████╔╝    ██║   ██║  ██║██║  ██╗██║  ██║   ██║   ██║  ██║
    ╚═══╝     ╚═╝   ╚═╝  ╚═╝╚═╝  ╚═╝╚═╝  ╚═╝   ╚═╝   ╚═╝  ╚═╝
ART
  printf '%s' "$RESET"
  printf '  %sव्याख्या%s  %s— research papers as editable explainer videos%s\n' \
    "$BOLD" "$RESET" "$DIM" "$RESET"
  printf '  %sself-hosted · open-source · bring-your-own-keys%s\n' "$DIM" "$RESET"
}

# Interactive check: no prompting when headless or without a TTY.
interactive() { [[ "$HEADLESS" == false && -t 0 ]]; }

# ask <var> <prompt> <default>  — reads into <var>, falls back to <default>.
ask() {
  local __var="$1" __prompt="$2" __default="$3" __reply=""
  if interactive; then
    printf '  %s%s%s %s[%s]%s ' "$BOLD" "$__prompt" "$RESET" "$DIM" "$__default" "$RESET"
    read -r __reply || true
  fi
  printf -v "$__var" '%s' "${__reply:-$__default}"
}

# ask_secret <var> <prompt> <default>  — hidden input; blank keeps the default.
ask_secret() {
  local __var="$1" __prompt="$2" __default="$3" __reply=""
  if interactive; then
    printf '  %s%s%s %s[keep generated]%s ' "$BOLD" "$__prompt" "$RESET" "$DIM" "$RESET"
    read -rs __reply || true
    printf '\n'
  fi
  printf -v "$__var" '%s' "${__reply:-$__default}"
}

# confirm <prompt> <default:y|n>  — returns 0 for yes.
confirm() {
  local __prompt="$1" __default="${2:-y}" __reply=""
  if ! interactive; then [[ "$__default" == "y" ]]; return; fi
  local __hint="[Y/n]"; [[ "$__default" == "n" ]] && __hint="[y/N]"
  printf '  %s%s%s %s%s%s ' "$BOLD" "$__prompt" "$RESET" "$DIM" "$__hint" "$RESET"
  read -r __reply || true
  __reply="${__reply:-$__default}"
  [[ "$__reply" =~ ^[Yy] ]]
}

gen_key() { openssl rand -base64 32 2>/dev/null || head -c 32 /dev/urandom | base64; }

port_free() {
  local p="$1"
  if command -v lsof >/dev/null 2>&1; then
    ! lsof -iTCP:"$p" -sTCP:LISTEN >/dev/null 2>&1
  elif command -v nc >/dev/null 2>&1; then
    ! nc -z localhost "$p" >/dev/null 2>&1
  else
    return 0
  fi
}

banner

# ── 1. Prerequisites ─────────────────────────────────────────────────────────
step "Checking prerequisites"
command -v docker >/dev/null 2>&1 || die "Docker is required. Install Docker Desktop / Engine and re-run."
if docker compose version >/dev/null 2>&1; then
  COMPOSE=(docker compose)
elif command -v docker-compose >/dev/null 2>&1; then
  COMPOSE=(docker-compose)
else
  die "Docker Compose v2 is required (\`docker compose\`)."
fi
docker info >/dev/null 2>&1 || die "Docker daemon is not running. Start Docker and re-run."
ok "Docker $(docker version --format '{{.Server.Version}}' 2>/dev/null || echo present)"
ok "Compose $("${COMPOSE[@]}" version --short 2>/dev/null || echo present)"
command -v openssl >/dev/null 2>&1 && ok "openssl" || warn "openssl not found — falling back to /dev/urandom for the key"

# ── 2. Configuration → .env ──────────────────────────────────────────────────
if [[ -f .env && "$RECONFIGURE" == false ]]; then
  step "Configuration"
  ok ".env already exists — keeping it (use --reconfigure to redo)."
else
  step "Configuration"
  if [[ -f .env && "$RECONFIGURE" == true ]]; then
    ts="$(date +%Y%m%d%H%M%S)"
    cp .env ".env.bak.$ts"
    warn "Backed up existing .env → .env.bak.$ts"
  fi

  if interactive; then
    info "Press Enter to accept each ${BOLD}[default]${RESET}. Nothing is sent anywhere."
  else
    info "Non-interactive — using defaults for everything."
  fi

  printf '\n  %sDatabase (Postgres)%s\n' "$BOLD" "$RESET"
  ask POSTGRES_USER     "Postgres user"      "vyakhya"
  ask POSTGRES_DB       "Postgres database"  "vyakhya"
  DEFAULT_DB_PASS="$(gen_key | tr -dc 'A-Za-z0-9' | head -c 24)"
  ask_secret POSTGRES_PASSWORD "Postgres password" "$DEFAULT_DB_PASS"

  printf '\n  %sObject storage (MinIO / S3)%s\n' "$BOLD" "$RESET"
  ask S3_ACCESS_KEY "S3 access key" "vyakhya"
  DEFAULT_S3_SECRET="$(gen_key | tr -dc 'A-Za-z0-9' | head -c 24)"
  ask_secret S3_SECRET_KEY "S3 secret key" "$DEFAULT_S3_SECRET"
  ask S3_BUCKET "S3 bucket" "vyakhya"

  printf '\n  %sPorts%s\n' "$BOLD" "$RESET"
  ask API_PORT    "API port"    "8000"
  ask WEB_PORT    "Web/UI port" "5173"
  ask RENDER_PORT "Render port" "8080"
  for pair in "API:$API_PORT" "Web:$WEB_PORT" "Render:$RENDER_PORT"; do
    name="${pair%%:*}"; p="${pair##*:}"
    port_free "$p" || warn "$name port $p looks busy — change it or free it before starting."
  done

  printf '\n  %sSecurity%s\n' "$BOLD" "$RESET"
  ENC_KEY="$(gen_key)"
  ok "Generated VYAKHYA_ENCRYPTION_KEY (encrypts provider keys at rest)."
  API_KEY="$(gen_key | tr -dc 'A-Za-z0-9' | head -c 40)"
  RENDER_API_KEY="$(gen_key | tr -dc 'A-Za-z0-9' | head -c 40)"
  ok "Generated VYAKHYA_API_KEY + RENDER_API_KEY (gate the API and render service)."

  printf '\n  %sAI agents%s\n' "$BOLD" "$RESET"
  if confirm "Enable the real Agno agent pipeline? (larger image; needs a provider key in Model Config)" "y"; then
    USE_AGNO=true; INSTALL_AGENTS=1
    ok "Agno agent pipeline enabled (studio/worker build the agents extra)."
  else
    USE_AGNO=false; INSTALL_AGENTS=0
    info "Using the simulated pipeline (no LLM calls)."
  fi

  cat > .env <<EOF
# ── Vyakhya environment ──────────────────────────────────────────────
# Generated by ./setup.sh on $(date -u +%Y-%m-%dT%H:%M:%SZ). Never commit this file.

# Encryption key used to encrypt provider API keys at rest (AES-256-GCM).
# KEEP THIS SECRET AND BACKED UP — losing it makes stored provider keys
# unrecoverable (just re-enter them in the Model Config UI).
VYAKHYA_ENCRYPTION_KEY=${ENC_KEY}

# API key gating the backend /api routes. The frontend build embeds it as
# VITE_API_KEY (same value). The backend↔render service shares RENDER_API_KEY.
VYAKHYA_API_KEY=${API_KEY}
VITE_API_KEY=${API_KEY}
RENDER_API_KEY=${RENDER_API_KEY}

# ── Database ─────────────────────────────────────────────────────────
POSTGRES_USER=${POSTGRES_USER}
POSTGRES_PASSWORD=${POSTGRES_PASSWORD}
POSTGRES_DB=${POSTGRES_DB}
DATABASE_URL=postgresql://${POSTGRES_USER}:${POSTGRES_PASSWORD}@postgres:5432/${POSTGRES_DB}

# ── Object storage (MinIO / S3) ──────────────────────────────────────
S3_ENDPOINT=http://minio:9000
S3_ACCESS_KEY=${S3_ACCESS_KEY}
S3_SECRET_KEY=${S3_SECRET_KEY}
S3_BUCKET=${S3_BUCKET}

# ── Services ─────────────────────────────────────────────────────────
API_PORT=${API_PORT}
WEB_PORT=${WEB_PORT}
RENDER_PORT=${RENDER_PORT}
RENDER_SERVICE_URL=http://render:8080
# Set true to delegate real renders to the Node render service (else simulated).
USE_RENDER_SERVICE=false

# ── Agents (Agno) ────────────────────────────────────────────────────
# Real Agno agent crew (needs a provider key in Model Config). INSTALL_AGENTS
# builds the studio/worker image with the agents extra (passed as a build arg).
USE_AGNO=${USE_AGNO}
INSTALL_AGENTS=${INSTALL_AGENTS}
SKILLS_DIR=

# ── App ──────────────────────────────────────────────────────────────
# Provider API keys are NOT set here — add them in the Model Config UI.
LOG_LEVEL=info
EOF
  chmod 600 .env
  ok "Wrote .env (chmod 600). Back it up separately from DB dumps."
fi

# Ensure newer keys exist even when keeping an older .env (so a plain restart
# picks up the Agno pipeline). Defaults enable it; edit .env to opt out.
ensure_env() { grep -qE "^$1=" .env 2>/dev/null || printf '%s=%s\n' "$1" "$2" >> .env; }
ensure_env USE_AGNO true
ensure_env INSTALL_AGENTS 1
ensure_env SKILLS_DIR ""

# Load ports from .env for the summary / startup, regardless of branch.
get_env() { grep -E "^$1=" .env | head -1 | cut -d= -f2- || true; }
API_PORT="$(get_env API_PORT)";  API_PORT="${API_PORT:-8000}"
WEB_PORT="$(get_env WEB_PORT)";  WEB_PORT="${WEB_PORT:-5173}"

# ── 3. Start the stack ───────────────────────────────────────────────────────
if [[ "$DO_UP" == false ]]; then
  step "Skipping Docker startup (--no-up)"
  info "When ready:  ${BOLD}${COMPOSE[*]} up -d --build${RESET}"
  exit 0
fi

step "Starting services"
info "studio · worker · render · postgres · minio"
if ! confirm "Build images and start the stack now?" "y"; then
  warn "Aborted before startup. Run again when ready."
  exit 0
fi

"${COMPOSE[@]}" up -d --build

# ── 4. Migrations (placeholder — wire to the real migration tool) ────────────
# "${COMPOSE[@]}" exec -T studio <migrate command>

# ── 5. Wait for health ───────────────────────────────────────────────────────
step "Waiting for the API to become healthy"
spin='⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏'
healthy=false
for i in $(seq 1 60); do
  if curl -fsS "http://localhost:${API_PORT}/health" >/dev/null 2>&1; then
    healthy=true; break
  fi
  c="${spin:i%${#spin}:1}"
  printf '\r  %s%s%s waiting… (%ss)' "$BLUE" "$c" "$RESET" "$i"
  sleep 1
done
printf '\r\033[K'
if [[ "$healthy" == true ]]; then
  ok "API healthy at http://localhost:${API_PORT}/health"
else
  warn "API not healthy yet — it may still be building. Check: ${BOLD}${COMPOSE[*]} logs -f studio${RESET}"
fi

# ── 6. Done ──────────────────────────────────────────────────────────────────
printf '\n%s%s  Vyakhya is up.  %s\n\n' "$BOLD" "$GREEN" "$RESET"
printf '  %sOpen%s      %s%shttp://localhost:%s%s\n' "$GREY" "$RESET" "$BOLD" "$BLUE" "${WEB_PORT}" "$RESET"
printf '  %sAPI%s       http://localhost:%s   %s(/docs for OpenAPI)%s\n' "$GREY" "$RESET" "${API_PORT}" "$DIM" "$RESET"
printf '  %sNext%s      add your model provider API keys in Model Config, then upload a PDF\n' "$GREY" "$RESET"
printf '\n'
printf '  %sLogs%s      %s logs -f studio\n' "$GREY" "$RESET" "${COMPOSE[*]}"
printf '  %sStop%s      %s down\n' "$GREY" "$RESET" "${COMPOSE[*]}"
printf '  %sReset%s     %s down -v   %s(wipes data volumes)%s\n' "$GREY" "$RESET" "${COMPOSE[*]}" "$DIM" "$RESET"
printf '\n'
