import { useCallback, useState } from 'react'
import { useSend } from '../hooks/useSend'
import { useServerHealth } from '../hooks/useServerHealth'
import styles from '../styles/global.module.css'

// ── Helpers ──

function Pair({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div style={{ marginTop: 8 }}>
      <span style={{ fontSize: 11, color: 'var(--text-dim)' }}>{label}</span>
      <div className={styles.mono} style={{ fontSize: 11, marginTop: 1 }}>
        {children}
      </div>
    </div>
  )
}

function pct(v: number | null | undefined): string {
  if (v == null) return '—'
  return `${(v * 100).toFixed(0)}%`
}

// ── Component ──

export default function ServerHealthPanel() {
  const { serverHealth: health, generationOverrides, aiConnected, isLoading } = useServerHealth()
  const send = useSend()

  // Generation override local state
  const [tempInput, setTempInput] = useState('')
  const [maxTokInput, setMaxTokInput] = useState('')

  const hasOverrides = Object.keys(generationOverrides).length > 0

  const applyOverrides = useCallback(() => {
    const payload: Record<string, unknown> = { type: 'ai.set_generation_overrides' }
    const temp = Number.parseFloat(tempInput)
    const maxTok = Number.parseInt(maxTokInput, 10)
    if (!Number.isNaN(temp)) payload.temperature = temp
    if (!Number.isNaN(maxTok)) payload.max_output_tokens = maxTok
    if (payload.temperature != null || payload.max_output_tokens != null) {
      send(payload)
    }
  }, [tempInput, maxTokInput, send])

  const clearOverrides = useCallback(() => {
    send({ type: 'ai.clear_generation_overrides' })
    setTempInput('')
    setMaxTokInput('')
  }, [send])

  if (isLoading) {
    return (
      <div className={styles.card}>
        <h3>Server Health</h3>
        <p style={{ fontSize: 12, color: 'var(--text-dim)' }}>Loading...</p>
      </div>
    )
  }

  if (!health) {
    return (
      <div className={styles.card}>
        <h3>Server Health</h3>
        <div style={{ display: 'flex', gap: 8, alignItems: 'center', marginTop: 4 }}>
          <span className={`${styles.badge} ${aiConnected ? styles.badgeYellow : styles.badgeRed}`}>
            {aiConnected ? 'no data' : 'disconnected'}
          </span>
          <span style={{ fontSize: 11, color: 'var(--text-dim)' }}>
            Server health not available
          </span>
        </div>
      </div>
    )
  }

  const llm = health.llm
  const metrics = llm?.engine_metrics ?? {}
  const templateCfg = llm?.template_config
  const genDefaults = llm?.generation_defaults
  const hasMetrics = Object.keys(metrics).length > 0

  return (
    <div className={styles.card}>
      <h3>Server Health</h3>

      {/* Status + model row */}
      <div
        style={{ display: 'flex', gap: 6, flexWrap: 'wrap', marginTop: 4, alignItems: 'center' }}
      >
        <span
          className={`${styles.badge} ${health.status === 'ok' ? styles.badgeGreen : styles.badgeRed}`}
        >
          {health.status}
        </span>
        <span className={`${styles.badge} ${styles.badgeDim}`}>{health.llm_backend}</span>
        {health.model && (
          <span className={styles.mono} style={{ fontSize: 11, color: '#aaa' }}>
            {health.model}
          </span>
        )}
      </div>

      {/* GPU Budget */}
      {health.gpu_budget && (
        <Pair label="GPU Budget">
          LLM {pct(health.gpu_budget.qwen_utilization)}
          {' + '}TTS {pct(health.gpu_budget.orpheus_utilization)}
          {' = '}
          {pct(health.gpu_budget.combined_utilization)}
          {' / cap '}
          {pct(health.gpu_budget.cap)}
        </Pair>
      )}

      {/* Plan Admission */}
      {health.plan_admission && (
        <Pair label="Plan Admission">
          inflight={health.plan_admission.inflight}/{health.plan_admission.max_inflight} admitted=
          {health.plan_admission.admitted} rejected={health.plan_admission.rejected}
        </Pair>
      )}

      {/* Sessions */}
      {health.converse_sessions && (
        <Pair label="Sessions">
          active={health.converse_sessions.active_sessions} registered=
          {health.converse_sessions.registered} preempted={health.converse_sessions.preempted}
        </Pair>
      )}

      {/* LLM Engine */}
      {llm && (
        <Pair label="LLM Engine">
          loaded={String(llm.loaded)} gen={llm.active_generations}/{llm.max_inflight} guided=
          {String(llm.guided_decoding)} template={String(llm.chat_template)}
        </Pair>
      )}

      {/* Template Config */}
      {templateCfg && (
        <Pair label="Model Template">
          family={templateCfg.family}
          {Object.entries(templateCfg.chat_template_kwargs).map(([k, v]) => (
            <span key={k}>
              {' '}
              {k}={String(v)}
            </span>
          ))}
          {templateCfg.notes && (
            <div style={{ fontSize: 10, color: '#777', marginTop: 2 }}>{templateCfg.notes}</div>
          )}
        </Pair>
      )}

      {/* vLLM Metrics */}
      {hasMetrics && (
        <Pair label="vLLM Metrics">
          {metrics.scheduler_running != null && <>running={metrics.scheduler_running} </>}
          {metrics.scheduler_waiting != null && <>waiting={metrics.scheduler_waiting} </>}
          {metrics.scheduler_swapped != null && <>swapped={metrics.scheduler_swapped} </>}
          {metrics.kv_cache_usage_pct != null && <>kv_cache={metrics.kv_cache_usage_pct}%</>}
        </Pair>
      )}

      {/* Generation Defaults */}
      {genDefaults && (
        <Pair label="Generation Defaults">
          temp={genDefaults.temperature} max_tokens={genDefaults.max_output_tokens} timeout=
          {genDefaults.timeout_s}s thinking={String(genDefaults.enable_thinking)}
        </Pair>
      )}

      {/* Dev-only generation overrides */}
      <div
        style={{
          marginTop: 12,
          padding: 8,
          border: '1px dashed #ff9800',
          borderRadius: 6,
          background: 'rgba(255,152,0,0.05)',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 6 }}>
          <span style={{ fontSize: 11, color: '#ff9800', fontWeight: 600 }}>
            DEV ONLY: Generation Overrides
          </span>
          {hasOverrides && (
            <span
              className={styles.badge}
              style={{ background: '#ff9800', color: '#fff', fontSize: 9 }}
            >
              ACTIVE
            </span>
          )}
        </div>
        {hasOverrides && (
          <div className={styles.mono} style={{ fontSize: 10, marginBottom: 6, color: '#ccc' }}>
            {Object.entries(generationOverrides).map(([k, v]) => (
              <span key={k}>
                {k}={v}{' '}
              </span>
            ))}
          </div>
        )}
        <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', alignItems: 'end' }}>
          <label style={{ fontSize: 11 }}>
            Temperature
            <input
              type="number"
              min={0}
              max={2}
              step={0.05}
              value={tempInput}
              onChange={(e) => setTempInput(e.target.value)}
              placeholder={String(genDefaults?.temperature ?? 0.7)}
              style={{ width: 70, marginLeft: 4 }}
            />
          </label>
          <label style={{ fontSize: 11 }}>
            Max Tokens
            <input
              type="number"
              min={64}
              max={2048}
              step={64}
              value={maxTokInput}
              onChange={(e) => setMaxTokInput(e.target.value)}
              placeholder={String(genDefaults?.max_output_tokens ?? 512)}
              style={{ width: 80, marginLeft: 4 }}
            />
          </label>
          <button
            type="button"
            onClick={applyOverrides}
            style={{ fontSize: 11, padding: '4px 10px' }}
          >
            Apply
          </button>
          <button
            type="button"
            onClick={clearOverrides}
            style={{ fontSize: 11, padding: '4px 10px' }}
          >
            Clear
          </button>
        </div>
      </div>
    </div>
  )
}
