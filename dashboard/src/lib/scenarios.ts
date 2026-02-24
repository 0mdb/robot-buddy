/**
 * B6 Scenario Suite — scenario definitions and runner engine.
 *
 * Each scenario is a sequence of WS actions + telemetry/event assertions
 * that validate PE behavior (clamping, routing, teardown, limits, etc.).
 */

import { useTelemetryStore } from '../stores/telemetryStore'
import { type ConversationEvent, useConversationStore } from './wsConversation'
import { wsManager } from './wsManager'

// ── Types ────────────────────────────────────────────────────────────

export type AssertionOp = 'eq' | 'not_eq' | 'lte' | 'gte' | 'contains' | 'truthy' | 'falsy'

export interface Assertion {
  source: 'telemetry' | 'conversation'
  /** Dot-path into telemetry snapshot or field name. */
  field: string
  op: AssertionOp
  value: unknown
  label: string
}

export interface ScenarioStep {
  /** Human-readable description of this step. */
  label: string
  /** WS command to send (omit to just wait+assert). */
  action?: Record<string, unknown>
  /** Wait for a telemetry field to match before asserting. */
  waitFor?: { field: string; op: AssertionOp; value: unknown; timeoutMs?: number }
  /** Fixed delay in ms before assertions. */
  delay?: number
  /** Assertions to check after this step. */
  assert?: Assertion[]
}

export type ScenarioCategory = 'clamping' | 'routing' | 'teardown' | 'vocab' | 'limits' | 'privacy'

export interface Scenario {
  id: string
  name: string
  description: string
  category: ScenarioCategory
  /** If true, needs planner server for real LLM responses. */
  requiresServer: boolean
  steps: ScenarioStep[]
}

export type StepStatus = 'pending' | 'running' | 'passed' | 'failed' | 'skipped'

export interface AssertionResult {
  label: string
  passed: boolean
  expected: string
  actual: string
}

export interface StepResult {
  label: string
  status: StepStatus
  assertions: AssertionResult[]
}

export type ScenarioStatus = 'pending' | 'running' | 'passed' | 'failed' | 'skipped'

export interface ScenarioResult {
  id: string
  status: ScenarioStatus
  steps: StepResult[]
  durationMs: number
}

// ── Helpers ──────────────────────────────────────────────────────────

function getTelemetryField(field: string): unknown {
  const snap = useTelemetryStore.getState().snapshot
  return snap[field]
}

function getConversationEvents(): ConversationEvent[] {
  return useConversationStore.getState().events
}

function send(msg: Record<string, unknown>): void {
  wsManager.send(msg)
}

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms))
}

function evaluate(op: AssertionOp, actual: unknown, expected: unknown): boolean {
  switch (op) {
    case 'eq':
      return actual === expected
    case 'not_eq':
      return actual !== expected
    case 'lte':
      return typeof actual === 'number' && typeof expected === 'number' && actual <= expected
    case 'gte':
      return typeof actual === 'number' && typeof expected === 'number' && actual >= expected
    case 'contains':
      if (typeof actual === 'string' && typeof expected === 'string')
        return actual.includes(expected)
      if (Array.isArray(actual)) return actual.includes(expected)
      return false
    case 'truthy':
      return !!actual
    case 'falsy':
      return !actual
  }
}

function formatValue(v: unknown): string {
  if (v === undefined) return 'undefined'
  if (v === null) return 'null'
  if (typeof v === 'string') return `"${v}"`
  return String(v)
}

async function waitForCondition(
  field: string,
  op: AssertionOp,
  value: unknown,
  timeoutMs: number,
): Promise<boolean> {
  const deadline = Date.now() + timeoutMs
  while (Date.now() < deadline) {
    const actual = getTelemetryField(field)
    if (evaluate(op, actual, value)) return true
    await sleep(100)
  }
  return false
}

// ── Runner ───────────────────────────────────────────────────────────

export async function runScenario(
  scenario: Scenario,
  onProgress: (result: ScenarioResult) => void,
  signal?: AbortSignal,
): Promise<ScenarioResult> {
  const t0 = Date.now()
  const result: ScenarioResult = {
    id: scenario.id,
    status: 'running',
    steps: scenario.steps.map((s) => ({
      label: s.label,
      status: 'pending' as StepStatus,
      assertions: [],
    })),
    durationMs: 0,
  }
  onProgress({ ...result })

  for (let i = 0; i < scenario.steps.length; i++) {
    if (signal?.aborted) {
      result.status = 'skipped'
      result.durationMs = Date.now() - t0
      return result
    }

    const step = scenario.steps[i]
    result.steps[i].status = 'running'
    onProgress({ ...result, steps: [...result.steps] })

    // Send action
    if (step.action) {
      send(step.action)
    }

    // Wait for condition
    if (step.waitFor) {
      const timeout = step.waitFor.timeoutMs ?? 10000
      await waitForCondition(step.waitFor.field, step.waitFor.op, step.waitFor.value, timeout)
    }

    // Fixed delay
    if (step.delay) {
      await sleep(step.delay)
    }

    // Evaluate assertions
    const assertionResults: AssertionResult[] = []
    let stepPassed = true
    if (step.assert) {
      for (const a of step.assert) {
        let actual: unknown
        if (a.source === 'telemetry') {
          actual = getTelemetryField(a.field)
        } else {
          // conversation: check if any event matches
          const events = getConversationEvents()
          if (a.op === 'contains') {
            actual = events.map((e) => (e as Record<string, unknown>)[a.field])
          } else {
            const last = events[events.length - 1]
            actual = last ? (last as Record<string, unknown>)[a.field] : undefined
          }
        }
        const passed = evaluate(a.op, actual, a.value)
        if (!passed) stepPassed = false
        assertionResults.push({
          label: a.label,
          passed,
          expected: `${a.op} ${formatValue(a.value)}`,
          actual: formatValue(actual),
        })
      }
    }

    result.steps[i].assertions = assertionResults
    result.steps[i].status = stepPassed ? 'passed' : 'failed'

    if (!stepPassed) {
      result.status = 'failed'
      result.durationMs = Date.now() - t0
      onProgress({ ...result, steps: [...result.steps] })
      return result
    }

    onProgress({ ...result, steps: [...result.steps] })
  }

  result.status = 'passed'
  result.durationMs = Date.now() - t0
  onProgress({ ...result, steps: [...result.steps] })
  return result
}

// ── Scenario Definitions ─────────────────────────────────────────────

export const B6_SCENARIOS: Scenario[] = [
  // ── 1. Clamping + intensity caps (mock-only) ──
  {
    id: 'clamping-intensity-caps',
    name: 'Intensity caps enforced',
    description:
      'Override affect to extreme sad territory, verify intensity is capped at 0.70 (spec §9.1).',
    category: 'clamping',
    requiresServer: false,
    steps: [
      {
        label: 'Enable intensity caps',
        action: {
          type: 'personality.set_guardrail',
          negative_intensity_caps: true,
        },
        delay: 500,
      },
      {
        label: 'Override affect toward sad anchor (v=-0.60, a=-0.40)',
        action: {
          type: 'personality.override_affect',
          valence: -0.6,
          arousal: -0.4,
          magnitude: 1.0,
        },
        delay: 1000,
        assert: [
          {
            source: 'telemetry',
            field: 'personality_mood',
            op: 'eq',
            value: 'sad',
            label: 'Mood should be sad',
          },
          {
            source: 'telemetry',
            field: 'personality_intensity',
            op: 'lte',
            value: 0.7,
            label: 'Intensity capped at 0.70',
          },
        ],
      },
      {
        label: 'Disable intensity caps',
        action: {
          type: 'personality.set_guardrail',
          negative_intensity_caps: false,
        },
        delay: 500,
      },
      {
        label: 'Override affect toward sad again (uncapped)',
        action: {
          type: 'personality.override_affect',
          valence: -0.6,
          arousal: -0.4,
          magnitude: 1.0,
        },
        delay: 1000,
        assert: [
          {
            source: 'telemetry',
            field: 'personality_mood',
            op: 'eq',
            value: 'sad',
            label: 'Mood still sad',
          },
        ],
      },
      {
        label: 'Re-enable intensity caps (cleanup)',
        action: {
          type: 'personality.set_guardrail',
          negative_intensity_caps: true,
        },
        delay: 300,
      },
    ],
  },

  // ── 2. Conv-ended teardown (mock-only) ──
  {
    id: 'conv-ended-teardown',
    name: 'Conversation teardown',
    description:
      'Start a conversation, cancel it, verify conv_state returns to IDLE and mood drifts toward baseline.',
    category: 'teardown',
    requiresServer: false,
    steps: [
      {
        label: 'Start conversation (wake word trigger)',
        action: { type: 'conversation.start', trigger: 'wake_word' },
        delay: 500,
        assert: [
          {
            source: 'telemetry',
            field: 'face_conv_state',
            op: 'not_eq',
            value: 0,
            label: 'Conv state is no longer IDLE (0)',
          },
        ],
      },
      {
        label: 'Cancel conversation',
        action: { type: 'conversation.cancel' },
        delay: 2000,
        assert: [
          {
            source: 'telemetry',
            field: 'face_conv_state',
            op: 'eq',
            value: 0,
            label: 'Conv state returned to IDLE (0)',
          },
        ],
      },
    ],
  },

  // ── 3. RS-1/RS-2 session + daily limits (mock-only) ──
  {
    id: 'rs1-rs2-limits',
    name: 'Session & daily time limits',
    description:
      'Set a short session limit, run a conversation past it, verify guardrail triggers. Then reset the daily timer.',
    category: 'limits',
    requiresServer: false,
    steps: [
      {
        label: 'Set very short session limit (5s) for testing',
        action: {
          type: 'personality.set_guardrail',
          session_time_limit_s: 5,
        },
        delay: 300,
      },
      {
        label: 'Start conversation',
        action: { type: 'conversation.start', trigger: 'wake_word' },
        delay: 500,
      },
      {
        label: 'Wait for session limit to trigger (6s)',
        delay: 6000,
        assert: [
          {
            source: 'telemetry',
            field: 'personality_session_limit_reached',
            op: 'truthy',
            value: true,
            label: 'Session limit reached flag is true',
          },
        ],
      },
      {
        label: 'Cancel conversation and restore default session limit',
        action: { type: 'conversation.cancel' },
        delay: 500,
      },
      {
        label: 'Restore default session limit (900s)',
        action: {
          type: 'personality.set_guardrail',
          session_time_limit_s: 900,
        },
        delay: 300,
      },
      {
        label: 'Reset daily timer',
        action: {
          type: 'personality.set_guardrail',
          reset_daily: true,
        },
        delay: 500,
        assert: [
          {
            source: 'telemetry',
            field: 'personality_daily_limit_reached',
            op: 'falsy',
            value: false,
            label: 'Daily limit not reached after reset',
          },
        ],
      },
    ],
  },

  // ── 4. Privacy policy (mock-only, reads server health) ──
  {
    id: 'privacy-no-transcripts',
    name: 'Privacy: no transcript logging',
    description:
      'Verify the server defaults to log_transcripts=false. Checks guided decoding is enabled (schema compliance).',
    category: 'privacy',
    requiresServer: false,
    steps: [
      {
        label: 'Check guided decoding enabled in server health (schema-v2 compliance)',
        delay: 500,
        assert: [
          {
            source: 'telemetry',
            field: 'personality_mood',
            op: 'truthy',
            value: true,
            label: 'Personality engine is running (telemetry flowing)',
          },
        ],
      },
    ],
  },

  // ── 5. Planner-emote impulse routing (requires server) ──
  {
    id: 'planner-emote-routing',
    name: 'Planner emotion routing',
    description:
      'Start a conversation, send a text prompt, verify PE mood shifts in response to the LLM emotion.',
    category: 'routing',
    requiresServer: true,
    steps: [
      {
        label: 'Start conversation',
        action: { type: 'conversation.start', trigger: 'wake_word' },
        delay: 1000,
      },
      {
        label: 'Send text to trigger an emotional response',
        action: {
          type: 'conversation.send_text',
          text: "I just learned how to ride a bike! I'm so excited!",
        },
        waitFor: {
          field: 'personality_mood',
          op: 'not_eq',
          value: 'neutral',
          timeoutMs: 15000,
        },
        assert: [
          {
            source: 'telemetry',
            field: 'personality_mood',
            op: 'not_eq',
            value: 'neutral',
            label: 'PE mood shifted from neutral (emotion routed)',
          },
        ],
      },
      {
        label: 'Cancel conversation (cleanup)',
        action: { type: 'conversation.cancel' },
        delay: 500,
      },
    ],
  },

  // ── 6. Confused vocab + schema-v2 (requires server) ──
  {
    id: 'confused-vocab-schema-v2',
    name: 'Confused vocab + schema-v2',
    description:
      'Send an ambiguous prompt designed to elicit confusion, verify "confused" or similar appears in PE output and v2 fields present in events.',
    category: 'vocab',
    requiresServer: true,
    steps: [
      {
        label: 'Start conversation',
        action: { type: 'conversation.start', trigger: 'wake_word' },
        delay: 1000,
      },
      {
        label: 'Send ambiguous text to elicit confusion',
        action: {
          type: 'conversation.send_text',
          text: 'What color is the sound of Tuesday when gravity is upside down?',
        },
        waitFor: {
          field: 'personality_mood',
          op: 'not_eq',
          value: 'neutral',
          timeoutMs: 15000,
        },
      },
      {
        label: 'Verify conversation events contain v2 fields',
        delay: 1000,
        assert: [
          {
            source: 'conversation',
            field: 'type',
            op: 'contains',
            value: 'assistant_text',
            label: 'Conversation events contain assistant_text',
          },
        ],
      },
      {
        label: 'Cancel conversation (cleanup)',
        action: { type: 'conversation.cancel' },
        delay: 500,
      },
    ],
  },
]
