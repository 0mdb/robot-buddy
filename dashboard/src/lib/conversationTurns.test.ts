// @vitest-environment node

import { beforeEach, describe, expect, it } from 'vitest'
import { useConversationTurnsStore } from './conversationTurns'
import type { ConversationEvent } from './wsConversation'

function evt(
  type: string,
  planner_turn_id: string | null,
  extra: Record<string, unknown> = {},
): ConversationEvent {
  const base: ConversationEvent = { ts_mono_ms: 0, type, ...extra }
  if (planner_turn_id !== null) base.planner_turn_id = planner_turn_id
  return base
}

describe('conversationTurns store', () => {
  beforeEach(() => {
    useConversationTurnsStore.getState().clear()
  })

  it('ignores events without planner_turn_id', () => {
    const { ingest } = useConversationTurnsStore.getState()
    ingest(evt('ai.conversation.emotion', null, { emotion: 'happy' }))
    expect(useConversationTurnsStore.getState().turns).toEqual([])
  })

  it('builds a new turn card on first event', () => {
    useConversationTurnsStore.getState().ingest(
      evt('ai.conversation.transcription', 't1', {
        text: 'hello',
        stt_latency_ms: 42,
      }),
    )
    const turns = useConversationTurnsStore.getState().turns
    expect(turns).toHaveLength(1)
    expect(turns[0].turn_id).toBe('t1')
    expect(turns[0].transcription).toBe('hello')
    expect(turns[0].stt_latency_ms).toBe(42)
    expect(turns[0].completed).toBe(false)
  })

  it('accumulates multi-event turns on a single card', () => {
    const s = useConversationTurnsStore.getState()
    s.ingest(evt('ai.conversation.transcription', 't2', { text: 'hi' }))
    s.ingest(
      evt('ai.conversation.tool_call', 't2', {
        name: 'look',
        ok: true,
        reason: 'ok',
        latency_ms: 150,
        has_image: true,
      }),
    )
    s.ingest(
      evt('ai.conversation.emotion', 't2', {
        emotion: 'curious',
        intensity: 0.4,
        llm_latency_ms: 800,
      }),
    )
    s.ingest(evt('ai.conversation.first_audio', 't2', { first_audio_ms: 1300 }))
    s.ingest(evt('ai.conversation.assistant_text', 't2', { text: 'I see!' }))
    s.ingest(
      evt('ai.conversation.done', 't2', {
        total_ms: 3200,
        llm_latency_ms: 800,
        first_audio_ms: 1300,
        tool_call_name: 'look',
        tool_call_ok: true,
        tool_call_latency_ms: 150,
      }),
    )
    const [card] = useConversationTurnsStore.getState().turns
    expect(card.transcription).toBe('hi')
    expect(card.tool_call?.name).toBe('look')
    expect(card.tool_call?.has_image).toBe(true)
    expect(card.emotion?.emotion).toBe('curious')
    expect(card.emotion?.llm_latency_ms).toBe(800)
    expect(card.first_audio_ms).toBe(1300)
    expect(card.assistant_text).toBe('I see!')
    expect(card.done?.total_ms).toBe(3200)
    expect(card.completed).toBe(true)
  })

  it('marks turn_error events as completed with error details', () => {
    const s = useConversationTurnsStore.getState()
    s.ingest(evt('ai.conversation.transcription', 't3', { text: 'hi' }))
    s.ingest(
      evt('ai.conversation.turn_error', 't3', {
        reason: 'llm_busy',
        stage: 'llm',
        latency_ms: 120,
      }),
    )
    const [card] = useConversationTurnsStore.getState().turns
    expect(card.error?.reason).toBe('llm_busy')
    expect(card.error?.stage).toBe('llm')
    expect(card.completed).toBe(true)
  })

  it('keeps separate cards per planner_turn_id, newest first', () => {
    const s = useConversationTurnsStore.getState()
    s.ingest(evt('ai.conversation.transcription', 'a', { text: 'first' }))
    s.ingest(evt('ai.conversation.transcription', 'b', { text: 'second' }))
    const turns = useConversationTurnsStore.getState().turns
    expect(turns.map((t) => t.turn_id)).toEqual(['b', 'a'])
  })

  it('caps at 20 turns', () => {
    const s = useConversationTurnsStore.getState()
    for (let i = 0; i < 30; i++) {
      s.ingest(evt('ai.conversation.transcription', `t${i}`, { text: String(i) }))
    }
    const turns = useConversationTurnsStore.getState().turns
    expect(turns).toHaveLength(20)
    // Newest first — last inserted "t29" should be at index 0.
    expect(turns[0].turn_id).toBe('t29')
  })
})
