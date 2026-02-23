import { useState } from 'react'
import { TimeSeriesChart } from '../components/TimeSeriesChart'
import styles from '../styles/global.module.css'

const WINDOW_OPTIONS = [30, 60, 120] as const

export default function TelemetryTab() {
  const [window, setWindow] = useState<number>(60)

  return (
    <div style={{ padding: 16, display: 'flex', flexDirection: 'column', gap: 16 }}>
      {/* Header row */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
        <div style={{ fontSize: 16, fontWeight: 600, color: '#ccc' }}>Telemetry</div>
        <div style={{ display: 'flex', gap: 6 }}>
          {WINDOW_OPTIONS.map((w) => (
            <button
              type="button"
              key={w}
              className={window === w ? styles.btnPrimary : undefined}
              style={{
                padding: '4px 12px',
                border: window === w ? 'none' : '1px solid #555',
                borderRadius: 4,
                background: window === w ? undefined : '#2a2a2a',
                color: window === w ? '#fff' : '#aaa',
                cursor: 'pointer',
                fontSize: 13,
                fontWeight: 600,
              }}
              onClick={() => setWindow(w)}
            >
              {w}s
            </button>
          ))}
        </div>
      </div>

      {/* Wheel Speeds */}
      <TimeSeriesChart
        title="Wheel Speeds"
        yLabel="mm/s"
        window={window}
        height={200}
        series={[
          { metric: 'speed_l', label: 'Speed L', color: '#3b82f6' },
          { metric: 'speed_r', label: 'Speed R', color: '#22d3ee' },
          { metric: 'v_cmd', label: 'V cmd', color: '#f97316' },
          { metric: 'v_capped', label: 'V capped', color: '#ef4444' },
        ]}
      />

      {/* Rotation */}
      <TimeSeriesChart
        title="Rotation"
        yLabel="mrad/s"
        window={window}
        height={200}
        series={[
          { metric: 'gyro_z', label: 'Gyro Z', color: '#a855f7' },
          { metric: 'w_cmd', label: 'W cmd', color: '#f97316' },
          { metric: 'w_capped', label: 'W capped', color: '#ef4444' },
        ]}
      />

      {/* Accelerometer */}
      <TimeSeriesChart
        title="Accelerometer"
        yLabel="mg"
        window={window}
        height={200}
        series={[
          { metric: 'accel_x', label: 'Accel X', color: '#ef4444' },
          { metric: 'accel_y', label: 'Accel Y', color: '#22c55e' },
          { metric: 'accel_z', label: 'Accel Z', color: '#3b82f6' },
        ]}
      />

      {/* Range */}
      <TimeSeriesChart
        title="Range"
        yLabel="mm"
        window={window}
        height={200}
        series={[{ metric: 'range_mm', label: 'Range', color: '#22c55e' }]}
        thresholds={[
          { value: 250, color: '#ef4444', label: 'Stop' },
          { value: 400, color: '#eab308', label: 'Release' },
        ]}
      />

      {/* Battery */}
      <TimeSeriesChart
        title="Battery"
        yLabel="mV"
        window={window}
        height={200}
        series={[{ metric: 'battery_mv', label: 'Battery', color: '#eab308' }]}
      />
    </div>
  )
}
