# Architecture — bookstack-mcp

Phase 1 output. This document describes the target architecture before
any implementation begins. It answers three questions:

1. **What are the components and what is each responsible for?**
2. **How does data flow between them?**
3. **What are the interfaces (contracts) between modules?**

Terminology used throughout:

- **Agent node** — one step of the LangGraph state machine (a Python
  function that receives the shared state, does one focused thing,
  returns a state patch).
- **Adapter** — the thinnest possible wrapper around an external
  dependency (LLM, vector store, embedding model). Adapters implement
  a `Protocol` so alternative implementations can be dropped in.
- **Service** — business logic that composes adapters (e.g. the
  retrieval service composes the embedder + vector store).

---

## 1. Top-level picture

```mermaid
flowchart LR
    subgraph Clients
        UI[React /ai page]
        MCPC[MCP Client<br/>MCP Client]
        CURL[cURL / scripts]
    end

    subgraph API["FastAPI (backend/app)"]
        direction TB
        ING[POST /api/v1/ingest]
        RET[POST /api/v1/retrieve]
        ASK[POST /api/v1/ask<br/>SSE stream]
        HEA[GET /api/v1/health<br/>GET /api/v1/config]
        LIB[/api/v1/library/*<br/>legacy CRUD/]
    end

    subgraph MCPS["MCP Server"]
        direction TB
        LRS[library_rag_server.py]
        MDS[meals_server.py<br/>legacy demo]
    end

    subgraph Core["Services (backend/app/services)"]
        direction TB
        ING_S[ingestion<br/>loader + chunker]
        RET_S[retrieval<br/>embedder + pgvector + retriever]
        AG_S[agents<br/>LangGraph state machine]
        GR_S[guardrails<br/>input + output + breaker]
        EV_S[events<br/>audit JSONL]
        TR_S[tracking<br/>MLflow optional]
    end

    subgraph Adapters["Adapters"]
        LLM[adapters/llm<br/>Groq]
        EMB[sentence-transformers]
    end

    subgraph Storage
        PG[(Postgres + pgvector)]
        FS[(audit/*.jsonl)]
        ML[(MLflow tracking dir)]
    end

    UI -->|fetch + EventSource| ASK
    UI --> RET
    UI --> LIB
    CURL --> API
    MCPC -->|JSON-RPC stdio| LRS
    LRS -->|HTTP| API

    ING --> ING_S
    RET --> RET_S
    ASK --> AG_S

    AG_S --> RET_S
    AG_S --> LLM
    AG_S --> GR_S
    AG_S --> EV_S
    AG_S --> TR_S

    ING_S --> EMB
    ING_S --> PG
    RET_S --> EMB
    RET_S --> PG
    EV_S --> FS
    TR_S --> ML
    LLM -.->|Groq HTTPS| Internet((Groq API))
```

---

## 2. Layered module map

```
backend/app/
├── main.py                ── FastAPI app factory, lifespan, router mounts
├── api/v1/
│   ├── ingest.py          ── POST /ingest
│   ├── retrieve.py        ── POST /retrieve
│   ├── ask.py             ── POST /ask (SSE)
│   ├── health.py          ── GET /health, /config
│   └── library.py         ── existing CRUD rehomed here
├── core/
│   ├── config.py          ── pydantic-settings (Settings)
│   ├── logging.py         ── JSON structured logging
│   └── errors.py          ── typed exceptions → HTTPException
├── db/
│   ├── session.py         ── sync + async SQLAlchemy engines
│   └── migrations.py      ── bootstrap CREATE EXTENSION vector + tables
├── models/                ── Author, Book, Document, Chunk
├── schemas/               ── Pydantic IO schemas (per endpoint + per node)
├── services/
│   ├── ingestion/
│   │   ├── loader.py      ── file/URL loaders
│   │   └── chunker.py     ── recursive char splitter
│   ├── retrieval/
│   │   ├── embedder.py    ── EmbedderProtocol + MiniLM impl
│   │   ├── vector_store.py── VectorStoreProtocol + pgvector impl
│   │   └── retriever.py   ── dense top-k (+ optional BM25 hybrid/rerank)
│   ├── guardrails/
│   │   ├── input.py       ── length cap, prompt-injection regex
│   │   ├── output.py      ── JSON-schema validation + retry-with-correction
│   │   └── breaker.py     ── tenacity + pybreaker
│   ├── agents/
│   │   ├── state.py       ── AgentState (TypedDict)
│   │   ├── prompts/       ── versioned prompt templates
│   │   ├── nodes/
│   │   │   ├── retriever.py
│   │   │   ├── analyzer.py
│   │   │   ├── writer.py
│   │   │   └── fallback.py
│   │   └── graph.py       ── StateGraph + conditional edges + compile()
│   ├── events/
│   │   └── audit.py       ── JSONL appender keyed by trace_id
│   └── tracking/
│       └── mlflow_client.py── no-op unless MLFLOW_TRACKING_URI set
├── adapters/
│   └── llm/
│       ├── base.py        ── ChatLLM protocol
│       ├── groq_llm.py    ── langchain-groq wrapper
│       └── null_llm.py    ── extractive stub for offline demos
├── eval/
│   ├── dataset.py         ── load curated QA jsonl
│   └── run_eval.py        ── Hit@k, Precision@k, Recall@k, MRR
└── tests/                 ── unit + integration

mcp-server/
├── meals_server.py        ── unchanged legacy
└── library_rag_server.py  ── HTTP-backed MCP tools over FastAPI

frontend/src/
├── pages/
│   ├── Home.jsx, CreateBook.jsx, UpdateBook.jsx   ── existing
│   ├── Ai.jsx             ── new: query + streaming answer + trace
│   └── Architecture.jsx   ── new: embeds the Mermaid diagram
└── features/
    └── aiSlice.js         ── new: SSE state handling

data/
└── seed/                  ── starter corpus (≤100 docs) so tests run offline

scripts/
├── bootstrap.sh
├── ingest.sh              ── pulls Wikipedia subset, chunks, embeds, stores
├── eval.sh
└── bench.sh               ── asyncio concurrency benchmark
```

---

## 3. Component responsibilities

### 3.1 `api/v1/` — HTTP surface

| Endpoint | Method | Responsibility | Error modes |
|---|---|---|---|
| `/ingest` | POST | Accept a document (text or URL), chunk, embed, upsert to pgvector. Returns `document_id` and chunk count. | 400 (empty/oversize), 502 (embedding failure) |
| `/retrieve` | POST | Debug-only: dense top-k retrieval with scores. Returns chunks + metadata. | 400 (bad params) |
| `/ask` | POST | Execute the LangGraph agent and **stream** tokens + node events via SSE. | 400, 429 (breaker open), 500 |
| `/health` | GET | Liveness + DB + LLM reachability. | — |
| `/config` | GET | Non-secret config snapshot (model names, chunk params, top-k). | — |
| `/library/*` | — | Existing CRUD, re-mounted. | unchanged |

### 3.2 `core/`

- **`config.Settings`** (pydantic-settings). Single source of truth:
  DB URLs, Groq key, MiniLM model id, chunk size/overlap, top-k,
  confidence thresholds, prompt version, MLflow URI.
- **`logging`** — JSON log lines keyed by `trace_id`; `trace_id` is
  generated at `/ask` entry and propagated through the state machine.
- **`errors`** — `GuardrailViolation`, `RetrievalEmpty`,
  `ValidationRetryExceeded`, `BreakerOpen`, `UpstreamTimeout`. Each
  maps to a deterministic HTTP status.

### 3.3 `db/`

- One Postgres instance, two schemas would be overkill — we use the
  default `public` schema.
- Tables:
  - `authors`, `books` — existing, unchanged.
  - `documents(id, source_type, source_uri, title, created_at, meta jsonb)`
  - `chunks(id, document_id, ord, text, token_count, embedding vector(384), meta jsonb)`
- `CREATE EXTENSION IF NOT EXISTS vector` runs in the lifespan hook.
- Index: `CREATE INDEX chunks_embedding_idx ON chunks USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100)`.

### 3.4 `services/ingestion/`

- **`loader`** — pluggable sources. V1 loaders: plain text, local file,
  Wikipedia-by-title. Async where I/O bound.
- **`chunker`** — recursive character splitter. Splits on `\n\n`, `\n`,
  `. `, then hard character count. Returns `List[ChunkDraft]` with
  `text, token_count, ord, meta`.
- Contract: `async def ingest(doc: DocumentInput) -> IngestResult`.

### 3.5 `services/retrieval/`

- **`EmbedderProtocol`** — `async encode(texts: list[str]) -> list[list[float]]`.
  Declares `dim: int`. Default impl: `all-MiniLM-L6-v2` (384-dim).
  Normalizes vectors to unit length so cosine == dot product.
- **`VectorStoreProtocol`** — `async upsert(items)`, `async search(query_vec, top_k, filters) -> list[Hit]`.
  Default: pgvector with `<=>` (cosine distance).
- **`retriever.retrieve(query, top_k=5, hybrid=False, rerank=False) -> list[Hit]`**
  composes the two. Optional BM25 union + lexical reranker gated
  behind flags.
- **Invariants** (enforced by unit tests): returned hits are sorted
  descending by similarity; scores in `[0, 1]`; `top_k` never violated.

### 3.6 `services/guardrails/`

- **`input.validate(user_query) -> ValidatedQuery`** — max length, empty
  check, regex set for obvious prompt-injection strings (`ignore previous`,
  `system:`, `you are now`, role-swap patterns). Raises
  `GuardrailViolation` on fail.
- **`output.validate(raw: str, schema: type[BaseModel]) -> BaseModel`** —
  tries `model_validate_json`; on failure, `retry_with_correction`
  composes a correction prompt containing the Pydantic error and asks
  the LLM to re-emit. Retries bounded by `OUTPUT_VALIDATION_MAX_RETRIES`
  (default 2). Exhausting retries raises `ValidationRetryExceeded`,
  which the router handles by routing to `fallback`.
- **`breaker`** — `tenacity.retry(wait_exponential(multiplier=1, max=8), stop=stop_after_attempt(4))` +
  `pybreaker.CircuitBreaker(fail_max=5, reset_timeout=30)`. Wraps every
  external network call (LLM, embeddings if remote, HTTP loaders).

### 3.7 `services/agents/` — LangGraph state machine

#### State

```python
class AgentState(TypedDict, total=False):
    trace_id: str
    query: str
    retrieved: list[Hit]          # set by retriever node
    avg_top_score: float          # ↑ for routing
    analysis: AnalysisOutput      # set by analyzer node
    self_confidence: float        # ↑ for routing
    answer: str                   # streamed incrementally by writer
    citations: list[int]          # chunk ids used
    needs_review: bool            # set by fallback
    audit_log: list[AuditEvent]   # appended by every node
    errors: list[str]
```

#### Nodes

| Node | Input (from state) | Output contract (Pydantic) | Behavior |
|---|---|---|---|
| `retriever` | `query` | `RetrieverOutput{hits, avg_top_score}` | Calls retrieval service, writes `retrieved` + `avg_top_score` |
| `analyzer` | `query`, `retrieved` | `AnalyzerOutput{summary, relevance_rationale, self_confidence in [0,1]}` | LLM prompt produces JSON; output guardrail validates |
| `writer` | `query`, `retrieved`, `analysis` | `WriterOutput{answer, citations}` (streamed) | LLM streams tokens; citations validated against retrieved ids |
| `fallback` | full state + reason | `WriterOutput` with safe, extractive answer | Returns top chunk verbatim with citation; sets `needs_review=True` |

#### Edges (conditional routing)

```mermaid
flowchart TD
    start([START]) --> in[input guardrail]
    in -->|valid| R[retriever]
    in -->|invalid| F[fallback]
    R -->|avg_top_score >= RETRIEVAL_CONF_THRESHOLD| A[analyzer]
    R -->|below threshold<br/>or empty retrieval| F
    A -->|self_confidence >= ANALYZER_CONF_THRESHOLD<br/>AND validation ok| W[writer]
    A -->|below threshold<br/>OR validation failed after retries| F
    W --> out[output guardrail]
    F --> out
    out --> done([END])
```

Thresholds are env-configurable (`RETRIEVAL_CONF_THRESHOLD=0.25`,
`ANALYZER_CONF_THRESHOLD=0.55` as starting defaults — to be tuned
during eval).

#### Audit log

Every node appends an `AuditEvent`:

```python
class AuditEvent(TypedDict):
    trace_id: str
    node: Literal["retriever","analyzer","writer","fallback","guard"]
    ts: str
    input_digest: str        # sha256 of input subset
    output_digest: str
    decision: str | None     # routing label chosen after this node
    confidence: float | None
    error: str | None
    duration_ms: int
```

The full list is returned in the final `/ask` SSE `event: done` frame
and also appended to `audit/<YYYY-MM-DD>.jsonl`.

#### Prompt versioning

- `services/agents/prompts/v1/{analyzer,writer,fallback}.md`.
- Active version picked by `PROMPT_VERSION` env var.
- Promotion rule: a new `vN+1` may only be set as default after
  `eval/run_eval.py` shows no regression on the fixed QA set. MLflow
  records the run id, version, and metric deltas.

### 3.8 `services/events/audit.py`

- Single responsibility: append `AuditEvent` to a daily JSONL file.
- Interface: `append(event: AuditEvent) -> None` (thread-safe via
  `asyncio.Lock`).
- No Kafka. The SSE `event: trace` frame carries live telemetry to
  the UI; the JSONL is the durable record.

### 3.9 `services/tracking/mlflow_client.py`

- Thin facade: `start_run`, `log_param`, `log_metric`, `end_run`.
- Becomes a no-op if `MLFLOW_TRACKING_URI` is unset — the rest of
  the code never branches on "is MLflow enabled?".
- Used by `eval/run_eval.py` and by the prompt-version promotion gate.

### 3.10 `adapters/llm/`

- `ChatLLM` protocol:
  ```python
  class ChatLLM(Protocol):
      name: str
      async def complete(self, messages: list[Message], **kw) -> str: ...
      async def stream(self, messages: list[Message], **kw) -> AsyncIterator[str]: ...
  ```
- `groq_llm.GroqLLM` — wraps `langchain-groq`'s `ChatGroq`. Supports
  JSON mode and tool binding.
- `null_llm.NullLLM` — used when `GROQ_API_KEY` is unset: returns the
  top retrieved chunk verbatim. Clearly marks the response as
  `[offline-extractive]` in the audit trail.

### 3.11 MCP server (`mcp-server/library_rag_server.py`)

Implements five MCP tools, each a thin HTTP client into FastAPI:

| Tool | Backend call |
|---|---|
| `semantic_search(query, top_k)` | `POST /api/v1/retrieve` |
| `get_document_by_id(document_id)` | `GET /api/v1/library/documents/{id}` |
| `answer_with_rag(query)` | `POST /api/v1/ask` (non-streamed variant returning final state) |
| `ingest_document(title, text)` | `POST /api/v1/ingest` |
| `list_sources()` | `GET /api/v1/library/documents?limit=100` |

This is what makes the phrase "LLM agents autonomously manage
documentation" true: MCP Client (or any MCP client) calls these
tools, which mutate and read the same backend the web UI uses.

### 3.12 Frontend

- `pages/Ai.jsx` consumes `/ask` via `fetch` + `EventSource`. Three
  panels:
  1. **Answer** — live-streamed tokens.
  2. **Retrieved chunks** — table of hit id, source, score, excerpt.
  3. **Trace** — collapsible list of `AuditEvent`s with node name,
     latency, confidence, decision.
- `pages/Architecture.jsx` — static page embedding the Mermaid from
  this doc (rendered client-side via `mermaid` npm package).
- `features/aiSlice.js` handles SSE lifecycle (`connecting`,
  `streaming`, `done`, `error`).

---

## 4. Data flow (request lifecycle of `POST /ask`)

```mermaid
sequenceDiagram
    autonumber
    participant UI as React /ai
    participant API as FastAPI /ask
    participant G as graph.compile()
    participant IN as input guardrail
    participant R as retriever node
    participant A as analyzer node
    participant W as writer node
    participant F as fallback node
    participant OUT as output guardrail
    participant AU as audit JSONL

    UI->>API: POST /ask { query }
    API->>API: generate trace_id, SSE open
    API->>G: ainvoke(state={query, trace_id})
    G->>IN: validate(query)
    IN-->>G: ok | violation→F
    G->>R: retrieve(query)
    R->>AU: append(retriever event)
    alt avg_top_score >= threshold
      G->>A: analyze(query, retrieved)
      A->>AU: append(analyzer event)
      alt self_confidence >= threshold AND output valid
        G->>W: stream(query, retrieved, analysis)
        loop for each token
          W-->>API: token
          API-->>UI: event: token {text}
        end
        W->>AU: append(writer event)
      else
        G->>F: fallback(reason=low_confidence)
        F-->>API: safe answer
        API-->>UI: event: token ... (non-streamed)
        F->>AU: append(fallback event, needs_review=true)
      end
    else
      G->>F: fallback(reason=retrieval_empty)
    end
    G->>OUT: validate(answer)
    OUT-->>API: validated
    API-->>UI: event: trace {audit_log}
    API-->>UI: event: done {citations, needs_review}
```

SSE event schema:

| event | data | when |
|---|---|---|
| `open` | `{trace_id}` | connection accepted |
| `node_start` | `{node, ts}` | each node entry |
| `node_end` | `{node, ms, decision}` | each node exit |
| `token` | `{text}` | writer/fallback streaming |
| `trace` | `{audit_log[]}` | just before done |
| `done` | `{citations, needs_review, error?}` | final |
| `error` | `{code, message}` | terminal failure |

## 5. Request lifecycle of `POST /ingest`

```mermaid
sequenceDiagram
    participant C as Client
    participant I as /ingest
    participant L as loader
    participant CH as chunker
    participant E as embedder
    participant V as pgvector
    C->>I: { title, text | url }
    I->>L: load(source)
    L-->>I: DocumentDraft
    I->>CH: chunk(text, size, overlap)
    CH-->>I: list[ChunkDraft]
    I->>E: encode([chunk.text ...])
    E-->>I: list[vector]
    I->>V: upsert(document, chunks, vectors)
    V-->>I: document_id, n_chunks
    I-->>C: 201 { document_id, n_chunks }
```

Idempotency: same `source_uri` + content hash → update in place.

## 6. Interfaces (the contracts that matter)

### 6.1 Python protocols

```python
class EmbedderProtocol(Protocol):
    name: str
    dim: int
    async def encode(self, texts: list[str]) -> list[list[float]]: ...

class VectorStoreProtocol(Protocol):
    async def upsert(self, items: list[VectorRow]) -> None: ...
    async def search(self, q: list[float], top_k: int,
                     filters: dict | None = None) -> list[Hit]: ...

class ChatLLM(Protocol):
    name: str
    async def complete(self, messages: list[Message], **kw) -> str: ...
    async def stream(self, messages: list[Message], **kw) -> AsyncIterator[str]: ...
```

### 6.2 Pydantic IO schemas (per endpoint)

```python
class IngestRequest(BaseModel):
    title: str
    text: str | None = None
    url: HttpUrl | None = None
    meta: dict[str, Any] = {}

class RetrieveRequest(BaseModel):
    query: str = Field(min_length=1, max_length=2000)
    top_k: int = Field(default=5, ge=1, le=50)
    hybrid: bool = False

class AskRequest(BaseModel):
    query: str = Field(min_length=1, max_length=2000)
    top_k: int = Field(default=5, ge=1, le=50)
    session_id: str | None = None
```

### 6.3 Per-node contracts (feed the output guardrail)

```python
class RetrieverOutput(BaseModel):
    hits: list[Hit]
    avg_top_score: float

class AnalyzerOutput(BaseModel):
    summary: str
    relevance_rationale: str
    self_confidence: float = Field(ge=0.0, le=1.0)

class WriterOutput(BaseModel):
    answer: str = Field(min_length=1)
    citations: list[int]   # chunk ids; must ⊆ retrieved ids
```

Each LLM call for analyzer/writer uses the schema's JSON output format
(Groq JSON mode). The output guardrail deserializes into the Pydantic
model; on failure it retries with the validation error appended to the
prompt.

## 7. Configuration

All config is centralized in `core/config.Settings` and driven by
environment variables. Defaults are safe and let the project run
on a laptop with no API keys (degraded to extractive mode).

| Setting | Env var | Default |
|---|---|---|
| Database URL | `DATABASE_URL` | `postgresql+psycopg://postgres:postgres@localhost:5432/bookstack` |
| Groq API key | `GROQ_API_KEY` | unset → NullLLM |
| Groq model | `GROQ_MODEL` | `llama-3.1-8b-instant` |
| Embedding model | `EMBED_MODEL` | `sentence-transformers/all-MiniLM-L6-v2` |
| Embedding dim | `EMBED_DIM` | `384` |
| Chunk size / overlap | `CHUNK_SIZE`, `CHUNK_OVERLAP` | `512` / `64` |
| Top-k default | `TOP_K` | `5` |
| Retrieval confidence threshold | `RETRIEVAL_CONF_THRESHOLD` | `0.25` |
| Analyzer confidence threshold | `ANALYZER_CONF_THRESHOLD` | `0.55` |
| Output validation retries | `OUTPUT_VALIDATION_MAX_RETRIES` | `2` |
| Prompt version | `PROMPT_VERSION` | `v1` |
| MLflow URI | `MLFLOW_TRACKING_URI` | unset → no-op |
| Audit log dir | `AUDIT_LOG_DIR` | `./audit` |
| CORS origins | `CORS_ORIGINS` | `http://localhost:5173,http://localhost:3000` |

## 8. Cross-cutting concerns

- **Async everywhere network is touched.** DB calls use the async
  SQLAlchemy engine. CRUD kept sync for parity with existing code —
  they are fast and local.
- **`trace_id`** is generated at `/ask` entry and flows through
  LangGraph state, every audit event, every log line, and the SSE
  frames back to the UI. This is how we "trace failures back to
  specific agent nodes" (interview claim).
- **Retries vs breakers** — `tenacity` retries transient failures per
  call (wait_exponential, max 4 attempts, up to 8s). `pybreaker`
  opens after 5 consecutive failures and stays open for 30s, short-
  circuiting further attempts — so a dead Groq endpoint fails fast
  instead of timing out forever.
- **Timeouts**: every outbound call has an explicit timeout
  (`httpx` default 10s, Groq client 30s).
- **Determinism for tests**: temperature 0 for analyzer; writer may
  use temperature > 0 but tests assert on *structure* not content.

## 9. What this design deliberately doesn't do

- No distributed task queue. Ingestion of 10K docs happens in a
  streaming async loop inside `scripts/ingest.sh` calling `/ingest`
  with concurrency 8. Fine for student scale.
- No per-user auth. The API is open.
- No cross-request memory. "Memory" is short-term, per-request state
  inside LangGraph. A future `session_id`-scoped conversation buffer
  is sketched in the schema but not implemented.
- No Kafka. The audit trail is JSONL + SSE; no streaming bus.
- No autoscaling. One backend container.

## 10. Done criteria for this architecture

When implementation finishes, the following will be true:

- `docker compose up` starts Postgres+pgvector, backend, frontend.
- `bash scripts/bootstrap.sh` creates tables, loads seed corpus,
  prints `Hit@5` from a mini eval.
- `POST /api/v1/ask` streams tokens over SSE, produces an answer
  with citations, and writes an audit trail JSONL.
- MCP client (MCP Client) connected to `library_rag_server.py`
  can call `semantic_search`, `answer_with_rag`, and `ingest_document`
  and see effects in both the DB and the web UI.
- `pytest` passes; `scripts/eval.sh` prints real metrics; if MLflow
  is enabled, the run appears in the UI at `http://localhost:5000`.

---

**End of Phase 1.** Awaiting sign-off to begin Phase 2 (scaffold the
new backend layout + config + logging + db/session/pgvector).
