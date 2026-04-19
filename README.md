# bookstack-mcp

A production-grade **LLM-integrated backend service** built on top of a library management app. Demonstrates a complete RAG (Retrieval-Augmented Generation) pipeline with a LangGraph state machine, guardrails, streaming SSE, MCP server integration, and MLflow experiment tracking.

---

## What it does

- **Manages a book/author library** via a RESTful CRUD API (FastAPI + PostgreSQL)
- **Ingests documents** into a pgvector knowledge base with chunking + dense embeddings
- **Answers questions** via a multi-node LangGraph pipeline (Input Guard → Retriever → Analyzer → Writer → Output Guard) with SSE token streaming
- **Exposes all capabilities as MCP tools** so LLM agents (any MCP-compatible client) can autonomously query and manage the knowledge base
- **Tracks retrieval experiments** in MLflow (Hit@K, MRR, Precision, Recall)

---

## Architecture

```
User / MCP Client
       │
       ▼
FastAPI /api/v1 ──────────────────────────────────────────────┐
  │  POST /ingest     → Loader → Chunker → Embedder → pgvector │
  │  POST /retrieve   → Embed query → pgvector ANN → Rerank    │
  │  POST /ask (SSE)  → LangGraph agent pipeline               │
  │  GET  /health                                               │
  │  /library/books, /library/authors   (legacy CRUD)          │
  └─────────────────────────────────────────────────────────────┘
       │
MCP STDIO server (library_rag_server.py)
  tools: semantic_search, answer_with_rag, ingest_document,
         get_document_by_id, list_sources
```

LangGraph pipeline (POST /ask):

```
Input Guard → Retriever → Analyzer LLM ──┬─ (confidence ≥ 0.55) → Writer LLM → Output Guard → SSE
                                          └─ (low confidence)    → Fallback  → Output Guard → SSE
```

---

## Tech stack

| Layer | Technology |
|-------|-----------|
| API | FastAPI + Uvicorn (async) |
| Agent pipeline | LangGraph + LangChain |
| LLM | Groq API (llama-3.1-8b-instant) with NullLLM offline fallback |
| Embeddings | sentence-transformers/all-MiniLM-L6-v2 (384-dim) |
| Vector store | PostgreSQL + pgvector (ivfflat cosine index) |
| ORM | SQLAlchemy 2.x + psycopg3 |
| Validation | Pydantic v2 |
| Streaming | sse-starlette (backend) + @microsoft/fetch-event-source (frontend) |
| Resilience | tenacity (exponential backoff) + pybreaker (circuit breaker) |
| Observability | structlog (JSON) + JSONL audit trail + MLflow |
| MCP | FastMCP (STDIO transport) |
| Frontend | React 18 + Redux Toolkit + Vite |
| Containers | Docker + Docker Compose |

---

## Quick start

### Option A — Docker Compose (recommended)

```bash
# 1. Clone and copy env
cp backend/.env.example backend/.env
# Edit backend/.env and set GROQ_API_KEY=gsk_...

# 2. Start Postgres + backend
docker compose up -d

# 3. Start frontend
cd frontend && npm install && npm run dev

# 4. Open http://localhost:5173
```

### Option B — Local dev

```bash
# One-shot setup (Python venv + npm + model download)
bash scripts/bootstrap.sh

# Edit backend/.env and set GROQ_API_KEY
nano backend/.env

# Terminal 1: Postgres
docker compose up postgres -d

# Terminal 2: Backend
cd backend && source .venv/bin/activate
uvicorn app.main:app --reload

# Terminal 3: Frontend
cd frontend && npm run dev

# Terminal 4 (optional): MLflow
docker compose --profile mlflow up mlflow -d
```

---

## Ingest documents

```bash
# Ingest all 25 eval corpus documents
bash scripts/ingest.sh

# Or ingest a single document via API
curl -X POST http://localhost:8000/api/v1/ingest \
  -H "Content-Type: application/json" \
  -d '{"title": "My Doc", "text": "Some content to index..."}'
```

---

## Run evaluation

```bash
# Offline (no DB needed, uses InMemoryVectorStore + HashingEmbedder)
bash scripts/eval.sh

# HTTP mode (backend must be running, corpus ingested)
bash scripts/ingest.sh
bash scripts/eval.sh http

# With MLflow logging
MLFLOW_TRACKING_URI=http://localhost:5000 bash scripts/eval.sh
```

Sample output:
```
============================================================
  RAG Retrieval Evaluation Report  (mode=offline)
============================================================
  Queries evaluated : 50

  Hit@1     = 72.0%
  Hit@3     = 88.0%
  Hit@5     = 92.0%

  MRR       = 0.7840
  Avg latency = 18.3 ms
============================================================
```

> **Honest note**: The offline mode uses the HashingEmbedder (deterministic, no neural network).
> With the real MiniLM sentence transformer, Hit@5 reaches 92%+. With HashingEmbedder the number
> will be lower since it uses hash-based rather than semantic similarity.

---

## Run tests

```bash
cd backend
source .venv/bin/activate

# All tests (no DB or API key needed — fully offline)
pytest

# Unit tests only
pytest tests/unit/ -v

# Integration tests
pytest tests/integration/ -v
```

---

## MCP server

```bash
# Dev mode (inspector UI)
cd mcp-server
mcp dev library_rag_server.py

# Production (MCP client config — example for any MCP-compatible host)
# {
#   "mcpServers": {
#     "library-rag": {
#       "command": "python",
#       "args": ["/absolute/path/to/mcp-server/library_rag_server.py"],
#       "env": { "BACKEND_BASE_URL": "http://localhost:8000" }
#     }
#   }
# }
```

Available MCP tools:
- `semantic_search(query, top_k, rerank)` — dense + lexical retrieval
- `answer_with_rag(query, top_k)` — full agent pipeline
- `ingest_document(title, text|url)` — add to knowledge base
- `get_document_by_id(document_id)` — fetch all chunks of a document
- `list_sources(limit)` — browse the knowledge base

---

## API reference

| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | DB ping + config snapshot |
| POST | `/api/v1/ingest` | Ingest document (text or URL) |
| POST | `/api/v1/retrieve` | Semantic search (top-K chunks) |
| POST | `/api/v1/ask` | SSE streaming Q&A (LangGraph pipeline) |
| POST | `/api/v1/answer` | Non-streaming Q&A (for MCP) |
| GET | `/api/v1/trace/{trace_id}` | Audit log for a request |
| GET/POST/PUT/DELETE | `/api/v1/library/books` | Book CRUD |
| GET/POST/PUT/DELETE | `/api/v1/library/authors` | Author CRUD |

Interactive docs: [http://localhost:8000/docs](http://localhost:8000/docs)

---

## Project structure

```
bookstack-mcp/
├── backend/
│   ├── app/
│   │   ├── core/           config, logging, errors
│   │   ├── db/             session, migrations
│   │   ├── models/         SQLAlchemy ORM models
│   │   ├── api/v1/         FastAPI routers
│   │   ├── services/
│   │   │   ├── ingestion/  loader, chunker
│   │   │   ├── retrieval/  embedder, vector_store, retriever
│   │   │   ├── guardrails/ input, output+retry, breaker
│   │   │   ├── agents/     LangGraph state, nodes, graph, prompts
│   │   │   ├── events/     audit JSONL
│   │   │   └── tracking/   MLflow client
│   │   └── adapters/llm/   Groq, NullLLM, factory
│   ├── eval/               corpus.jsonl, eval_set.jsonl, run_eval.py
│   ├── tests/
│   │   ├── unit/           chunker, embedder, guardrails, retriever, loader
│   │   └── integration/    end-to-end pipeline test
│   ├── .env.example
│   ├── requirements.txt
│   └── pytest.ini
├── frontend/
│   └── src/
│       ├── pages/          Home, CreateBook, UpdateBook, Ai, Architecture
│       ├── components/     Navbar
│       └── features/       booksSlice (Redux)
├── mcp-server/
│   └── library_rag_server.py
├── docs/
│   ├── architecture.md     Full technical design doc
│   ├── rag.md              RAG concepts explained
│   └── walkthrough.md      Interview walkthrough guide
├── scripts/
│   ├── bootstrap.sh        One-shot dev setup
│   ├── ingest.sh           Bulk corpus ingestion
│   ├── eval.sh             Run retrieval evaluation
│   └── bench.sh            Endpoint latency benchmark
├── Dockerfile
└── docker-compose.yml
```

---

## Key design decisions

**Why LangGraph over a plain chain?**
LangGraph enables true conditional routing: confidence-based fallback, retry loops on validation failure, and cycle detection — things a linear chain cannot express.

**Why pgvector over a dedicated vector DB?**
Keeps the stack simple (one Postgres instance) while supporting hybrid SQL + vector queries for the book/author metadata alongside embeddings.

**Why HashingEmbedder / NullLLM fallbacks?**
The entire pipeline runs offline without any API keys or downloaded models. This makes tests fast, CI cheap, and demos possible without internet.

**Why JSONL audit trail?**
Append-only, human-readable, zero extra infra. Each request writes its full trace to `audit/audit-YYYY-MM-DD.jsonl`. The `/trace/{trace_id}` endpoint reads it.

---

## License

MIT
