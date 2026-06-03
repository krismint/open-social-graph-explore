#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

SAMPLE_DB="${OSGE_SAMPLE_DB:-$PROJECT_ROOT/database/osge_sample.db}"
if [[ ! -f "$SAMPLE_DB" ]]; then
  echo "Missing sample database: $SAMPLE_DB" >&2
  exit 1
fi

export OSGE_DB="$SAMPLE_DB"
export OSGE_PORT="${OSGE_PORT:-8011}"
export OSGE_WEB_LOG="${OSGE_WEB_LOG:-$PROJECT_ROOT/logs/osge_sample_web.log}"
export OSGE_WEB_PID="${OSGE_WEB_PID:-$PROJECT_ROOT/logs/osge_sample_web.pid}"

if [[ -z "${OSGE_PYTHON:-}" && -x "$PROJECT_ROOT/.venv/bin/python" ]]; then
  export OSGE_PYTHON="$PROJECT_ROOT/.venv/bin/python"
fi

exec "$PROJECT_ROOT/scripts/osge_service.sh" "${1:-status}"
