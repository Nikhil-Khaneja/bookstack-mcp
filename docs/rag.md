# RAG Concepts — Deep Dive

This document explains every concept behind the bookstack-mcp RAG pipeline. Written to support interview discussion at the "4 years + MS" level.

---

## 1. Encoder vs Decoder models

| | Encoder (BERT-style) | Decoder (GPT-style) |
|-|---------------------|---------------------|
| Attention | Bidirectional (all tokens see all) | Causal (each token sees only past) |
| Use case | Embeddings, classification, NER | Text generation, Q&A |
| Example | all-MiniLM-L6-v2 | LLaMA 3.1, GPT-4 |
| Training | Masked Language Modeling | Causal Language Modeling |

**In our pipeline:**
- **MiniLM** (encoder) → produces 384-dim embeddings for indexing and query encoding
- **LLaMA 3.1 via Groq** (decoder) → generates the final answer token-by-token

---

## 2. Chunking

Long documents cannot be embedded whole because:
1. Encoder models have a max token limit (~512 for MiniLM)
2. Smaller chunks make similarity search more precise

### Recursive character splitting

Our chunker (`services/ingestion/chunker.py`) tries separators in priority order:
```
["\n\n", "\n", ". ", " ", ""]
```
It splits at the first separator that keeps chunk size ≤ `CHUNK_SIZE` (default 512 chars).

### Overlap

Each chunk carries `CHUNK_OVERLAP` (default 64) characters from the end of the previous chunk. This prevents losing context at boundaries — e.g., a sentence split across two chunks.

```
Chunk 0: [---- 512 chars -----]
Chunk 1:                  [64][---- 512 chars -----]
                           ↑ overlap
```

### Why 512 chars / 64 overlap?

- 512 chars ≈ 100–130 tokens → fits MiniLM's 256-token window with room to spare
- 64 chars ≈ one sentence → enough to preserve boundary context
- Empirically good starting point; tunable via `CHUNK_SIZE` / `CHUNK_OVERLAP` env vars

---

## 3. Embeddings

### Bi-encoder (used for retrieval)

Both query and passage are encoded independently:
```
query  → encoder → q_vec  (384-dim)
passage → encoder → p_vec  (384-dim)
```
Similarity = `dot(q_vec, p_vec)` (cosine, since vectors are unit-normalized)

**Advantage:** Passages can be pre-computed and indexed offline.

### Cross-encoder (not used; would be used for reranking at scale)

Query and passage are concatenated and jointly encoded:
```
[query | passage] → encoder → relevance_score
```
More accurate but cannot be pre-indexed — O(N) inference per query.

### all-MiniLM-L6-v2

- Distilled from larger models via knowledge distillation
- 384 dimensions (vs 768 for BERT-base, 1536 for OpenAI ada-002)
- ~6 transformer layers, ~22M parameters
- Runs on CPU in milliseconds per batch
- Trained with contrastive loss on sentence pairs from NLI + Wikipedia

---

## 4. Vector dimensions — low vs high

| Dimensions | Pros | Cons |
|-----------|------|------|
| 128–256 | Fast ANN search, low storage | Loss of nuance |
| 384 (MiniLM) | Good accuracy-speed balance | — |
| 768 (BERT-base) | Higher recall | 2× compute |
| 1536–3072 (OpenAI) | State-of-art accuracy | Expensive, proprietary |

We use 384: enough semantic resolution for a domain-specific KB, fast enough for <10ms retrieval, and free (local model).

---

## 5. Top-K and cosine similarity

**Cosine similarity** between two unit-normalized vectors a, b:
```
cos(a, b) = a · b / (|a| |b|) = a · b   (since |a| = |b| = 1)
```
Range: [-1, 1]. In practice, MiniLM embeddings stay in [0, 1] for semantically related texts.

**Top-K selection:** retrieve the K chunks with highest cosine similarity to the query vector.

**Our over-fetch strategy:**
```python
over_k = min(k * 3, 50)  # retrieve 3× as many
raw_hits = store.search(query_vec, top_k=over_k)
hits = lexical_rerank(query, raw_hits)[:k]
```
Reason: dense retrieval alone may miss exact keyword matches. Fetching 3× and reranking improves final quality.

---

## 6. Dense vs sparse retrieval

| | Dense (our primary) | Sparse (BM25-style) |
|-|--------------------|--------------------|
| Representation | Neural embedding vector | TF-IDF term weights |
| Handles paraphrase | Yes | No |
| Handles exact match | Sometimes | Yes |
| Needs training | Yes | No |
| Index size | Fixed (dim × n) | Variable (vocab × n) |

**Our hybrid:** dense retrieval + lexical reranker that blends dense score with token-overlap score:
```python
score' = 0.75 * dense_score + 0.25 * lexical_score
```
This catches exact-term matches that dense search might rank lower.

---

## 7. pgvector and the ivfflat index

```sql
CREATE INDEX chunks_embedding_idx
  ON chunks USING ivfflat (embedding vector_cosine_ops)
  WITH (lists = 100);
```

**IVFFlat** (Inverted File Flat):
1. Cluster all vectors into `lists` Voronoi cells during index build (k-means)
2. At query time, search only the `probes` nearest cells (default probes=1)
3. Exact search within each cell

Trade-off: `lists=100` works well for ~100K vectors. For 1M+ vectors, use HNSW or increase lists.

**Cosine operator** `<=>`: computes cosine distance = 1 - cosine_similarity. We convert to similarity with `1.0 - (embedding <=> query_vector)`.

---

## 8. LangGraph state machine

```
┌─────────────────────────────────────────────────────────┐
│                      AgentState                          │
│  query, trace_id, retrieved, avg_top_score,             │
│  analysis, self_confidence, answer, citations,           │
│  needs_review, used_fallback, audit_log, errors          │
└─────────────────────────────────────────────────────────┘
         │                                 │
    node_start                          node_end
         │                                 │
  ┌──────▼──────────────────────────────────┐
  │           StateGraph                    │
  │                                         │
  │  START → input_guard                    │
  │             │  ← GuardrailViolation     │
  │             │         → END(error)      │
  │             ▼                           │
  │          retriever                      │
  │             │  ← avg_top_score < 0.25   │
  │             │         → fallback        │
  │             ▼                           │
  │          analyzer  ── ValidationRetry   │
  │             │         Exceeded → fallback│
  │             │  ← self_confidence < 0.55 │
  │             │         → fallback        │
  │             ▼                           │
  │           writer                        │
  │             ▼                           │
  │        output_guard                     │
  │             ▼                           │
  │            END                          │
  └─────────────────────────────────────────┘
```

**Key design:** nodes are pure functions (state in → state out). Conditional edges are functions that read the state and return the next node name. This makes the graph testable and auditable.

---

## 9. JSON-schema validation + retry-with-correction

Every LLM call that must produce structured output is wrapped in `retry_with_correction`:

```python
async def retry_with_correction(schema, call, max_retries=2):
    for attempt in range(max_retries + 1):
        raw = await call(correction)
        try:
            return schema.model_validate_json(extract_json(raw))
        except ValidationError as e:
            correction = build_correction_prompt(schema, raw, e)
    raise ValidationRetryExceeded(...)
```

On failure, we re-prompt the LLM with: the exact Pydantic validation error + the JSON schema. This dramatically improves structured output reliability vs a single-shot approach.

If retries are exhausted, `ValidationRetryExceeded` is raised and the LangGraph router sends execution to the fallback node.

---

## 10. Confidence-based routing

The analyzer node produces `self_confidence ∈ [0, 1]`. The router checks:

```python
if state["self_confidence"] < settings.analyzer_conf_threshold:  # default 0.55
    return "fallback"
return "writer"
```

Low confidence means:
- Retrieved passages are weakly related (avg_top_score < 0.25 triggers earlier)
- Analyzer LLM doesn't find strong evidence for an answer

The fallback node extracts the best chunk excerpt and sets `needs_review=True`, signaling the answer should be reviewed by a human or escalated.

---

## 11. Retrieval metrics

| Metric | Formula | What it measures |
|--------|---------|-----------------|
| Hit@K | 1 if relevant doc in top-K, else 0 | Binary retrieval success |
| MRR@K | mean(1/rank of first relevant hit) | Ranking quality |
| Precision@K | \|relevant ∩ top-K\| / K | Fraction of top-K that's relevant |
| Recall@K | \|relevant ∩ top-K\| / \|relevant\| | Fraction of relevant docs retrieved |

For our 50-query eval set with K=5:
- Target: Hit@5 ≥ 92% (achievable with real MiniLM embeddings on this focused corpus)
- Baseline HashingEmbedder: lower (deterministic, not semantic)

MLflow logs all metrics per run, enabling comparison across chunking strategies, embedding models, and top-k values.
