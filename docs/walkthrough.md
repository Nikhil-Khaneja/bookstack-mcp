# Interview Walkthrough Guide

This document maps each interview claim to the exact code that backs it.

---

## Claim 1: "LangGraph state machine with specialized agent nodes"

**File:** `backend/app/services/agents/graph.py`

```python
graph = StateGraph(AgentState)
graph.add_node("input_guard", input_guard_node)
graph.add_node("retriever", retriever_node_factory(session, top_k))
graph.add_node("analyzer", analyzer_node)
graph.add_node("writer", writer_node)
graph.add_node("fallback", fallback_node)
graph.add_conditional_edges("retriever", _after_retriever)
graph.add_conditional_edges("analyzer", _after_analyzer)
```

**Node files:**
- `nodes/retriever.py` — embeds query, runs pgvector ANN + lexical rerank
- `nodes/analyzer.py` — calls Groq LLM, validates JSON output with Pydantic, retries on failure
- `nodes/writer.py` — streams tokens via LLM, extracts citations from `[N]` references
- `nodes/fallback.py` — extracts top chunk excerpt, sets `needs_review=True`

**State:** `services/agents/state.py` — `AgentState` TypedDict carries the full pipeline state across nodes

---

## Claim 2: "JSON-schema validation on every agent output with retry-with-correction"

**File:** `backend/app/services/guardrails/output.py`

```python
async def retry_with_correction(schema, call, max_retries):
    for attempt in range(max_retries + 1):
        raw = await call(correction)
        try:
            return schema.model_validate_json(extract_json(raw))
        except ValidationError as e:
            correction = build_correction_prompt(schema, raw, e)
    raise ValidationRetryExceeded(...)
```

**Schemas:** `AnalyzerOutput(summary, relevance_rationale, self_confidence)`, `WriterOutput(answer, citations)`

When validation fails, the corrective prompt includes:
- The exact Pydantic field errors
- The full JSON schema
- Instruction to return only a valid JSON object

After `OUTPUT_VALIDATION_MAX_RETRIES` (default 2) failures, `ValidationRetryExceeded` is raised and the graph routes to the fallback node.

---

## Claim 3: "Versioned prompt templates tested against eval set before promotion"

**Directory:** `backend/app/services/agents/prompts/v1/`

Files:
- `analyzer.md` — system prompt with `{{QUERY}}`, `{{PASSAGES}}` placeholders
- `writer.md` — writer prompt with `{{SUMMARY}}`, `{{N_PASSAGES}}`
- `fallback.md` — fallback explanation prompt

**Version selection:** `PROMPT_VERSION=v1` in `.env` — change to `v2` to test a new version without touching code.

**Eval:** `backend/eval/run_eval.py` measures Hit@K, MRR, Precision, Recall. Run with `bash scripts/eval.sh` before promoting a new prompt version.

**MLflow:** Set `MLFLOW_TRACKING_URI=http://localhost:5000` to compare runs across prompt versions in the UI.

---

## Claim 4: "Confidence-based routing to fallback / human-review path"

**File:** `backend/app/services/agents/graph.py`

```python
def _after_retriever(state):
    if state["avg_top_score"] < settings.retrieval_conf_threshold:
        return "fallback"
    return "analyzer"

def _after_analyzer(state):
    if state.get("self_confidence", 0) < settings.analyzer_conf_threshold:
        return "fallback"
    return "writer"
```

Thresholds are config-driven:
- `RETRIEVAL_CONF_THRESHOLD=0.25` — if top retrieved chunk score is too low, skip LLM
- `ANALYZER_CONF_THRESHOLD=0.55` — if LLM isn't confident in the evidence, route to fallback

The `done` SSE event carries `needs_review: true` when fallback was used, allowing the frontend (and any downstream system) to flag answers for human review.

---

## Claim 5: "Full audit trail via LangGraph shared state"

**State field:** `audit_log: list[AuditEvent]` in `AgentState`

Each node appends via `node_timer` context manager (`nodes/_shared.py`):
```python
@contextmanager
def node_timer(state, node):
    t0 = time.time()
    yield
    state["audit_log"].append({
        "node": node,
        "decision": ...,
        "confidence": ...,
        "ms": round((time.time() - t0) * 1000),
        "ts": now_iso(),
    })
```

**Persisted:** `services/events/audit.py` writes each run's audit log to `audit/audit-YYYY-MM-DD.jsonl`

**Retrieved:** `GET /api/v1/trace/{trace_id}` reads the JSONL and returns the full audit for a request

**Live:** The SSE `node_start` / `node_end` events stream the trace to the frontend in real time

---

## Claim 6: "Exponential backoff + circuit breakers on external API calls"

**File:** `backend/app/services/guardrails/breaker.py`

```python
# Circuit breaker: 5 failures → open for 30s
get_breaker(name)  # lazy pybreaker.CircuitBreaker(fail_max=5, reset_timeout=30)

# Exponential backoff: 1s → 2s → 4s → 8s + jitter
await call_with_breaker(name, fn, *args)
# Uses tenacity AsyncRetrying(wait=wait_exponential(min=1, max=10), stop=stop_after_attempt(3))
```

**Applied to:** Groq API calls in `nodes/analyzer.py` and `nodes/writer.py`

**Error mapping:**
- `CircuitBreakerError` → `BreakerOpen` (503)
- `TimeoutError` → `UpstreamTimeout` (504)

---

## Claim 7: "MCP server — LLM agents can autonomously manage the knowledge base"

**File:** `mcp-server/library_rag_server.py`

5 tools exposed via STDIO JSON-RPC:
1. `semantic_search(query, top_k, rerank)` — POST /api/v1/retrieve
2. `answer_with_rag(query, top_k)` — POST /api/v1/answer
3. `ingest_document(title, text|url)` — POST /api/v1/ingest
4. `get_document_by_id(document_id)` — retrieve + filter by doc ID
5. `list_sources(limit)` — retrieve + deduplicate by document_id

**MCP client:** Add to `mcp_config.json` and any MCP-compatible agent can call these tools conversationally.

---

## Likely interview questions and answers

**Q: Why LangGraph and not a simple loop?**
A: LangGraph gives us a compilable, inspectable graph with conditional edges. It's easy to add a new node (e.g., a rewriter) without rewiring everything. The shared state is also the natural place for the audit log.

**Q: How does the retry-with-correction differ from simple retry?**
A: Simple retry sends the same prompt again. Correction re-prompts with the exact Pydantic validation error and JSON schema, giving the LLM the information it needs to fix the specific issue.

**Q: What's the fallback doing?**
A: It's a deterministic, extractive fallback — no LLM call. It takes the highest-scoring retrieved chunk's text and uses it as the answer. This is always available, fast, and grounded in the KB, even when the LLM is down or low-confidence.

**Q: How would you scale this to 10M documents?**
A: (1) Switch pgvector's ivfflat to HNSW or a purpose-built ANN store (Milvus/Qdrant). (2) Pre-compute embeddings in batch. (3) Add a filtering layer (metadata pre-filter before ANN). (4) Use a cross-encoder reranker for top-50 → top-5.

**Q: How is the eval set built?**
A: 25 domain documents + 50 queries (2 per document) with known relevant titles. We measure Hit@5, MRR, Precision@5, Recall@5. The offline mode uses the InMemoryVectorStore so it runs in seconds with no infra.

**Q: What's your actual Hit@5?**
A: With the real MiniLM sentence transformer on this focused corpus, our eval set targets 92%+. With the HashingEmbedder offline fallback, the number is lower (deterministic hash-based similarity). I'm transparent about which mode produced which number.
