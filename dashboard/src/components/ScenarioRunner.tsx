import { useCallback, useRef, useState } from 'react'
import { useServerHealth } from '../hooks/useServerHealth'
import {
  B6_SCENARIOS,
  runScenario,
  type ScenarioResult,
  type ScenarioStatus,
  type StepStatus,
} from '../lib/scenarios'
import styles from '../styles/global.module.css'

// ── Status helpers ───────────────────────────────────────────────────

const STATUS_ICON: Record<ScenarioStatus | StepStatus, string> = {
  pending: '\u25cb', // ○
  running: '\u25d4', // ◔
  passed: '\u2713', // ✓
  failed: '\u2717', // ✗
  skipped: '\u2013', // –
}

const STATUS_COLOR: Record<ScenarioStatus | StepStatus, string> = {
  pending: 'var(--text-dim)',
  running: 'var(--blue)',
  passed: 'var(--green)',
  failed: 'var(--red)',
  skipped: 'var(--text-dim)',
}

const CATEGORY_COLOR: Record<string, string> = {
  clamping: '#ff9800',
  routing: '#03a9f4',
  teardown: '#9c27b0',
  vocab: '#4caf50',
  limits: '#e91e63',
  privacy: '#607d8b',
}

// ── Component ────────────────────────────────────────────────────────

export default function ScenarioRunner() {
  const [results, setResults] = useState<Map<string, ScenarioResult>>(new Map())
  const [running, setRunning] = useState(false)
  const [expanded, setExpanded] = useState<Set<string>>(new Set())
  const abortRef = useRef<AbortController | null>(null)
  const { serverHealth } = useServerHealth()
  const serverOnline = !!serverHealth?.status

  const updateResult = useCallback((r: ScenarioResult) => {
    setResults((prev) => {
      const next = new Map(prev)
      next.set(r.id, r)
      return next
    })
  }, [])

  const runAll = useCallback(async () => {
    setRunning(true)
    const ctrl = new AbortController()
    abortRef.current = ctrl

    // Reset all results
    setResults(new Map())

    for (const scenario of B6_SCENARIOS) {
      if (ctrl.signal.aborted) break

      if (scenario.requiresServer && !serverOnline) {
        updateResult({
          id: scenario.id,
          status: 'skipped',
          steps: scenario.steps.map((s) => ({
            label: s.label,
            status: 'skipped',
            assertions: [],
          })),
          durationMs: 0,
        })
        continue
      }

      await runScenario(scenario, updateResult, ctrl.signal)
    }

    setRunning(false)
    abortRef.current = null
  }, [serverOnline, updateResult])

  const runSingle = useCallback(
    async (scenarioId: string) => {
      const scenario = B6_SCENARIOS.find((s) => s.id === scenarioId)
      if (!scenario) return

      if (scenario.requiresServer && !serverOnline) {
        updateResult({
          id: scenario.id,
          status: 'skipped',
          steps: scenario.steps.map((s) => ({
            label: s.label,
            status: 'skipped',
            assertions: [],
          })),
          durationMs: 0,
        })
        return
      }

      setRunning(true)
      const ctrl = new AbortController()
      abortRef.current = ctrl
      await runScenario(scenario, updateResult, ctrl.signal)
      setRunning(false)
      abortRef.current = null
    },
    [serverOnline, updateResult],
  )

  const stopAll = useCallback(() => {
    abortRef.current?.abort()
  }, [])

  const toggleExpand = useCallback((id: string) => {
    setExpanded((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }, [])

  // Summary counts
  const total = B6_SCENARIOS.length
  const passed = Array.from(results.values()).filter((r) => r.status === 'passed').length
  const failed = Array.from(results.values()).filter((r) => r.status === 'failed').length
  const skipped = Array.from(results.values()).filter((r) => r.status === 'skipped').length

  return (
    <details className={styles.card}>
      <summary style={{ cursor: 'pointer', fontWeight: 600, fontSize: 14, marginBottom: 8 }}>
        B6 Scenarios
        {results.size > 0 && (
          <span style={{ fontWeight: 400, fontSize: 12, marginLeft: 8, color: 'var(--text-dim)' }}>
            {passed}/{total} passed
            {failed > 0 && (
              <span style={{ color: 'var(--red)', marginLeft: 4 }}>{failed} failed</span>
            )}
            {skipped > 0 && <span style={{ marginLeft: 4 }}>{skipped} skipped</span>}
          </span>
        )}
      </summary>

      {/* Controls bar */}
      <div style={{ display: 'flex', gap: 8, alignItems: 'center', marginBottom: 8 }}>
        {!running ? (
          <button
            type="button"
            onClick={runAll}
            style={{
              padding: '4px 12px',
              background: 'var(--accent)',
              color: '#fff',
              border: 'none',
              borderRadius: 4,
              cursor: 'pointer',
              fontSize: 12,
            }}
          >
            Run All
          </button>
        ) : (
          <button
            type="button"
            onClick={stopAll}
            style={{
              padding: '4px 12px',
              background: 'var(--red)',
              color: '#fff',
              border: 'none',
              borderRadius: 4,
              cursor: 'pointer',
              fontSize: 12,
            }}
          >
            Stop
          </button>
        )}
        {!serverOnline && (
          <span style={{ fontSize: 11, color: 'var(--yellow)' }}>
            Server offline — server-required scenarios will be skipped
          </span>
        )}
      </div>

      {/* Scenario list */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
        {B6_SCENARIOS.map((scenario) => {
          const r = results.get(scenario.id)
          const isExpanded = expanded.has(scenario.id)
          const status: ScenarioStatus = r?.status ?? 'pending'

          return (
            <div
              key={scenario.id}
              style={{
                border: '1px solid var(--border)',
                borderRadius: 6,
                padding: '6px 8px',
                background: status === 'failed' ? 'rgba(244,67,54,0.06)' : 'transparent',
              }}
            >
              {/* Scenario header row */}
              {/* biome-ignore lint/a11y/useKeyWithClickEvents: dev-only tuning UI */}
              <div
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: 8,
                  cursor: 'pointer',
                }}
                onClick={() => toggleExpand(scenario.id)}
              >
                {/* Status icon */}
                <span
                  style={{
                    color: STATUS_COLOR[status],
                    fontWeight: 700,
                    fontSize: 14,
                    width: 16,
                    textAlign: 'center',
                  }}
                >
                  {STATUS_ICON[status]}
                </span>

                {/* Category badge */}
                <span
                  className={styles.badge}
                  style={{
                    background: CATEGORY_COLOR[scenario.category] ?? '#888',
                    color: '#fff',
                    fontSize: 9,
                    padding: '1px 5px',
                  }}
                >
                  {scenario.category}
                </span>

                {/* Name */}
                <span style={{ flex: 1, fontSize: 12, fontWeight: 500 }}>
                  {scenario.name}
                  {scenario.requiresServer && (
                    <span style={{ fontSize: 9, color: 'var(--text-dim)', marginLeft: 4 }}>
                      [server]
                    </span>
                  )}
                </span>

                {/* Duration */}
                {r && r.durationMs > 0 && (
                  <span style={{ fontSize: 10, color: 'var(--text-dim)' }}>
                    {(r.durationMs / 1000).toFixed(1)}s
                  </span>
                )}

                {/* Run button */}
                <button
                  type="button"
                  onClick={(e) => {
                    e.stopPropagation()
                    runSingle(scenario.id)
                  }}
                  disabled={running}
                  style={{
                    padding: '2px 8px',
                    fontSize: 10,
                    background: 'transparent',
                    color: 'var(--text-dim)',
                    border: '1px solid var(--border)',
                    borderRadius: 3,
                    cursor: running ? 'default' : 'pointer',
                    opacity: running ? 0.4 : 1,
                  }}
                >
                  Run
                </button>
              </div>

              {/* Expanded: step details */}
              {isExpanded && (
                <div style={{ marginTop: 6, paddingLeft: 24 }}>
                  <div style={{ fontSize: 11, color: 'var(--text-dim)', marginBottom: 4 }}>
                    {scenario.description}
                  </div>
                  {(
                    r?.steps ??
                    scenario.steps.map((s) => ({
                      label: s.label,
                      status: 'pending' as StepStatus,
                      assertions: [],
                    }))
                  ).map((step, i) => (
                    <div key={i} style={{ marginBottom: 4 }}>
                      <div
                        style={{
                          display: 'flex',
                          alignItems: 'center',
                          gap: 6,
                          fontSize: 11,
                        }}
                      >
                        <span
                          style={{
                            color: STATUS_COLOR[step.status],
                            fontWeight: 600,
                            width: 12,
                            textAlign: 'center',
                          }}
                        >
                          {STATUS_ICON[step.status]}
                        </span>
                        <span>{step.label}</span>
                      </div>
                      {/* Assertion results */}
                      {step.assertions.length > 0 && (
                        <div style={{ paddingLeft: 18 }}>
                          {step.assertions.map((a, j) => (
                            <div
                              key={j}
                              style={{
                                fontSize: 10,
                                color: a.passed ? 'var(--green)' : 'var(--red)',
                                display: 'flex',
                                gap: 6,
                              }}
                            >
                              <span>{a.passed ? '\u2713' : '\u2717'}</span>
                              <span>{a.label}</span>
                              {!a.passed && (
                                <span style={{ color: 'var(--text-dim)' }}>
                                  (expected {a.expected}, got {a.actual})
                                </span>
                              )}
                            </div>
                          ))}
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              )}
            </div>
          )
        })}
      </div>
    </details>
  )
}
