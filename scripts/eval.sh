#!/usr/bin/env bash
# eval.sh — Run retrieval evaluation and optionally log to MLflow.
# Usage:
#   bash scripts/eval.sh                    # offline mode
#   bash scripts/eval.sh http               # HTTP mode (backend must be running)
#   MLFLOW_TRACKING_URI=http://localhost:5000 bash scripts/eval.sh
set -euo pipefail

MODE="${1:-offline}"
BASE_URL="${2:-http://localhost:8000}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
BACKEND="$ROOT/backend"
VENV="$BACKEND/.venv/bin/activate"
REPORT="$BACKEND/eval/report_$(date +%Y%m%d_%H%M%S).json"

log() { echo "[eval] $*"; }

if [ ! -f "$VENV" ]; then
  echo "ERROR: venv not found at $VENV — run scripts/bootstrap.sh first." >&2
  exit 1
fi

source "$VENV"
cd "$BACKEND"

log "Running eval in $MODE mode…"
if [ "$MODE" = "http" ]; then
  python -m eval.run_eval --mode http --base-url "$BASE_URL" \
    --k 1 3 5 --report "$REPORT"
else
  python -m eval.run_eval --mode offline \
    --k 1 3 5 --report "$REPORT"
fi

log "Report saved: $REPORT"
