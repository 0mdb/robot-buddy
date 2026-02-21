import { useState } from 'react'
import { FaultBadges } from '../components/FaultBadges'
import { Joystick } from '../components/Joystick'
import { Sparkline } from '../components/Sparkline'
import { useSend } from '../hooks/useSend'
import { useTelemetry } from '../hooks/useTelemetry'
import styles from '../styles/global.module.css'

interface GaugeCardProps {
  label: string
  unit: string
  metric: string
  valueField: string
  decimals?: number
}

function GaugeCard({ label, unit, metric, valueField, decimals = 0 }: GaugeCardProps) {
  const value = useTelemetry((s) => s.snapshot[valueField])
  const display = typeof value === 'number' ? value.toFixed(decimals) : '--'

  return (
    <div className={styles.card} style={{ padding: 10, minWidth: 0 }}>
      <div style={{ fontSize: 11, color: '#999', marginBottom: 2 }}>{label}</div>
      <div className={styles.mono} style={{ fontSize: 22, fontWeight: 700, lineHeight: 1.1 }}>
        {display}
        <span style={{ fontSize: 11, fontWeight: 400, color: '#888', marginLeft: 4 }}>{unit}</span>
      </div>
      <div style={{ marginTop: 6, height: 32 }}>
        <Sparkline metric={metric} />
      </div>
    </div>
  )
}

export default function DriveTab() {
  const send = useSend()
  const currentMode = useTelemetry((s) => s.snapshot.mode)
  const faultFlags = useTelemetry((s) => (s.snapshot.fault_flags as number) ?? 0)
  const speedCaps = useTelemetry(
    (s) => s.snapshot.speed_caps as Array<{ scale: number; reason: string }> | undefined,
  )
  const [videoEnabled, setVideoEnabled] = useState(false)

  const modeButtons: { label: string; mode: string }[] = [
    { label: 'IDLE', mode: 'IDLE' },
    { label: 'TELEOP', mode: 'TELEOP' },
    { label: 'WANDER', mode: 'WANDER' },
  ]

  return (
    <div style={{ display: 'flex', gap: 16, height: '100%', padding: 16 }}>
      {/* Left column — controls */}
      <div style={{ width: 200, flexShrink: 0, display: 'flex', flexDirection: 'column', gap: 10 }}>
        <div className={styles.card} style={{ padding: 12 }}>
          <div style={{ fontSize: 12, fontWeight: 600, marginBottom: 8, color: '#ccc' }}>MODE</div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
            {modeButtons.map((btn) => (
              <button
                type="button"
                key={btn.mode}
                className={currentMode === btn.mode ? styles.btnPrimary : undefined}
                style={{
                  padding: '8px 0',
                  border: currentMode === btn.mode ? 'none' : '1px solid #555',
                  borderRadius: 4,
                  background: currentMode === btn.mode ? undefined : '#2a2a2a',
                  color: currentMode === btn.mode ? '#fff' : '#aaa',
                  cursor: 'pointer',
                  fontWeight: 600,
                  fontSize: 13,
                }}
                onClick={() => send({ type: 'set_mode', mode: btn.mode })}
              >
                {btn.label}
              </button>
            ))}
          </div>
        </div>

        <button
          type="button"
          className={styles.btnDanger}
          style={{
            padding: '16px 0',
            fontSize: 18,
            fontWeight: 800,
            letterSpacing: 2,
            borderRadius: 6,
            border: '2px solid #ff2222',
            cursor: 'pointer',
          }}
          onClick={() => send({ type: 'e_stop' })}
        >
          E-STOP
        </button>

        <button
          type="button"
          style={{
            padding: '8px 0',
            border: '1px solid #555',
            borderRadius: 4,
            background: '#2a2a2a',
            color: '#ccc',
            cursor: 'pointer',
            fontSize: 13,
          }}
          onClick={() => send({ type: 'clear' })}
        >
          Clear Faults
        </button>

        <button
          type="button"
          style={{
            padding: '8px 0',
            border: '1px solid #555',
            borderRadius: 4,
            background: videoEnabled ? '#1a3a1a' : '#2a2a2a',
            color: videoEnabled ? '#6f6' : '#ccc',
            cursor: 'pointer',
            fontSize: 13,
          }}
          onClick={() => setVideoEnabled((v) => !v)}
        >
          {videoEnabled ? 'Video ON' : 'Video OFF'}
        </button>

        {videoEnabled && (
          <div className={styles.card} style={{ padding: 4, overflow: 'hidden' }}>
            <img
              src="/video"
              alt="Robot camera"
              style={{ width: '100%', display: 'block', borderRadius: 4 }}
            />
          </div>
        )}
      </div>

      {/* Center column — joystick */}
      <div
        style={{
          flex: '0 0 280px',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
        }}
      >
        <Joystick onTwist={(v, w) => send({ type: 'twist', v, w })} />
      </div>

      {/* Right area — gauges, faults, speed caps */}
      <div style={{ flex: 1, minWidth: 0, display: 'flex', flexDirection: 'column', gap: 12 }}>
        <div className={styles.grid2} style={{ gap: 10 }}>
          <GaugeCard label="Speed L" unit="mm/s" metric="speed_l" valueField="speed_l" />
          <GaugeCard label="Speed R" unit="mm/s" metric="speed_r" valueField="speed_r" />
          <GaugeCard label="V meas" unit="mm/s" metric="v_meas" valueField="v_meas" />
          <GaugeCard label="W meas" unit="mrad/s" metric="w_meas" valueField="w_meas" />
          <GaugeCard
            label="Gyro Z"
            unit="mrad/s"
            metric="gyro_z"
            valueField="gyro_z"
            decimals={1}
          />
          <GaugeCard label="Range" unit="mm" metric="range_mm" valueField="range_mm" />
          <GaugeCard label="Battery" unit="mV" metric="battery_mv" valueField="battery_mv" />
          <GaugeCard
            label="Tick dt"
            unit="ms"
            metric="tick_dt_ms"
            valueField="tick_dt_ms"
            decimals={1}
          />
        </div>

        {/* Fault badges */}
        <div className={styles.card} style={{ padding: 10 }}>
          <div style={{ fontSize: 12, fontWeight: 600, marginBottom: 6, color: '#ccc' }}>
            FAULTS
          </div>
          <FaultBadges flags={faultFlags} />
        </div>

        {/* Speed caps */}
        {speedCaps && Array.isArray(speedCaps) && speedCaps.length > 0 && (
          <div className={styles.card} style={{ padding: 10 }}>
            <div style={{ fontSize: 12, fontWeight: 600, marginBottom: 6, color: '#ccc' }}>
              SPEED CAPS
            </div>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
              {speedCaps.map((cap, i: number) => (
                <span
                  key={
                    typeof cap === 'object' && cap !== null
                      ? (cap as { scale: number; reason: string }).reason
                      : i
                  }
                  className={styles.badgeYellow}
                >
                  {typeof cap === 'object' && cap !== null
                    ? `${(cap as { scale: number; reason: string }).reason} (${Math.round((cap as { scale: number; reason: string }).scale * 100)}%)`
                    : String(cap)}
                </span>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
