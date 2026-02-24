import { useCallback, useEffect, useRef, useState } from 'react'
import { useParamsList, useUpdateParams } from '../hooks/useParams'
import { useSend } from '../hooks/useSend'
import { useTelemetry } from '../hooks/useTelemetry'
import { debounce } from '../lib/debounce'
import { useConversationStore } from '../lib/wsConversation'
import { useTelemetryStore } from '../stores/telemetryStore'
import styles from '../styles/global.module.css'

// ── Mood Anchors (mirrors supervisor/personality/affect.py:22-36) ──

const MOOD_ANCHORS: [string, number, number][] = [
  ['neutral', 0.0, 0.0],
  ['happy', 0.7, 0.35],
  ['excited', 0.65, 0.8],
  ['curious', 0.4, 0.45],
  ['love', 0.8, 0.15],
  ['silly', 0.55, 0.6],
  ['thinking', 0.1, 0.2],
  ['surprised', 0.15, 0.8],
  ['sad', -0.6, -0.4],
  ['scared', -0.7, 0.65],
  ['angry', -0.6, 0.7],
  ['confused', -0.2, 0.3],
  ['sleepy', 0.05, -0.8],
]

const MOOD_COLORS: Record<string, string> = {
  neutral: '#888',
  happy: '#ffeb3b',
  excited: '#ff9800',
  curious: '#03a9f4',
  love: '#e91e63',
  silly: '#cddc39',
  thinking: '#9c27b0',
  surprised: '#ff5722',
  sad: '#2196f3',
  scared: '#607d8b',
  angry: '#f44336',
  confused: '#795548',
  sleepy: '#3f51b5',
}

const RISKY_BADGE = (
  <span
    className={styles.badge}
    style={{ background: '#ff9800', color: '#fff', fontSize: 9, padding: '1px 4px' }}
  >
    risky
  </span>
)

// ── VA Scatter Plot ──

function VAScatterPlot() {
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const trailRef = useRef<{ v: number; a: number; t: number }[]>([])

  useEffect(() => {
    if (!canvasRef.current) return

    const canvas = canvasRef.current
    const ctx = canvas.getContext('2d')
    if (!ctx) return

    const W = 280
    const H = 280
    const PAD = 30
    const plotW = W - PAD * 2
    const plotH = H - PAD * 2

    const toX = (v: number) => PAD + ((v + 1) / 2) * plotW
    const toY = (a: number) => PAD + ((1 - a) / 2) * plotH

    let animId = 0

    const draw = () => {
      const store = useTelemetryStore.getState()
      const snap = store.snapshot
      const v = typeof snap.personality_valence === 'number' ? snap.personality_valence : 0
      const a = typeof snap.personality_arousal === 'number' ? snap.personality_arousal : 0
      const mood = typeof snap.personality_mood === 'string' ? snap.personality_mood : 'neutral'

      const now = performance.now()
      trailRef.current.push({ v, a, t: now })
      const cutoff = now - 30000
      trailRef.current = trailRef.current.filter((p) => p.t > cutoff)

      ctx.clearRect(0, 0, W, H)

      ctx.fillStyle = 'rgba(0,0,0,0.3)'
      ctx.fillRect(0, 0, W, H)

      ctx.strokeStyle = 'rgba(255,255,255,0.08)'
      ctx.lineWidth = 1
      ctx.beginPath()
      ctx.moveTo(toX(0), PAD)
      ctx.lineTo(toX(0), H - PAD)
      ctx.moveTo(PAD, toY(0))
      ctx.lineTo(W - PAD, toY(0))
      ctx.stroke()

      ctx.fillStyle = '#666'
      ctx.font = '9px monospace'
      ctx.textAlign = 'center'
      ctx.fillText('Valence', W / 2, H - 4)
      ctx.save()
      ctx.translate(8, H / 2)
      ctx.rotate(-Math.PI / 2)
      ctx.fillText('Arousal', 0, 0)
      ctx.restore()
      ctx.fillText('-1', PAD, H - 4)
      ctx.fillText('+1', W - PAD, H - 4)
      ctx.textAlign = 'left'
      ctx.fillText('+1', 2, PAD + 4)
      ctx.fillText('-1', 2, H - PAD)

      for (const [name, mv, ma] of MOOD_ANCHORS) {
        const x = toX(mv)
        const y = toY(ma)
        ctx.beginPath()
        ctx.arc(x, y, 3, 0, Math.PI * 2)
        ctx.fillStyle = MOOD_COLORS[name] ?? '#888'
        ctx.globalAlpha = 0.5
        ctx.fill()
        ctx.globalAlpha = 1.0

        ctx.fillStyle = '#777'
        ctx.font = '8px monospace'
        ctx.textAlign = 'center'
        ctx.fillText(name, x, y - 6)
      }

      const trail = trailRef.current
      for (let i = 0; i < trail.length; i++) {
        const p = trail[i]
        const age = (now - p.t) / 30000
        const alpha = Math.max(0.05, 1.0 - age)
        ctx.beginPath()
        ctx.arc(toX(p.v), toY(p.a), 1.5, 0, Math.PI * 2)
        ctx.fillStyle = `rgba(100,180,255,${alpha.toFixed(2)})`
        ctx.fill()
      }

      const cx = toX(v)
      const cy = toY(a)
      ctx.beginPath()
      ctx.arc(cx, cy, 5, 0, Math.PI * 2)
      ctx.fillStyle = MOOD_COLORS[mood] ?? '#64b4ff'
      ctx.fill()
      ctx.strokeStyle = '#fff'
      ctx.lineWidth = 1.5
      ctx.stroke()

      animId = requestAnimationFrame(draw)
    }

    animId = requestAnimationFrame(draw)
    return () => cancelAnimationFrame(animId)
  }, [])

  return (
    <canvas
      ref={canvasRef}
      width={280}
      height={280}
      style={{ borderRadius: 6, border: '1px solid rgba(255,255,255,0.06)' }}
    />
  )
}

// ── Mood & Intensity Bar ──

function MoodBar() {
  const mood = useTelemetry((s) => s.snapshot.personality_mood)
  const intensity = useTelemetry((s) => s.snapshot.personality_intensity)
  const layer = useTelemetry((s) => s.snapshot.personality_layer)
  const idleState = useTelemetry((s) => s.snapshot.personality_idle_state)
  const convActive = useTelemetry((s) => s.snapshot.personality_conversation_active)

  const moodStr = typeof mood === 'string' ? mood : 'neutral'
  const intensityNum = typeof intensity === 'number' ? intensity : 0
  const layerNum = typeof layer === 'number' ? layer : 0
  const idleStr = typeof idleState === 'string' ? idleState : 'awake'
  const isConv = convActive === true

  const idleColor = idleStr === 'awake' ? '#4caf50' : idleStr === 'drowsy' ? '#ff9800' : '#2196f3'

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
        <span style={{ color: 'var(--text-dim)', fontSize: 11, width: 52 }}>Mood</span>
        <span
          className={styles.badge}
          style={{ background: MOOD_COLORS[moodStr] ?? '#888', color: '#fff' }}
        >
          {moodStr}
        </span>
        <div
          style={{
            flex: 1,
            height: 6,
            background: '#333',
            borderRadius: 3,
            overflow: 'hidden',
          }}
        >
          <div
            style={{
              width: `${(intensityNum * 100).toFixed(0)}%`,
              height: '100%',
              background: MOOD_COLORS[moodStr] ?? 'var(--accent)',
              transition: 'width 80ms linear',
            }}
          />
        </div>
        <span
          className={styles.mono}
          style={{ color: '#888', fontSize: 11, width: 32, textAlign: 'right' }}
        >
          {`${(intensityNum * 100).toFixed(0)}%`}
        </span>
      </div>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
        <span style={{ color: 'var(--text-dim)', fontSize: 11, width: 52 }}>Layer</span>
        <span className={styles.badge} style={{ background: '#555', color: '#ccc' }}>
          L{layerNum}
        </span>
        <span className={styles.badge} style={{ background: idleColor, color: '#fff' }}>
          {idleStr}
        </span>
        <span
          className={styles.badge}
          style={{ background: isConv ? '#4caf50' : '#555', color: '#fff' }}
        >
          {isConv ? 'conv active' : 'no conv'}
        </span>
      </div>
    </div>
  )
}

// ── Session Timers ──

function SessionTimers() {
  const sessionTimeS = useTelemetry((s) => s.snapshot.personality_session_time_s)
  const dailyTimeS = useTelemetry((s) => s.snapshot.personality_daily_time_s)
  const sessionLimitReached = useTelemetry((s) => s.snapshot.personality_session_limit_reached)
  const dailyLimitReached = useTelemetry((s) => s.snapshot.personality_daily_limit_reached)

  const sessionS = typeof sessionTimeS === 'number' ? sessionTimeS : 0
  const dailyS = typeof dailyTimeS === 'number' ? dailyTimeS : 0
  const sessionLimit = sessionLimitReached === true
  const dailyLimit = dailyLimitReached === true

  const sessionLimitS = 900
  const dailyLimitS = 2700

  const sessionPct = sessionLimitS > 0 ? Math.min(100, (sessionS / sessionLimitS) * 100) : 0
  const dailyPct = dailyLimitS > 0 ? Math.min(100, (dailyS / dailyLimitS) * 100) : 0

  const barColor = (pct: number) => (pct > 85 ? '#f44336' : pct > 60 ? '#ff9800' : '#4caf50')

  const fmtTime = (s: number) => {
    const m = Math.floor(s / 60)
    const sec = Math.floor(s % 60)
    return `${m}:${sec.toString().padStart(2, '0')}`
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
        <span style={{ color: 'var(--text-dim)', fontSize: 11, width: 52 }}>Session</span>
        <div
          style={{
            flex: 1,
            height: 6,
            background: '#333',
            borderRadius: 3,
            overflow: 'hidden',
          }}
        >
          <div
            style={{
              width: `${sessionPct.toFixed(0)}%`,
              height: '100%',
              background: barColor(sessionPct),
              transition: 'width 200ms linear',
            }}
          />
        </div>
        <span className={styles.mono} style={{ color: '#888', fontSize: 11, width: 64 }}>
          {fmtTime(sessionS)} / {fmtTime(sessionLimitS)}
        </span>
        {sessionLimit && (
          <span className={styles.badge} style={{ background: '#f44336', color: '#fff' }}>
            limit
          </span>
        )}
      </div>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
        <span style={{ color: 'var(--text-dim)', fontSize: 11, width: 52 }}>Daily</span>
        <div
          style={{
            flex: 1,
            height: 6,
            background: '#333',
            borderRadius: 3,
            overflow: 'hidden',
          }}
        >
          <div
            style={{
              width: `${dailyPct.toFixed(0)}%`,
              height: '100%',
              background: barColor(dailyPct),
              transition: 'width 200ms linear',
            }}
          />
        </div>
        <span className={styles.mono} style={{ color: '#888', fontSize: 11, width: 64 }}>
          {fmtTime(dailyS)} / {fmtTime(dailyLimitS)}
        </span>
        {dailyLimit && (
          <span className={styles.badge} style={{ background: '#f44336', color: '#fff' }}>
            limit
          </span>
        )}
      </div>
    </div>
  )
}

// ── Guardrail Status ──

function GuardrailStatus() {
  const [lastTrigger, setLastTrigger] = useState<{ rule: string; ts: number } | null>(null)
  const lastTriggerRef = useRef(lastTrigger)
  lastTriggerRef.current = lastTrigger

  useEffect(() => {
    return useConversationStore.subscribe((state) => {
      for (const e of state.events) {
        if (
          e.type === 'personality.event.guardrail_triggered' &&
          (!lastTriggerRef.current || e.ts_mono_ms > lastTriggerRef.current.ts)
        ) {
          setLastTrigger({ rule: String(e.rule ?? ''), ts: e.ts_mono_ms })
        }
      }
    })
  }, [])

  const agoS = lastTrigger != null ? Math.max(0, (performance.now() - lastTrigger.ts) / 1000) : null

  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
      <span style={{ color: 'var(--text-dim)', fontSize: 11, width: 52 }}>Guard</span>
      {lastTrigger ? (
        <>
          <span className={styles.badge} style={{ background: '#ff9800', color: '#fff' }}>
            {lastTrigger.rule}
          </span>
          <span className={styles.mono} style={{ color: '#888', fontSize: 11 }}>
            {agoS !== null ? `${agoS.toFixed(0)}s ago` : ''}
          </span>
        </>
      ) : (
        <span className={styles.mono} style={{ color: '#666', fontSize: 11 }}>
          no guardrail triggers
        </span>
      )}
    </div>
  )
}

// ── Personality Axes Sliders ──

const AXIS_DEFS = [
  { name: 'personality.energy', label: 'Energy', risky: true },
  { name: 'personality.reactivity', label: 'Reactivity', risky: true },
  { name: 'personality.initiative', label: 'Initiative', risky: true },
  { name: 'personality.vulnerability', label: 'Vulnerability', risky: true },
  { name: 'personality.predictability', label: 'Predictability', risky: false },
] as const

const AXIS_DEFAULTS: Record<string, number> = {
  'personality.energy': 0.4,
  'personality.reactivity': 0.5,
  'personality.initiative': 0.3,
  'personality.vulnerability': 0.35,
  'personality.predictability': 0.75,
}

function AxesControls() {
  const { data: paramsList } = useParamsList()
  const updateParams = useUpdateParams()
  const [local, setLocal] = useState<Record<string, number>>({})

  // Initialize from server params
  useEffect(() => {
    if (!paramsList) return
    const init: Record<string, number> = {}
    for (const p of paramsList) {
      if (p.name.startsWith('personality.') && !p.name.includes('guardrail')) {
        init[p.name] = typeof p.value === 'number' ? p.value : (p.default as number)
      }
    }
    setLocal((prev) => {
      if (Object.keys(prev).length === 0) return init
      return prev
    })
  }, [paramsList])

  const debouncedApply = useRef(
    debounce((items: Record<string, number>) => {
      updateParams.mutate(items)
    }, 300),
  ).current

  const handleChange = useCallback(
    (name: string, value: number) => {
      setLocal((prev) => {
        const next = { ...prev, [name]: value }
        debouncedApply({ [name]: value })
        return next
      })
    },
    [debouncedApply],
  )

  const resetDefaults = useCallback(() => {
    setLocal(AXIS_DEFAULTS)
    updateParams.mutate(AXIS_DEFAULTS)
  }, [updateParams])

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
        <span style={{ color: 'var(--text-dim)', fontSize: 11, fontWeight: 600 }}>
          Personality Axes
        </span>
        <button
          type="button"
          onClick={resetDefaults}
          style={{
            padding: '2px 8px',
            fontSize: 10,
            border: '1px solid #555',
            borderRadius: 4,
            background: '#1a1a2e',
            color: '#888',
            cursor: 'pointer',
          }}
        >
          Reset defaults
        </button>
      </div>
      {AXIS_DEFS.map((axis) => (
        <div key={axis.name} style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <span style={{ color: '#aaa', fontSize: 11, width: 90 }}>
            {axis.label} {axis.risky && RISKY_BADGE}
          </span>
          <input
            type="range"
            min={0}
            max={1}
            step={0.05}
            value={local[axis.name] ?? AXIS_DEFAULTS[axis.name]}
            onChange={(e) => handleChange(axis.name, Number(e.target.value))}
            style={{ flex: 1 }}
          />
          <span className={styles.mono} style={{ color: '#888', fontSize: 11, width: 28 }}>
            {(local[axis.name] ?? AXIS_DEFAULTS[axis.name]).toFixed(2)}
          </span>
        </div>
      ))}
    </div>
  )
}

// ── Guardrail Toggles ──

function GuardrailControls() {
  const { data: paramsList } = useParamsList()
  const updateParams = useUpdateParams()
  const send = useSend()

  const [bools, setBools] = useState<Record<string, boolean>>({
    'personality.guardrail.negative_duration_caps': true,
    'personality.guardrail.negative_intensity_caps': true,
    'personality.guardrail.context_gate': true,
  })
  const [sliders, setSliders] = useState<Record<string, number>>({
    'personality.guardrail.session_time_limit_s': 900,
    'personality.guardrail.daily_time_limit_s': 2700,
  })

  useEffect(() => {
    if (!paramsList) return
    const b: Record<string, boolean> = {}
    const s: Record<string, number> = {}
    for (const p of paramsList) {
      if (p.name === 'personality.guardrail.negative_duration_caps') b[p.name] = !!p.value
      else if (p.name === 'personality.guardrail.negative_intensity_caps') b[p.name] = !!p.value
      else if (p.name === 'personality.guardrail.context_gate') b[p.name] = !!p.value
      else if (p.name === 'personality.guardrail.session_time_limit_s') s[p.name] = p.value
      else if (p.name === 'personality.guardrail.daily_time_limit_s') s[p.name] = p.value
    }
    if (Object.keys(b).length > 0) setBools((prev) => (Object.keys(prev).length === 3 ? b : prev))
    if (Object.keys(s).length > 0) setSliders((prev) => ({ ...prev, ...s }))
  }, [paramsList])

  const debouncedSlider = useRef(
    debounce((items: Record<string, number>) => {
      updateParams.mutate(items)
    }, 300),
  ).current

  const toggleBool = useCallback(
    (name: string, value: boolean) => {
      setBools((prev) => ({ ...prev, [name]: value }))
      updateParams.mutate({ [name]: value })
    },
    [updateParams],
  )

  const handleSlider = useCallback(
    (name: string, value: number) => {
      setSliders((prev) => ({ ...prev, [name]: value }))
      debouncedSlider({ [name]: value })
    },
    [debouncedSlider],
  )

  const fmtTime = (s: number) => {
    const m = Math.floor(s / 60)
    return `${m} min`
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
        <span style={{ color: 'var(--text-dim)', fontSize: 11, fontWeight: 600 }}>Guardrails</span>
        <button
          type="button"
          onClick={() => send({ type: 'personality.set_guardrail', reset_daily: true })}
          style={{
            padding: '2px 8px',
            fontSize: 10,
            border: '1px solid #555',
            borderRadius: 4,
            background: '#1a1a2e',
            color: '#888',
            cursor: 'pointer',
          }}
        >
          Reset daily timer
        </button>
      </div>
      {[
        { name: 'personality.guardrail.negative_duration_caps', label: 'Duration caps' },
        { name: 'personality.guardrail.negative_intensity_caps', label: 'Intensity caps' },
        { name: 'personality.guardrail.context_gate', label: 'Context gate' },
      ].map((g) => (
        <label
          key={g.name}
          style={{ display: 'flex', alignItems: 'center', gap: 8, color: '#aaa', fontSize: 11 }}
        >
          <input
            type="checkbox"
            checked={bools[g.name] ?? true}
            onChange={(e) => toggleBool(g.name, e.target.checked)}
          />
          {g.label} {RISKY_BADGE}
        </label>
      ))}
      {[
        {
          name: 'personality.guardrail.session_time_limit_s',
          label: 'Session limit',
          max: 7200,
        },
        {
          name: 'personality.guardrail.daily_time_limit_s',
          label: 'Daily limit',
          max: 14400,
        },
      ].map((s) => (
        <div key={s.name} style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <span style={{ color: '#aaa', fontSize: 11, width: 90 }}>
            {s.label} {RISKY_BADGE}
          </span>
          <input
            type="range"
            min={0}
            max={s.max}
            step={60}
            value={sliders[s.name] ?? 900}
            onChange={(e) => handleSlider(s.name, Number(e.target.value))}
            style={{ flex: 1 }}
          />
          <span className={styles.mono} style={{ color: '#888', fontSize: 11, width: 42 }}>
            {fmtTime(sliders[s.name] ?? 900)}
          </span>
        </div>
      ))}
    </div>
  )
}

// ── Debug Impulse Injection ──

function ImpulseInjector() {
  const send = useSend()
  const [valence, setValence] = useState(0.0)
  const [arousal, setArousal] = useState(0.0)
  const [magnitude, setMagnitude] = useState(0.5)

  const inject = useCallback(() => {
    send({ type: 'personality.override_affect', valence, arousal, magnitude })
  }, [send, valence, arousal, magnitude])

  const preset = useCallback(
    (v: number, a: number, m: number) => {
      setValence(v)
      setArousal(a)
      setMagnitude(m)
      send({ type: 'personality.override_affect', valence: v, arousal: a, magnitude: m })
    },
    [send],
  )

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
      <span style={{ color: 'var(--text-dim)', fontSize: 11, fontWeight: 600 }}>
        Debug Impulse Injection
      </span>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
        <span style={{ color: '#aaa', fontSize: 11, width: 60 }}>Valence</span>
        <input
          type="range"
          min={-1}
          max={1}
          step={0.05}
          value={valence}
          onChange={(e) => setValence(Number(e.target.value))}
          style={{ flex: 1 }}
        />
        <span className={styles.mono} style={{ color: '#888', fontSize: 11, width: 36 }}>
          {valence.toFixed(2)}
        </span>
      </div>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
        <span style={{ color: '#aaa', fontSize: 11, width: 60 }}>Arousal</span>
        <input
          type="range"
          min={-1}
          max={1}
          step={0.05}
          value={arousal}
          onChange={(e) => setArousal(Number(e.target.value))}
          style={{ flex: 1 }}
        />
        <span className={styles.mono} style={{ color: '#888', fontSize: 11, width: 36 }}>
          {arousal.toFixed(2)}
        </span>
      </div>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
        <span style={{ color: '#aaa', fontSize: 11, width: 60 }}>Magnitude</span>
        <input
          type="range"
          min={0}
          max={1}
          step={0.05}
          value={magnitude}
          onChange={(e) => setMagnitude(Number(e.target.value))}
          style={{ flex: 1 }}
        />
        <span className={styles.mono} style={{ color: '#888', fontSize: 11, width: 36 }}>
          {magnitude.toFixed(2)}
        </span>
      </div>
      <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
        <button type="button" onClick={inject} style={{ padding: '4px 10px', fontSize: 11 }}>
          Inject
        </button>
        <button
          type="button"
          onClick={() => preset(0.7, 0.3, 0.6)}
          style={{ padding: '4px 10px', fontSize: 11 }}
        >
          Happy boost
        </button>
        <button
          type="button"
          onClick={() => preset(0.1, -0.5, 0.5)}
          style={{ padding: '4px 10px', fontSize: 11 }}
        >
          Calm down
        </button>
        <button
          type="button"
          onClick={() => preset(0.5, 0.8, 0.7)}
          style={{ padding: '4px 10px', fontSize: 11 }}
        >
          Excite
        </button>
        <button
          type="button"
          onClick={() => preset(0.0, 0.0, 1.0)}
          style={{ padding: '4px 10px', fontSize: 11 }}
        >
          Reset baseline
        </button>
      </div>
    </div>
  )
}

// ── Main Panel ──

export default function PersonalityPanel() {
  return (
    <div className={styles.card}>
      <h3>Personality Engine</h3>
      <div style={{ display: 'flex', gap: 16, marginTop: 8, flexWrap: 'wrap' }}>
        {/* Left: VA Scatter */}
        <VAScatterPlot />

        {/* Right: Status panels */}
        <div style={{ flex: 1, minWidth: 250, display: 'flex', flexDirection: 'column', gap: 12 }}>
          <MoodBar />
          <SessionTimers />
          <GuardrailStatus />
        </div>
      </div>

      {/* Tuning controls */}
      <div
        style={{
          display: 'flex',
          gap: 24,
          marginTop: 16,
          flexWrap: 'wrap',
          borderTop: '1px solid rgba(255,255,255,0.06)',
          paddingTop: 12,
        }}
      >
        <div style={{ flex: 1, minWidth: 260 }}>
          <AxesControls />
        </div>
        <div style={{ flex: 1, minWidth: 260 }}>
          <GuardrailControls />
        </div>
      </div>

      {/* Impulse injection */}
      <div
        style={{
          marginTop: 12,
          borderTop: '1px solid rgba(255,255,255,0.06)',
          paddingTop: 12,
        }}
      >
        <ImpulseInjector />
      </div>
    </div>
  )
}
