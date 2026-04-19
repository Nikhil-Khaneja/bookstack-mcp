"""Retrieval evaluation script.

Measures Hit@K, MRR@K, Precision@K, Recall@K against a curated eval set.
Optionally logs results to MLflow.

Usage:
  # Offline mode (no Postgres, no Groq key needed):
  python -m eval.run_eval

  # HTTP mode (backend must be running at http://localhost:8000):
  python -m eval.run_eval --mode http --base-url http://localhost:8000

  # Different k values:
  python -m eval.run_eval --k 1 3 5

  # Save report:
  python -m eval.run_eval --report eval/report.json
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("run_eval")

EVAL_DIR = Path(__file__).parent
CORPUS_FILE = EVAL_DIR / "corpus.jsonl"
EVAL_FILE = EVAL_DIR / "eval_set.jsonl"


# ── Data classes ──────────────────────────────────────────────────────

@dataclass
class CorpusDoc:
    title: str
    text: str


@dataclass
class EvalQuery:
    query: str
    relevant_titles: list[str]


@dataclass
class QueryResult:
    query: str
    relevant_titles: list[str]
    retrieved_titles: list[str]   # ordered, top-K
    retrieved_scores: list[float]
    latency_ms: float
    hits_at: dict[int, bool] = field(default_factory=dict)
    rr: float = 0.0               # reciprocal rank


# ── Loaders ───────────────────────────────────────────────────────────

def load_corpus() -> list[CorpusDoc]:
    docs = []
    with CORPUS_FILE.open() as f:
        for line in f:
            line = line.strip()
            if line:
                d = json.loads(line)
                docs.append(CorpusDoc(title=d["title"], text=d["text"]))
    return docs


def load_eval_set() -> list[EvalQuery]:
    queries = []
    with EVAL_FILE.open() as f:
        for line in f:
            line = line.strip()
            if line:
                d = json.loads(line)
                queries.append(EvalQuery(query=d["query"], relevant_titles=d["relevant_titles"]))
    return queries


# ── Offline mode ──────────────────────────────────────────────────────

def _build_offline_store(docs: list[CorpusDoc]) -> Any:
    """Build an InMemoryVectorStore with the corpus embedded."""
    # Dynamically add repo root so imports work when called as:
    #   python -m eval.run_eval  (from backend/)
    backend_root = EVAL_DIR.parent
    if str(backend_root) not in sys.path:
        sys.path.insert(0, str(backend_root))

    from app.services.ingestion.loader import load_text
    from app.services.ingestion.chunker import chunk_text
    from app.services.retrieval.embedder import get_embedder
    from app.services.retrieval.vector_store import InMemoryVectorStore

    store = InMemoryVectorStore()
    emb = get_embedder()

    for doc in docs:
        draft = load_text(title=doc.title, text=doc.text)
        chunks = chunk_text(draft.text)
        vectors = emb.encode([c.text for c in chunks])
        store.upsert_document(draft, chunks, vectors)
        log.info("ingested '%s' → %d chunks", doc.title, len(chunks))

    return store, emb


def run_offline(
    docs: list[CorpusDoc],
    queries: list[EvalQuery],
    top_k: int,
) -> list[QueryResult]:
    backend_root = EVAL_DIR.parent
    if str(backend_root) not in sys.path:
        sys.path.insert(0, str(backend_root))

    from app.services.retrieval.retriever import lexical_rerank

    store, emb = _build_offline_store(docs)
    results = []

    for eq in queries:
        t0 = time.perf_counter()
        qvec = emb.encode([eq.query])[0]
        raw = store.search(qvec, top_k=top_k * 3)
        hits = lexical_rerank(eq.query, raw)[:top_k]
        latency_ms = (time.perf_counter() - t0) * 1000

        retrieved_titles = [h.document_title for h in hits]
        retrieved_scores = [h.score for h in hits]
        results.append(_score_result(eq, retrieved_titles, retrieved_scores, latency_ms))

    return results


# ── HTTP mode ─────────────────────────────────────────────────────────

def _ingest_http(base_url: str, docs: list[CorpusDoc]) -> None:
    with httpx.Client(base_url=base_url, timeout=60.0) as client:
        for doc in docs:
            resp = client.post(
                "/api/v1/ingest",
                json={"title": doc.title, "text": doc.text},
            )
            resp.raise_for_status()
            data = resp.json()
            action = "deduped" if not data.get("deduped", True) else "ingested"
            log.info("%s '%s' → %d chunks", action, doc.title, data.get("n_chunks", 0))


def run_http(
    base_url: str,
    docs: list[CorpusDoc],
    queries: list[EvalQuery],
    top_k: int,
    ingest: bool,
) -> list[QueryResult]:
    if ingest:
        log.info("Ingesting %d corpus documents via HTTP…", len(docs))
        _ingest_http(base_url, docs)

    results = []
    with httpx.Client(base_url=base_url, timeout=30.0) as client:
        for eq in queries:
            t0 = time.perf_counter()
            resp = client.post(
                "/api/v1/retrieve",
                json={"query": eq.query, "top_k": top_k, "rerank": True},
            )
            resp.raise_for_status()
            latency_ms = (time.perf_counter() - t0) * 1000

            data = resp.json()
            hits = data.get("hits", [])
            retrieved_titles = [h["document_title"] for h in hits]
            retrieved_scores = [h["score"] for h in hits]
            results.append(_score_result(eq, retrieved_titles, retrieved_scores, latency_ms))

    return results


# ── Scoring ───────────────────────────────────────────────────────────

def _score_result(
    eq: EvalQuery,
    retrieved_titles: list[str],
    retrieved_scores: list[float],
    latency_ms: float,
) -> QueryResult:
    relevant_set = set(eq.relevant_titles)
    rr = 0.0
    for rank, title in enumerate(retrieved_titles, start=1):
        if title in relevant_set:
            rr = 1.0 / rank
            break

    return QueryResult(
        query=eq.query,
        relevant_titles=eq.relevant_titles,
        retrieved_titles=retrieved_titles,
        retrieved_scores=retrieved_scores,
        latency_ms=latency_ms,
        rr=rr,
    )


def compute_metrics(results: list[QueryResult], k_values: list[int]) -> dict[str, float]:
    """Aggregate metrics across all queries for each k value."""
    metrics: dict[str, float] = {}
    n = len(results)

    mrr_sum = sum(r.rr for r in results)
    metrics["MRR"] = round(mrr_sum / n, 4) if n else 0.0

    for k in k_values:
        hit_sum = 0
        prec_sum = 0.0
        rec_sum = 0.0

        for r in results:
            relevant_set = set(r.relevant_titles)
            top_k_titles = set(r.retrieved_titles[:k])
            true_positives = len(top_k_titles & relevant_set)

            hit = 1 if true_positives > 0 else 0
            hit_sum += hit
            prec_sum += true_positives / k if k else 0.0
            rec_sum += true_positives / len(relevant_set) if relevant_set else 0.0

        metrics[f"Hit@{k}"] = round(hit_sum / n, 4) if n else 0.0
        metrics[f"Precision@{k}"] = round(prec_sum / n, 4) if n else 0.0
        metrics[f"Recall@{k}"] = round(rec_sum / n, 4) if n else 0.0

    avg_latency = sum(r.latency_ms for r in results) / n if n else 0.0
    metrics["avg_latency_ms"] = round(avg_latency, 1)

    return metrics


# ── MLflow logging ────────────────────────────────────────────────────

def log_to_mlflow(
    params: dict[str, Any],
    metrics: dict[str, float],
    run_name: str,
) -> None:
    tracking_uri = os.getenv("MLFLOW_TRACKING_URI", "")
    if not tracking_uri:
        log.info("MLFLOW_TRACKING_URI not set — skipping MLflow logging")
        return

    try:
        import mlflow
        mlflow.set_tracking_uri(tracking_uri)
        with mlflow.start_run(run_name=run_name):
            for k, v in params.items():
                mlflow.log_param(k, v)
            for k, v in metrics.items():
                mlflow.log_metric(k, v)
        log.info("MLflow run logged to %s", tracking_uri)
    except Exception as e:
        log.warning("MLflow logging failed (non-fatal): %s", e)


# ── Report ────────────────────────────────────────────────────────────

def print_report(
    metrics: dict[str, float],
    results: list[QueryResult],
    k_values: list[int],
    mode: str,
) -> None:
    print("\n" + "=" * 60)
    print(f"  RAG Retrieval Evaluation Report  (mode={mode})")
    print("=" * 60)
    print(f"  Queries evaluated : {len(results)}")
    print()

    for k in k_values:
        print(f"  Hit@{k:<3}     = {metrics[f'Hit@{k}']:.1%}")
        print(f"  Precision@{k:<3} = {metrics[f'Precision@{k}']:.1%}")
        print(f"  Recall@{k:<3}   = {metrics[f'Recall@{k}']:.1%}")
        print()

    print(f"  MRR             = {metrics['MRR']:.4f}")
    print(f"  Avg latency     = {metrics['avg_latency_ms']:.1f} ms")
    print("=" * 60)

    # Failures (queries where relevant doc not in top-5)
    max_k = max(k_values)
    failures = [
        r for r in results
        if not any(t in set(r.retrieved_titles[:max_k]) for t in r.relevant_titles)
    ]
    if failures:
        print(f"\n  Misses at top-{max_k} ({len(failures)}/{len(results)}):")
        for r in failures:
            print(f"    Q: {r.query[:70]}")
            print(f"       want: {r.relevant_titles}")
            print(f"       got:  {r.retrieved_titles[:3]}")
    else:
        print(f"\n  No misses at top-{max_k}!")
    print()


# ── CLI ───────────────────────────────────────────────────────────────

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Evaluate RAG retrieval quality")
    p.add_argument(
        "--mode", choices=["offline", "http"], default="offline",
        help="offline = InMemoryVectorStore; http = running backend",
    )
    p.add_argument("--base-url", default="http://localhost:8000")
    p.add_argument("--top-k", type=int, default=5, help="top-k for retrieval")
    p.add_argument(
        "--k", type=int, nargs="+", default=[1, 3, 5],
        help="k values to report metrics for",
    )
    p.add_argument("--no-ingest", action="store_true",
                   help="skip ingestion in http mode (corpus already in DB)")
    p.add_argument("--report", help="save JSON report to this path")
    p.add_argument("--mlflow-run-name", default="rag_eval",
                   help="MLflow run name (used only when MLFLOW_TRACKING_URI is set)")
    return p.parse_args()


def main() -> None:
    args = parse_args()

    corpus = load_corpus()
    queries = load_eval_set()
    log.info("Corpus: %d docs | Eval set: %d queries", len(corpus), len(queries))

    top_k = max(args.top_k, max(args.k))

    if args.mode == "offline":
        log.info("Running in offline mode (InMemoryVectorStore + local embedder)")
        results = run_offline(corpus, queries, top_k)
    else:
        log.info("Running in http mode → %s", args.base_url)
        results = run_http(
            base_url=args.base_url,
            docs=corpus,
            queries=queries,
            top_k=top_k,
            ingest=not args.no_ingest,
        )

    k_values = sorted(set(args.k))
    metrics = compute_metrics(results, k_values)

    params = {
        "mode": args.mode,
        "top_k": top_k,
        "n_corpus_docs": len(corpus),
        "n_queries": len(queries),
    }

    print_report(metrics, results, k_values, args.mode)
    log_to_mlflow(params, metrics, args.mlflow_run_name)

    if args.report:
        report_path = Path(args.report)
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report = {
            "params": params,
            "metrics": metrics,
            "queries": [
                {
                    "query": r.query,
                    "relevant_titles": r.relevant_titles,
                    "retrieved_titles": r.retrieved_titles,
                    "rr": r.rr,
                    "latency_ms": r.latency_ms,
                }
                for r in results
            ],
        }
        report_path.write_text(json.dumps(report, indent=2))
        log.info("Report saved to %s", report_path)


if __name__ == "__main__":
    main()
