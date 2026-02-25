import { useCallback, useEffect, useRef, useState } from 'react'
import { useSend } from '../hooks/useSend'
import { type ConversationEvent, useConversationStore } from '../lib/wsConversation'
import styles from '../styles/global.module.css'

interface ConvBenchmarkResult {
  index: number
  total: number
  text: string
  emotion: string
  ws_connect_ms?: number
  llm_latency_ms?: number
  llm_observed_ms?: number
  tts_ttfb_ms?: number
  total_ms?: number
  error?: string
}

interface ConvBenchmarkSummary {
  count: number
  mean_ws_connect_ms?: number
  p50_ws_connect_ms?: number
  p95_ws_connect_ms?: number
  mean_llm_ms?: number
  p50_llm_ms?: number
  p95_llm_ms?: number
  mean_llm_observed_ms?: number
  p50_llm_observed_ms?: number
  p95_llm_observed_ms?: number
  mean_tts_ttfb_ms?: number
  p50_tts_ttfb_ms?: number
  p95_tts_ttfb_ms?: number
  mean_total_ms?: number
  p50_total_ms?: number
  p95_total_ms?: number
  error?: string
}

export default function ConvBenchmark() {
  const send = useSend()
  const [running, setRunning] = useState(false)
  const [results, setResults] = useState<ConvBenchmarkResult[]>([])
  const [summary, setSummary] = useState<ConvBenchmarkSummary | null>(null)
  const [progress, setProgress] = useState<{ index: number; total: number } | null>(null)
  const versionRef = useRef(0)

  useEffect(() => {
    const unsub = useConversationStore.subscribe((state) => {
      if (state.version === versionRef.current) return
      versionRef.current = state.version

      const latest = state.events[state.events.length - 1]
      if (!latest) return

      if (latest.type === 'conv.benchmark.progress') {
        const r = latest as unknown as ConversationEvent & ConvBenchmarkResult
        setResults((prev) => [...prev, r])
        setProgress({ index: (r.index ?? 0) + 1, total: r.total ?? 0 })
      } else if (latest.type === 'conv.benchmark.done') {
        const s = latest as unknown as ConversationEvent & ConvBenchmarkSummary
        setSummary(s)
        setRunning(false)
        setProgress(null)
      }
    })
    return unsub
  }, [])

  const startBenchmark = useCallback(() => {
    setRunning(true)
    setResults([])
    setSummary(null)
    setProgress({ index: 0, total: 0 })
    send({ type: 'conv_benchmark.start' })
  }, [send])

  return (
    <div className={styles.card}>
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          gap: 12,
        }}
      >
        <h3 style={{ margin: 0 }}>Conv Benchmark</h3>
        <button
          type="button"
          onClick={startBenchmark}
          disabled={running}
          style={{
            padding: '4px 12px',
            fontSize: 12,
            opacity: running ? 0.5 : 1,
          }}
        >
          {running ? 'Running...' : 'Run Benchmark'}
        </button>
      </div>

      {/* Progress bar */}
      {progress && progress.total > 0 && (
        <div style={{ marginTop: 8 }}>
          <div
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: 8,
              marginBottom: 4,
            }}
          >
            <span className={styles.mono} style={{ color: '#888', fontSize: 11 }}>
              {progress.index}/{progress.total}
            </span>
          </div>
          <div
            style={{
              height: 4,
              background: '#333',
              borderRadius: 2,
              overflow: 'hidden',
            }}
          >
            <div
              style={{
                width: `${(progress.index / progress.total) * 100}%`,
                height: '100%',
                background: 'var(--accent)',
                transition: 'width 200ms',
              }}
            />
          </div>
        </div>
      )}

      {/* Results table */}
      {results.length > 0 && (
        <div
          style={{
            marginTop: 8,
            overflow: 'auto',
            border: '1px solid rgba(255,255,255,0.06)',
            borderRadius: 6,
            background: 'rgba(0,0,0,0.12)',
          }}
        >
          <table
            className={styles.mono}
            style={{
              width: '100%',
              fontSize: 11,
              borderCollapse: 'collapse',
            }}
          >
            <thead>
              <tr style={{ color: '#888', textAlign: 'left' }}>
                <th style={{ padding: '4px 8px' }}>#</th>
                <th style={{ padding: '4px 8px' }}>Text</th>
                <th style={{ padding: '4px 8px', textAlign: 'right' }}>WS</th>
                <th style={{ padding: '4px 8px', textAlign: 'right' }}>LLM</th>
                <th style={{ padding: '4px 8px', textAlign: 'right' }}>TTS TTFB</th>
                <th style={{ padding: '4px 8px', textAlign: 'right' }}>Total</th>
              </tr>
            </thead>
            <tbody>
              {results.map((r) => (
                <tr key={r.index} style={{ borderTop: '1px solid rgba(255,255,255,0.04)' }}>
                  <td style={{ padding: '3px 8px', color: '#666' }}>{r.index + 1}</td>
                  <td
                    style={{
                      padding: '3px 8px',
                      maxWidth: 180,
                      overflow: 'hidden',
                      textOverflow: 'ellipsis',
                      whiteSpace: 'nowrap',
                    }}
                  >
                    {r.text}
                  </td>
                  {r.error ? (
                    <td colSpan={4} style={{ padding: '3px 8px', color: '#f44336' }}>
                      {r.error}
                    </td>
                  ) : (
                    <>
                      <td style={{ padding: '3px 8px', textAlign: 'right', color: '#888' }}>
                        {r.ws_connect_ms !== undefined ? `${r.ws_connect_ms.toFixed(0)}ms` : '—'}
                      </td>
                      <td style={{ padding: '3px 8px', textAlign: 'right' }}>
                        <div
                          style={{
                            display: 'flex',
                            flexDirection: 'column',
                            alignItems: 'flex-end',
                          }}
                        >
                          <span>
                            {r.llm_latency_ms !== undefined
                              ? `${r.llm_latency_ms.toFixed(0)}ms`
                              : '—'}
                          </span>
                          {r.llm_observed_ms !== undefined && (
                            <span style={{ color: '#777', fontSize: 10 }}>
                              obs {r.llm_observed_ms.toFixed(0)}ms
                            </span>
                          )}
                        </div>
                      </td>
                      <td style={{ padding: '3px 8px', textAlign: 'right' }}>
                        {r.tts_ttfb_ms !== undefined ? `${r.tts_ttfb_ms.toFixed(0)}ms` : '—'}
                      </td>
                      <td style={{ padding: '3px 8px', textAlign: 'right' }}>
                        {r.total_ms !== undefined ? `${r.total_ms.toFixed(0)}ms` : '—'}
                      </td>
                    </>
                  )}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Summary */}
      {summary && !summary.error && (
        <div
          className={styles.mono}
          style={{
            display: 'flex',
            gap: 16,
            marginTop: 8,
            fontSize: 11,
            flexWrap: 'wrap',
          }}
        >
          {summary.mean_ws_connect_ms !== undefined &&
            summary.p50_ws_connect_ms !== undefined &&
            summary.p95_ws_connect_ms !== undefined && (
              <span>
                WS mean/p50/p95{' '}
                <strong>
                  {summary.mean_ws_connect_ms.toFixed(0)}/{summary.p50_ws_connect_ms.toFixed(0)}/
                  {summary.p95_ws_connect_ms.toFixed(0)}ms
                </strong>
              </span>
            )}
          {summary.mean_llm_ms !== undefined &&
            summary.p50_llm_ms !== undefined &&
            summary.p95_llm_ms !== undefined && (
              <span>
                LLM mean/p50/p95{' '}
                <strong>
                  {summary.mean_llm_ms.toFixed(0)}/{summary.p50_llm_ms.toFixed(0)}/
                  {summary.p95_llm_ms.toFixed(0)}ms
                </strong>
              </span>
            )}
          {summary.mean_llm_observed_ms !== undefined &&
            summary.p50_llm_observed_ms !== undefined &&
            summary.p95_llm_observed_ms !== undefined && (
              <span>
                LLM(obs) mean/p50/p95{' '}
                <strong>
                  {summary.mean_llm_observed_ms.toFixed(0)}/{summary.p50_llm_observed_ms.toFixed(0)}
                  /{summary.p95_llm_observed_ms.toFixed(0)}ms
                </strong>
              </span>
            )}
          {summary.mean_tts_ttfb_ms !== undefined &&
            summary.p50_tts_ttfb_ms !== undefined &&
            summary.p95_tts_ttfb_ms !== undefined && (
              <span>
                TTS TTFB mean/p50/p95{' '}
                <strong>
                  {summary.mean_tts_ttfb_ms.toFixed(0)}/{summary.p50_tts_ttfb_ms.toFixed(0)}/
                  {summary.p95_tts_ttfb_ms.toFixed(0)}ms
                </strong>
              </span>
            )}
          {summary.mean_total_ms !== undefined &&
            summary.p50_total_ms !== undefined &&
            summary.p95_total_ms !== undefined && (
              <span>
                Total mean/p50/p95{' '}
                <strong>
                  {summary.mean_total_ms.toFixed(0)}/{summary.p50_total_ms.toFixed(0)}/
                  {summary.p95_total_ms.toFixed(0)}ms
                </strong>
              </span>
            )}
        </div>
      )}

      {summary?.error && (
        <div className={styles.mono} style={{ color: '#f44336', marginTop: 8, fontSize: 11 }}>
          Error: {summary.error}
        </div>
      )}

      {results.length === 0 && !running && (
        <div className={styles.mono} style={{ color: '#666', fontSize: 11, marginTop: 8 }}>
          Run a benchmark to measure LLM + TTS latency (text mode, no STT).
        </div>
      )}
    </div>
  )
}
