/**
 * Phase C: turn-id keyed view of the /converse event stream.
 *
 * The existing wsConversation store appends every inbound supervisor event
 * into a flat list. ConversationStudio needs a tighter view: one card per
 * /converse turn, accumulating transcription, tool_call, emotion, etc.
 * into a TurnCard.
 *
 * The turn key here is the *planner* turn UUID (supervisor events carry it
 * as `planner_turn_id`). That matches the `turn_id` field on McpAuditEntry
 * so the dashboard can cross-link ConversationStudio rows with MCP Activity.
 */

import { create } from 'zustand'
import type { TurnCard } from '../types'
import type { ConversationEvent } from './wsConversation'

const MAX_TURNS = 20

function extractPlannerTurnId(evt: ConversationEvent): string | null {
  const v = evt.planner_turn_id
  if (typeof v === 'string' && v.length > 0) return v
  return null
}

function updateCard(card: TurnCard, evt: ConversationEvent): TurnCard {
  const t = String(evt.type || '')
  // The ai_worker forwards planner /converse events as `ai.conversation.*`,
  // so our type strings are prefixed. Match the tail after the last dot.
  const tail = t.split('.').slice(-1)[0] ?? ''

  switch (tail) {
    case 'transcription': {
      const stt = evt.stt_latency_ms
      return {
        ...card,
        transcription: String(evt.text ?? ''),
        stt_latency_ms: typeof stt === 'number' ? stt : card.stt_latency_ms,
      }
    }
    case 'tool_call': {
      return {
        ...card,
        tool_call: {
          type: 'tool_call',
          turn_id: card.turn_id,
          name: (evt.name as string | null) ?? null,
          ok: Boolean(evt.ok ?? true),
          reason: String(evt.reason ?? ''),
          latency_ms: Number(evt.latency_ms ?? 0),
          has_image: Boolean(evt.has_image ?? false),
        },
      }
    }
    case 'emotion': {
      return {
        ...card,
        emotion: {
          type: 'emotion',
          turn_id: card.turn_id,
          emotion: String(evt.emotion ?? ''),
          intensity: Number(evt.intensity ?? 0),
          mood_reason: evt.mood_reason ? String(evt.mood_reason) : undefined,
          llm_latency_ms: typeof evt.llm_latency_ms === 'number' ? evt.llm_latency_ms : undefined,
        },
      }
    }
    case 'gesture': {
      const names = Array.isArray(evt.names) ? (evt.names as string[]) : []
      return { ...card, gestures: names }
    }
    case 'memory_extract': {
      const tags = Array.isArray(evt.tags) ? (evt.tags as { tag: string; category: string }[]) : []
      return { ...card, memory_tags: tags }
    }
    case 'first_audio': {
      const ms = Number(evt.first_audio_ms ?? 0)
      return { ...card, first_audio_ms: ms }
    }
    case 'assistant_text': {
      return { ...card, assistant_text: String(evt.text ?? '') }
    }
    case 'turn_error': {
      return {
        ...card,
        error: {
          type: 'turn_error',
          turn_id: card.turn_id,
          reason: String(evt.reason ?? ''),
          stage: String(evt.stage ?? 'unknown'),
          latency_ms: Number(evt.latency_ms ?? 0),
        },
        completed: true,
      }
    }
    case 'done': {
      return {
        ...card,
        done: {
          type: 'done',
          turn_id: card.turn_id,
          total_ms: evt.total_ms as number | undefined,
          llm_latency_ms: evt.llm_latency_ms as number | null | undefined,
          first_audio_ms: evt.first_audio_ms as number | null | undefined,
          tool_call_name: (evt.tool_call_name as string | null | undefined) ?? null,
          tool_call_ok: typeof evt.tool_call_ok === 'boolean' ? evt.tool_call_ok : undefined,
          tool_call_latency_ms:
            typeof evt.tool_call_latency_ms === 'number' ? evt.tool_call_latency_ms : undefined,
        },
        completed: true,
      }
    }
    default:
      return card
  }
}

interface TurnsStore {
  turns: TurnCard[]
  version: number
  ingest: (evt: ConversationEvent) => void
  clear: () => void
}

export const useConversationTurnsStore = create<TurnsStore>()((set, get) => ({
  turns: [],
  version: 0,

  ingest: (evt: ConversationEvent) => {
    const planner_turn_id = extractPlannerTurnId(evt)
    if (!planner_turn_id) return

    const state = get()
    const idx = state.turns.findIndex((t) => t.turn_id === planner_turn_id)
    if (idx >= 0) {
      const updated = updateCard(state.turns[idx], evt)
      const turns = [...state.turns]
      turns[idx] = updated
      set({ turns, version: state.version + 1 })
      return
    }

    // New turn: create a card, cap list length.
    const card: TurnCard = {
      turn_id: planner_turn_id,
      started_ms: Date.now(),
      completed: false,
    }
    const withEvent = updateCard(card, evt)
    const turns = [withEvent, ...state.turns].slice(0, MAX_TURNS)
    set({ turns, version: state.version + 1 })
  },

  clear: () => set({ turns: [], version: 0 }),
}))

// Exported for unit testing.
export const __test_internals = { extractPlannerTurnId, updateCard }
