#!/usr/bin/env bash
set -Eeuo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKEND_DIR="$ROOT_DIR/backend"
FRONTEND_DIR="$ROOT_DIR/frontend"

POSTGRES_HOST="${POSTGRES_HOST:-localhost}"
POSTGRES_PORT="${POSTGRES_PORT:-5432}"
POSTGRES_DB="${POSTGRES_DB:-ontology_platform}"
POSTGRES_USER="${POSTGRES_USER:-ontology}"
POSTGRES_DATA_DIR="${POSTGRES_DATA_DIR:-/var/lib/postgresql/18/main}"
PG_CTL="${PG_CTL:-/usr/lib/postgresql/18/bin/pg_ctl}"
POSTGRES_RUN_USER="${POSTGRES_RUN_USER:-}"
LEGACY_DATABASE_URL="postgresql+psycopg://ontology:ontology@localhost:5432/ontology_platform"
DEFAULT_DATABASE_URL="${LEGACY_DATABASE_URL}?client_encoding=utf8"

NEO4J_HOME="${NEO4J_HOME:-/opt/neo4j}"
NEO4J_HOST="${NEO4J_HOST:-localhost}"
NEO4J_BOLT_PORT="${NEO4J_BOLT_PORT:-7687}"
NEO4J_HTTP_PORT="${NEO4J_HTTP_PORT:-7474}"

BACKEND_HOST="${BACKEND_HOST:-127.0.0.1}"
BACKEND_PORT="${BACKEND_PORT:-8000}"
FRONTEND_HOST="${FRONTEND_HOST:-127.0.0.1}"
FRONTEND_PORT="${FRONTEND_PORT:-5173}"

BACKEND_PID=""
FRONTEND_PID=""

log() {
  printf '[start-local] %s\n' "$*"
}

fail() {
  printf '[start-local] ERROR: %s\n' "$*" >&2
  exit 1
}

command_exists() {
  command -v "$1" >/dev/null 2>&1
}

require_command() {
  command_exists "$1" || fail "Missing required command: $1"
}

tcp_ready() {
  local host="$1"
  local port="$2"
  timeout 1 bash -c "cat < /dev/null > /dev/tcp/$host/$port" >/dev/null 2>&1
}

wait_for_tcp() {
  local name="$1"
  local host="$2"
  local port="$3"
  local timeout_seconds="${4:-60}"

  for ((i = 1; i <= timeout_seconds; i++)); do
    if tcp_ready "$host" "$port"; then
      log "$name is ready at $host:$port"
      return 0
    fi
    sleep 1
  done

  fail "$name did not become ready at $host:$port within ${timeout_seconds}s"
}

wait_for_postgres() {
  local timeout_seconds="${1:-60}"

  for ((i = 1; i <= timeout_seconds; i++)); do
    if pg_isready -h "$POSTGRES_HOST" -p "$POSTGRES_PORT" -U "$POSTGRES_USER" -d "$POSTGRES_DB" >/dev/null 2>&1; then
      log "PostgreSQL is ready at $POSTGRES_HOST:$POSTGRES_PORT"
      return 0
    fi
    sleep 1
  done

  fail "PostgreSQL did not become ready at $POSTGRES_HOST:$POSTGRES_PORT within ${timeout_seconds}s"
}

pg_ctl_cmd() {
  if [[ -n "$POSTGRES_RUN_USER" && "$(id -un)" != "$POSTGRES_RUN_USER" ]]; then
    sudo -u "$POSTGRES_RUN_USER" "$PG_CTL" -D "$POSTGRES_DATA_DIR" "$@"
  else
    "$PG_CTL" -D "$POSTGRES_DATA_DIR" "$@"
  fi
}

start_postgres() {
  if pg_ctl_cmd start; then
    return 0
  fi

  if [[ -z "$POSTGRES_RUN_USER" ]] && command_exists sudo; then
    log "Retrying PostgreSQL start as postgres user"
    sudo -u postgres "$PG_CTL" -D "$POSTGRES_DATA_DIR" start
    return 0
  fi

  return 1
}

start_postgres_if_needed() {
  require_command pg_isready

  if pg_isready -h "$POSTGRES_HOST" -p "$POSTGRES_PORT" -U "$POSTGRES_USER" -d "$POSTGRES_DB" >/dev/null 2>&1; then
    log "PostgreSQL already running"
    return 0
  fi

  [[ -x "$PG_CTL" ]] || fail "pg_ctl not found or not executable at $PG_CTL"
  [[ -d "$POSTGRES_DATA_DIR" ]] || fail "PostgreSQL data directory not found at $POSTGRES_DATA_DIR"

  log "Starting PostgreSQL"
  start_postgres || fail "Failed to start PostgreSQL"
  wait_for_postgres 60
}

start_neo4j_if_needed() {
  if tcp_ready "$NEO4J_HOST" "$NEO4J_BOLT_PORT"; then
    log "Neo4j Bolt already running"
    return 0
  fi

  [[ -x "$NEO4J_HOME/bin/neo4j" ]] || fail "Neo4j executable not found at $NEO4J_HOME/bin/neo4j"

  log "Starting Neo4j"
  "$NEO4J_HOME/bin/neo4j" start
  wait_for_tcp "Neo4j Bolt" "$NEO4J_HOST" "$NEO4J_BOLT_PORT" 90
  wait_for_tcp "Neo4j HTTP" "$NEO4J_HOST" "$NEO4J_HTTP_PORT" 30
}

ensure_backend_env() {
  if [[ ! -f "$BACKEND_DIR/.env" ]]; then
    [[ -f "$ROOT_DIR/.env.example" ]] || fail "Missing .env.example; cannot create backend/.env"
    log "Creating backend/.env from .env.example"
    cp "$ROOT_DIR/.env.example" "$BACKEND_DIR/.env"
  fi

  if grep -Fxq "DATABASE_URL=$LEGACY_DATABASE_URL" "$BACKEND_DIR/.env"; then
    log "Updating backend/.env DATABASE_URL to request UTF-8 client encoding"
    sed -i "s|^DATABASE_URL=$LEGACY_DATABASE_URL$|DATABASE_URL=$DEFAULT_DATABASE_URL|" "$BACKEND_DIR/.env"
  fi
}

install_frontend_dependencies() {
  if [[ ! -d "$FRONTEND_DIR/node_modules" ]]; then
    log "Installing frontend dependencies"
    (cd "$FRONTEND_DIR" && npm install)
  fi
}

cleanup() {
  if [[ -n "$FRONTEND_PID" ]] && kill -0 "$FRONTEND_PID" >/dev/null 2>&1; then
    kill "$FRONTEND_PID" >/dev/null 2>&1 || true
  fi
  if [[ -n "$BACKEND_PID" ]] && kill -0 "$BACKEND_PID" >/dev/null 2>&1; then
    kill "$BACKEND_PID" >/dev/null 2>&1 || true
  fi
}

main() {
  require_command bash
  require_command timeout
  require_command uv
  require_command npm

  ensure_backend_env
  start_postgres_if_needed
  start_neo4j_if_needed

  log "Syncing backend Python environment"
  (cd "$BACKEND_DIR" && uv sync --extra dev)

  log "Running database migrations"
  (cd "$BACKEND_DIR" && uv run alembic upgrade head)

  install_frontend_dependencies

  trap cleanup EXIT INT TERM

  log "Starting backend API at http://$BACKEND_HOST:$BACKEND_PORT"
  (cd "$BACKEND_DIR" && uv run uvicorn app.main:app --host "$BACKEND_HOST" --port "$BACKEND_PORT" --reload) &
  BACKEND_PID="$!"

  wait_for_tcp "Backend API" "$BACKEND_HOST" "$BACKEND_PORT" 60

  log "Starting frontend at http://$FRONTEND_HOST:$FRONTEND_PORT"
  (cd "$FRONTEND_DIR" && npm run dev -- --host "$FRONTEND_HOST" --port "$FRONTEND_PORT") &
  FRONTEND_PID="$!"

  wait_for_tcp "Frontend" "$FRONTEND_HOST" "$FRONTEND_PORT" 60

  log "Project is running"
  log "Backend:  http://$BACKEND_HOST:$BACKEND_PORT"
  log "Frontend: http://$FRONTEND_HOST:$FRONTEND_PORT"
  log "Press Ctrl+C to stop backend and frontend. PostgreSQL and Neo4j stay running."

  wait "$BACKEND_PID" "$FRONTEND_PID"
}

main "$@"
