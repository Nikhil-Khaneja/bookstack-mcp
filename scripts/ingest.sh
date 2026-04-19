#!/usr/bin/env bash
# ingest.sh — Bulk-ingest all corpus documents into the running backend.
# Usage: bash scripts/ingest.sh [BASE_URL]
# Defaults to http://localhost:8000
set -euo pipefail

BASE_URL="${1:-http://localhost:8000}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
CORPUS="$ROOT/backend/eval/corpus.jsonl"

log() { echo "[ingest] $*"; }

if [ ! -f "$CORPUS" ]; then
  echo "ERROR: corpus file not found at $CORPUS" >&2
  exit 1
fi

log "Ingesting corpus from $CORPUS → $BASE_URL"
total=0
ok=0
fail=0

while IFS= read -r line; do
  [ -z "$line" ] && continue
  title=$(echo "$line" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d['title'])")
  total=$((total+1))
  http_code=$(curl -s -o /dev/null -w "%{http_code}" \
    -X POST "$BASE_URL/api/v1/ingest" \
    -H "Content-Type: application/json" \
    -d "$line")
  if [ "$http_code" = "200" ] || [ "$http_code" = "201" ]; then
    log "  [OK $http_code] $title"
    ok=$((ok+1))
  else
    log "  [FAIL $http_code] $title"
    fail=$((fail+1))
  fi
done < "$CORPUS"

log ""
log "Done: $ok/$total ingested, $fail failed."
