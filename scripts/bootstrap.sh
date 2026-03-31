#!/usr/bin/env bash
# bootstrap.sh — one-shot local dev setup
# Usage: bash scripts/bootstrap.sh
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
BACKEND="$ROOT/backend"
FRONTEND="$ROOT/frontend"
MCP="$ROOT/mcp-server"

log() { echo "[bootstrap] $*"; }

# ── 1. Python venv ───────────────────────────────────────────────────
log "Creating Python virtual environment…"
python3 -m venv "$BACKEND/.venv"
source "$BACKEND/.venv/bin/activate"
pip install --quiet --upgrade pip
pip install --quiet -r "$BACKEND/requirements.txt"
log "Backend deps installed."

# ── 2. MCP server deps ───────────────────────────────────────────────
log "Installing MCP server deps…"
pip install --quiet -r "$MCP/requirements.txt"

# ── 3. .env file ────────────────────────────────────────────────────
if [ ! -f "$BACKEND/.env" ]; then
  log "Copying .env.example → .env (edit to add GROQ_API_KEY)"
  cp "$BACKEND/.env.example" "$BACKEND/.env"
else
  log ".env already exists — skipping."
fi

# ── 4. Frontend deps ─────────────────────────────────────────────────
log "Installing frontend npm deps…"
cd "$FRONTEND"
npm install --silent
cd "$ROOT"

# ── 5. Pre-download embedding model ─────────────────────────────────
log "Pre-downloading all-MiniLM-L6-v2 (may take a moment)…"
source "$BACKEND/.venv/bin/activate"
python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('sentence-transformers/all-MiniLM-L6-v2')" \
  && log "Embedding model cached." \
  || log "WARNING: model download failed; HashingEmbedder fallback will be used."

log ""
log "Bootstrap complete! Next steps:"
log "  1. Edit backend/.env and set GROQ_API_KEY=gsk_..."
log "  2. Start Postgres:   docker compose up postgres -d"
log "  3. Start backend:    cd backend && source .venv/bin/activate && uvicorn app.main:app --reload"
log "  4. Start frontend:   cd frontend && npm run dev"
log "  5. Run eval:         cd backend && python -m eval.run_eval"
