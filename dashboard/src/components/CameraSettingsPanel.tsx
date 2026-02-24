import type { MouseEvent as ReactMouseEvent } from 'react'
import { useCallback, useRef, useState } from 'react'
import { useTelemetry } from '../hooks/useTelemetry'
import { debounce } from '../lib/debounce'
import { hsvRangeFromSample, type OpenCvHsv, rgbToOpenCvHsv } from '../lib/vision/color'
import styles from '../styles/global.module.css'
import type { ParamDef, TelemetryPayload } from '../types'

const FLOOR_KEYS = [
  'vision.floor_hsv_h_low',
  'vision.floor_hsv_h_high',
  'vision.floor_hsv_s_low',
  'vision.floor_hsv_s_high',
  'vision.floor_hsv_v_low',
  'vision.floor_hsv_v_high',
] as const

const BALL_KEYS = [
  'vision.ball_hsv_h_low',
  'vision.ball_hsv_h_high',
  'vision.ball_hsv_s_low',
  'vision.ball_hsv_s_high',
  'vision.ball_hsv_v_low',
  'vision.ball_hsv_v_high',
  'vision.min_ball_radius_px',
] as const

const SAFETY_KEYS = ['vision.stale_ms', 'vision.clear_low', 'vision.clear_high'] as const

const ALL_KEYS = [...FLOOR_KEYS, ...BALL_KEYS, ...SAFETY_KEYS] as const

function getNumber(p: ParamDef | undefined, fallback = 0): number {
  const v = p?.value
  return typeof v === 'number' ? v : fallback
}

function getDefault(p: ParamDef | undefined, fallback = 0): number {
  const v = p?.default
  return typeof v === 'number' ? v : fallback
}

function clamp(n: number, min: number, max: number): number {
  if (n < min) return min
  if (n > max) return max
  return n
}

function shortParamName(name: string): string {
  const i = name.lastIndexOf('.')
  return i >= 0 ? name.slice(i + 1) : name
}

function SliderField({
  name,
  label,
  value,
  p,
  onChange,
}: {
  name: string
  label: string
  value: number
  p: ParamDef | undefined
  onChange: (value: number) => void
}) {
  const min = typeof p?.min === 'number' ? p.min : 0
  const max = typeof p?.max === 'number' ? p.max : 255
  const step = typeof p?.step === 'number' ? p.step : 1

  return (
    <label style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', gap: 10 }}>
        <span>{label}</span>
        <span className={styles.mono} style={{ color: 'var(--text)', fontWeight: 700 }}>
          {value}
        </span>
      </div>
      <input
        type="range"
        value={value}
        min={min}
        max={max}
        step={step}
        onChange={(e) => onChange(Number(e.target.value))}
      />
      <div style={{ display: 'flex', justifyContent: 'space-between', color: 'var(--text-dim)' }}>
        <span className={styles.mono} style={{ fontSize: 11 }}>
          {name}
        </span>
        <span className={styles.mono} style={{ fontSize: 11 }}>
          [{min}..{max}]
        </span>
      </div>
    </label>
  )
}

function Toggle({
  checked,
  label,
  onChange,
}: {
  checked: boolean
  label: string
  onChange: (checked: boolean) => void
}) {
  return (
    <label style={{ display: 'flex', alignItems: 'center', gap: 8, color: '#aaa' }}>
      <input type="checkbox" checked={checked} onChange={(e) => onChange(e.target.checked)} />
      {label}
    </label>
  )
}

export function CameraSettingsPanel({
  pmap,
  onApply,
  applying,
}: {
  pmap: Map<string, ParamDef>
  onApply: (patch: Record<string, number>) => void
  applying: boolean
}) {
  // Live readouts
  const visionFps = useTelemetry((s) => (s.snapshot as TelemetryPayload).vision_fps ?? 0, 200)
  const visionAgeMs = useTelemetry((s) => (s.snapshot as TelemetryPayload).vision_age_ms ?? 0, 200)
  const clearConf = useTelemetry((s) => (s.snapshot as TelemetryPayload).clear_conf ?? -1, 200)
  const ballConf = useTelemetry((s) => (s.snapshot as TelemetryPayload).ball_conf ?? 0, 200)
  const ballBearing = useTelemetry((s) => (s.snapshot as TelemetryPayload).ball_bearing ?? 0, 200)
  const workerAlive = useTelemetry(
    (s) => ((s.snapshot as TelemetryPayload).worker_alive ?? {}) as Record<string, boolean>,
    500,
  )
  const visionAlive = workerAlive.vision === true

  // UI toggles
  const [videoEnabled, setVideoEnabled] = useState(false)
  const [liveApply, setLiveApply] = useState(true)
  const [pickTarget, setPickTarget] = useState<'off' | 'floor' | 'ball'>('off')

  // Eyedropper tolerances
  const [deltaH, setDeltaH] = useState(10)
  const [deltaS, setDeltaS] = useState(40)
  const [deltaV, setDeltaV] = useState(40)

  // Local staged values (initialize once from current params)
  const [local, setLocal] = useState<Record<string, number>>(() => {
    const out: Record<string, number> = {}
    for (const name of ALL_KEYS) out[name] = getNumber(pmap.get(name), 0)
    return out
  })

  // Debounced live-apply (coalesce multiple field edits)
  const onApplyRef = useRef(onApply)
  onApplyRef.current = onApply
  const pendingRef = useRef<Record<string, number>>({})
  const flushPending = useCallback(() => {
    const patch = pendingRef.current
    pendingRef.current = {}
    if (Object.keys(patch).length === 0) return
    onApplyRef.current(patch)
  }, [])
  const debouncedFlush = useRef(debounce(flushPending, 150)).current

  const queueApply = useCallback(
    (patch: Record<string, number>) => {
      if (!liveApply) return
      Object.assign(pendingRef.current, patch)
      debouncedFlush()
    },
    [debouncedFlush, liveApply],
  )

  const setField = useCallback(
    (name: string, value: number) => {
      setLocal((prev) => ({ ...prev, [name]: value }))
      queueApply({ [name]: value })
    },
    [queueApply],
  )

  const applyAll = useCallback(() => {
    debouncedFlush.cancel()
    pendingRef.current = {}
    const patch: Record<string, number> = {}
    for (const name of ALL_KEYS) {
      const v = local[name]
      if (typeof v === 'number') patch[name] = v
    }
    onApply(patch)
  }, [debouncedFlush, local, onApply])

  const resetGroup = useCallback(
    (names: readonly string[]) => {
      const patch: Record<string, number> = {}
      for (const name of names) patch[name] = getDefault(pmap.get(name), local[name] ?? 0)
      setLocal((prev) => ({ ...prev, ...patch }))
      queueApply(patch)
    },
    [local, pmap, queueApply],
  )

  // Video + picking
  const imgRef = useRef<HTMLImageElement | null>(null)
  const canvasRef = useRef<HTMLCanvasElement | null>(null)
  const [lastPick, setLastPick] = useState<{
    rgb: [number, number, number]
    hsv: OpenCvHsv
    target: 'floor' | 'ball'
  } | null>(null)

  const handleVideoClick = useCallback(
    (e: ReactMouseEvent<HTMLElement>) => {
      if (pickTarget === 'off') return
      const img = imgRef.current
      if (!img) return

      const rect = img.getBoundingClientRect()
      if (rect.width <= 0 || rect.height <= 0) return

      const w = img.naturalWidth || img.width
      const h = img.naturalHeight || img.height
      if (!w || !h) return

      const x = clamp(Math.floor(((e.clientX - rect.left) / rect.width) * w), 0, w - 1)
      const y = clamp(Math.floor(((e.clientY - rect.top) / rect.height) * h), 0, h - 1)

      const canvas = canvasRef.current ?? document.createElement('canvas')
      canvasRef.current = canvas
      canvas.width = w
      canvas.height = h

      const ctx = canvas.getContext('2d', { willReadFrequently: true })
      if (!ctx) return

      try {
        ctx.drawImage(img, 0, 0, w, h)
        const data = ctx.getImageData(x, y, 1, 1).data
        const rgb: [number, number, number] = [data[0] ?? 0, data[1] ?? 0, data[2] ?? 0]
        const hsv = rgbToOpenCvHsv(rgb[0], rgb[1], rgb[2])

        const range = hsvRangeFromSample(hsv, { dh: deltaH, ds: deltaS, dv: deltaV })
        const patch: Record<string, number> = {}

        if (pickTarget === 'floor') {
          patch['vision.floor_hsv_h_low'] = range.hLow
          patch['vision.floor_hsv_h_high'] = range.hHigh
          patch['vision.floor_hsv_s_low'] = range.sLow
          patch['vision.floor_hsv_s_high'] = range.sHigh
          patch['vision.floor_hsv_v_low'] = range.vLow
          patch['vision.floor_hsv_v_high'] = range.vHigh
        } else {
          patch['vision.ball_hsv_h_low'] = range.hLow
          patch['vision.ball_hsv_h_high'] = range.hHigh
          patch['vision.ball_hsv_s_low'] = range.sLow
          patch['vision.ball_hsv_s_high'] = range.sHigh
          patch['vision.ball_hsv_v_low'] = range.vLow
          patch['vision.ball_hsv_v_high'] = range.vHigh
        }

        setLastPick({ rgb, hsv, target: pickTarget })
        setLocal((prev) => ({ ...prev, ...patch }))
        queueApply(patch)
      } catch {
        // drawImage/getImageData can throw if the browser considers the image tainted.
      }
    },
    [deltaH, deltaS, deltaV, pickTarget, queueApply],
  )

  const ballHueWrap = (local['vision.ball_hsv_h_low'] ?? 0) > (local['vision.ball_hsv_h_high'] ?? 0)

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
      {/* Controls */}
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 12, alignItems: 'center' }}>
        <Toggle checked={liveApply} label="Live apply" onChange={setLiveApply} />
        <Toggle checked={videoEnabled} label="Video preview" onChange={setVideoEnabled} />
        <button type="button" className={styles.btnPrimary} disabled={applying} onClick={applyAll}>
          {applying ? 'Applying…' : 'Apply'}
        </button>

        <span className={styles.mono} style={{ color: 'var(--text-dim)' }}>
          vision {visionAlive ? 'up' : 'down'} | {visionFps.toFixed(1)} fps | age{' '}
          {visionAgeMs.toFixed(0)} ms | clear {clearConf.toFixed(2)} | ball {ballConf.toFixed(2)} @{' '}
          {ballBearing.toFixed(1)}°
        </span>
      </div>

      {/* Video + eyedropper */}
      <div className={styles.card}>
        <h3 style={{ marginBottom: 6 }}>Video + Eyedropper</h3>
        {!visionAlive && (
          <div className={styles.mono} style={{ color: 'var(--red)', marginBottom: 8 }}>
            Vision worker is down — /video may be unavailable.
          </div>
        )}

        <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap', alignItems: 'flex-start' }}>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
            {videoEnabled ? (
              <button
                type="button"
                aria-label="Pick pixel from video"
                onClick={handleVideoClick}
                style={{
                  padding: 0,
                  borderRadius: 6,
                  border: '1px solid #333',
                  background: 'transparent',
                  cursor: pickTarget === 'off' ? 'default' : 'crosshair',
                }}
              >
                <img
                  ref={imgRef}
                  src="/video"
                  alt="Vision preview"
                  style={{
                    width: 360,
                    maxWidth: '100%',
                    display: 'block',
                    borderRadius: 6,
                  }}
                />
              </button>
            ) : (
              <div
                style={{
                  width: 360,
                  height: 240,
                  maxWidth: '100%',
                  borderRadius: 6,
                  border: '1px dashed rgba(255,255,255,0.15)',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  color: 'var(--text-dim)',
                }}
              >
                Video preview OFF
              </div>
            )}

            <div className={styles.mono} style={{ fontSize: 11, color: 'var(--text-dim)' }}>
              Tip: enable Video preview, set Pick mode, then click a pixel.
            </div>
          </div>

          <div style={{ display: 'flex', flexDirection: 'column', gap: 10, minWidth: 260 }}>
            <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap', alignItems: 'center' }}>
              <span style={{ color: 'var(--text-dim)', fontSize: 12 }}>Pick mode</span>
              <label style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
                <input
                  type="radio"
                  checked={pickTarget === 'off'}
                  onChange={() => setPickTarget('off')}
                />
                Off
              </label>
              <label style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
                <input
                  type="radio"
                  checked={pickTarget === 'floor'}
                  onChange={() => setPickTarget('floor')}
                />
                Floor
              </label>
              <label style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
                <input
                  type="radio"
                  checked={pickTarget === 'ball'}
                  onChange={() => setPickTarget('ball')}
                />
                Ball
              </label>
            </div>

            <div
              className={styles.grid3}
              style={{ gridTemplateColumns: 'repeat(3, minmax(80px, 1fr))' }}
            >
              <label style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
                <span>ΔH</span>
                <input
                  type="number"
                  value={deltaH}
                  min={0}
                  max={179}
                  onChange={(e) => setDeltaH(Number(e.target.value))}
                />
              </label>
              <label style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
                <span>ΔS</span>
                <input
                  type="number"
                  value={deltaS}
                  min={0}
                  max={255}
                  onChange={(e) => setDeltaS(Number(e.target.value))}
                />
              </label>
              <label style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
                <span>ΔV</span>
                <input
                  type="number"
                  value={deltaV}
                  min={0}
                  max={255}
                  onChange={(e) => setDeltaV(Number(e.target.value))}
                />
              </label>
            </div>

            <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
              <div className={styles.mono} style={{ color: 'var(--text-dim)' }}>
                Last pick
              </div>
              {lastPick ? (
                <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                  <div
                    style={{
                      width: 20,
                      height: 20,
                      borderRadius: 4,
                      border: '1px solid rgba(255,255,255,0.15)',
                      background: `rgb(${lastPick.rgb[0]},${lastPick.rgb[1]},${lastPick.rgb[2]})`,
                    }}
                  />
                  <div className={styles.mono} style={{ fontSize: 12 }}>
                    {lastPick.target} rgb=({lastPick.rgb.join(',')}) hsv=(
                    {lastPick.hsv.h},{lastPick.hsv.s},{lastPick.hsv.v})
                  </div>
                </div>
              ) : (
                <div className={styles.mono} style={{ color: 'var(--text-dim)', fontSize: 12 }}>
                  —
                </div>
              )}
            </div>
          </div>
        </div>
      </div>

      {/* Floor HSV */}
      <div className={styles.card}>
        <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12 }}>
          <h3 style={{ marginBottom: 6 }}>Floor HSV</h3>
          <button type="button" disabled={applying} onClick={() => resetGroup(FLOOR_KEYS)}>
            Reset to defaults
          </button>
        </div>
        <div className={styles.grid2}>
          {FLOOR_KEYS.map((name) => (
            <SliderField
              key={name}
              name={name}
              label={shortParamName(name)}
              value={local[name] ?? getNumber(pmap.get(name), 0)}
              p={pmap.get(name)}
              onChange={(v) => setField(name, v)}
            />
          ))}
        </div>
      </div>

      {/* Ball HSV */}
      <div className={styles.card}>
        <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            <h3 style={{ marginBottom: 6 }}>Ball HSV</h3>
            {ballHueWrap && <span className={`${styles.badge} ${styles.badgeYellow}`}>H wrap</span>}
          </div>
          <button type="button" disabled={applying} onClick={() => resetGroup(BALL_KEYS)}>
            Reset to defaults
          </button>
        </div>
        <div className={styles.grid2}>
          {BALL_KEYS.map((name) => (
            <SliderField
              key={name}
              name={name}
              label={shortParamName(name)}
              value={local[name] ?? getNumber(pmap.get(name), 0)}
              p={pmap.get(name)}
              onChange={(v) => setField(name, v)}
            />
          ))}
        </div>
        <div
          className={styles.mono}
          style={{ color: 'var(--text-dim)', fontSize: 11, marginTop: 8 }}
        >
          Hue wrap-around: if H low &gt; H high, the range is [low..179] ∪ [0..high].
        </div>
      </div>

      {/* Safety policy */}
      <div className={styles.card}>
        <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12 }}>
          <h3 style={{ marginBottom: 6 }}>Vision Safety</h3>
          <button type="button" disabled={applying} onClick={() => resetGroup(SAFETY_KEYS)}>
            Reset to defaults
          </button>
        </div>
        <div className={styles.grid3}>
          {SAFETY_KEYS.map((name) => (
            <SliderField
              key={name}
              name={name}
              label={shortParamName(name)}
              value={local[name] ?? getNumber(pmap.get(name), 0)}
              p={pmap.get(name)}
              onChange={(v) => setField(name, v)}
            />
          ))}
        </div>
      </div>
    </div>
  )
}
