import { useEffect, useMemo, useState } from 'react'
import { CameraSettingsPanel } from '../components/CameraSettingsPanel'
import { Sparkline } from '../components/Sparkline'
import { useParamsList, useUpdateParams } from '../hooks/useParams'
import { useTelemetry } from '../hooks/useTelemetry'
import styles from '../styles/global.module.css'
import type { ParamDef } from '../types'

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/** Build a name->ParamDef lookup from the param list */
function paramMap(params: ParamDef[] | undefined): Map<string, ParamDef> {
  const m = new Map<string, ParamDef>()
  if (params) for (const p of params) m.set(p.name, p)
  return m
}

function shortParamName(name: string): string {
  const i = name.lastIndexOf('.')
  return i >= 0 ? name.slice(i + 1) : name
}

/** Labelled number input */
function NumField({
  label,
  value,
  step,
  min,
  max,
  onChange,
}: {
  label: string
  value: number
  step?: number
  min?: number
  max?: number
  onChange: (v: number) => void
}) {
  return (
    <label style={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
      <span>{label}</span>
      <input
        type="number"
        value={value}
        step={step ?? 0.001}
        min={min}
        max={max}
        style={{ width: '100%' }}
        onChange={(e) => onChange(Number(e.target.value))}
      />
    </label>
  )
}

/** Labelled range slider with live readout */
function RangeField({
  label,
  value,
  min,
  max,
  step,
  onChange,
}: {
  label: string
  value: number
  min: number
  max: number
  step?: number
  onChange: (v: number) => void
}) {
  return (
    <label style={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
      <span>
        {label}: <strong>{value}</strong>
      </span>
      <input
        type="range"
        value={value}
        min={min}
        max={max}
        step={step ?? 1}
        onChange={(e) => onChange(Number(e.target.value))}
      />
    </label>
  )
}

// ---------------------------------------------------------------------------
// Static key arrays (outside components to avoid re-creation on render)
// ---------------------------------------------------------------------------

const PID_KEYS = ['reflex.kV', 'reflex.kS', 'reflex.Kp', 'reflex.Ki', 'reflex.K_yaw'] as const
const LIMITS_KEYS = [
  'reflex.max_v_mm_s',
  'reflex.max_a_mm_s2',
  'reflex.max_w_mrad_s',
  'reflex.max_aw_mrad_s2',
] as const
const PWM_KEYS = ['reflex.min_pwm', 'reflex.max_pwm'] as const
const PID_ALL_KEYS = [...PID_KEYS, ...LIMITS_KEYS, ...PWM_KEYS]

// ---------------------------------------------------------------------------
// Section components
// ---------------------------------------------------------------------------

function PIDSection({
  pmap,
  onApply,
  applying,
}: {
  pmap: Map<string, ParamDef>
  onApply: (patch: Record<string, number>) => void
  applying: boolean
}) {
  const allKeys = PID_ALL_KEYS

  const initialValues = useMemo(() => {
    const v: Record<string, number> = {}
    for (const k of allKeys) v[k] = pmap.get(k)?.value ?? 0
    return v
  }, [pmap])

  const [local, setLocal] = useState<Record<string, number>>(initialValues)

  useEffect(() => {
    setLocal(initialValues)
  }, [initialValues])

  const set = (key: string, v: number) => setLocal((prev) => ({ ...prev, [key]: v }))

  return (
    <>
      <h3>PID Gains</h3>
      <div className={styles.grid3}>
        {PID_KEYS.map((k) => (
          <NumField
            key={k}
            label={shortParamName(k)}
            value={local[k] ?? 0}
            step={pmap.get(k)?.step}
            min={pmap.get(k)?.min}
            max={pmap.get(k)?.max}
            onChange={(v) => set(k, v)}
          />
        ))}
      </div>

      <h3 style={{ marginTop: 12 }}>Motion Limits</h3>
      <div className={styles.grid3}>
        {LIMITS_KEYS.map((k) => (
          <NumField
            key={k}
            label={shortParamName(k)}
            value={local[k] ?? 0}
            step={pmap.get(k)?.step ?? 1}
            min={pmap.get(k)?.min}
            max={pmap.get(k)?.max}
            onChange={(v) => set(k, v)}
          />
        ))}
      </div>

      <h3 style={{ marginTop: 12 }}>PWM Bounds</h3>
      <div className={styles.grid3}>
        {PWM_KEYS.map((k) => (
          <NumField
            key={k}
            label={shortParamName(k)}
            value={local[k] ?? 0}
            step={pmap.get(k)?.step ?? 1}
            min={pmap.get(k)?.min}
            max={pmap.get(k)?.max}
            onChange={(v) => set(k, v)}
          />
        ))}
      </div>

      <div style={{ marginTop: 12, display: 'flex', alignItems: 'center', gap: 12 }}>
        <button
          type="button"
          className={styles.btnPrimary}
          disabled={applying}
          onClick={() => {
            const patch: Record<string, number> = {}
            for (const k of allKeys) {
              if (local[k] !== undefined) patch[k] = local[k]
            }
            onApply(patch)
          }}
        >
          {applying ? 'Applying...' : 'Apply All'}
        </button>
      </div>

      <div style={{ marginTop: 12 }}>
        <div style={{ fontSize: 12, color: '#999', marginBottom: 4 }}>speed_l sparkline</div>
        <Sparkline metric="speed_l" width={280} height={40} />
      </div>
    </>
  )
}

function RangeSection({
  pmap,
  onApply,
  applying,
}: {
  pmap: Map<string, ParamDef>
  onApply: (patch: Record<string, number>) => void
  applying: boolean
}) {
  const keys = ['reflex.range_stop_mm', 'reflex.range_release_mm'] as const

  const initialValues = useMemo(() => {
    const v: Record<string, number> = {}
    for (const k of keys) v[k] = pmap.get(k)?.value ?? 0
    return v
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pmap, keys])

  const [local, setLocal] = useState<Record<string, number>>(initialValues)

  useEffect(() => {
    setLocal(initialValues)
  }, [initialValues])

  const set = (key: string, v: number) => setLocal((prev) => ({ ...prev, [key]: v }))

  const rangeMm = useTelemetry((s) => s.snapshot.range_mm)

  return (
    <>
      <RangeField
        label="range_stop_mm"
        value={local['reflex.range_stop_mm'] ?? 250}
        min={pmap.get('reflex.range_stop_mm')?.min ?? 100}
        max={pmap.get('reflex.range_stop_mm')?.max ?? 500}
        step={pmap.get('reflex.range_stop_mm')?.step ?? 10}
        onChange={(v) => set('reflex.range_stop_mm', v)}
      />
      <RangeField
        label="range_release_mm"
        value={local['reflex.range_release_mm'] ?? 400}
        min={pmap.get('reflex.range_release_mm')?.min ?? 200}
        max={pmap.get('reflex.range_release_mm')?.max ?? 800}
        step={pmap.get('reflex.range_release_mm')?.step ?? 10}
        onChange={(v) => set('reflex.range_release_mm', v)}
      />

      <div style={{ marginTop: 8 }}>
        <span style={{ fontSize: 12, color: '#999' }}>Live range_mm: </span>
        <span className={styles.mono} style={{ fontSize: 16, fontWeight: 700 }}>
          {typeof rangeMm === 'number' ? rangeMm.toFixed(0) : '--'} mm
        </span>
      </div>

      <div style={{ marginTop: 8 }}>
        <button
          type="button"
          className={styles.btnPrimary}
          disabled={applying}
          onClick={() => {
            const patch: Record<string, number> = {}
            for (const k of keys) {
              if (local[k] !== undefined) patch[k] = local[k]
            }
            onApply(patch)
          }}
        >
          {applying ? 'Applying...' : 'Apply'}
        </button>
      </div>
    </>
  )
}

function IMUSection({
  pmap,
  onApply,
  applying,
}: {
  pmap: Map<string, ParamDef>
  onApply: (patch: Record<string, number>) => void
  applying: boolean
}) {
  const readOnlyKeys = [
    'reflex.imu_odr_hz',
    'reflex.imu_gyro_range_dps',
    'reflex.imu_accel_range_g',
  ] as const
  const editKeys = [
    'reflex.tilt_thresh_deg',
    'reflex.tilt_hold_ms',
    'reflex.stall_thresh_ms',
  ] as const

  const initialValues = useMemo(() => {
    const v: Record<string, number> = {}
    for (const k of editKeys) v[k] = pmap.get(k)?.value ?? 0
    return v
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pmap, editKeys])

  const [local, setLocal] = useState<Record<string, number>>(initialValues)

  useEffect(() => {
    setLocal(initialValues)
  }, [initialValues])

  const set = (key: string, v: number) => setLocal((prev) => ({ ...prev, [key]: v }))

  const gyroZ = useTelemetry((s) => s.snapshot.gyro_z)

  return (
    <>
      <h3>Read-only (boot_only)</h3>
      <div className={styles.grid3}>
        {readOnlyKeys.map((k) => {
          const p = pmap.get(k)
          return (
            <div key={k}>
              <label>{shortParamName(k)}</label>
              <div className={styles.mono} style={{ fontSize: 16, fontWeight: 600 }}>
                {p?.value ?? '--'}
              </div>
            </div>
          )
        })}
      </div>

      <h3 style={{ marginTop: 12 }}>Thresholds</h3>
      <RangeField
        label="tilt_thresh_deg"
        value={local['reflex.tilt_thresh_deg'] ?? 30}
        min={pmap.get('reflex.tilt_thresh_deg')?.min ?? 10}
        max={pmap.get('reflex.tilt_thresh_deg')?.max ?? 60}
        step={pmap.get('reflex.tilt_thresh_deg')?.step ?? 1}
        onChange={(v) => set('reflex.tilt_thresh_deg', v)}
      />
      <RangeField
        label="tilt_hold_ms"
        value={local['reflex.tilt_hold_ms'] ?? 500}
        min={pmap.get('reflex.tilt_hold_ms')?.min ?? 100}
        max={pmap.get('reflex.tilt_hold_ms')?.max ?? 2000}
        step={pmap.get('reflex.tilt_hold_ms')?.step ?? 50}
        onChange={(v) => set('reflex.tilt_hold_ms', v)}
      />
      <RangeField
        label="stall_thresh_ms"
        value={local['reflex.stall_thresh_ms'] ?? 1000}
        min={pmap.get('reflex.stall_thresh_ms')?.min ?? 200}
        max={pmap.get('reflex.stall_thresh_ms')?.max ?? 5000}
        step={pmap.get('reflex.stall_thresh_ms')?.step ?? 100}
        onChange={(v) => set('reflex.stall_thresh_ms', v)}
      />

      <div style={{ marginTop: 8 }}>
        <span style={{ fontSize: 12, color: '#999' }}>Live gyro_z: </span>
        <span className={styles.mono} style={{ fontSize: 16, fontWeight: 700 }}>
          {typeof gyroZ === 'number' ? gyroZ.toFixed(1) : '--'} mrad/s
        </span>
      </div>

      <div style={{ marginTop: 8 }}>
        <button
          type="button"
          className={styles.btnPrimary}
          disabled={applying}
          onClick={() => {
            const patch: Record<string, number> = {}
            for (const k of editKeys) {
              if (local[k] !== undefined) patch[k] = local[k]
            }
            onApply(patch)
          }}
        >
          {applying ? 'Applying...' : 'Apply'}
        </button>
      </div>
    </>
  )
}

// ---------------------------------------------------------------------------
// Main Tab
// ---------------------------------------------------------------------------

export default function CalibrationTab() {
  const { data: params, isLoading } = useParamsList()
  const updateParams = useUpdateParams()
  const pmap = useMemo(() => paramMap(params), [params])

  const handleApply = (patch: Record<string, number>) => {
    updateParams.mutate(patch)
  }

  if (isLoading) {
    return <div style={{ padding: 16, color: '#888' }}>Loading parameters...</div>
  }

  return (
    <div style={{ padding: 16, display: 'flex', flexDirection: 'column', gap: 12 }}>
      {/* PID Tuner */}
      <details open className={styles.card}>
        <summary style={{ cursor: 'pointer', fontWeight: 600, fontSize: 14, marginBottom: 8 }}>
          PID Tuner
        </summary>
        <PIDSection pmap={pmap} onApply={handleApply} applying={updateParams.isPending} />
      </details>

      {/* Vision / HSV Tuner */}
      <details className={styles.card}>
        <summary style={{ cursor: 'pointer', fontWeight: 600, fontSize: 14, marginBottom: 8 }}>
          Camera / Vision
        </summary>
        <CameraSettingsPanel pmap={pmap} onApply={handleApply} applying={updateParams.isPending} />
      </details>

      {/* Range Sensor */}
      <details className={styles.card}>
        <summary style={{ cursor: 'pointer', fontWeight: 600, fontSize: 14, marginBottom: 8 }}>
          Range Sensor
        </summary>
        <RangeSection pmap={pmap} onApply={handleApply} applying={updateParams.isPending} />
      </details>

      {/* IMU */}
      <details className={styles.card}>
        <summary style={{ cursor: 'pointer', fontWeight: 600, fontSize: 14, marginBottom: 8 }}>
          IMU
        </summary>
        <IMUSection pmap={pmap} onApply={handleApply} applying={updateParams.isPending} />
      </details>
    </div>
  )
}
