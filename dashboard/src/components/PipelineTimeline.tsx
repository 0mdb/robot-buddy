import { useMemo } from 'react'
import { type ConversationEvent, useConversationStore } from '../lib/wsConversation'
import styles from '../styles/global.module.css'

// ---------------------------------------------------------------------------
// Stage definitions
// ---------------------------------------------------------------------------

interface Stage {
  name: string
  color: string
  startMs: number
  endMs: number | null // null = in-progress
}

const STAGE_COLORS: Record<string, string> = {
  Listen: '#2196f3',
  STT: '#009688',
  LLM: '#ff9800',
  'TTS Gen': '#9c27b0',
  Playback: '#4caf50',
  Error: '#f44336',
}

// ---------------------------------------------------------------------------
// Turn derivation from flat event list
// ---------------------------------------------------------------------------

interface Turn {
  sessionId: string
  t0: number
  stages: Stage[]
  totalMs: number | null // null = still in progress
  error: boolean
}

function deriveTurns(events: ConversationEvent[], maxTurns: number): Turn[] {
  // Group events by session_id
  const sessions = new Map<string, ConversationEvent[]>()
  for (const e of events) {
    const sid = e.session_id as string | undefined
    if (!sid) continue
    let list = sessions.get(sid)
    if (!list) {
      list = []
      sessions.set(sid, list)
    }
    list.push(e)
  }

  const turns: Turn[] = []

  for (const [sessionId, evts] of sessions) {
    // Sort by timestamp (should already be ordered, but be safe)
    evts.sort((a, b) => a.ts_mono_ms - b.ts_mono_ms)

    const t0 = evts[0].ts_mono_ms
    const stages: Stage[] = []
    let hasError = false

    // Milestone timestamps
    let sessionStart: number | null = null
    let vadEnd: number | null = null
    let transcription: number | null = null
    let emotion: number | null = null
    let firstAudio: number | null = null
    let ttsFinished: number | null = null
    let sessionEnd: number | null = null

    for (const e of evts) {
      switch (e.type) {
        case 'conv.session.started':
          sessionStart = e.ts_mono_ms
          break
        case 'ear.event.end_of_utterance':
          vadEnd = e.ts_mono_ms
          break
        case 'ai.conversation.transcription':
          transcription = e.ts_mono_ms
          break
        case 'ai.conversation.emotion':
          emotion = e.ts_mono_ms
          break
        case 'ai.conversation.first_audio':
          firstAudio = e.ts_mono_ms
          break
        case 'tts.event.finished':
          ttsFinished = e.ts_mono_ms
          break
        case 'conv.session.ended':
          sessionEnd = e.ts_mono_ms
          break
        case 'ai.conversation.done': {
          const reason = e.reason as string | undefined
          if (reason === 'error') hasError = true
          break
        }
      }
    }

    const base = sessionStart ?? t0

    // Build stages in pipeline order
    // Listen: session start → VAD end
    if (vadEnd !== null) {
      stages.push({ name: 'Listen', color: STAGE_COLORS.Listen, startMs: base, endMs: vadEnd })
    } else if (!transcription && !emotion && !firstAudio && !ttsFinished && !sessionEnd) {
      // Still listening
      stages.push({ name: 'Listen', color: STAGE_COLORS.Listen, startMs: base, endMs: null })
    }

    // STT: VAD end → transcription
    if (vadEnd !== null && transcription !== null) {
      stages.push({
        name: 'STT',
        color: STAGE_COLORS.STT,
        startMs: vadEnd,
        endMs: transcription,
      })
    } else if (vadEnd !== null && !transcription && !emotion && !firstAudio && !sessionEnd) {
      stages.push({ name: 'STT', color: STAGE_COLORS.STT, startMs: vadEnd, endMs: null })
    }

    // LLM: transcription → emotion (or first_audio if no emotion)
    // For text-only (no VAD/STT), fall back to session start
    const llmEnd = emotion ?? firstAudio
    const llmStart = transcription ?? vadEnd ?? sessionStart
    if (llmStart !== null && llmEnd !== null) {
      stages.push({ name: 'LLM', color: STAGE_COLORS.LLM, startMs: llmStart, endMs: llmEnd })
    } else if (llmStart !== null && !llmEnd && !firstAudio && !ttsFinished && !sessionEnd) {
      stages.push({ name: 'LLM', color: STAGE_COLORS.LLM, startMs: llmStart, endMs: null })
    }

    // TTS Gen: emotion → first_audio
    if (emotion !== null && firstAudio !== null) {
      stages.push({
        name: 'TTS Gen',
        color: STAGE_COLORS['TTS Gen'],
        startMs: emotion,
        endMs: firstAudio,
      })
    } else if (emotion !== null && !firstAudio && !ttsFinished && !sessionEnd) {
      stages.push({
        name: 'TTS Gen',
        color: STAGE_COLORS['TTS Gen'],
        startMs: emotion,
        endMs: null,
      })
    }

    // Playback: first_audio → tts_finished
    if (firstAudio !== null && ttsFinished !== null) {
      stages.push({
        name: 'Playback',
        color: STAGE_COLORS.Playback,
        startMs: firstAudio,
        endMs: ttsFinished,
      })
    } else if (firstAudio !== null && !ttsFinished && !sessionEnd) {
      stages.push({
        name: 'Playback',
        color: STAGE_COLORS.Playback,
        startMs: firstAudio,
        endMs: null,
      })
    }

    const lastComplete = ttsFinished ?? firstAudio ?? emotion ?? transcription ?? vadEnd ?? null
    const totalMs =
      sessionEnd !== null
        ? sessionEnd - base
        : lastComplete !== null && stages.every((s) => s.endMs !== null)
          ? lastComplete - base
          : null

    if (stages.length > 0) {
      turns.push({ sessionId, t0: base, stages, totalMs, error: hasError })
    }
  }

  // Return most recent turns
  return turns.slice(-maxTurns)
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

const MAX_TURNS = 5

export default function PipelineTimeline() {
  const events = useConversationStore((s) => s.events)

  const turns = useMemo(() => deriveTurns(events, MAX_TURNS), [events])

  if (turns.length === 0) {
    return (
      <div style={{ padding: '8px 0' }}>
        <span className={styles.mono} style={{ color: '#666', fontSize: 11 }}>
          No conversation turns yet — trigger a wake word or send text to see the pipeline.
        </span>
      </div>
    )
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 6, padding: '8px 0' }}>
      {turns.map((turn) => (
        <TurnRow key={turn.sessionId} turn={turn} />
      ))}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Turn row
// ---------------------------------------------------------------------------

function TurnRow({ turn }: { turn: Turn }) {
  // Calculate total span for width percentages
  const now = Date.now() // fallback reference for in-progress

  // Find the latest end time (or estimate for in-progress)
  const allEndMs = turn.stages.map((s) => s.endMs ?? now)
  const spanMs = Math.max(...allEndMs) - turn.t0

  if (spanMs <= 0) return null

  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
      {/* Session ID (first 6 chars) */}
      <span
        className={styles.mono}
        style={{ color: '#666', fontSize: 10, width: 44, flexShrink: 0 }}
        title={turn.sessionId}
      >
        {turn.sessionId.slice(0, 6)}
      </span>

      {/* Segmented bar */}
      <div
        style={{
          flex: 1,
          height: 20,
          display: 'flex',
          borderRadius: 4,
          overflow: 'hidden',
          background: 'rgba(255,255,255,0.04)',
          position: 'relative',
        }}
      >
        {turn.stages.map((stage) => {
          const durationMs = (stage.endMs ?? now) - stage.startMs
          const pct = (durationMs / spanMs) * 100
          const inProgress = stage.endMs === null

          return (
            <div
              key={stage.name}
              title={`${stage.name}: ${durationMs.toFixed(0)} ms`}
              style={{
                width: `${pct}%`,
                minWidth: 2,
                height: '100%',
                background: stage.color,
                opacity: inProgress ? undefined : 0.85,
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                overflow: 'hidden',
                animation: inProgress ? 'pipeline-pulse 1.2s ease-in-out infinite' : undefined,
              }}
            >
              {pct > 12 && (
                <span
                  style={{
                    fontSize: 9,
                    color: '#fff',
                    fontWeight: 600,
                    whiteSpace: 'nowrap',
                    textShadow: '0 0 3px rgba(0,0,0,0.6)',
                  }}
                >
                  {stage.name} {durationMs.toFixed(0)}ms
                </span>
              )}
            </div>
          )
        })}
      </div>

      {/* Total duration */}
      <span
        className={styles.mono}
        style={{
          color: turn.error ? '#f44336' : turn.totalMs !== null ? '#aaa' : '#666',
          fontSize: 11,
          width: 56,
          flexShrink: 0,
          textAlign: 'right',
        }}
      >
        {turn.totalMs !== null ? `${turn.totalMs.toFixed(0)}ms` : '...'}
      </span>
    </div>
  )
}
