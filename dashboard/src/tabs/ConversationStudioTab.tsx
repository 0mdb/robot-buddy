import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import ConvBenchmark from '../components/ConvBenchmark'
import PipelineTimeline from '../components/PipelineTimeline'
import TurnCards from '../components/TurnCards'
import WakeWordWorkbench from '../components/WakeWordWorkbench'
import { useParamsList, useUpdateParams } from '../hooks/useParams'
import { useSend } from '../hooks/useSend'
import { useTelemetry } from '../hooks/useTelemetry'
import { debounce } from '../lib/debounce'
import { type ConversationEvent, useConversationStore } from '../lib/wsConversation'
import styles from '../styles/global.module.css'
import ft from './FaceTab.module.css'

const CONV_PREFIXES = ['tts', 'personality', 'ear', 'ai', 'conv'] as const
type ConvPrefix = (typeof CONV_PREFIXES)[number]

function compactFields(fields: Record<string, unknown>): string {
  return Object.entries(fields)
    .map(([k, v]) => `${k}=${typeof v === 'object' ? JSON.stringify(v) : String(v)}`)
    .join('  ')
}

function compactConvEvent(e: ConversationEvent): string {
  const { ts_mono_ms: _ts, type: _type, ...rest } = e
  return compactFields(rest as Record<string, unknown>)
}

export default function ConversationStudioTab() {
  const send = useSend()

  // -- Telemetry (conversation-relevant) --
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

  // -- Conversation capture --
  const convConnected = useConversationStore((s) => s.connected)
  const convPaused = useConversationStore((s) => s.paused)
  const setConvPaused = useConversationStore((s) => s.setPaused)
  const convAllRef = useRef<ConversationEvent[]>([])
  const convAll = useConversationStore((s) => {
    const next = s.events
    const prev = convAllRef.current
    if (next.length === prev.length && next.every((e, i) => e === prev[i])) {
      return prev
    }
    convAllRef.current = next
    return next
  })

  // Event log filters
  const [convEnabledPrefixes, setConvEnabledPrefixes] = useState<Set<ConvPrefix>>(
    () => new Set<ConvPrefix>(['tts', 'ear', 'ai', 'conv']),
  )
  const [convSearch, setConvSearch] = useState('')
  const [convNewest, setConvNewest] = useState(true)

  const convFiltered = useMemo(() => {
    const searchLower = convSearch.toLowerCase()
    return convAll.filter((e) => {
      const prefix = e.type.split('.')[0] as ConvPrefix
      if (!convEnabledPrefixes.has(prefix)) return false
      if (searchLower) {
        const row = `${e.type} ${compactConvEvent(e)}`.toLowerCase()
        if (!row.includes(searchLower)) return false
      }
      return true
    })
  }, [convAll, convEnabledPrefixes, convSearch])

  const convDisplayed = useMemo(
    () => (convNewest ? [...convFiltered].slice(-300).reverse() : convFiltered.slice(-300)),
    [convFiltered, convNewest],
  )

  // -- Conversation controls --
  const [dashPttHeld, setDashPttHeld] = useState(false)
  const [chatText, setChatText] = useState('')
  const [muteSpeaker, setMuteSpeaker] = useState(false)
  const [muteChimes, setMuteChimes] = useState(false)
  const [noTtsGeneration, setNoTtsGeneration] = useState(false)
  const [speakerVolume, setSpeakerVolume] = useState(80)

  // Params: volume + planner controls
  const { data: paramsList } = useParamsList()
  const updateParams = useUpdateParams()
  const volParam = paramsList?.find((p) => p.name === 'tts.speaker_volume')

  useEffect(() => {
    if (volParam?.value != null) setSpeakerVolume(Number(volParam.value))
  }, [volParam?.value])

  const debouncedVolume = useRef(
    debounce((v: number) => {
      updateParams.mutate({ 'tts.speaker_volume': v })
    }, 150),
  ).current

  const [plannerEnabled, setPlannerEnabled] = useState(true)
  const [plannerPeriodS, setPlannerPeriodS] = useState(5)
  const plannerEnabledParam = paramsList?.find((p) => p.name === 'planner.enabled')
  const plannerPeriodParam = paramsList?.find((p) => p.name === 'planner.plan_period_s')

  useEffect(() => {
    if (plannerEnabledParam?.value != null) setPlannerEnabled(Boolean(plannerEnabledParam.value))
  }, [plannerEnabledParam?.value])

  useEffect(() => {
    if (plannerPeriodParam?.value != null) setPlannerPeriodS(Number(plannerPeriodParam.value))
  }, [plannerPeriodParam?.value])

  const debouncedPeriod = useRef(
    debounce((v: number) => {
      updateParams.mutate({ 'planner.plan_period_s': v })
    }, 200),
  ).current

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
    useConversationStore.getState().push({
      ts_mono_ms: Date.now(),
      type: 'ai.conversation.user_text',
      text,
    })
    setChatText('')
  }, [chatText, send])

  return (
    <div className={ft.controlsCol}>
      {/* ── Conversation Studio card ────────────────────────────── */}
      <div className={styles.card}>
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            gap: 12,
          }}
        >
          <h3 style={{ margin: 0 }}>Conversation Studio</h3>
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

        {/* Inputs */}
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

        <hr
          style={{
            border: 'none',
            borderTop: '1px solid rgba(255,255,255,0.06)',
            margin: '10px 0',
          }}
        />

        {/* Status + toggles */}
        <div className={ft.convStatus}>
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
            <label style={{ display: 'flex', alignItems: 'center', gap: 6, color: '#aaa' }}>
              Vol {speakerVolume}%
              <input
                type="range"
                min={0}
                max={100}
                step={1}
                value={speakerVolume}
                onChange={(e) => {
                  const v = Number(e.target.value)
                  setSpeakerVolume(v)
                  debouncedVolume(v)
                }}
                style={{ minWidth: 100 }}
              />
            </label>
          </div>
        </div>

        {/* Planner controls */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap' }}>
          <label style={{ display: 'flex', alignItems: 'center', gap: 6, color: '#aaa' }}>
            <input
              type="checkbox"
              checked={plannerEnabled}
              onChange={(e) => {
                const v = e.target.checked
                setPlannerEnabled(v)
                updateParams.mutate({ 'planner.enabled': v })
              }}
            />
            AI planner
          </label>
          <label
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: 6,
              color: plannerEnabled ? '#aaa' : '#555',
            }}
          >
            <span style={{ fontSize: 11 }}>every</span>
            <input
              type="range"
              min={1}
              max={120}
              step={1}
              value={plannerPeriodS}
              disabled={!plannerEnabled}
              onChange={(e) => {
                const v = Number(e.target.value)
                setPlannerPeriodS(v)
                debouncedPeriod(v)
              }}
              style={{ minWidth: 100 }}
            />
            <span className={styles.mono} style={{ fontSize: 11, width: 32 }}>
              {plannerPeriodS}s
            </span>
          </label>
        </div>

        {/* Pipeline Timeline */}
        <div style={{ marginTop: 8 }}>
          <span className={styles.mono} style={{ color: 'var(--text-dim)', fontSize: 11 }}>
            Pipeline Timeline
          </span>
          <PipelineTimeline />
        </div>

        {/* Phase C turn cards */}
        <div style={{ marginTop: 12 }}>
          <span className={styles.mono} style={{ color: 'var(--text-dim)', fontSize: 11 }}>
            Turns
          </span>
          <TurnCards />
        </div>

        {/* Event log */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
          <div style={{ display: 'flex', alignItems: 'center', flexWrap: 'wrap', gap: 4 }}>
            {CONV_PREFIXES.map((prefix) => {
              const active = convEnabledPrefixes.has(prefix)
              return (
                <button
                  type="button"
                  key={prefix}
                  onClick={() =>
                    setConvEnabledPrefixes((prev) => {
                      const next = new Set(prev)
                      if (next.has(prefix)) next.delete(prefix)
                      else next.add(prefix)
                      return next
                    })
                  }
                  style={{
                    padding: '3px 8px',
                    fontSize: 11,
                    fontWeight: 600,
                    fontFamily: 'var(--font-mono)',
                    border: `1px solid ${active ? '#4fc3f7' : '#333'}`,
                    borderRadius: 4,
                    background: active ? '#4fc3f722' : '#1a1a2e',
                    color: active ? '#4fc3f7' : '#555',
                    cursor: 'pointer',
                  }}
                >
                  {prefix}
                </button>
              )
            })}
            <input
              type="text"
              placeholder="Search..."
              value={convSearch}
              onChange={(e) => setConvSearch(e.target.value)}
              style={{
                flex: 1,
                maxWidth: 200,
                padding: '4px 8px',
                fontSize: 12,
                fontFamily: 'var(--font-mono)',
                background: '#1a1a2e',
                border: '1px solid #0f3460',
                borderRadius: 4,
                color: '#eee',
                outline: 'none',
              }}
            />
            <button
              type="button"
              onClick={() => setConvNewest((v) => !v)}
              style={{
                padding: '3px 8px',
                fontSize: 11,
                fontFamily: 'var(--font-mono)',
                border: '1px solid #333',
                borderRadius: 4,
                background: '#1a1a2e',
                color: '#888',
                cursor: 'pointer',
              }}
            >
              {convNewest ? 'newest' : 'oldest'}
            </button>
            <button
              type="button"
              onClick={() => setConvPaused(!convPaused)}
              style={{
                padding: '3px 8px',
                fontSize: 11,
                fontFamily: 'var(--font-mono)',
                border: `1px solid ${convPaused ? '#ff9800' : '#333'}`,
                borderRadius: 4,
                background: convPaused ? '#ff980022' : '#1a1a2e',
                color: convPaused ? '#ff9800' : '#888',
                cursor: 'pointer',
              }}
            >
              {convPaused ? 'paused' : 'live'}
            </button>
            <span className={styles.mono} style={{ color: '#555', fontSize: 11, marginLeft: 4 }}>
              {convFiltered.length}/{convAll.length}
            </span>
          </div>
          <div
            style={{
              maxHeight: 220,
              overflow: 'auto',
              border: '1px solid rgba(255,255,255,0.06)',
              borderRadius: 6,
              padding: 8,
              background: 'rgba(0,0,0,0.12)',
            }}
          >
            {convDisplayed.length === 0 ? (
              <span className={styles.mono} style={{ color: '#888', fontSize: 12 }}>
                No events match filters.
              </span>
            ) : (
              convDisplayed.map((e) => (
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
        </div>
      </div>

      {/* ── Diagnostics ─────────────────────────────────────────── */}
      <div className={ft.sectionHeader}>Diagnostics</div>

      <details className={ft.detailsSection}>
        <summary>Conv Benchmark</summary>
        <ConvBenchmark />
      </details>

      <details className={ft.detailsSection}>
        <summary>Wake Word Workbench</summary>
        <WakeWordWorkbench />
      </details>
    </div>
  )
}
