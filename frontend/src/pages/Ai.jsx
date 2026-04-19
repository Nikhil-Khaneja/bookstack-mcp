import { useRef, useState } from 'react'
import { fetchEventSource } from '@microsoft/fetch-event-source'
import { API_BASE } from '../apiBase'

// ── Colors for the per-node trace panel ──────────────────────────
const NODE_COLOR = {
  input_guard:  '#0ea5e9',
  retriever:    '#22c55e',
  analyzer:     '#a855f7',
  writer:       '#f59e0b',
  fallback:     '#ef4444',
  output_guard: '#64748b',
}

export default function Ai() {
  const [query, setQuery] = useState('')
  const [topK, setTopK] = useState(5)
  const [streaming, setStreaming] = useState(false)
  const [answer, setAnswer] = useState('')
  const [hits, setHits] = useState([])
  const [nodes, setNodes] = useState([])  // [{node, decision, confidence, ms, state}]
  const [done, setDone] = useState(null)
  const [err, setErr] = useState(null)
  const abortRef = useRef(null)

  const reset = () => {
    setAnswer('')
    setHits([])
    setNodes([])
    setDone(null)
    setErr(null)
  }

  const submit = async () => {
    if (!query.trim() || streaming) return
    reset()
    setStreaming(true)

    const ctrl = new AbortController()
    abortRef.current = ctrl

    try {
      await fetchEventSource(`${API_BASE}/api/v1/ask`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ query, top_k: Number(topK) }),
        signal: ctrl.signal,
        openWhenHidden: true,
        onopen: async (res) => {
          if (!res.ok) throw new Error(`HTTP ${res.status}`)
        },
        onmessage: (msg) => {
          let data = {}
          try { data = JSON.parse(msg.data) } catch { return }
          switch (msg.event) {
            case 'open':
              break
            case 'node_start':
              setNodes((prev) => [
                ...prev,
                { node: data.node, state: 'running', decision: null, confidence: null, ms: null },
              ])
              break
            case 'node_end':
              setNodes((prev) => {
                const out = [...prev]
                for (let i = out.length - 1; i >= 0; i--) {
                  if (out[i].node === data.node && out[i].state === 'running') {
                    out[i] = { ...out[i], state: 'done', ...data }
                    break
                  }
                }
                return out
              })
              break
            case 'hits':
              setHits(data.retrieved || [])
              break
            case 'token':
              setAnswer((a) => a + (data.text || ''))
              break
            case 'trace':
              // Full audit trail; we already have node_start/node_end events.
              break
            case 'done':
              setDone(data)
              break
            case 'error':
              setErr(data)
              break
            default:
              break
          }
        },
        onerror: (e) => {
          setErr({ code: 'stream_error', message: String(e) })
          throw e
        },
      })
    } catch (e) {
      if (!err) setErr({ code: 'stream_error', message: String(e) })
    } finally {
      setStreaming(false)
    }
  }

  const cancel = () => {
    abortRef.current?.abort()
    setStreaming(false)
  }

  return (
    <div style={{ display: 'grid', gap: 16 }}>
      <h2>AI Console</h2>

      <div style={{ display: 'flex', gap: 8, alignItems: 'flex-start' }}>
        <textarea
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Ask a question about the knowledge base…"
          rows={3}
          style={{ flex: 1, padding: 8 }}
        />
        <div style={{ display: 'grid', gap: 4 }}>
          <label>
            top_k <input type="number" min={1} max={50} value={topK}
              onChange={(e) => setTopK(e.target.value)} style={{ width: 64 }} />
          </label>
          {streaming
            ? <button onClick={cancel}>Cancel</button>
            : <button onClick={submit} disabled={!query.trim()}>Ask</button>}
        </div>
      </div>

      {err && (
        <div style={{ padding: 8, background: '#fee2e2', color: '#991b1b' }}>
          <strong>{err.code}:</strong> {err.message}
        </div>
      )}

      {/* Answer */}
      <section>
        <h3>Answer {done?.used_fallback && <span style={{ color: '#f59e0b' }}>(fallback)</span>} {done?.needs_review && <span style={{ color: '#ef4444' }}>NEEDS REVIEW</span>}</h3>
        <div style={{ whiteSpace: 'pre-wrap', background: '#f8fafc', padding: 12, minHeight: 80 }}>
          {answer || (streaming ? '…' : '')}
        </div>
        {done?.citations?.length > 0 && (
          <div style={{ marginTop: 4, fontSize: 12 }}>
            citations: {done.citations.map((c) => `[${c}]`).join(' ')}
          </div>
        )}
      </section>

      {/* Trace */}
      <section>
        <h3>Pipeline trace</h3>
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
          {nodes.map((n, i) => (
            <div key={i} style={{
              padding: '4px 10px',
              border: `2px solid ${NODE_COLOR[n.node] || '#334155'}`,
              background: n.state === 'running' ? '#fef9c3' : '#fff',
              borderRadius: 6,
              fontSize: 12,
            }}>
              <strong style={{ color: NODE_COLOR[n.node] || '#334155' }}>{n.node}</strong>
              {n.state === 'done' && (
                <>
                  {' '}· {n.decision || '—'}
                  {n.confidence != null && <> · conf={n.confidence.toFixed(2)}</>}
                  {n.ms != null && <> · {n.ms}ms</>}
                  {n.error && <span style={{ color: '#ef4444' }}> · {n.error}</span>}
                </>
              )}
              {n.state === 'running' && ' · running…'}
            </div>
          ))}
        </div>
      </section>

      {/* Retrieved chunks */}
      <section>
        <h3>Retrieved chunks ({hits.length})</h3>
        <table style={{ width: '100%', fontSize: 12, borderCollapse: 'collapse' }}>
          <thead>
            <tr>
              <th style={th}>chunk_id</th><th style={th}>doc</th>
              <th style={th}>ord</th><th style={th}>score</th><th style={th}>excerpt</th>
            </tr>
          </thead>
          <tbody>
            {hits.map((h) => (
              <tr key={h.chunk_id}>
                <td style={td}>{h.chunk_id}</td>
                <td style={td}>{h.document_title}</td>
                <td style={td}>{h.ord}</td>
                <td style={td}>{h.score?.toFixed(3)}</td>
                <td style={td}>{(h.text || '').slice(0, 200)}…</td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>
    </div>
  )
}

const th = { textAlign: 'left', borderBottom: '1px solid #e5e7eb', padding: 4 }
const td = { borderBottom: '1px solid #f1f5f9', padding: 4, verticalAlign: 'top' }
