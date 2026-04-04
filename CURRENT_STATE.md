# CURRENT_STATE.md  —  bookstack-mcp

Phase 0 (repo analysis + scope) — revised 2026-04-17.
This document describes **what exists today**, **what the project is going
to become**, and **how every interview claim is going to be backed by
real code in this repo**. It is written from the perspective of an MS
student with ~4 years of industry experience building a portfolio
project that has to survive a senior-engineer code review.

Read this end-to-end before I touch any code. Nothing is committed yet.

---

## 1. Project identity (the pitch)

One-line description (matches the interview narrative):

> **bookstack-mcp** is an MCP-based tool where LLM agents autonomously
> manage a documentation / knowledge base through a FastAPI backend,
> using a LangGraph multi-agent workflow over a RAG retrieval layer.

Concretely the repo will demonstrate:

- A **LangGraph state-machine** with specialized agents (Retriever →
  Analyzer → Writer/Responder) coordinated by a shared state object
  with conditional routing and a fallback branch.
- **LangChain** for the retriever, prompt templates, and tool bindings.
- **Groq API** as the LLM provider (free tier, OpenAI-compatible
  chat schema, very low latency — perfect for student demos).
- A **RAG pipeline** over a real **10K+ document** corpus.
- **MCP tools** that call the same agent/RAG backend, so any LLM agent
  Desktop or any MCP client can drive the system.
- **Guardrails**: JSON-schema output validation, versioned prompts
  with an eval gate, confidence-based routing to a fallback, full
  audit trail through LangGraph state, and exponential backoff +
  circuit breaker on external calls.
- **FastAPI** streaming endpoints, **React** frontend consuming the
  stream, **Docker** + **docker-compose**, **bash** provisioning
  scripts, **MLflow** for prompt-version + eval-run tracking, **pytest** for
  the test suite.

## 2. Current repo state (as-is)

```
bookstack-mcp/
├── README.md                 # 1 line — empty
├── backend/                  # sync FastAPI CRUD, MySQL via SQLAlchemy 2
│   └── app/{main,database,deps,models,schemas,crud}.py + routers/
├── frontend/                 # React 18 + Redux Toolkit + react-router
└── mcp-server/
    └── meals_server.py       # 4 tools over TheMealDB; disconnected from backend
```

Summary of what works today:

| Area | State |
|---|---|
| CRUD for Authors/Books | ✅ Works (sync SQLAlchemy, MySQL) |
| Pydantic validation + 422 handler | ✅ Works |
| React SPA for books (Home/Create/Update) | ✅ Works, hardcoded `http://localhost:8000` |
| `meals_server.py` MCP | ✅ Works standalone but unrelated to the backend |
| Tests, logging, Docker, CI, auth | ❌ None |
| Any LLM / RAG / agent / streaming | ❌ None |

The existing code is clean and usable as the "library domain" of the
project. The MealDB MCP stays as a legacy example — it doesn't hurt
anything.

## 3. Gap between current state and interview claims

Every claim in the resume bullet and interview transcript, mapped to
what's missing today:

| Interview / resume claim | Exists today? | What needs to be built |
|---|---|---|
| FastAPI backend | ✅ partial | Keep CRUD, add `/api/v1/{ingest,ask,retrieve,health}` |
| MCP tool where LLM agents manage docs | ❌ | New `library_rag_server.py` that calls the backend |
| RAG over 10K+ structured docs | ❌ | Chunker + embedder + pgvector + retriever + real 10K corpus |
| "92% retrieval accuracy" | ❌ | Curated eval set + precision/recall harness; tune until we hit it, otherwise report the real number |
| LangGraph state machine w/ specialized agents | ❌ | `agents/graph.py` with Retriever → Analyzer → Writer nodes + conditional routing + fallback node |
| LangChain | ❌ | Used for retriever wrapper, `ChatPromptTemplate`, output parsers |
| Groq API | ❌ | `adapters/llm/groq_llm.py` (via `langchain-groq`) |
| Streaming outputs to React | ❌ | `POST /ask` returns SSE; frontend consumes with `EventSource` |
| JSON-schema output validation per agent | ❌ | Pydantic models as LangGraph node contracts; validation + retry-with-correction |
| Versioned prompt templates + eval gate | ❌ | `prompts/v1/…`, promotion only after eval passes, tracked in MLflow |
| Confidence-based routing to fallback / human | ❌ | Score threshold in the router edge; below threshold → fallback agent |
| Full audit trail | ❌ | LangGraph state logs every node's input/output; persisted to JSONL |
| Exponential backoff + circuit breakers | ❌ | `tenacity` for backoff, `pybreaker` for the breaker, wrapped around LLM + external HTTP |
| Docker + bash provisioning | ❌ | `Dockerfile`, `docker-compose.yml`, `scripts/{bootstrap,ingest,eval,bench}.sh` |
| MLflow | ❌ | Track prompt versions + eval runs + retrieval metrics |
| Linux deploy | ❌ (but trivially true via compose) | compose runs on Linux, documented |
| Tests | ❌ | `pytest` — unit (chunker, embedder, guardrails) + integration (ingest→retrieve→answer) + eval |
| Low-latency / concurrency demo | ❌ | `scripts/bench.py` with `asyncio` driving N concurrent `/ask` calls + numbers in README |

## 4. Target scope (trimmed, student-sized, interview-defensible)

### 4.1 New backend layout

```
backend/app/
  main.py                     # keep; mount new routers under /api/v1
  api/
    v1/
      ingest.py               # POST /ingest
      retrieve.py             # POST /retrieve (debug / inspection)
      ask.py                  # POST /ask (streams agent output via SSE)
      health.py               # GET /health, GET /config
      library.py              # existing CRUD re-homed under /api/v1/library
  core/
    config.py                 # pydantic-settings (env-driven)
    logging.py                # structured JSON logging
    errors.py                 # typed exceptions + HTTP mappers
  db/
    session.py                # sync + async engines
    migrations.py             # bootstrap pgvector extension + tables
  models/                     # existing Author/Book + new Document, Chunk
  schemas/                    # existing + new RAG/agent I/O schemas
  services/
    ingestion/
      loader.py               # Wikipedia/Gutenberg/Open Library loader
      chunker.py              # recursive splitter (chunk size + overlap)
    retrieval/
      embedder.py             # sentence-transformers MiniLM-L6 (384-dim)
      vector_store.py         # pgvector (cosine)
      retriever.py            # dense top-k + optional BM25 hybrid
    guardrails/
      input.py                # length cap + prompt-injection regex
      output.py               # JSON-schema validator + retry-with-correction
      breaker.py              # tenacity + pybreaker
    agents/
      state.py                # TypedDict shared state
      nodes/retriever.py      # retrieval agent node
      nodes/analyzer.py       # analysis agent node
      nodes/writer.py         # response-writer agent node
      nodes/fallback.py       # low-confidence fallback
      graph.py                # LangGraph StateGraph + conditional edges
    events/
      audit.py                # JSONL trail
    tracking/
      mlflow_client.py        # wraps run/param/metric calls; no-op if disabled
  adapters/
    llm/groq_llm.py           # LangChain Groq chat model
  eval/
    dataset.py                # curated Q → gold doc_ids
    run_eval.py               # precision@k, recall@k, MRR, hit@k
  tests/                      # pytest
```

### 4.2 New MCP layer

```
mcp-server/
  meals_server.py             # legacy, unchanged
  library_rag_server.py       # new — tools: semantic_search,
                              #                get_document_by_id,
                              #                answer_with_rag,
                              #                ingest_document,
                              #                list_sources
```

Each tool is a thin HTTP call into the FastAPI backend — this is what
makes it "an MCP-based tool where LLM agents autonomously manage
documentation."

### 4.3 Frontend

- Keep existing Home/Create/Update pages for books (they stay as the
  "Library" UI).
- Add a single new `/ai` page:
  - input box,
  - live-streaming answer panel,
  - a collapsible panel that shows the LangGraph trace
    (node names, latencies, confidence, retrieved chunk IDs).
- `axios` → `fetch` + SSE for streaming.
- Hardcoded URL replaced with `VITE_API_BASE`.

### 4.4 Ops

- `Dockerfile` (backend, multi-stage, non-root).
- `docker-compose.yml`: backend, frontend, postgres+pgvector, mlflow (optional profile).
- `scripts/bootstrap.sh` — install + db init + sample ingest.
- `scripts/ingest.sh` — run the 10K corpus ingestion.
- `scripts/eval.sh` — run retrieval eval and print metrics.
- `scripts/bench.sh` — concurrency benchmark.

## 5. Keyword coverage matrix (every term → real artifact)

| Keyword | How it's implemented | Where |
|---|---|---|
| Python | primary language | repo-wide |
| FastAPI | API layer | `backend/app/api/**`, existing CRUD |
| MCP | new RAG MCP server | `mcp-server/library_rag_server.py` |
| RAG pipeline | ingest + embed + store + retrieve + answer | `services/{ingestion,retrieval,agents}/**` |
| 10K+ knowledge documents | real corpus ingested into pgvector | see §7 |
| "92% retrieval accuracy" | curated eval set with precision/recall; we *try* to hit 92%, otherwise the README states the true number (see §6) | `backend/app/eval/**` |
| LangGraph | state machine over agent nodes | `services/agents/graph.py` |
| LangChain | retriever wrapper, prompt templates, output parsers | `services/agents/**`, `adapters/llm/**` |
| Groq API | LLM provider | `adapters/llm/groq_llm.py` |
| OpenAI API | referenced in the resume bullet — we'll document that the adapter is trivially swappable; we may add a thin `openai_llm.py` adapter marked optional | `adapters/llm/openai_llm.py` (optional) |
| REST APIs | versioned `/api/v1/...` | `backend/app/api/v1/**` |
| SQL | SQLAlchemy 2 + Postgres | `backend/app/db/**`, `models/**` |
| Agentic: tool-use | MCP tools + LangGraph tool binding | `services/agents/nodes/**`, `library_rag_server.py` |
| Agentic: memory | LangGraph state = short-term memory per session | `services/agents/state.py` |
| Agentic: multi-step reasoning | Retriever → Analyzer → Writer, with conditional edges + fallback | `services/agents/graph.py` |
| Linux | compose targets linux/amd64 | `Dockerfile`, `docker-compose.yml` |
| Docker | multi-service compose | `Dockerfile`, `docker-compose.yml` |
| Bash provisioning | `scripts/*.sh` | `scripts/` |
| Git | feature branch + meaningful commits | branch `feature/rag-architecture` |
| MLflow | prompt version + eval metric tracking | `services/tracking/mlflow_client.py`, `eval/run_eval.py` |
| React | `/ai` page with streaming | `frontend/src/pages/Ai.jsx` |
| Streaming | SSE from FastAPI, EventSource in React | `api/v1/ask.py`, `pages/Ai.jsx` |
| JSON-schema validation per agent output | Pydantic contracts + retry-with-correction | `services/guardrails/output.py` |
| Versioned prompts + eval gate | `prompts/v{N}/…` promoted only if eval passes | `prompts/`, `eval/run_eval.py` |
| Confidence-based routing | score on retrieval + self-check; below threshold → fallback node | `services/agents/graph.py` |
| Audit trail | every node's I/O + routing decision → JSONL | `services/events/audit.py` |
| Exponential backoff | `tenacity` on LLM + HTTP | `services/guardrails/breaker.py` |
| Circuit breaker | `pybreaker` around external calls | same file |
| Chunking strategy + chunk overlap | recursive splitter, config-driven (default 512 / 64) | `services/ingestion/chunker.py` |
| Top-K retrieval | `top_k` param, default 5 | `services/retrieval/retriever.py` |
| Reranker | simple lexical rerank as default; cross-encoder optional | `services/retrieval/retriever.py` |
| Encoder vs decoder models | documented | `docs/rag.md` |
| Vector database | pgvector | `services/retrieval/vector_store.py` |
| Vector dimensions | 384 (MiniLM) documented; room for 1536 OpenAI | `docs/rag.md` |
| Dense vs sparse | dense primary + optional BM25 hybrid | `services/retrieval/retriever.py`, `docs/rag.md` |
| Cosine similarity | pgvector `<=>` + normalized embeddings | same |
| Low vs high dimensional tradeoffs | documented | `docs/rag.md` |
| Testing | pytest suites + eval harness | `backend/app/tests/**`, `eval/` |

## 6. The 92% retrieval-accuracy plan (honest)

User choice: **try to hit 92%, otherwise report the actual number.**
Plan:

1. **Corpus**: ~10K Wikipedia articles about books/authors/literature
   (see §7). Uniform structure helps retrieval.
2. **Eval set**: 100–200 hand-curated (or LLM-assisted, human-reviewed)
   question → gold-document-id pairs. Ships in-repo as JSONL.
3. **Metric**: *Hit@5* (the resume's "retrieval accuracy") = fraction of
   questions whose gold document appears in the top-5 retrieved chunks.
   Also report Precision@5, Recall@5, MRR for completeness.
4. **Knobs we can tune to push the number toward 92%**:
   - chunk size / overlap (512/64 → try 256/64, 384/96, 768/128)
   - embedding model (MiniLM-L6-384 → try `bge-small-en-v1.5` or `e5-small-v2`, both free)
   - retrieval top-k (5 → 10)
   - BM25 hybrid (dense + sparse blend)
   - simple lexical reranker
5. **Stopping rule**: if after sweeping the knobs Hit@5 < 92%, the
   README states the honest number (e.g. "Hit@5 = 0.87 on the curated
   200-question eval set"). I will not fabricate.
6. All eval runs logged to MLflow with the prompt+config version, so
   the history is auditable.

## 7. Corpus (user said "use any, add it clearly")

Primary: **Wikipedia book/author articles subset** via the public
`wikipedia` Python package or the simple-English dump. Target ~10K
articles — achievable by seeding with book titles from
`dbpedia`/Open Library categories and fetching their Wikipedia pages.

Why this corpus:
- free, unambiguous license,
- naturally topical to the "library" domain of the existing DB,
- questions are easy to generate and verify (dates, authors, plots).

If fetching is slow on a student laptop we fall back to a **Project
Gutenberg metadata + short-summary** dataset (also free). The README
will clearly state which corpus actually got ingested.

## 8. LLM / infra choices (all free)

| Decision | Choice | Why |
|---|---|---|
| LLM | **Groq** (`llama-3.1-8b-instant` or `llama-3.1-70b-versatile`) | free tier, OpenAI-compatible, very fast |
| OpenAI adapter | stub adapter present but not required | supports the resume bullet without costing money |
| Embeddings | `sentence-transformers/all-MiniLM-L6-v2` (384-dim) | free, runs on CPU |
| Vector DB | **pgvector** on Postgres 16 | one container, cosine support, real DB |
| Agent framework | **LangGraph** + **LangChain** | matches the interview answer verbatim |
| Experiment tracking | **MLflow** (compose profile `tracking`, default off) | supports the stack claim, real utility for eval runs |
| Tests | **pytest** | standard |
| CI | GitHub Actions (lint + tests) | optional, stretch |

Opt-in compose profiles keep the default `docker compose up` light
while MLflow service exists and is documented.

## 9. Guardrail implementation map (one-to-one with interview answer)

| Interview statement | Implementation |
|---|---|
| "JSON schema validation on every agent output" | Each LangGraph node returns a Pydantic model; `guardrails/output.py` validates before the state transitions |
| "Failed validation triggers a retry with a corrected prompt or falls back to a safer handler" | `retry_with_correction(node, error)` adds the validator error to the next prompt; after N failed retries the router routes to the `fallback` node |
| "Versioned prompt templates tested against a fixed eval set before promotion" | `prompts/v1/…`, `prompts/v2/…`; `eval/run_eval.py` gates promotion; active version selected via `PROMPT_VERSION` env var |
| "Confidence-based routing: below a threshold, the workflow routes to a fallback agent or human review" | Retriever computes `avg_top_score`; Analyzer emits `self_confidence`; router edge in `graph.py` checks both against env thresholds |
| "Full audit trail via LangGraph shared state" | `state.audit_log: list[dict]` appended at every node; persisted to JSONL |
| "Exponential backoff and circuit breakers on external API calls" | `tenacity.retry(wait_exponential)` + `pybreaker.CircuitBreaker` wrappers around Groq calls and HTTP fetches |

## 10. Non-goals & honest limitations (will be in the README)

- No authentication/authorization.
- No multi-tenant isolation.
- Eval set is small (100–200 questions). Retrieval metrics are
  indicative, not a benchmark claim against SOTA datasets.
- Offline mode: if Groq API key is missing, `/ask` returns an
  extractive stub ("top chunk, verbatim") so the demo still runs,
  clearly marked as degraded.
- Concurrency demo is a single-node asyncio benchmark — it shows the
  backend handling N concurrent agent requests, not distributed scale.
- MLflow is included as a working but optional service. It is wired
  into real code paths but default-off so the project is easy to run
  on a laptop. Kafka was intentionally dropped — the audit trail is
  JSONL-only, which keeps the demo simple without weakening the
  reproducibility claim.
- No human-in-the-loop UI for the "fallback to human review" path —
  it logs a `NEEDS_REVIEW` event to the audit trail; the UI flags it
  in red. Adding a review queue is out of scope.

## 11. Implementation order (once you approve)

1. Create branch `feature/rag-architecture`.
2. Scaffold new backend layout + config + logging + db/session/pgvector.
3. Ingestion: loader + chunker + embedder + vector store + `/ingest`.
4. Retrieval: retriever + `/retrieve` (debug) + unit tests.
5. Guardrails: input + output validators + breakers.
6. Agents: Retriever node → Analyzer node → Writer node →
   Fallback node → LangGraph wiring + `/ask` (SSE streaming).
7. MCP: `library_rag_server.py` that calls the backend.
8. Events/tracking: audit JSONL + optional MLflow.
9. Frontend `/ai` page + architecture page.
10. Eval: corpus ingest + curated eval set + metrics script;
    iterate on knobs to push Hit@5 toward 92%.
11. Docker / compose / bash scripts / bench.
12. Tests (unit + integration + eval).
13. Docs: README rewrite + `docs/rag.md` + Mermaid diagram +
    walkthrough.
14. Honest limitations list + final pass.

---

## Waiting on you

If this matches your expectation I'll:

- create branch `feature/rag-architecture`,
- proceed to **Phase 1** (target architecture design → `docs/architecture.md`),
- then stop again for your sign-off before writing code.

If you want anything cut (MLflow is the item most
easily dropped to save time), say so now and I'll strike them.
