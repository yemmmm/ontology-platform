#!/usr/bin/env bash
set -Eeuo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKEND_DIR="$ROOT_DIR/backend"
FRONTEND_DIR="$ROOT_DIR/frontend"
COMPOSE_FILE="$ROOT_DIR/docker-compose.yml"

# Service configuration
POSTGRES_HOST="${POSTGRES_HOST:-localhost}"
POSTGRES_PORT="${POSTGRES_PORT:-5434}"
POSTGRES_DB="${POSTGRES_DB:-ontology_platform}"
POSTGRES_USER="${POSTGRES_USER:-ontology}"
NEO4J_HOST="${NEO4J_HOST:-localhost}"
NEO4J_BOLT_PORT="${NEO4J_BOLT_PORT:-7687}"
NEO4J_HTTP_PORT="${NEO4J_HTTP_PORT:-7474}"
NEO4J_USER="${NEO4J_USER:-neo4j}"
NEO4J_PASSWORD="${NEO4J_PASSWORD:-ontology-platform}"
OXIGRAPH_HOST="${OXIGRAPH_HOST:-localhost}"
OXIGRAPH_PORT="${OXIGRAPH_PORT:-7878}"
BACKEND_HOST="${BACKEND_HOST:-0.0.0.0}"
BACKEND_PORT="${BACKEND_PORT:-8001}"
FRONTEND_HOST="${FRONTEND_HOST:-0.0.0.0}"
FRONTEND_PORT="${FRONTEND_PORT:-5173}"

BACKEND_PID=""
FRONTEND_PID=""

log() { printf '[start-local] %s\n' "$*"; }
fail() { printf '[start-local] ERROR: %s\n' "$*" >&2; exit 1; }

command_exists() { command -v "$1" >/dev/null 2>&1; }
require_command() { command_exists "$1" || fail "Missing required command: $1"; }

tcp_ready() {
  timeout 1 bash -c "cat < /dev/null > /dev/tcp/$1/$2" >/dev/null 2>&1
}

wait_for_tcp() {
  local name="$1" host="$2" port="$3" timeout_seconds="${4:-60}"
  local connect_host="$host"

  if [[ "$connect_host" == "0.0.0.0" ]]; then
    connect_host="127.0.0.1"
  fi

  for ((i = 1; i <= timeout_seconds; i++)); do
    if tcp_ready "$connect_host" "$port"; then
      log "$name is ready at $host:$port"
      return 0
    fi
    sleep 1
  done
  fail "$name did not become ready at $host:$port within ${timeout_seconds}s"
}

wait_for_postgres() {
  local container="ontology-platform-postgres"
  for ((i = 1; i <= 60; i++)); do
    if docker exec "$container" pg_isready -U "$POSTGRES_USER" -d "$POSTGRES_DB" >/dev/null 2>&1; then
      log "PostgreSQL is ready at $POSTGRES_HOST:$POSTGRES_PORT"
      return 0
    fi
    sleep 1
  done
  fail "PostgreSQL did not become ready within 60s"
}

wait_for_neo4j() {
  local container="ontology-platform-neo4j"
  local timeout_seconds="${1:-120}"

  for ((i = 1; i <= timeout_seconds; i++)); do
    if docker exec "$container" cypher-shell -u "$NEO4J_USER" -p "$NEO4J_PASSWORD" \
      "RETURN 1" >/dev/null 2>&1; then
      log "Neo4j is ready at $NEO4J_HOST:$NEO4J_BOLT_PORT"
      return 0
    fi
    sleep 1
  done

  docker logs --tail 80 "$container" >&2 || true
  fail "Neo4j did not become ready for Bolt queries within ${timeout_seconds}s"
}

start_docker_services() {
  log "Starting PostgreSQL, Neo4j, and Oxigraph via Docker Compose"
  docker compose -f "$COMPOSE_FILE" up -d

  log "Waiting for PostgreSQL..."
  wait_for_postgres
  log "Waiting for Neo4j..."
  wait_for_tcp "Neo4j HTTP" "$NEO4J_HOST" "$NEO4J_HTTP_PORT" 30
  wait_for_neo4j 120
  log "Waiting for Oxigraph..."
  wait_for_tcp "Oxigraph HTTP" "$OXIGRAPH_HOST" "$OXIGRAPH_PORT" 60
}

ensure_backend_env() {
  if [[ ! -f "$BACKEND_DIR/.env" ]]; then
    [[ -f "$ROOT_DIR/.env.example" ]] || fail "Missing .env.example; cannot create backend/.env"
    log "Creating backend/.env from .env.example"
    cp "$ROOT_DIR/.env.example" "$BACKEND_DIR/.env"
    sed -i "s|POSTGRES_PORT=5432|POSTGRES_PORT=$POSTGRES_PORT|" "$BACKEND_DIR/.env"
    sed -i "s|localhost:5432/|localhost:$POSTGRES_PORT/|" "$BACKEND_DIR/.env"
  fi
}

install_frontend_dependencies() {
  if [[ ! -d "$FRONTEND_DIR/node_modules" ]]; then
    log "Installing frontend dependencies"
    (cd "$FRONTEND_DIR" && npm install)
  fi
}

port_owner_hint() {
  local port="$1"

  if command_exists lsof; then
    lsof -nP -iTCP:"$port" -sTCP:LISTEN 2>/dev/null || true
    return
  fi

  if command_exists ss; then
    ss -ltnp "sport = :$port" 2>/dev/null || true
    return
  fi
}

port_owner_pids() {
  local port="$1"

  if command_exists lsof; then
    lsof -tiTCP:"$port" -sTCP:LISTEN 2>/dev/null || true
    return
  fi

  if command_exists fuser; then
    fuser "${port}/tcp" 2>/dev/null || true
    return
  fi
}

process_belongs_to_project() {
  local pid="$1"
  local command cwd

  command="$(ps -p "$pid" -o command= 2>/dev/null || true)"
  cwd="$(readlink "/proc/$pid/cwd" 2>/dev/null || true)"

  [[ "$command" == *"$ROOT_DIR"* || "$cwd" == "$ROOT_DIR"* ]]
}

wait_for_port_free() {
  local host="$1" port="$2" timeout_seconds="${3:-10}"
  local connect_host="$host"

  if [[ "$connect_host" == "0.0.0.0" ]]; then
    connect_host="127.0.0.1"
  fi

  for ((i = 1; i <= timeout_seconds; i++)); do
    if ! tcp_ready "$connect_host" "$port"; then
      return 0
    fi
    sleep 1
  done

  return 1
}

ensure_port_available() {
  local name="$1" host="$2" port="$3"
  local connect_host="$host"
  local owner pids pid project_pids=()

  if [[ "$connect_host" == "0.0.0.0" ]]; then
    connect_host="127.0.0.1"
  fi

  if ! tcp_ready "$connect_host" "$port"; then
    return 0
  fi

  pids="$(port_owner_pids "$port")"
  if [[ -n "$pids" ]]; then
    for pid in $pids; do
      if process_belongs_to_project "$pid"; then
        project_pids+=("$pid")
      fi
    done
  fi

  if [[ ${#project_pids[@]} -eq 0 ]]; then
    owner="$(port_owner_hint "$port")"
    if [[ -n "$owner" ]]; then
      printf '%s\n' "$owner" >&2
    fi
    fail "$name port $port is already in use. Stop the existing process or choose another port."
  fi

  log "Stopping existing $name process on port $port"
  for pid in "${project_pids[@]}"; do
    kill_tree "$pid"
  done

  if ! wait_for_port_free "$host" "$port" 10; then
    owner="$(port_owner_hint "$port")"
    if [[ -n "$owner" ]]; then
      printf '%s\n' "$owner" >&2
    fi
    fail "$name port $port is still in use after stopping the existing project process."
  fi
}

kill_tree() {
  local pid="$1"
  local child

  for child in $(pgrep -P "$pid" 2>/dev/null || true); do
    kill_tree "$child"
  done

  kill "$pid" >/dev/null 2>&1 || true
}

cleanup() {
  for pid in "$FRONTEND_PID" "$BACKEND_PID"; do
    if [[ -n "$pid" ]] && kill -0 "$pid" >/dev/null 2>&1; then
      kill_tree "$pid"
    fi
  done
}

main() {
  require_command bash
  require_command timeout
  require_command uv
  require_command npm
  require_command docker

  ensure_backend_env
  start_docker_services

  log "Syncing backend Python environment"
  (cd "$BACKEND_DIR" && uv sync --extra dev)

  log "Running database migrations"
  (cd "$BACKEND_DIR" && uv run alembic upgrade head)

  install_frontend_dependencies

  log "Building frontend production assets"
  (cd "$FRONTEND_DIR" && npm run build)

  trap cleanup EXIT INT TERM

  ensure_port_available "Backend API" "$BACKEND_HOST" "$BACKEND_PORT"
  ensure_port_available "Frontend" "$FRONTEND_HOST" "$FRONTEND_PORT"

  log "Starting backend API at http://$BACKEND_HOST:$BACKEND_PORT"
  (cd "$BACKEND_DIR" && uv run uvicorn app.main:app --host "$BACKEND_HOST" --port "$BACKEND_PORT" --reload) &
  BACKEND_PID="$!"

  wait_for_tcp "Backend API" "$BACKEND_HOST" "$BACKEND_PORT" 60

  log "Starting frontend production preview at http://$FRONTEND_HOST:$FRONTEND_PORT"
  (cd "$FRONTEND_DIR" && npm run preview -- --host "$FRONTEND_HOST" --port "$FRONTEND_PORT" --strictPort) &
  FRONTEND_PID="$!"

  wait_for_tcp "Frontend" "$FRONTEND_HOST" "$FRONTEND_PORT" 60

  log "Project is running"
  log "Backend:  http://$BACKEND_HOST:$BACKEND_PORT"
  log "Frontend: http://$FRONTEND_HOST:$FRONTEND_PORT"
  log "Press Ctrl+C to stop backend and frontend. Docker services stay running."

  wait "$BACKEND_PID" "$FRONTEND_PID"
}

main "$@"
