import { useEffect, useRef } from 'react'
import mermaid from 'mermaid'

const DIAGRAM = `
flowchart LR
  U[User / Client] -->|HTTP / SSE| API[FastAPI /api/v1]
  API --> IG[Input Guardrails]
  IG --> RET[Retriever<br/>pgvector + rerank]
  RET --> ANZ[Analyzer LLM<br/>JSON-validated]
  ANZ -->|low confidence| FB[Fallback Agent]
  ANZ -->|ok| WR[Writer LLM<br/>streaming]
  WR --> OG[Output Guardrails]
  FB --> OG
  OG --> SSE[SSE events:<br/>token / node / trace / done]
  SSE --> U

  subgraph Infra
    PG[(Postgres + pgvector)]
    MLF[(MLflow)]
    AUD[(Audit JSONL)]
  end

  RET --- PG
  API -.log.-> AUD
  API -.eval.-> MLF

  MCP[MCP STDIO server] -->|httpx| API
`

const INGEST = `
sequenceDiagram
  autonumber
  participant C as Client
  participant API as FastAPI /ingest
  participant L as Loader
  participant CH as Chunker
  participant EM as Embedder (MiniLM-384)
  participant VS as PgVectorStore

  C->>API: POST {title, text|url}
  API->>L: load -> DocumentDraft(+content_hash)
  L->>CH: chunk_text(size=512, overlap=64)
  CH->>EM: encode(chunks)
  EM->>VS: upsert_document(doc, chunks, vecs)
  VS-->>API: (document_id, n_chunks, created)
  API-->>C: {document_id, n_chunks, deduped}
`

const ASK = `
sequenceDiagram
  autonumber
  participant C as Client
  participant API as FastAPI /ask (SSE)
  participant G as LangGraph
  participant R as Retriever
  participant A as Analyzer
  participant W as Writer
  participant F as Fallback

  C->>API: POST {query, top_k}
  API->>G: run_agent_stream
  G->>R: retrieve top-K + rerank
  R-->>G: hits, avg_top_score
  G-->>C: event: hits
  G->>A: analyze (JSON-validated, retry)
  A-->>G: {summary, self_confidence}
  alt confidence >= threshold
    G->>W: stream tokens
    W-->>C: event: token*
  else low confidence / empty
    G->>F: fallback_node
    F-->>C: event: token (fallback)
  end
  G-->>C: event: done {citations, needs_review}
`

export default function Architecture() {
  const topRef = useRef(null)
  const ingRef = useRef(null)
  const askRef = useRef(null)

  useEffect(() => {
    mermaid.initialize({ startOnLoad: false, securityLevel: 'loose', theme: 'default' })
    const render = async () => {
      try {
        const { svg: s1 } = await mermaid.render('m-top', DIAGRAM)
        if (topRef.current) topRef.current.innerHTML = s1
        const { svg: s2 } = await mermaid.render('m-ing', INGEST)
        if (ingRef.current) ingRef.current.innerHTML = s2
        const { svg: s3 } = await mermaid.render('m-ask', ASK)
        if (askRef.current) askRef.current.innerHTML = s3
      } catch (e) {
        console.error('mermaid render error', e)
      }
    }
    render()
  }, [])

  return (
    <div style={{ display: 'grid', gap: 20 }}>
      <h2>System Architecture</h2>
      <p style={{ color: '#475569', fontSize: 13 }}>
        Live rendering of the RAG + LangGraph agent pipeline. Source-of-truth diagrams
        also live in <code>docs/architecture.md</code>.
      </p>

      <section>
        <h3>Top-level request flow</h3>
        <div ref={topRef} style={{ background: '#fff', padding: 12, border: '1px solid #e2e8f0' }} />
      </section>

      <section>
        <h3>Ingestion path</h3>
        <div ref={ingRef} style={{ background: '#fff', padding: 12, border: '1px solid #e2e8f0' }} />
      </section>

      <section>
        <h3>/ask — LangGraph state machine</h3>
        <div ref={askRef} style={{ background: '#fff', padding: 12, border: '1px solid #e2e8f0' }} />
      </section>
    </div>
  )
}
