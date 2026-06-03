#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_ROOT"

OSGE_PYTHON="${OSGE_PYTHON:-${VENV_PYTHON:-python}}"
OSGE_UVICORN="${OSGE_UVICORN:-${VENV_UVICORN:-}}"

OSGE_HOST="${OSGE_HOST:-127.0.0.1}"
OSGE_PORT="${OSGE_PORT:-8010}"
OSGE_DEFAULT_DB="${OSGE_DEFAULT_DB:-$PROJECT_ROOT/data/database/osge_overlay.db}"
OSGE_DB="${OSGE_DB:-$OSGE_DEFAULT_DB}"
OSGE_WEB_LOG="${OSGE_WEB_LOG:-$PROJECT_ROOT/logs/osge_web.log}"
OSGE_WEB_PID="${OSGE_WEB_PID:-$PROJECT_ROOT/logs/osge_web.pid}"

OSGE_CDP_PORT="${OSGE_CDP_PORT:-9222}"
OSGE_CDP_PROFILE="${OSGE_CDP_PROFILE:-${XDG_CACHE_HOME:-$HOME/.cache}/osge-chromium}"
OSGE_CDP_HEADLESS="${OSGE_CDP_HEADLESS:-0}"
OSGE_START_CDP="${OSGE_START_CDP:-0}"

mkdir -p "$PROJECT_ROOT/logs"

runtime_hint() {
  echo "Install dependencies into the selected Python, or set OSGE_PYTHON to a Python that already has them." >&2
  echo "Examples:" >&2
  echo "  python -m pip install -r requirements.txt" >&2
  echo "  OSGE_PYTHON=.venv/bin/python $0 start" >&2
}

health_url() {
  printf "http://%s:%s/api/health" "$OSGE_HOST" "$OSGE_PORT"
}

cdp_url() {
  printf "http://127.0.0.1:%s/json/version" "$OSGE_CDP_PORT"
}

is_web_ready() {
  curl -fsS "$(health_url)" >/dev/null 2>&1
}

is_cdp_ready() {
  curl -fsS "$(cdp_url)" >/dev/null 2>&1
}

require_runtime() {
  if ! command -v "$OSGE_PYTHON" >/dev/null 2>&1; then
    echo "Missing Python runtime: $OSGE_PYTHON" >&2
    runtime_hint
    exit 1
  fi
  if [[ -n "$OSGE_UVICORN" ]]; then
    if ! command -v "$OSGE_UVICORN" >/dev/null 2>&1; then
      echo "Missing uvicorn command: $OSGE_UVICORN" >&2
      runtime_hint
      exit 1
    fi
  else
    if ! "$OSGE_PYTHON" -c "import uvicorn" >/dev/null 2>&1; then
      echo "Missing uvicorn module for Python runtime: $OSGE_PYTHON" >&2
      runtime_hint
      exit 1
    fi
  fi
}

wait_for_web() {
  local deadline=$((SECONDS + 30))
  until is_web_ready; do
    if (( SECONDS >= deadline )); then
      echo "OSGE Web did not become ready within 30s." >&2
      tail -40 "$OSGE_WEB_LOG" >&2 || true
      exit 1
    fi
    sleep 0.5
  done
}

find_web_pids() {
  ps -eo pid=,args= |
    awk -v port="--port $OSGE_PORT" \
        -v app="web.app:app" \
        'index($0, app) && index($0, port) && $0 !~ /awk -v/ {print $1}'
}

find_cdp_pids() {
  ps -eo pid=,args= |
    awk -v port="--remote-debugging-port=$OSGE_CDP_PORT" \
        -v profile="--user-data-dir=$OSGE_CDP_PROFILE" \
        'index($0, port) && index($0, profile) && $0 !~ /awk -v/ {print $1}'
}

terminate_pids() {
  local label="$1"
  shift
  local pids=("$@")

  if (( ${#pids[@]} == 0 )); then
    echo "$label is not running."
    return 0
  fi

  echo "Stopping $label: ${pids[*]}"
  kill "${pids[@]}" 2>/dev/null || true
  sleep 2

  local alive=()
  local pid
  for pid in "${pids[@]}"; do
    if kill -0 "$pid" 2>/dev/null; then
      alive+=("$pid")
    fi
  done

  if (( ${#alive[@]} > 0 )); then
    echo "Force stopping $label: ${alive[*]}"
    kill -9 "${alive[@]}" 2>/dev/null || true
  fi
}

start_cdp() {
  if is_cdp_ready; then
    echo "Chromium CDP is already ready: $(cdp_url)"
    return 0
  fi

  echo "Starting Chromium CDP on port $OSGE_CDP_PORT..."
  local args=(
    "$OSGE_PYTHON"
    "$PROJECT_ROOT/scripts/start_cdp_chromium.py"
    "--port" "$OSGE_CDP_PORT"
    "--profile-dir" "$OSGE_CDP_PROFILE"
  )
  if [[ "$OSGE_CDP_HEADLESS" == "1" || "$OSGE_CDP_HEADLESS" == "true" ]]; then
    args+=("--headless")
  fi
  "${args[@]}"
}

start_web() {
  require_runtime
  if is_web_ready; then
    echo "OSGE Web is already ready: $(health_url)"
    return 0
  fi

  local old_pid=""
  if [[ -f "$OSGE_WEB_PID" ]]; then
    old_pid="$(cat "$OSGE_WEB_PID" || true)"
  fi
  if [[ -n "$old_pid" ]] && ! kill -0 "$old_pid" 2>/dev/null; then
    rm -f "$OSGE_WEB_PID"
  fi

  echo "Starting OSGE Web on $OSGE_HOST:$OSGE_PORT..."
  if [[ -n "$OSGE_UVICORN" ]]; then
    OSGE_DB="$OSGE_DB" \
    OSGE_CDP_PORT="$OSGE_CDP_PORT" \
    OSGE_CDP_PROFILE="$OSGE_CDP_PROFILE" \
    setsid "$OSGE_UVICORN" web.app:app --host "$OSGE_HOST" --port "$OSGE_PORT" \
      >> "$OSGE_WEB_LOG" 2>&1 < /dev/null &
  else
    OSGE_DB="$OSGE_DB" \
    OSGE_CDP_PORT="$OSGE_CDP_PORT" \
    OSGE_CDP_PROFILE="$OSGE_CDP_PROFILE" \
    setsid "$OSGE_PYTHON" -m uvicorn web.app:app --host "$OSGE_HOST" --port "$OSGE_PORT" \
      >> "$OSGE_WEB_LOG" 2>&1 < /dev/null &
  fi
  echo "$!" > "$OSGE_WEB_PID"
  wait_for_web
  echo "OSGE Web ready: $(health_url)"
}

stop_web() {
  local pids=()
  if [[ -f "$OSGE_WEB_PID" ]]; then
    local pid
    pid="$(cat "$OSGE_WEB_PID" || true)"
    if [[ -n "$pid" ]] && kill -0 "$pid" 2>/dev/null; then
      pids+=("$pid")
    fi
  fi
  while IFS= read -r pid; do
    [[ -n "$pid" ]] && pids+=("$pid")
  done < <(find_web_pids)

  if (( ${#pids[@]} > 0 )); then
    mapfile -t pids < <(printf "%s\n" "${pids[@]}" | sort -nu)
  fi

  terminate_pids "OSGE Web" "${pids[@]}"
  rm -f "$OSGE_WEB_PID"
}

stop_cdp() {
  local pids=()
  while IFS= read -r pid; do
    [[ -n "$pid" ]] && pids+=("$pid")
  done < <(find_cdp_pids)

  terminate_pids "Chromium CDP" "${pids[@]}"
}

start_all() {
  require_runtime
  if [[ "$OSGE_START_CDP" == "1" || "$OSGE_START_CDP" == "true" ]]; then
    start_cdp
  else
    echo "Chromium CDP start is deferred until a crawl job runs. Set OSGE_START_CDP=1 to prestart it."
  fi
  start_web
  echo
  status_all
}

stop_all() {
  stop_web
  stop_cdp
}

status_all() {
  if is_web_ready; then
    echo "OSGE Web: running at $(health_url)"
  else
    echo "OSGE Web: stopped"
  fi

  if is_cdp_ready; then
    echo "Chromium CDP: running at $(cdp_url)"
  else
    echo "Chromium CDP: stopped"
  fi

  if [[ -f "$OSGE_WEB_PID" ]]; then
    echo "OSGE Web PID file: $OSGE_WEB_PID ($(cat "$OSGE_WEB_PID"))"
  fi
  echo "OSGE DB: $OSGE_DB"
  echo "CDP profile: $OSGE_CDP_PROFILE"
}

case "${1:-status}" in
  start)
    start_all
    ;;
  stop)
    stop_all
    ;;
  restart)
    stop_all
    start_all
    ;;
  status)
    status_all
    ;;
  *)
    echo "Usage: $0 {start|stop|restart|status}" >&2
    exit 2
    ;;
esac
