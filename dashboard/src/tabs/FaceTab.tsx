import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { FACE_FLAGS, GESTURES, MOODS, SYSTEM_MODES } from '../constants'
import { useSend } from '../hooks/useSend'
import { useTelemetry } from '../hooks/useTelemetry'
import { debounce } from '../lib/debounce'
import styles from '../styles/global.module.css'

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const CONV_STATE_NAMES = [
  'IDLE',
  'ATTENTION',
  'LISTENING',
  'PTT',
  'THINKING',
  'SPEAKING',
  'ERROR',
  'DONE',
]
const CONV_STATE_COLORS = [
  '#444',
  '#ff9800',
  '#2196f3',
  '#42a5f5',
  '#9c27b0',
  '#4caf50',
  '#f44336',
  '#444',
]

const SEQ_PHASE_NAMES = ['IDLE', 'ANTICIPATION', 'RAMP_DOWN', 'SWITCH', 'RAMP_UP']

// Mood ID → name (must match FaceMood enum in protocol.py)
const MOOD_ID_NAMES = [
  'neutral',
  'happy',
  'excited',
  'curious',
  'sad',
  'scared',
  'angry',
  'surprised',
  'sleepy',
  'love',
  'silly',
  'thinking',
  'confused',
]

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface FaceState {
  mood: string
  intensity: number
  brightness: number
  gazeX: number
  gazeY: number
}

interface FlagState {
  idle_wander: boolean
  autoblink: boolean
  solid_eye: boolean
  show_mouth: boolean
  edge_glow: boolean
  sparkle: boolean
  afterglow: boolean
}

// ---------------------------------------------------------------------------
// Main Tab
// ---------------------------------------------------------------------------

export default function FaceTab() {
  const send = useSend()

  // -- Telemetry --
  const faceConnected = useTelemetry((s) => s.snapshot.face_connected)
  const faceRxMs = useTelemetry((s) => s.snapshot.face_rx_mono_ms)
  const tickMonoMs = useTelemetry((s) => s.snapshot.tick_mono_ms)
  const currentMood = useTelemetry((s) => s.snapshot.face_mood)
  const currentFlags = useTelemetry((s) => s.snapshot.face_manual_flags)
  const currentManualLock = useTelemetry((s) => s.snapshot.face_manual_lock)
  const currentTalking = useTelemetry((s) => s.snapshot.face_talking)
  const currentTalkingEnergy = useTelemetry((s) => s.snapshot.face_talking_energy)

  // Conversation state + mood sequencer (read-only display)
  // snapshot is Record<string, unknown>, so narrow each field to its expected type.
  const convStateRaw = useTelemetry((s) => s.snapshot.face_conv_state)
  const convTimerMsRaw = useTelemetry((s) => s.snapshot.face_conv_timer_ms)
  const seqPhaseRaw = useTelemetry((s) => s.snapshot.face_seq_phase)
  const seqMoodIdRaw = useTelemetry((s) => s.snapshot.face_seq_mood_id)
  const seqIntensityRaw = useTelemetry((s) => s.snapshot.face_seq_intensity)
  const choreoActiveRaw = useTelemetry((s) => s.snapshot.face_choreo_active)
  const convState = typeof convStateRaw === 'number' ? convStateRaw : 0
  const convTimerMs = typeof convTimerMsRaw === 'number' ? convTimerMsRaw : null
  const seqPhase = typeof seqPhaseRaw === 'number' ? seqPhaseRaw : 0
  const seqMoodId = typeof seqMoodIdRaw === 'number' ? seqMoodIdRaw : 0
  const seqIntensity = typeof seqIntensityRaw === 'number' ? seqIntensityRaw : 0
  const choreoActive = choreoActiveRaw === true

  // -- Local state: mood/gaze/brightness --
  const [face, setFace] = useState<FaceState>({
    mood: 'neutral',
    intensity: 200,
    brightness: 180,
    gazeX: 0,
    gazeY: 0,
  })

  // Sync mood from telemetry on first connection
  useEffect(() => {
    if (typeof currentMood === 'string' && currentMood) {
      setFace((prev) => ({ ...prev, mood: currentMood }))
    }
  }, [currentMood])

  // -- Local state: system mode --
  const [sysMode, setSysMode] = useState('NONE')
  const [sysParam, setSysParam] = useState(0)

  // -- Local state: talking --
  const [talking, setTalking] = useState(false)
  const [talkEnergy, setTalkEnergy] = useState(128)

  // Sync talking state from telemetry
  useEffect(() => {
    if (typeof currentTalking === 'boolean') setTalking(currentTalking)
  }, [currentTalking])
  useEffect(() => {
    if (typeof currentTalkingEnergy === 'number') setTalkEnergy(currentTalkingEnergy)
  }, [currentTalkingEnergy])

  // -- Local state: flags --
  const [flags, setFlags] = useState<FlagState>({
    idle_wander: true,
    autoblink: true,
    solid_eye: false,
    show_mouth: true,
    edge_glow: false,
    sparkle: false,
    afterglow: false,
  })

  // Sync flags from telemetry bitmask
  useEffect(() => {
    if (typeof currentFlags === 'number') {
      setFlags({
        idle_wander: !!(currentFlags & (1 << 0)),
        autoblink: !!(currentFlags & (1 << 1)),
        solid_eye: !!(currentFlags & (1 << 2)),
        show_mouth: !!(currentFlags & (1 << 3)),
        edge_glow: !!(currentFlags & (1 << 4)),
        sparkle: !!(currentFlags & (1 << 5)),
        afterglow: !!(currentFlags & (1 << 6)),
      })
    }
  }, [currentFlags])

  // -- Local state: manual lock --
  const [manualLock, setManualLock] = useState(false)

  useEffect(() => {
    if (typeof currentManualLock === 'boolean') setManualLock(currentManualLock)
  }, [currentManualLock])

  // -- Debounced senders --
  const debouncedFaceState = useRef(
    debounce((s: FaceState) => {
      send({
        type: 'face_set_state',
        emotion: s.mood,
        intensity: s.intensity / 255,
        gaze_x: s.gazeX / 127,
        gaze_y: s.gazeY / 127,
        brightness: s.brightness / 255,
      })
    }, 150),
  ).current

  const debouncedSysMode = useRef(
    debounce((mode: string, param: number) => {
      send({ type: 'face_set_system', mode, param })
    }, 150),
  ).current

  const debouncedTalking = useRef(
    debounce((t: boolean, e: number) => {
      send({ type: 'face_set_talking', talking: t, energy: e })
    }, 150),
  ).current

  // -- Face state update helper --
  const updateFace = useCallback(
    (patch: Partial<FaceState>) => {
      setFace((prev) => {
        const next = { ...prev, ...patch }
        debouncedFaceState(next)
        return next
      })
    },
    [debouncedFaceState],
  )

  // -- Send flags --
  const sendFlags = useCallback(
    (f: FlagState) => {
      send({
        type: 'face_set_flags',
        idle_wander: f.idle_wander,
        autoblink: f.autoblink,
        solid_eye: f.solid_eye,
        show_mouth: f.show_mouth,
        edge_glow: f.edge_glow,
        sparkle: f.sparkle,
        afterglow: f.afterglow,
      })
    },
    [send],
  )

  // -- Connection age --
  const ageMs = useMemo(() => {
    if (typeof faceRxMs === 'number' && typeof tickMonoMs === 'number') {
      return Math.max(0, tickMonoMs - faceRxMs)
    }
    return null
  }, [faceRxMs, tickMonoMs])

  return (
    <div style={{ padding: 16, display: 'flex', flexDirection: 'column', gap: 12 }}>
      {/* Connection status */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
        <span className={`${styles.badge} ${faceConnected ? styles.badgeGreen : styles.badgeRed}`}>
          {faceConnected ? 'Face Connected' : 'Face Disconnected'}
        </span>
        {ageMs !== null && (
          <span className={styles.mono} style={{ color: '#888', fontSize: 11 }}>
            {ageMs.toFixed(0)} ms ago
          </span>
        )}
      </div>

      {/* Face State — read-only conversation + sequencer display */}
      <div className={styles.card}>
        <h3>Face State</h3>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 6, marginTop: 4 }}>
          {/* Conversation state */}
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <span style={{ color: 'var(--text-dim)', fontSize: 11, width: 52 }}>Conv</span>
            <span
              className={styles.badge}
              style={{
                background: CONV_STATE_COLORS[convState] ?? '#444',
                color: '#fff',
              }}
            >
              {CONV_STATE_NAMES[convState] ?? '?'}
            </span>
            <span className={styles.mono} style={{ color: '#888', fontSize: 11 }}>
              {convTimerMs !== null ? `${convTimerMs} ms` : '—'}
            </span>
          </div>

          {/* Mood sequencer */}
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <span style={{ color: 'var(--text-dim)', fontSize: 11, width: 52 }}>Mood</span>
            <span className={styles.mono} style={{ minWidth: 72 }}>
              {MOOD_ID_NAMES[seqMoodId] ?? '?'}
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
                  width: `${(seqIntensity * 100).toFixed(0)}%`,
                  height: '100%',
                  background: 'var(--accent)',
                  transition: 'width 80ms linear',
                }}
              />
            </div>
            <span
              className={styles.mono}
              style={{ color: '#888', fontSize: 11, width: 32, textAlign: 'right' }}
            >
              {`${(seqIntensity * 100).toFixed(0)}%`}
            </span>
          </div>

          {/* Sequencer phase + choreography */}
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <span style={{ color: 'var(--text-dim)', fontSize: 11, width: 52 }}>Phase</span>
            <span className={styles.mono}>{SEQ_PHASE_NAMES[seqPhase] ?? '?'}</span>
            {choreoActive && (
              <span className={styles.badge} style={{ background: '#9c27b0', color: '#fff' }}>
                choreo
              </span>
            )}
          </div>
        </div>
      </div>

      {/* Mood section */}
      <div className={styles.card}>
        <h3>Mood</h3>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 8, marginTop: 4 }}>
          <label>
            Emotion
            <select
              value={face.mood}
              onChange={(e) => updateFace({ mood: e.target.value })}
              style={{ marginLeft: 8, minWidth: 140 }}
            >
              {MOODS.map((m) => (
                <option key={m} value={m}>
                  {m}
                </option>
              ))}
            </select>
          </label>

          <label>
            Intensity: {face.intensity}
            <input
              type="range"
              min={0}
              max={255}
              value={face.intensity}
              onChange={(e) => updateFace({ intensity: Number(e.target.value) })}
            />
          </label>

          <label>
            Brightness: {face.brightness}
            <input
              type="range"
              min={0}
              max={255}
              value={face.brightness}
              onChange={(e) => updateFace({ brightness: Number(e.target.value) })}
            />
          </label>

          <label>
            Gaze X: {face.gazeX}
            <input
              type="range"
              min={-128}
              max={127}
              value={face.gazeX}
              onChange={(e) => updateFace({ gazeX: Number(e.target.value) })}
            />
          </label>

          <label>
            Gaze Y: {face.gazeY}
            <input
              type="range"
              min={-128}
              max={127}
              value={face.gazeY}
              onChange={(e) => updateFace({ gazeY: Number(e.target.value) })}
            />
          </label>

          <button
            type="button"
            style={{ alignSelf: 'flex-start' }}
            onClick={() => updateFace({ gazeX: 0, gazeY: 0 })}
          >
            Center Gaze
          </button>
        </div>
      </div>

      {/* Gestures section */}
      <div className={styles.card}>
        <h3>Gestures</h3>
        <div className={styles.grid3} style={{ marginTop: 4 }}>
          {GESTURES.map((g) => (
            <button
              type="button"
              key={g}
              onClick={() => send({ type: 'face_gesture', name: g, duration_ms: 500 })}
              style={{ padding: '8px 0', fontSize: 13, fontWeight: 500 }}
            >
              {g}
            </button>
          ))}
        </div>
      </div>

      {/* System Mode section */}
      <div className={styles.card}>
        <h3>System Mode</h3>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 8, marginTop: 4 }}>
          <label>
            Mode
            <select
              value={sysMode}
              onChange={(e) => {
                const mode = e.target.value
                setSysMode(mode)
                debouncedSysMode(mode, sysParam)
              }}
              style={{ marginLeft: 8, minWidth: 160 }}
            >
              {SYSTEM_MODES.map((m) => (
                <option key={m} value={m}>
                  {m}
                </option>
              ))}
            </select>
          </label>

          <label>
            Param: {sysParam}
            <input
              type="range"
              min={0}
              max={255}
              value={sysParam}
              onChange={(e) => {
                const val = Number(e.target.value)
                setSysParam(val)
                debouncedSysMode(sysMode, val)
              }}
            />
          </label>
        </div>
      </div>

      {/* Talking section */}
      <div className={styles.card}>
        <h3>Talking</h3>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 8, marginTop: 4 }}>
          <label style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <input
              type="checkbox"
              checked={talking}
              onChange={(e) => {
                const t = e.target.checked
                setTalking(t)
                debouncedTalking(t, talkEnergy)
              }}
            />
            Talking
          </label>

          <label>
            Energy: {talkEnergy}
            <input
              type="range"
              min={0}
              max={255}
              value={talkEnergy}
              onChange={(e) => {
                const val = Number(e.target.value)
                setTalkEnergy(val)
                debouncedTalking(talking, val)
              }}
            />
          </label>
        </div>
      </div>

      {/* Flags section */}
      <div className={styles.card}>
        <h3>Flags</h3>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 6, marginTop: 4 }}>
          {FACE_FLAGS.map((f) => {
            const flagKey = f.name as keyof FlagState
            return (
              <label key={f.bit} style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                <input
                  type="checkbox"
                  checked={flags[flagKey] ?? false}
                  onChange={(e) => {
                    const next = { ...flags, [flagKey]: e.target.checked }
                    setFlags(next)
                    sendFlags(next)
                  }}
                />
                {f.label}
                <span style={{ color: '#666', fontSize: 11 }}>(bit {f.bit})</span>
              </label>
            )
          })}
        </div>
      </div>

      {/* Manual Lock */}
      <div className={styles.card}>
        <h3>Manual Lock</h3>
        <label style={{ display: 'flex', alignItems: 'center', gap: 8, marginTop: 4 }}>
          <input
            type="checkbox"
            checked={manualLock}
            onChange={(e) => {
              const enabled = e.target.checked
              setManualLock(enabled)
              send({ type: 'face_manual_lock', enabled })
            }}
          />
          face_manual_lock
          <span style={{ color: '#666', fontSize: 11 }}>(prevents autonomous face updates)</span>
        </label>
      </div>
    </div>
  )
}
