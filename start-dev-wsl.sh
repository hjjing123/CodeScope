#!/usr/bin/env bash

set -Eeuo pipefail

BACKEND_PORT=8000
FRONTEND_PORT=5173
FRONTEND_WATCH_MODE="${FRONTEND_WATCH_MODE:-polling}"
FRONTEND_WATCH_INTERVAL_MS="${FRONTEND_WATCH_INTERVAL_MS:-300}"
WORKER_QUEUES="import,scan,patch,env,report,low"
WORKER_LOG_LEVEL="info"
BACKEND_READY_TIMEOUT_SECONDS="${BACKEND_READY_TIMEOUT_SECONDS:-60}"
FRONTEND_READY_TIMEOUT_SECONDS="${FRONTEND_READY_TIMEOUT_SECONDS:-180}"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --backend-port)
      BACKEND_PORT="${2:-}"
      shift 2
      ;;
    --frontend-port)
      FRONTEND_PORT="${2:-}"
      shift 2
      ;;
    --frontend-watch-mode)
      FRONTEND_WATCH_MODE="${2:-}"
      shift 2
      ;;
    --frontend-watch-interval-ms)
      FRONTEND_WATCH_INTERVAL_MS="${2:-}"
      shift 2
      ;;
    --worker-queues)
      WORKER_QUEUES="${2:-}"
      shift 2
      ;;
    --worker-log-level)
      WORKER_LOG_LEVEL="${2:-}"
      shift 2
      ;;
    *)
      echo "Unknown argument: $1" >&2
      echo "Usage: $0 [--backend-port <port>] [--frontend-port <port>] [--frontend-watch-mode <polling|native>] [--frontend-watch-interval-ms <ms>] [--worker-queues <queues>] [--worker-log-level <level>]" >&2
      exit 2
      ;;
  esac
done

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$SCRIPT_DIR"
BACKEND_DIR="$REPO_ROOT/backend"
FRONTEND_DIR="$REPO_ROOT/frontend"
WSL_VENV_DIR="$BACKEND_DIR/.venv-wsl"

assert_path_exists() {
  local path="$1"
  local message="$2"
  if [[ ! -e "$path" ]]; then
    echo "$message" >&2
    exit 1
  fi
}

start_dev_process() {
  local name="$1"
  local cwd="$2"
  local log_path="$3"
  shift 3
  echo "[start] $name"
  (
    cd "$cwd"
    exec "$@" >>"$log_path" 2>&1
  ) &
  LAST_STARTED_PID="$!"
}

log_supervisor() {
  local message="$1"
  local line
  line="[$(date '+%H:%M:%S')] $message"
  printf '%s\n' "$line" >>"$SUPERVISOR_LOG"
  printf '%s\n' "$line" || true
}

is_process_running() {
  local pid="${1:-}"
  [[ -n "$pid" ]] && kill -0 "$pid" 2>/dev/null
}

wait_for_http_ready() {
  local name="$1"
  local url="$2"
  local timeout_seconds="$3"
  local pid="$4"
  local start_ts
  local http_code

  start_ts="$(date +%s)"
  while true; do
    if [[ -n "$pid" ]] && ! is_process_running "$pid"; then
      echo "[error] ${name} exited before ${url} became ready." >&2
      return 1
    fi

    http_code="$(curl --silent --show-error --output /dev/null --write-out '%{http_code}' --max-time 3 "$url" 2>/dev/null || true)"
    if [[ "$http_code" =~ ^2[0-9][0-9]$ || "$http_code" =~ ^3[0-9][0-9]$ ]]; then
      echo "[ready] $name -> $url ($http_code)"
      return 0
    fi

    if (( $(date +%s) - start_ts >= timeout_seconds )); then
      echo "[warn] Timed out waiting for $name at $url (last status: ${http_code:-n/a})." >&2
      return 2
    fi

    sleep 1
  done
}

print_log_tail() {
  local name="$1"
  local log_path="$2"
  local lines="${3:-40}"
  if [[ ! -f "$log_path" ]]; then
    return
  fi
  echo "[log] Last ${lines} lines from ${name}: $log_path"
  tail -n "$lines" "$log_path" || true
}

collect_descendants() {
  local pid="$1"
  local child
  local children
  children="$(pgrep -P "$pid" || true)"
  for child in $children; do
    collect_descendants "$child"
  done
  echo "$pid"
}

stop_process_tree() {
  local pid="${1:-}"
  if [[ -z "$pid" ]]; then
    return
  fi
  if ! kill -0 "$pid" 2>/dev/null; then
    return
  fi
  local all_pids
  all_pids="$(collect_descendants "$pid" | awk '!seen[$0]++')"
  if [[ -n "$all_pids" ]]; then
    while IFS= read -r p; do
      kill -TERM "$p" 2>/dev/null || true
    done <<< "$all_pids"

    local deadline
    deadline=$((SECONDS + 5))
    while (( SECONDS < deadline )); do
      local has_running=0
      while IFS= read -r p; do
        if kill -0 "$p" 2>/dev/null; then
          has_running=1
          break
        fi
      done <<< "$all_pids"

      if [[ "$has_running" -eq 0 ]]; then
        break
      fi
      sleep 0.2
    done

    while IFS= read -r p; do
      if kill -0 "$p" 2>/dev/null; then
        kill -KILL "$p" 2>/dev/null || true
      fi
      wait "$p" 2>/dev/null || true
    done <<< "$all_pids"
  fi
}

assert_valid_port() {
  local port="$1"
  local flag_name="$2"
  if [[ ! "$port" =~ ^[0-9]+$ ]] || (( port < 1 || port > 65535 )); then
    echo "Invalid ${flag_name}: ${port}. Expected an integer between 1 and 65535." >&2
    exit 2
  fi
}

assert_valid_positive_integer() {
  local value="$1"
  local flag_name="$2"
  if [[ ! "$value" =~ ^[0-9]+$ ]] || (( value < 1 )); then
    echo "Invalid ${flag_name}: ${value}. Expected an integer greater than 0." >&2
    exit 2
  fi
}

normalize_frontend_watch_mode() {
  local mode="$1"
  case "${mode,,}" in
    polling)
      echo "polling"
      ;;
    native)
      echo "native"
      ;;
    *)
      echo "Invalid --frontend-watch-mode: ${mode}. Expected 'polling' or 'native'." >&2
      exit 2
      ;;
  esac
}

port_in_use() {
  local port="$1"
  ss -ltn "sport = :$port" 2>/dev/null | awk 'NR > 1 { found = 1 } END { exit found ? 0 : 1 }'
}

find_available_port() {
  local requested_port="$1"
  local search_span="$2"
  local candidate_port="$requested_port"
  local index=0
  while (( index <= search_span )); do
    if ! port_in_use "$candidate_port"; then
      echo "$candidate_port"
      return 0
    fi
    candidate_port=$((candidate_port + 1))
    if (( candidate_port > 65535 )); then
      break
    fi
    index=$((index + 1))
  done
  return 1
}

assert_path_exists "$BACKEND_DIR" "Missing backend directory: $BACKEND_DIR"
assert_path_exists "$FRONTEND_DIR" "Missing frontend directory: $FRONTEND_DIR"
assert_path_exists "$BACKEND_DIR/pyproject.toml" "Missing backend/pyproject.toml"
assert_path_exists "$FRONTEND_DIR/package.json" "Missing frontend/package.json"

if [[ -s "$HOME/.nvm/nvm.sh" ]]; then
  # shellcheck disable=SC1090
  . "$HOME/.nvm/nvm.sh"
  if command -v nvm >/dev/null 2>&1; then
    nvm use --silent default >/dev/null 2>&1 || true
  fi
fi

if ! command -v node >/dev/null 2>&1; then
  echo "node not found. Install a native Linux Node.js runtime in WSL." >&2
  exit 1
fi

if ! command -v npm >/dev/null 2>&1; then
  echo "npm not found. Install Node.js and ensure npm is on PATH." >&2
  exit 1
fi

if ! command -v curl >/dev/null 2>&1; then
  echo "curl not found. Install curl in WSL to enable startup readiness checks." >&2
  exit 1
fi

NODE_BIN="$(command -v node)"
NPM_BIN="$(command -v npm)"
NODE_VERSION="$("$NODE_BIN" -p 'process.versions.node')"

if [[ "$NODE_BIN" == /mnt/c/* || "$NODE_BIN" == /c/* || "$NPM_BIN" == /mnt/c/* || "$NPM_BIN" == /c/* ]]; then
  echo "WSL resolved Windows Node.js tooling (node=$NODE_BIN, npm=$NPM_BIN)." >&2
  echo "Use a native Linux Node.js runtime in WSL, for example by loading nvm before running this script." >&2
  exit 1
fi

if ! "$NODE_BIN" -e "const [maj, min, pat] = process.versions.node.split('.').map(Number); const ok = (maj === 20 && (min > 19 || (min === 19 && pat >= 0))) || (maj === 22 && (min > 12 || (min === 12 && pat >= 0))) || maj > 22; process.exit(ok ? 0 : 1)"; then
  echo "Node.js $NODE_VERSION is too old. Vite 7 requires Node.js 20.19+ or 22.12+." >&2
  exit 1
fi

assert_valid_port "$BACKEND_PORT" "--backend-port"
assert_valid_port "$FRONTEND_PORT" "--frontend-port"
assert_valid_positive_integer "$FRONTEND_WATCH_INTERVAL_MS" "--frontend-watch-interval-ms"
FRONTEND_WATCH_MODE="$(normalize_frontend_watch_mode "$FRONTEND_WATCH_MODE")"

RESOLVED_BACKEND_PORT="$(find_available_port "$BACKEND_PORT" 30 || true)"
if [[ -z "$RESOLVED_BACKEND_PORT" ]]; then
  echo "No available backend port found starting from $BACKEND_PORT within range $BACKEND_PORT-$((BACKEND_PORT + 30))." >&2
  exit 1
fi
if [[ "$RESOLVED_BACKEND_PORT" != "$BACKEND_PORT" ]]; then
  echo "[warn] Backend port $BACKEND_PORT is in use, switched to $RESOLVED_BACKEND_PORT"
fi
BACKEND_PORT="$RESOLVED_BACKEND_PORT"

RESOLVED_FRONTEND_PORT="$(find_available_port "$FRONTEND_PORT" 30 || true)"
if [[ -z "$RESOLVED_FRONTEND_PORT" ]]; then
  echo "No available frontend port found starting from $FRONTEND_PORT within range $FRONTEND_PORT-$((FRONTEND_PORT + 30))." >&2
  exit 1
fi
if [[ "$RESOLVED_FRONTEND_PORT" != "$FRONTEND_PORT" ]]; then
  echo "[warn] Frontend port $FRONTEND_PORT is in use, switched to $RESOLVED_FRONTEND_PORT"
fi
FRONTEND_PORT="$RESOLVED_FRONTEND_PORT"

FRONTEND_ENV=()
if [[ "$FRONTEND_WATCH_MODE" == "polling" ]]; then
  FRONTEND_ENV=(env CHOKIDAR_USEPOLLING=true CHOKIDAR_INTERVAL="$FRONTEND_WATCH_INTERVAL_MS")
fi

VITE_BIN="$FRONTEND_DIR/node_modules/.bin/vite"
if [[ -x "$VITE_BIN" ]]; then
  FRONTEND_CMD=("${FRONTEND_ENV[@]}" "$VITE_BIN" --host 0.0.0.0 --port "$FRONTEND_PORT" --strictPort)
else
  FRONTEND_CMD=("${FRONTEND_ENV[@]}" "$NPM_BIN" run dev -- --host 0.0.0.0 --port "$FRONTEND_PORT" --strictPort)
fi

if command -v uv >/dev/null 2>&1; then
  if [[ ! -v UV_LINK_MODE ]]; then
    export UV_LINK_MODE="copy"
  fi
  export UV_PROJECT_ENVIRONMENT="$WSL_VENV_DIR"
  echo "[setup] Syncing WSL virtual environment at $WSL_VENV_DIR"
  (
    cd "$BACKEND_DIR"
    uv sync --extra dev
  )
fi

VENV_PYTHON="$WSL_VENV_DIR/bin/python"
if [[ ! -x "$VENV_PYTHON" ]]; then
  echo "backend/.venv-wsl/bin/python is missing. Install uv in WSL and run 'cd backend && UV_PROJECT_ENVIRONMENT=.venv-wsl uv sync --extra dev' first." >&2
  exit 1
fi

MIGRATE_CMD=("$VENV_PYTHON" -m alembic upgrade head)
BACKEND_CMD=(
  "$VENV_PYTHON"
  -m
  uvicorn
  app.main:app
  --host
  0.0.0.0
  --port
  "$BACKEND_PORT"
)
WORKER_CMD=("$VENV_PYTHON" -m app.worker --queues "$WORKER_QUEUES" --log-level "$WORKER_LOG_LEVEL")

BACKEND_PID=""
FRONTEND_PID=""
WORKER_PID=""
READINESS_PID=""
LAST_STARTED_PID=""
TRIGGER_PROCESS=""
TRIGGER_EXIT_CODE=0
LOG_DIR="$REPO_ROOT/.logs/wsl-dev"
BACKEND_LOG="$LOG_DIR/backend.log"
FRONTEND_LOG="$LOG_DIR/frontend.log"
WORKER_LOG="$LOG_DIR/worker.log"
SUPERVISOR_LOG="$LOG_DIR/supervisor.log"

mkdir -p "$LOG_DIR"
: > "$BACKEND_LOG"
: > "$FRONTEND_LOG"
: > "$WORKER_LOG"
: > "$SUPERVISOR_LOG"

echo "[setup] Applying database migrations"
if ! (
  cd "$BACKEND_DIR"
  "${MIGRATE_CMD[@]}"
) >>"$BACKEND_LOG" 2>&1; then
  echo "[error] Failed to apply database migrations." >&2
  print_log_tail "backend" "$BACKEND_LOG"
  exit 1
fi

FRONTEND_DEV_URL_WAS_SET=0
FRONTEND_DEV_PORT_WAS_SET=0
VITE_HMR_CLIENT_PORT_WAS_SET=0
ORIGINAL_FRONTEND_DEV_URL=""
ORIGINAL_FRONTEND_DEV_PORT=""
ORIGINAL_VITE_HMR_CLIENT_PORT=""

if [[ -v FRONTEND_DEV_URL ]]; then
  FRONTEND_DEV_URL_WAS_SET=1
  ORIGINAL_FRONTEND_DEV_URL="$FRONTEND_DEV_URL"
fi
if [[ -v FRONTEND_DEV_PORT ]]; then
  FRONTEND_DEV_PORT_WAS_SET=1
  ORIGINAL_FRONTEND_DEV_PORT="$FRONTEND_DEV_PORT"
fi
if [[ -v VITE_HMR_CLIENT_PORT ]]; then
  VITE_HMR_CLIENT_PORT_WAS_SET=1
  ORIGINAL_VITE_HMR_CLIENT_PORT="$VITE_HMR_CLIENT_PORT"
fi

cleanup() {
  if [[ "$FRONTEND_DEV_URL_WAS_SET" -eq 1 ]]; then
    export FRONTEND_DEV_URL="$ORIGINAL_FRONTEND_DEV_URL"
  else
    unset FRONTEND_DEV_URL || true
  fi

  if [[ "$FRONTEND_DEV_PORT_WAS_SET" -eq 1 ]]; then
    export FRONTEND_DEV_PORT="$ORIGINAL_FRONTEND_DEV_PORT"
  else
    unset FRONTEND_DEV_PORT || true
  fi

  if [[ "$VITE_HMR_CLIENT_PORT_WAS_SET" -eq 1 ]]; then
    export VITE_HMR_CLIENT_PORT="$ORIGINAL_VITE_HMR_CLIENT_PORT"
  else
    unset VITE_HMR_CLIENT_PORT || true
  fi

  stop_process_tree "$READINESS_PID"
  stop_process_tree "$FRONTEND_PID"
  stop_process_tree "$WORKER_PID"
  stop_process_tree "$BACKEND_PID"
}

trap cleanup EXIT
trap 'log_supervisor "received signal INT"; exit 130' INT
trap 'log_supervisor "received signal TERM"; exit 130' TERM
trap 'log_supervisor "received signal HUP"; exit 129' HUP

export FRONTEND_DEV_URL="http://127.0.0.1:${FRONTEND_PORT}"
export FRONTEND_DEV_PORT="$FRONTEND_PORT"
export VITE_HMR_CLIENT_PORT="$FRONTEND_PORT"
if [[ ! -v FRONTEND_DEV_PROXY_TIMEOUT_SECONDS ]]; then
  export FRONTEND_DEV_PROXY_TIMEOUT_SECONDS="45"
fi
if [[ ! -v CODESCOPE_SCAN_ENGINE_MODE ]]; then
  export CODESCOPE_SCAN_ENGINE_MODE="external"
fi
if [[ ! -v CODESCOPE_SCAN_DISPATCH_BACKEND ]]; then
  export CODESCOPE_SCAN_DISPATCH_BACKEND="celery"
fi
if [[ ! -v CODESCOPE_SCAN_EXTERNAL_RUNTIME_PROFILE ]]; then
  export CODESCOPE_SCAN_EXTERNAL_RUNTIME_PROFILE="wsl"
fi
if [[ ! -v CODESCOPE_SCAN_EXTERNAL_CONTAINER_COMPAT_MODE ]]; then
  export CODESCOPE_SCAN_EXTERNAL_CONTAINER_COMPAT_MODE="0"
fi
if [[ ! -v CODESCOPE_SCAN_EXTERNAL_JOERN_HOME ]]; then
  export CODESCOPE_SCAN_EXTERNAL_JOERN_HOME="../infra/tools/joern-cli"
fi
if [[ ! -v CODESCOPE_SCAN_EXTERNAL_STAGE_JOERN_COMMAND ]]; then
  export CODESCOPE_SCAN_EXTERNAL_STAGE_JOERN_COMMAND="builtin:joern"
fi
if [[ ! -v CODESCOPE_SCAN_EXTERNAL_STAGE_IMPORT_COMMAND ]]; then
  export CODESCOPE_SCAN_EXTERNAL_STAGE_IMPORT_COMMAND="builtin:neo4j_import"
fi
if [[ ! -v CODESCOPE_SCAN_EXTERNAL_STAGE_POST_LABELS_COMMAND ]]; then
  export CODESCOPE_SCAN_EXTERNAL_STAGE_POST_LABELS_COMMAND="builtin:post_labels"
fi
if [[ ! -v CODESCOPE_SCAN_EXTERNAL_STAGE_RULES_COMMAND ]]; then
  export CODESCOPE_SCAN_EXTERNAL_STAGE_RULES_COMMAND="builtin:rules"
fi
if [[ ! -v CODESCOPE_SCAN_EXTERNAL_IMPORT_DATA_MOUNT ]]; then
  export CODESCOPE_SCAN_EXTERNAL_IMPORT_DATA_MOUNT="codescope_neo4j_data_{job_id}"
fi
if [[ ! -v CODESCOPE_SCAN_EXTERNAL_NEO4J_URI ]]; then
  export CODESCOPE_SCAN_EXTERNAL_NEO4J_URI="bolt://127.0.0.1:7687"
fi
if [[ ! -v CODESCOPE_SCAN_EXTERNAL_NEO4J_USER ]]; then
  export CODESCOPE_SCAN_EXTERNAL_NEO4J_USER="neo4j"
fi
if [[ ! -v CODESCOPE_SCAN_EXTERNAL_NEO4J_PASSWORD ]]; then
  export CODESCOPE_SCAN_EXTERNAL_NEO4J_PASSWORD="codescope123"
fi
if [[ ! -v CODESCOPE_SCAN_EXTERNAL_NEO4J_DATABASE ]]; then
  export CODESCOPE_SCAN_EXTERNAL_NEO4J_DATABASE="neo4j"
fi
if [[ ! -v CODESCOPE_SCAN_EXTERNAL_NEO4J_RUNTIME_CONTAINER_NAME ]]; then
  export CODESCOPE_SCAN_EXTERNAL_NEO4J_RUNTIME_CONTAINER_NAME="codescope_neo4j_{job_id}"
fi
if [[ ! -v CODESCOPE_SCAN_EXTERNAL_NEO4J_RUNTIME_RESTART_MODE ]]; then
  export CODESCOPE_SCAN_EXTERNAL_NEO4J_RUNTIME_RESTART_MODE="docker_ephemeral"
fi
if [[ ! -v CODESCOPE_SCAN_EXTERNAL_NEO4J_RUNTIME_RESTART_WAIT_SECONDS ]]; then
  export CODESCOPE_SCAN_EXTERNAL_NEO4J_RUNTIME_RESTART_WAIT_SECONDS="10"
fi

start_dev_process "backend" "$BACKEND_DIR" "$BACKEND_LOG" "${BACKEND_CMD[@]}"
BACKEND_PID="$LAST_STARTED_PID"
log_supervisor "backend pid=$BACKEND_PID"
start_dev_process "worker" "$BACKEND_DIR" "$WORKER_LOG" "${WORKER_CMD[@]}"
WORKER_PID="$LAST_STARTED_PID"
log_supervisor "worker pid=$WORKER_PID"
start_dev_process "frontend" "$FRONTEND_DIR" "$FRONTEND_LOG" "${FRONTEND_CMD[@]}"
FRONTEND_PID="$LAST_STARTED_PID"
log_supervisor "frontend pid=$FRONTEND_PID"

FRONTEND_READY_URL="http://127.0.0.1:${FRONTEND_PORT}/@vite/client"

run_readiness_checks() {
  local frontend_status=0
  local backend_status=0
  local login_status=0

  wait_for_http_ready "frontend dev server" "$FRONTEND_READY_URL" "$FRONTEND_READY_TIMEOUT_SECONDS" "$FRONTEND_PID" || frontend_status=$?
  if [[ "$frontend_status" -ne 0 ]]; then
    print_log_tail "frontend" "$FRONTEND_LOG"
    if [[ "$frontend_status" -eq 1 ]]; then
      echo "[warn] Frontend process exited before readiness check passed." >&2
    else
      echo "[warn] Frontend is still warming up. Services stay running; wait a bit longer and then open the backend URL." >&2
    fi
  fi

  wait_for_http_ready "backend health" "http://127.0.0.1:${BACKEND_PORT}/healthz" "$BACKEND_READY_TIMEOUT_SECONDS" "$BACKEND_PID" || backend_status=$?
  if [[ "$backend_status" -ne 0 ]]; then
    print_log_tail "backend" "$BACKEND_LOG"
    if [[ "$backend_status" -eq 1 ]]; then
      echo "[warn] Backend process exited before health check passed." >&2
    else
      echo "[warn] Backend health check timed out. Check backend log if API is unreachable." >&2
    fi
    return 0
  fi

  if curl --silent --show-error --output /dev/null --write-out '%{http_code}' --max-time 5 "$FRONTEND_READY_URL" 2>/dev/null | grep -Eq '^2[0-9][0-9]$|^3[0-9][0-9]$'; then
    wait_for_http_ready "backend login page" "http://127.0.0.1:${BACKEND_PORT}/login" "$BACKEND_READY_TIMEOUT_SECONDS" "$BACKEND_PID" || login_status=$?
    if [[ "$login_status" -ne 0 ]]; then
      print_log_tail "backend" "$BACKEND_LOG"
      print_log_tail "frontend" "$FRONTEND_LOG"
      echo "[warn] Backend login page readiness check did not pass yet." >&2
    fi
  else
    echo "[warn] Skipping backend login readiness check because frontend dev server is not ready yet." >&2
  fi
}

echo
echo "Backend:  http://127.0.0.1:${BACKEND_PORT}"
echo "Frontend: http://127.0.0.1:${FRONTEND_PORT}"
if [[ "$FRONTEND_WATCH_MODE" == "polling" ]]; then
  echo "Watch:    frontend=${FRONTEND_WATCH_MODE} (${FRONTEND_WATCH_INTERVAL_MS}ms)"
else
  echo "Watch:    frontend=${FRONTEND_WATCH_MODE}"
fi
echo "SPA via backend in dev proxies to same host:${FRONTEND_PORT}"
echo "Worker:   queues=${WORKER_QUEUES}"
echo "Logs:     $LOG_DIR"
echo "Press Ctrl+C to stop all processes."
echo
log_supervisor "startup complete backend=$BACKEND_PID worker=$WORKER_PID frontend=$FRONTEND_PID"
if [[ "$FRONTEND_WATCH_MODE" == "polling" ]]; then
  log_supervisor "frontend watch mode=${FRONTEND_WATCH_MODE} interval_ms=${FRONTEND_WATCH_INTERVAL_MS}"
else
  log_supervisor "frontend watch mode=${FRONTEND_WATCH_MODE}"
fi

run_readiness_checks &
READINESS_PID="$!"
log_supervisor "readiness pid=$READINESS_PID"

while true; do
  sleep 0.5

  if ! kill -0 "$BACKEND_PID" 2>/dev/null; then
    TRIGGER_PROCESS="backend"
    wait "$BACKEND_PID" || TRIGGER_EXIT_CODE=$?
    log_supervisor "backend exited with code $TRIGGER_EXIT_CODE"
    print_log_tail "backend" "$BACKEND_LOG"
    echo "[stop] backend exited with code $TRIGGER_EXIT_CODE"
    break
  fi

  if ! kill -0 "$FRONTEND_PID" 2>/dev/null; then
    TRIGGER_PROCESS="frontend"
    wait "$FRONTEND_PID" || TRIGGER_EXIT_CODE=$?
    log_supervisor "frontend exited with code $TRIGGER_EXIT_CODE"
    print_log_tail "frontend" "$FRONTEND_LOG"
    echo "[stop] frontend exited with code $TRIGGER_EXIT_CODE"
    break
  fi

  if ! kill -0 "$WORKER_PID" 2>/dev/null; then
    TRIGGER_PROCESS="worker"
    wait "$WORKER_PID" || TRIGGER_EXIT_CODE=$?
    log_supervisor "worker exited with code $TRIGGER_EXIT_CODE"
    print_log_tail "worker" "$WORKER_LOG"
    echo "[stop] worker exited with code $TRIGGER_EXIT_CODE"
    break
  fi
done

if [[ -n "$TRIGGER_PROCESS" && "$TRIGGER_EXIT_CODE" -ne 0 ]]; then
  exit "$TRIGGER_EXIT_CODE"
fi

exit 0
