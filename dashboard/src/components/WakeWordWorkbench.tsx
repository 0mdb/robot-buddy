import { useCallback, useEffect, useRef, useState } from 'react'
import { useSend } from '../hooks/useSend'
import { debounce } from '../lib/debounce'
import { useConversationStore } from '../lib/wsConversation'
import styles from '../styles/global.module.css'

const MAX_SCORE_HISTORY = 62 // ~5s at 12.5 Hz
const MAX_DETECTIONS = 20

interface ScoreEntry {
  ts: number
  score: number
}

interface Detection {
  ts: number
  model: string
  score: number
}

export default function WakeWordWorkbench() {
  const send = useSend()
  const [scoreHistory, setScoreHistory] = useState<ScoreEntry[]>([])
  const [threshold, setThreshold] = useState(0.5)
  const [detections, setDetections] = useState<Detection[]>([])
  const [soakActive, setSoakActive] = useState(false)
  const [soakStart, setSoakStart] = useState(0)
  const [soakFpCount, setSoakFpCount] = useState(0)
  const [soakElapsed, setSoakElapsed] = useState(0)
  const versionRef = useRef(0)
  const soakTimerRef = useRef<ReturnType<typeof setInterval> | null>(null)

  // Enable score streaming on mount, disable on unmount
  useEffect(() => {
    send({ type: 'ear.stream_scores', enabled: true })
    return () => {
      send({ type: 'ear.stream_scores', enabled: false })
    }
  }, [send])

  // Subscribe to conversation events for OWW scores and wake word detections
  useEffect(() => {
    const unsub = useConversationStore.subscribe((state) => {
      if (state.version === versionRef.current) return
      versionRef.current = state.version

      const latest = state.events[state.events.length - 1]
      if (!latest) return

      if (latest.type === 'ear.event.oww_score') {
        const scores = latest.scores as Record<string, number> | undefined
        if (scores) {
          // Use the first model's score (typically "hey_buddy")
          const score = Object.values(scores)[0] ?? 0
          setScoreHistory((prev) => {
            const next = [...prev, { ts: latest.ts_mono_ms, score }]
            return next.length > MAX_SCORE_HISTORY ? next.slice(-MAX_SCORE_HISTORY) : next
          })
          // Update threshold from server if provided
          const serverThreshold = latest.threshold as number | undefined
          if (serverThreshold !== undefined) {
            setThreshold(serverThreshold)
          }
        }
      } else if (latest.type === 'ear.event.wake_word') {
        const model = (latest.model as string) ?? '?'
        const score = (latest.score as number) ?? 0
        setDetections((prev) => {
          const next = [...prev, { ts: latest.ts_mono_ms, model, score }]
          return next.length > MAX_DETECTIONS ? next.slice(-MAX_DETECTIONS) : next
        })
        setSoakFpCount((prev) => prev + 1)
      }
    })
    return unsub
  }, [])

  // Debounced threshold sender
  const debouncedThreshold = useRef(
    debounce((val: number) => {
      send({ type: 'ear.set_threshold', threshold: val })
    }, 200),
  ).current

  const handleThresholdChange = useCallback(
    (val: number) => {
      setThreshold(val)
      debouncedThreshold(val)
    },
    [debouncedThreshold],
  )

  // Soak test timer
  const startSoak = useCallback(() => {
    setSoakActive(true)
    setSoakFpCount(0)
    setSoakStart(Date.now())
    setSoakElapsed(0)
    soakTimerRef.current = setInterval(() => {
      setSoakElapsed(Date.now() - Date.now()) // will be corrected below
    }, 1000)
  }, [])

  // Fix the timer to use soakStart properly
  useEffect(() => {
    if (!soakActive) return
    const timer = setInterval(() => {
      setSoakElapsed(Math.floor((Date.now() - soakStart) / 1000))
    }, 1000)
    return () => clearInterval(timer)
  }, [soakActive, soakStart])

  const stopSoak = useCallback(() => {
    setSoakActive(false)
    if (soakTimerRef.current) {
      clearInterval(soakTimerRef.current)
      soakTimerRef.current = null
    }
  }, [])

  const fpPerHour = soakElapsed > 0 ? (soakFpCount / soakElapsed) * 3600 : 0

  return (
    <div className={styles.card}>
      <h3>Wake Word Workbench</h3>

      <div style={{ display: 'flex', flexDirection: 'column', gap: 10, marginTop: 4 }}>
        {/* Score sparkline */}
        <div>
          <span className={styles.mono} style={{ color: 'var(--text-dim)', fontSize: 11 }}>
            OWW Score (5s window, 12.5 Hz)
          </span>
          <div
            style={{
              position: 'relative',
              height: 60,
              display: 'flex',
              alignItems: 'flex-end',
              gap: 1,
              marginTop: 4,
              background: 'rgba(0,0,0,0.12)',
              border: '1px solid rgba(255,255,255,0.06)',
              borderRadius: 6,
              padding: '4px 2px',
              overflow: 'hidden',
            }}
          >
            {scoreHistory.map((s, i) => {
              const pct = Math.min(1, Math.max(0, s.score)) * 100
              return (
                <div
                  key={`${s.ts}-${i}`}
                  style={{
                    flex: 1,
                    height: `${pct}%`,
                    minWidth: 2,
                    background: s.score >= threshold ? '#f44336' : '#4caf50',
                    borderRadius: '1px 1px 0 0',
                    opacity: 0.85,
                  }}
                />
              )
            })}
            {/* Threshold line */}
            <div
              style={{
                position: 'absolute',
                left: 0,
                right: 0,
                bottom: `${threshold * 100}%`,
                height: 0,
                borderTop: '1px dashed #ff9800',
                pointerEvents: 'none',
              }}
            />
            {/* Threshold label */}
            <span
              className={styles.mono}
              style={{
                position: 'absolute',
                right: 4,
                bottom: `calc(${threshold * 100}% + 2px)`,
                fontSize: 9,
                color: '#ff9800',
                pointerEvents: 'none',
              }}
            >
              {threshold.toFixed(2)}
            </span>
            {scoreHistory.length === 0 && (
              <span
                className={styles.mono}
                style={{
                  position: 'absolute',
                  left: '50%',
                  top: '50%',
                  transform: 'translate(-50%, -50%)',
                  fontSize: 10,
                  color: '#666',
                }}
              >
                Waiting for scores...
              </span>
            )}
          </div>
        </div>

        {/* Threshold slider */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <label style={{ fontSize: 11, color: 'var(--text-dim)', whiteSpace: 'nowrap' }}>
            Threshold
          </label>
          <input
            type="range"
            min={0}
            max={1}
            step={0.01}
            value={threshold}
            onChange={(e) => handleThresholdChange(Number(e.target.value))}
            style={{ flex: 1 }}
          />
          <span
            className={styles.mono}
            style={{ fontSize: 11, color: '#aaa', width: 36, textAlign: 'right' }}
          >
            {threshold.toFixed(2)}
          </span>
        </div>

        {/* Soak test */}
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: 12,
            flexWrap: 'wrap',
          }}
        >
          <button
            type="button"
            onClick={soakActive ? stopSoak : startSoak}
            style={{
              padding: '4px 12px',
              fontSize: 11,
              border: `1px solid ${soakActive ? '#f44336' : '#333'}`,
              borderRadius: 4,
              background: soakActive ? 'rgba(244,67,54,0.15)' : '#1a1a2e',
              color: soakActive ? '#f44336' : '#888',
              cursor: 'pointer',
            }}
          >
            {soakActive ? 'Stop Soak' : 'Start Soak Test'}
          </button>
          {(soakActive || soakElapsed > 0) && (
            <>
              <span className={styles.mono} style={{ fontSize: 11, color: '#888' }}>
                {formatDuration(soakElapsed)}
              </span>
              <span className={styles.mono} style={{ fontSize: 11, color: '#aaa' }}>
                {soakFpCount} detection{soakFpCount !== 1 ? 's' : ''}
              </span>
              <span
                className={styles.mono}
                style={{
                  fontSize: 11,
                  color: soakFpCount > 0 ? '#ff9800' : '#4caf50',
                }}
              >
                {fpPerHour.toFixed(1)}/hr
              </span>
            </>
          )}
        </div>

        {/* Detection log */}
        <div>
          <span className={styles.mono} style={{ color: 'var(--text-dim)', fontSize: 11 }}>
            Recent Detections ({detections.length})
          </span>
          <div
            style={{
              maxHeight: 120,
              overflow: 'auto',
              border: '1px solid rgba(255,255,255,0.06)',
              borderRadius: 6,
              padding: 6,
              background: 'rgba(0,0,0,0.12)',
              marginTop: 4,
            }}
          >
            {detections.length === 0 ? (
              <span className={styles.mono} style={{ color: '#666', fontSize: 11 }}>
                No detections yet.
              </span>
            ) : (
              detections
                .slice()
                .reverse()
                .map((d, i) => (
                  <div key={`${d.ts}-${i}`} className={styles.mono} style={{ fontSize: 11 }}>
                    <span style={{ color: '#777' }}>{d.model}</span>{' '}
                    <span
                      style={{
                        color: d.score >= 0.8 ? '#f44336' : d.score >= 0.6 ? '#ff9800' : '#aaa',
                      }}
                    >
                      score={d.score.toFixed(3)}
                    </span>
                  </div>
                ))
            )}
          </div>
        </div>
      </div>
    </div>
  )
}

function formatDuration(seconds: number): string {
  const m = Math.floor(seconds / 60)
  const s = seconds % 60
  return `${m}:${s.toString().padStart(2, '0')}`
}
