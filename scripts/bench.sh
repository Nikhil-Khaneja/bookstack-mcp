#!/usr/bin/env bash
# bench.sh — Latency benchmark for /retrieve and /ask endpoints.
# Requires: curl, jq, a running backend.
# Usage: bash scripts/bench.sh [BASE_URL] [N_REQUESTS]
set -euo pipefail

BASE_URL="${1:-http://localhost:8000}"
N="${2:-20}"

log() { echo "[bench] $*"; }

QUERIES=(
  "How does multi-head attention work in transformers?"
  "What is RAG and how does it reduce hallucinations?"
  "How does pgvector store embeddings?"
  "What is exponential backoff?"
  "How does LangGraph enable conditional routing?"
)

log "Benchmarking $BASE_URL with $N requests per endpoint…"
log ""

# ── /retrieve latency ───────────────────────────────────────────────
log "=== POST /api/v1/retrieve (top_k=5, rerank=true) ==="
total_ms=0
for i in $(seq 1 "$N"); do
  q="${QUERIES[$((RANDOM % ${#QUERIES[@]}))]}"
  t_start=$(($(date +%s%N)/1000000))
  curl -s -o /dev/null -X POST "$BASE_URL/api/v1/retrieve" \
    -H "Content-Type: application/json" \
    -d "{\"query\":\"$q\",\"top_k\":5,\"rerank\":true}"
  t_end=$(($(date +%s%N)/1000000))
  ms=$((t_end - t_start))
  total_ms=$((total_ms + ms))
done
avg=$((total_ms / N))
log "  Requests: $N | Total: ${total_ms}ms | Avg: ${avg}ms"
log ""

# ── /answer latency (non-streaming) ────────────────────────────────
log "=== POST /api/v1/answer (non-streaming) ==="
total_ms=0
for i in $(seq 1 "$N"); do
  q="${QUERIES[$((RANDOM % ${#QUERIES[@]}))]}"
  t_start=$(($(date +%s%N)/1000000))
  curl -s -o /dev/null -X POST "$BASE_URL/api/v1/answer" \
    -H "Content-Type: application/json" \
    -d "{\"query\":\"$q\",\"top_k\":5}"
  t_end=$(($(date +%s%N)/1000000))
  ms=$((t_end - t_start))
  total_ms=$((total_ms + ms))
done
avg=$((total_ms / N))
log "  Requests: $N | Total: ${total_ms}ms | Avg: ${avg}ms"
log ""

log "Benchmark complete."
