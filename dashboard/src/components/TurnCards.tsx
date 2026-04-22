/**
 * Phase C: per-turn cards for ConversationStudio.
 *
 * Reads the turn store populated by wsConversation → conversationTurns.ingest
 * and renders one legible card per /converse turn. Newest first, capped at 20.
 *
 * Each card shows: transcription, tool_call badge + image hint, pipeline
 * timings (llm / first_audio / total), assistant text, error state.
 */

import { useConversationTurnsStore } from '../lib/conversationTurns'
import styles from '../styles/global.module.css'
import type { TurnCard } from '../types'

function fmtMs(n: number | null | undefined): string {
  if (n === null || n === undefined) return '—'
  return `${Math.round(n)}ms`
}

function ToolCallBadge({ card }: { card: TurnCard }) {
  const tc = card.tool_call
  if (!tc) return null
  const color = tc.ok ? '#4caf50' : '#f44336'
  const name = tc.name ?? 'none'
  return (
    <span
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        gap: 6,
        padding: '2px 8px',
        borderRadius: 4,
        border: `1px solid ${color}`,
        color,
        background: `${color}14`,
        fontSize: 11,
        fontFamily: 'var(--font-mono)',
      }}
      title={tc.reason}
    >
      <span>{name}</span>
      <span style={{ opacity: 0.7 }}>{fmtMs(tc.latency_ms)}</span>
      {tc.has_image ? <span title="has image">📷</span> : null}
    </span>
  )
}

function Timings({ card }: { card: TurnCard }) {
  const llm = card.emotion?.llm_latency_ms ?? card.done?.llm_latency_ms
  const firstAudio = card.first_audio_ms ?? card.done?.first_audio_ms
  const total = card.done?.total_ms
  const stt = card.stt_latency_ms
  return (
    <div
      style={{
        display: 'flex',
        gap: 12,
        fontSize: 11,
        fontFamily: 'var(--font-mono)',
        color: 'var(--text-dim)',
      }}
    >
      {stt !== undefined ? <span title="STT latency">stt: {fmtMs(stt)}</span> : null}
      {llm !== undefined && llm !== null ? (
        <span title="Time to LLM metadata ready">llm: {fmtMs(llm)}</span>
      ) : null}
      {firstAudio !== undefined && firstAudio !== null ? (
        <span title="Time to first audio chunk">first-audio: {fmtMs(firstAudio)}</span>
      ) : null}
      {total !== undefined ? <span title="Total turn duration">total: {fmtMs(total)}</span> : null}
    </div>
  )
}

function TurnCardRow({ card }: { card: TurnCard }) {
  const errored = card.error !== undefined
  const borderColor = errored ? 'var(--red)' : 'var(--border)'

  return (
    <div
      className={styles.card}
      style={{
        padding: 10,
        marginBottom: 8,
        border: `1px solid ${borderColor}`,
        display: 'flex',
        flexDirection: 'column',
        gap: 6,
      }}
    >
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: 8,
          flexWrap: 'wrap',
          justifyContent: 'space-between',
        }}
      >
        <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
          <span
            className={styles.mono}
            style={{ fontSize: 10, color: 'var(--text-dim)' }}
            title={`turn ${card.turn_id}`}
          >
            {card.turn_id.slice(0, 8)}
          </span>
          <ToolCallBadge card={card} />
          {card.emotion ? (
            <span
              style={{
                fontSize: 11,
                color: '#ce93d8',
                fontFamily: 'var(--font-mono)',
              }}
              title={card.emotion.mood_reason}
            >
              {card.emotion.emotion} @ {card.emotion.intensity.toFixed(2)}
            </span>
          ) : null}
        </div>
        <Timings card={card} />
      </div>

      {card.transcription ? (
        <div style={{ fontSize: 12 }}>
          <span style={{ color: 'var(--text-dim)' }}>you: </span>
          <span style={{ color: '#ddd' }}>{card.transcription}</span>
        </div>
      ) : null}

      {card.assistant_text ? (
        <div style={{ fontSize: 12 }}>
          <span style={{ color: 'var(--text-dim)' }}>buddy: </span>
          <span style={{ color: '#eee' }}>{card.assistant_text}</span>
        </div>
      ) : null}

      {card.error ? (
        <div
          style={{
            fontSize: 11,
            color: '#f88',
            fontFamily: 'var(--font-mono)',
            background: 'rgba(244,67,54,0.08)',
            padding: '4px 8px',
            borderRadius: 4,
          }}
        >
          turn_error · stage={card.error.stage} · reason={card.error.reason} ·{' '}
          {fmtMs(card.error.latency_ms)}
        </div>
      ) : null}
    </div>
  )
}

export function TurnCards() {
  const turns = useConversationTurnsStore((s) => s.turns)

  if (turns.length === 0) {
    return (
      <div
        style={{
          color: 'var(--text-dim)',
          fontSize: 12,
          fontStyle: 'italic',
          padding: '8px 0',
        }}
      >
        No conversation turns yet — send a message or press PTT.
      </div>
    )
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column' }}>
      {turns.map((card) => (
        <TurnCardRow key={card.turn_id} card={card} />
      ))}
    </div>
  )
}

export default TurnCards
