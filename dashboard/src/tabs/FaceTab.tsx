import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import FaceMirrorCanvas, {
  type MirrorMode,
  type SandboxDispatch,
} from '../components/FaceMirrorCanvas'
import PersonalityPanel from '../components/PersonalityPanel'
import PipelineTimeline from '../components/PipelineTimeline'
import ScenarioRunner from '../components/ScenarioRunner'
import ServerHealthPanel from '../components/ServerHealthPanel'
import TtsBenchmark from '../components/TtsBenchmark'
import WakeWordWorkbench from '../components/WakeWordWorkbench'
import { FACE_FLAGS, GESTURES, MOODS, SYSTEM_MODES } from '../constants'
import type { AnimFps } from '../face_sim'
import { ANIM_FPS_OPTIONS } from '../face_sim'
import { useSend } from '../hooks/useSend'
import { useTelemetry } from '../hooks/useTelemetry'
import { debounce } from '../lib/debounce'
import { type ConversationEvent, useConversationStore } from '../lib/wsConversation'
import { type CapturedPacket, useProtocolStore } from '../lib/wsProtocol'
import styles from '../styles/global.module.css'
import ft from './FaceTab.module.css'

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

function compactFields(fields: Record<string, unknown>): string {
  return Object.entries(fields)
    .map(([k, v]) => `${k}=${typeof v === 'object' ? JSON.stringify(v) : String(v)}`)
    .join('  ')
}

function compactConvEvent(e: ConversationEvent): string {
  // Remove shared envelope-ish fields to keep rows readable.
  const { ts_mono_ms: _ts, type: _type, ...rest } = e
  return compactFields(rest as Record<string, unknown>)
}

/** Convert FlagState to bitmask. */
function flagsToBitmask(f: FlagState): number {
  let mask = 0
  if (f.idle_wander) mask |= 1 << 0
  if (f.autoblink) mask |= 1 << 1
  if (f.solid_eye) mask |= 1 << 2
  if (f.show_mouth) mask |= 1 << 3
  if (f.edge_glow) mask |= 1 << 4
  if (f.sparkle) mask |= 1 << 5
  if (f.afterglow) mask |= 1 << 6
  return mask
}

// Gesture name → ID (indexes match GestureId enum in constants.ts)
const GESTURE_NAME_TO_ID: Record<string, number> = {}
for (let i = 0; i < GESTURES.length; i++) {
  GESTURE_NAME_TO_ID[GESTURES[i]] = i
}

// System mode name → ID
const SYSTEM_MODE_TO_ID: Record<string, number> = {}
for (let i = 0; i < SYSTEM_MODES.length; i++) {
  SYSTEM_MODE_TO_ID[SYSTEM_MODES[i]] = i
}

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

  // ── Mirror controls (Phase 6) ───────────────────────────────
  const [mirrorMode, setMirrorMode] = useState<MirrorMode>('live')
  const [mirrorFps, setMirrorFps] = useState<AnimFps>(30)
  const [mirrorDet, setMirrorDet] = useState(false)
  const sandboxRef = useRef<SandboxDispatch | null>(null)

  const handleSandboxDispatch = useCallback((d: SandboxDispatch | null) => {
    sandboxRef.current = d
  }, [])

  // -- Telemetry --
  const faceConnected = useTelemetry((s) => s.snapshot.face_connected)
  const faceRxMs = useTelemetry((s) => s.snapshot.face_rx_mono_ms)
  const tickMonoMs = useTelemetry((s) => s.snapshot.tick_mono_ms)
  const currentMood = useTelemetry((s) => s.snapshot.face_mood)
  const currentFlags = useTelemetry((s) => s.snapshot.face_manual_flags)
  const currentManualLock = useTelemetry((s) => s.snapshot.face_manual_lock)
  const currentTalking = useTelemetry((s) => s.snapshot.face_talking)
  const currentTalkingEnergy = useTelemetry((s) => s.snapshot.face_talking_energy)
  const sessionIdRaw = useTelemetry((s) => s.snapshot.session_id)
  const aiStateRaw = useTelemetry((s) => s.snapshot.ai_state)
  const micLinkUpRaw = useTelemetry((s) => s.snapshot.mic_link_up)
  const spkLinkUpRaw = useTelemetry((s) => s.snapshot.spk_link_up)
  const speakingRaw = useTelemetry((s) => s.snapshot.speaking)
  const sessionId = typeof sessionIdRaw === 'string' ? sessionIdRaw : ''
  const aiState = typeof aiStateRaw === 'string' ? aiStateRaw : ''
  const micLinkUp = micLinkUpRaw === true
  const spkLinkUp = spkLinkUpRaw === true
  const speaking = speakingRaw === true

  // -- Protocol capture (for live face TX mirroring) --
  const protoConnected = useProtocolStore((s) => s.connected)
  const protoPaused = useProtocolStore((s) => s.paused)
  const setProtoPaused = useProtocolStore((s) => s.setPaused)
  const faceTxRecentRef = useRef<CapturedPacket[]>([])
  const faceTxRecent = useProtocolStore((s) => {
    const out: CapturedPacket[] = []
    for (let i = s.packets.length - 1; i >= 0 && out.length < 12; i--) {
      const p = s.packets[i]
      if (p.device === 'face' && p.direction === 'TX') out.push(p)
    }
    const prev = faceTxRecentRef.current
    if (out.length === prev.length && out.every((p, i) => p === prev[i])) {
      return prev
    }
    faceTxRecentRef.current = out
    return out
  })

  // -- Conversation capture (for Studio diagnostics) --
  const convConnected = useConversationStore((s) => s.connected)
  const convPaused = useConversationStore((s) => s.paused)
  const setConvPaused = useConversationStore((s) => s.setPaused)
  const convRecentRef = useRef<ConversationEvent[]>([])
  const convRecent = useConversationStore((s) => {
    const next = s.events.slice(Math.max(0, s.events.length - 30))
    const prev = convRecentRef.current
    if (next.length === prev.length && next.every((e, i) => e === prev[i])) {
      return prev
    }
    convRecentRef.current = next
    return next
  })

  // Conversation controls (Studio)
  const [dashPttHeld, setDashPttHeld] = useState(false)
  const [chatText, setChatText] = useState('')
  const [muteSpeaker, setMuteSpeaker] = useState(false)
  const [muteChimes, setMuteChimes] = useState(false)
  const [noTtsGeneration, setNoTtsGeneration] = useState(false)

  const startWakeWord = useCallback(() => {
    send({ type: 'conversation.start', trigger: 'wake_word' })
  }, [send])

  const startDashboardPtt = useCallback(() => {
    setDashPttHeld(true)
    send({ type: 'conversation.start', trigger: 'ptt' })
  }, [send])

  const endDashboardPtt = useCallback(() => {
    setDashPttHeld(false)
    send({ type: 'conversation.end_utterance' })
  }, [send])

  const cancelConversation = useCallback(() => {
    setDashPttHeld(false)
    send({ type: 'conversation.cancel' })
  }, [send])

  const sendChat = useCallback(() => {
    const text = chatText.trim()
    if (!text) return
    send({ type: 'conversation.send_text', text })
    setChatText('')
  }, [chatText, send])

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
        // Always send to supervisor
        debouncedFaceState(next)
        // Also dispatch to sandbox if active
        if (sandboxRef.current) {
          const moodIdx = MOODS.indexOf(next.mood as (typeof MOODS)[number])
          sandboxRef.current.setMood(
            moodIdx >= 0 ? moodIdx : 0,
            next.intensity,
            next.brightness,
            next.gazeX,
            next.gazeY,
          )
        }
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
      // Also dispatch to sandbox
      if (sandboxRef.current) {
        sandboxRef.current.setFlags(flagsToBitmask(f))
      }
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

  const faceTxAgeMs = useMemo(() => {
    const last = faceTxRecent[0] ?? null
    if (!last) return null
    if (typeof tickMonoMs !== 'number') return null
    return Math.max(0, tickMonoMs - last.ts_mono_ms)
  }, [faceTxRecent, tickMonoMs])

  const isSandbox = mirrorMode === 'sandbox'

  return (
    <div style={{ padding: 16, display: 'flex', flexDirection: 'column', gap: 12 }}>
      {/* Header row */}
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          gap: 12,
          flexWrap: 'wrap',
        }}
      >
        <div style={{ fontSize: 16, fontWeight: 600, color: '#ccc' }}>Tuning Studio</div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
          <span
            className={`${styles.badge} ${faceConnected ? styles.badgeGreen : styles.badgeRed}`}
          >
            {faceConnected ? 'Face Connected' : 'Face Disconnected'}
          </span>
          {ageMs !== null && (
            <span className={styles.mono} style={{ color: '#888', fontSize: 11 }}>
              face rx {ageMs.toFixed(0)} ms
            </span>
          )}

          <span
            className={`${styles.badge} ${protoConnected ? styles.badgeGreen : styles.badgeRed}`}
          >
            {protoConnected ? 'Protocol Connected' : 'Protocol Disconnected'}
          </span>
          <button
            type="button"
            className={`${ft.segBtn} ${protoPaused ? ft.segBtnActive : ''}`}
            onClick={() => setProtoPaused(!protoPaused)}
            style={{ borderRadius: 4 }}
          >
            {protoPaused ? 'Paused' : 'Live'}
          </button>
          {faceTxAgeMs !== null && (
            <span className={styles.mono} style={{ color: '#888', fontSize: 11 }}>
              face tx {faceTxAgeMs.toFixed(0)} ms
            </span>
          )}
        </div>
      </div>

      {/* Mirror controls (Phase 6) */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 12, flexWrap: 'wrap' }}>
        {/* Mode toggle: Live | Sandbox */}
        <div style={{ display: 'flex' }}>
          <button
            type="button"
            className={`${ft.segBtn} ${mirrorMode === 'live' ? ft.segBtnActive : ''}`}
            onClick={() => setMirrorMode('live')}
            style={{ borderRadius: '4px 0 0 4px' }}
          >
            Live
          </button>
          <button
            type="button"
            className={`${ft.segBtn} ${mirrorMode === 'sandbox' ? ft.segBtnActive : ''}`}
            onClick={() => setMirrorMode('sandbox')}
            style={{ borderRadius: '0 4px 4px 0', borderLeft: 'none' }}
          >
            Sandbox
          </button>
        </div>

        {/* FPS toggle */}
        <div style={{ display: 'flex' }}>
          {ANIM_FPS_OPTIONS.map((fpsOpt, i) => (
            <button
              type="button"
              key={fpsOpt}
              className={`${ft.segBtn} ${mirrorFps === fpsOpt ? ft.segBtnActive : ''}`}
              onClick={() => setMirrorFps(fpsOpt)}
              style={{
                borderRadius:
                  i === 0 ? '4px 0 0 4px' : i === ANIM_FPS_OPTIONS.length - 1 ? '0 4px 4px 0' : '0',
                borderLeft: i > 0 ? 'none' : undefined,
              }}
            >
              {fpsOpt}
            </button>
          ))}
        </div>

        {/* Deterministic checkbox */}
        <label
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: 5,
            fontSize: 11,
            color: mirrorDet ? '#9c27b0' : '#888',
            cursor: 'pointer',
          }}
        >
          <input
            type="checkbox"
            checked={mirrorDet}
            onChange={(e) => setMirrorDet(e.target.checked)}
          />
          Deterministic
        </label>

        {/* Reset button (sandbox only) */}
        {isSandbox && sandboxRef.current && (
          <button
            type="button"
            className={ft.segBtn}
            onClick={() => sandboxRef.current?.reset()}
            style={{ borderRadius: 4, color: '#ff5252', borderColor: '#ff5252' }}
          >
            Reset
          </button>
        )}
      </div>

      {/* ── SECTION: Face Controls ──────────────────────────────── */}
      <div className={ft.sectionHeader}>Face Controls</div>

      {/* Phase 1: Two-column layout — Mirror (sticky left) + Controls (right) */}
      <div className={ft.faceArea}>
        {/* Left: Face Mirror Canvas (sticky) */}
        <div className={ft.mirrorCol}>
          <div className={styles.card}>
            <FaceMirrorCanvas
              mode={mirrorMode}
              fps={mirrorFps}
              deterministic={mirrorDet}
              onSandboxDispatch={handleSandboxDispatch}
            />
          </div>
        </div>

        {/* Right: Scrollable face controls */}
        <div className={ft.controlsCol}>
          {/* Face State — read-only conversation + sequencer display */}
          <div className={styles.card}>
            <h3>Face State</h3>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
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
                  {convTimerMs !== null ? `${convTimerMs} ms` : '\u2014'}
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
            <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
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

          {/* Gestures — Phase 1: compact 4-column grid */}
          <div className={styles.card}>
            <h3>Gestures</h3>
            <div className={ft.gestureGrid}>
              {GESTURES.map((g) => (
                <button
                  type="button"
                  key={g}
                  className={ft.gestureBtn}
                  onClick={() => {
                    send({ type: 'face_gesture', name: g, duration_ms: 500 })
                    const gid = GESTURE_NAME_TO_ID[g]
                    if (gid !== undefined && sandboxRef.current) {
                      sandboxRef.current.triggerGesture(gid, 500)
                    }
                  }}
                >
                  {g}
                </button>
              ))}
            </div>
          </div>

          {/* System Mode */}
          <div className={`${styles.card} ${isSandbox ? ft.cardDisabled : ''}`}>
            <h3>System Mode</h3>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
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

          {/* Phase 1: Merged "Face Options" — Talking + Flags + Manual Lock */}
          <div className={`${styles.card} ${isSandbox ? ft.cardDisabled : ''}`}>
            <h3>Face Options</h3>
            <div className={ft.faceOptionsGrid}>
              {/* Talking */}
              <label style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                <input
                  type="checkbox"
                  checked={talking}
                  onChange={(e) => {
                    const t = e.target.checked
                    setTalking(t)
                    debouncedTalking(t, talkEnergy)
                    if (sandboxRef.current) {
                      sandboxRef.current.setTalking(t, talkEnergy)
                    }
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
                    if (sandboxRef.current) {
                      sandboxRef.current.setTalking(talking, val)
                    }
                  }}
                />
              </label>

              {/* Flags */}
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

              {/* Manual Lock */}
              <label style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                <input
                  type="checkbox"
                  checked={manualLock}
                  onChange={(e) => {
                    const enabled = e.target.checked
                    setManualLock(enabled)
                    send({ type: 'face_manual_lock', enabled })
                  }}
                />
                Manual Lock
                <span style={{ color: '#666', fontSize: 11 }}>(prevents autonomous updates)</span>
              </label>
            </div>
          </div>
        </div>
      </div>

      {/* ── SECTION: Conversation ───────────────────────────────── */}
      <div className={ft.sectionHeader}>Conversation</div>

      {/* Conversation Studio */}
      <div className={styles.card}>
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            gap: 12,
          }}
        >
          <h3 style={{ margin: 0 }}>Conversation (Studio)</h3>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
            <span
              className={`${styles.badge} ${convConnected ? styles.badgeGreen : styles.badgeRed}`}
            >
              {convConnected ? 'Conversation Connected' : 'Conversation Disconnected'}
            </span>
            <button
              type="button"
              className={`${ft.segBtn} ${convPaused ? ft.segBtnActive : ''}`}
              onClick={() => setConvPaused(!convPaused)}
              style={{ borderRadius: 4 }}
            >
              {convPaused ? 'Paused' : 'Live'}
            </button>
            <button
              type="button"
              className={ft.segBtn}
              onClick={() => useConversationStore.getState().clear()}
              style={{ borderRadius: 4 }}
            >
              Clear
            </button>
          </div>
        </div>

        {/* Phase 3: Inputs section */}
        <div className={ft.convInputs} style={{ marginTop: 10 }}>
          <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
            <button type="button" onClick={startWakeWord} style={{ padding: '6px 10px' }}>
              Sim Wake Word
            </button>
            <button
              type="button"
              onMouseDown={() => {
                if (!dashPttHeld) startDashboardPtt()
              }}
              onMouseUp={() => {
                if (dashPttHeld) endDashboardPtt()
              }}
              onMouseLeave={() => {
                if (dashPttHeld) endDashboardPtt()
              }}
              onTouchStart={() => {
                if (!dashPttHeld) startDashboardPtt()
              }}
              onTouchEnd={() => {
                if (dashPttHeld) endDashboardPtt()
              }}
              style={{
                padding: '6px 10px',
                border: `1px solid ${dashPttHeld ? '#ff9800' : '#333'}`,
                background: dashPttHeld ? 'rgba(255,152,0,0.15)' : '#1a1a2e',
                color: dashPttHeld ? '#ff9800' : '#ddd',
              }}
            >
              {dashPttHeld ? 'PTT (Release to Send)' : 'PTT (Hold)'}
            </button>
            <button type="button" onClick={cancelConversation} style={{ padding: '6px 10px' }}>
              Cancel
            </button>
          </div>

          <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
            <input
              value={chatText}
              onChange={(e) => setChatText(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter') sendChat()
              }}
              placeholder="Type message\u2026"
              style={{
                flex: 1,
                minWidth: 180,
                padding: '6px 10px',
                borderRadius: 6,
                border: '1px solid rgba(255,255,255,0.12)',
                background: 'rgba(0,0,0,0.25)',
                color: '#ddd',
              }}
            />
            <button type="button" onClick={sendChat} style={{ padding: '6px 10px' }}>
              Send
            </button>
          </div>
        </div>

        {/* Phase 3: Outputs section — divider, then status rows */}
        <hr
          style={{
            border: 'none',
            borderTop: '1px solid rgba(255,255,255,0.06)',
            margin: '10px 0',
          }}
        />

        <div className={ft.convStatus}>
          {/* Device badges */}
          <div className={ft.convStatusRow}>
            <span className={styles.mono} style={{ color: '#888', fontSize: 11 }}>
              session {sessionId ? sessionId : '\u2014'}
            </span>
            <span className={styles.mono} style={{ color: '#888', fontSize: 11 }}>
              ai_state {aiState ? aiState : '\u2014'}
            </span>
            <span className={`${styles.badge} ${micLinkUp ? styles.badgeGreen : styles.badgeRed}`}>
              {micLinkUp ? 'mic up' : 'mic down'}
            </span>
            <span className={`${styles.badge} ${spkLinkUp ? styles.badgeGreen : styles.badgeRed}`}>
              {spkLinkUp ? 'spk up' : 'spk down'}
            </span>
            <span className={`${styles.badge} ${speaking ? styles.badgeGreen : styles.badgeRed}`}>
              {speaking ? 'speaking' : 'not speaking'}
            </span>
          </div>

          {/* Mute toggles */}
          <div className={ft.convToggles}>
            <label style={{ display: 'flex', alignItems: 'center', gap: 6, color: '#aaa' }}>
              <input
                type="checkbox"
                checked={muteSpeaker}
                onChange={(e) => {
                  const muted = e.target.checked
                  setMuteSpeaker(muted)
                  send({ type: 'tts.set_mute', muted, mute_chimes: muteChimes })
                }}
              />
              Mute speaker
            </label>
            <label style={{ display: 'flex', alignItems: 'center', gap: 6, color: '#aaa' }}>
              <input
                type="checkbox"
                checked={muteChimes}
                onChange={(e) => {
                  const mc = e.target.checked
                  setMuteChimes(mc)
                  send({ type: 'tts.set_mute', muted: muteSpeaker, mute_chimes: mc })
                }}
              />
              Mute chimes
            </label>
            <label style={{ display: 'flex', alignItems: 'center', gap: 6, color: '#aaa' }}>
              <input
                type="checkbox"
                checked={noTtsGeneration}
                onChange={(e) => {
                  const enabled = e.target.checked
                  setNoTtsGeneration(enabled)
                  send({ type: 'conversation.config', stream_audio: !enabled, stream_text: true })
                }}
              />
              No TTS generation
            </label>
          </div>
        </div>

        {/* Pipeline Timeline */}
        <div style={{ marginTop: 8 }}>
          <span className={styles.mono} style={{ color: 'var(--text-dim)', fontSize: 11 }}>
            Pipeline Timeline
          </span>
          <PipelineTimeline />
        </div>

        {/* Phase 3: Event log — collapsed by default */}
        <details className={ft.eventLogDetails}>
          <summary>Show events ({convRecent.length})</summary>
          <div
            style={{
              maxHeight: 220,
              overflow: 'auto',
              border: '1px solid rgba(255,255,255,0.06)',
              borderRadius: 6,
              padding: 8,
              background: 'rgba(0,0,0,0.12)',
              marginTop: 4,
            }}
          >
            {convRecent.length === 0 ? (
              <span className={styles.mono} style={{ color: '#888', fontSize: 12 }}>
                No conversation events yet.
              </span>
            ) : (
              convRecent.map((e) => (
                <div
                  key={`${e.ts_mono_ms}-${e.type}-${String(e.turn_id ?? '')}`}
                  className={styles.mono}
                >
                  <span style={{ color: '#777' }}>{e.type}</span>{' '}
                  <span style={{ color: '#aaa' }}>{compactConvEvent(e)}</span>
                </div>
              ))
            )}
          </div>
        </details>
      </div>

      {/* ── SECTION: Personality ────────────────────────────────── */}
      <div className={ft.sectionHeader}>Personality</div>

      {/* Phase 3: PE moved here — immediately after face controls + conversation */}
      <PersonalityPanel />

      {/* ── SECTION: Diagnostics ───────────────────────────────── */}
      <div className={ft.sectionHeader}>Diagnostics</div>

      {/* B6 Scenario Suite (already collapsible) */}
      <ScenarioRunner />

      {/* Phase 2: Server Health — collapsible, default closed */}
      <details className={ft.detailsSection}>
        <summary>Server Health</summary>
        <ServerHealthPanel />
      </details>

      {/* Phase 2: TTS Benchmark — collapsible, default closed */}
      <details className={ft.detailsSection}>
        <summary>TTS Benchmark</summary>
        <TtsBenchmark />
      </details>

      {/* Phase 2: Wake Word Workbench — collapsible, default closed */}
      <details className={ft.detailsSection}>
        <summary>Wake Word Workbench</summary>
        <WakeWordWorkbench />
      </details>
    </div>
  )
}
