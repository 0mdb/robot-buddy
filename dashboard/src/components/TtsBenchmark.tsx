import { useCallback, useEffect, useRef, useState } from 'react'
import { useSend } from '../hooks/useSend'
import { type ConversationEvent, useConversationStore } from '../lib/wsConversation'
import styles from '../styles/global.module.css'

interface BenchmarkResult {
  index: number
  total: number
  text: string
  emotion: string
  ttfb_ms?: number
  total_ms?: number
  audio_duration_ms?: number
  chunk_count?: number
  error?: string
}

interface BenchmarkSummary {
  count: number
  mean_ttfb_ms?: number
  p50_ttfb_ms?: number
  p95_ttfb_ms?: number
  mean_total_ms?: number
  error?: string
}

export default function TtsBenchmark() {
  const send = useSend()
  const [running, setRunning] = useState(false)
  const [results, setResults] = useState<BenchmarkResult[]>([])
  const [summary, setSummary] = useState<BenchmarkSummary | null>(null)
  const [progress, setProgress] = useState<{ index: number; total: number } | null>(null)
  const versionRef = useRef(0)

  // Subscribe to conversation events for benchmark results
  useEffect(() => {
    const unsub = useConversationStore.subscribe((state) => {
      if (state.version === versionRef.current) return
      versionRef.current = state.version

      // Process only latest event
      const latest = state.events[state.events.length - 1]
      if (!latest) return

      if (latest.type === 'tts.benchmark.progress') {
        const r = latest as unknown as ConversationEvent & BenchmarkResult
        setResults((prev) => [...prev, r])
        setProgress({ index: (r.index ?? 0) + 1, total: r.total ?? 0 })
      } else if (latest.type === 'tts.benchmark.done') {
        const s = latest as unknown as ConversationEvent & BenchmarkSummary
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
    send({ type: 'tts_benchmark.start' })
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
        <h3 style={{ margin: 0 }}>TTS Benchmark</h3>
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
                <th style={{ padding: '4px 8px' }}>Emotion</th>
                <th style={{ padding: '4px 8px', textAlign: 'right' }}>TTFB</th>
                <th style={{ padding: '4px 8px', textAlign: 'right' }}>Total</th>
                <th style={{ padding: '4px 8px', textAlign: 'right' }}>Audio</th>
                <th style={{ padding: '4px 8px', textAlign: 'right' }}>Chunks</th>
              </tr>
            </thead>
            <tbody>
              {results.map((r) => (
                <tr key={r.index} style={{ borderTop: '1px solid rgba(255,255,255,0.04)' }}>
                  <td style={{ padding: '3px 8px', color: '#666' }}>{r.index + 1}</td>
                  <td
                    style={{
                      padding: '3px 8px',
                      maxWidth: 200,
                      overflow: 'hidden',
                      textOverflow: 'ellipsis',
                      whiteSpace: 'nowrap',
                    }}
                  >
                    {r.text}
                  </td>
                  <td style={{ padding: '3px 8px', color: '#888' }}>{r.emotion}</td>
                  {r.error ? (
                    <td colSpan={4} style={{ padding: '3px 8px', color: '#f44336' }}>
                      {r.error}
                    </td>
                  ) : (
                    <>
                      <td style={{ padding: '3px 8px', textAlign: 'right' }}>
                        {r.ttfb_ms?.toFixed(0)}ms
                      </td>
                      <td style={{ padding: '3px 8px', textAlign: 'right' }}>
                        {r.total_ms?.toFixed(0)}ms
                      </td>
                      <td style={{ padding: '3px 8px', textAlign: 'right', color: '#888' }}>
                        {r.audio_duration_ms?.toFixed(0)}ms
                      </td>
                      <td style={{ padding: '3px 8px', textAlign: 'right', color: '#888' }}>
                        {r.chunk_count}
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
          {summary.mean_ttfb_ms !== undefined && (
            <span>
              TTFB mean <strong>{summary.mean_ttfb_ms.toFixed(0)}ms</strong>
            </span>
          )}
          {summary.p50_ttfb_ms !== undefined && (
            <span>
              p50 <strong>{summary.p50_ttfb_ms.toFixed(0)}ms</strong>
            </span>
          )}
          {summary.p95_ttfb_ms !== undefined && (
            <span>
              p95 <strong>{summary.p95_ttfb_ms.toFixed(0)}ms</strong>
            </span>
          )}
          {summary.mean_total_ms !== undefined && (
            <span>
              Total mean <strong>{summary.mean_total_ms.toFixed(0)}ms</strong>
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
          Run a benchmark to measure TTS synthesis latency across a fixed corpus.
        </div>
      )}
    </div>
  )
}
