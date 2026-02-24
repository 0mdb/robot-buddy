import type { MouseEvent as ReactMouseEvent } from 'react'
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useResetVisionMask, useSaveVisionMask, useVisionMask } from '../hooks/useVisionMask'
import { hsvRangeFromSample, type OpenCvHsv, rgbToOpenCvHsv } from '../lib/vision/color'
import styles from '../styles/global.module.css'
import type { VisionMaskPoint, VisionMaskV1 } from '../types'

type Tool = 'off' | 'mask_floor' | 'mask_ball' | 'pick_floor' | 'pick_ball'

function clamp01(n: number): number {
  if (n < 0) return 0
  if (n > 1) return 1
  return n
}

function roundNorm(n: number): number {
  const v = clamp01(n)
  return Math.round(v * 10000) / 10000
}

function emptyMask(): VisionMaskV1 {
  return {
    version: 1,
    floor: { enabled: false, exclude_polys: [] },
    ball: { enabled: false, exclude_polys: [] },
  }
}

function pointsAttr(poly: VisionMaskPoint[]): string {
  return poly.map(([x, y]) => `${x},${y}`).join(' ')
}

export function VisionMaskEditor({
  videoEnabled,
  visionAlive,
  onParamPatch,
}: {
  videoEnabled: boolean
  visionAlive: boolean
  onParamPatch: (patch: Record<string, number>) => void
}) {
  const { data, isLoading, error } = useVisionMask()
  const save = useSaveVisionMask()
  const reset = useResetVisionMask()

  const [tool, setTool] = useState<Tool>('off')

  // Eyedropper tolerances
  const [deltaH, setDeltaH] = useState(10)
  const [deltaS, setDeltaS] = useState(40)
  const [deltaV, setDeltaV] = useState(40)

  const [lastPick, setLastPick] = useState<{
    rgb: [number, number, number]
    hsv: OpenCvHsv
    target: 'floor' | 'ball'
  } | null>(null)

  const [dirty, setDirty] = useState(false)
  const [mask, setMask] = useState<VisionMaskV1>(() => emptyMask())

  useEffect(() => {
    if (!data || dirty) return
    setMask(data)
  }, [data, dirty])

  const [draftFloor, setDraftFloor] = useState<VisionMaskPoint[]>([])
  const [draftBall, setDraftBall] = useState<VisionMaskPoint[]>([])

  const activeMask: 'floor' | 'ball' | null = useMemo(() => {
    if (tool === 'mask_floor') return 'floor'
    if (tool === 'mask_ball') return 'ball'
    return null
  }, [tool])

  const activePick: 'floor' | 'ball' | null = useMemo(() => {
    if (tool === 'pick_floor') return 'floor'
    if (tool === 'pick_ball') return 'ball'
    return null
  }, [tool])

  const imgRef = useRef<HTMLImageElement | null>(null)
  const canvasRef = useRef<HTMLCanvasElement | null>(null)

  const getClickNorm = useCallback((e: ReactMouseEvent<HTMLElement>) => {
    const img = imgRef.current
    if (!img) return null

    const rect = img.getBoundingClientRect()
    if (rect.width <= 0 || rect.height <= 0) return null

    const nx = clamp01((e.clientX - rect.left) / rect.width)
    const ny = clamp01((e.clientY - rect.top) / rect.height)
    return { nx, ny }
  }, [])

  const handleClick = useCallback(
    (e: ReactMouseEvent<HTMLElement>) => {
      if (!videoEnabled) return

      const img = imgRef.current
      if (!img) return

      const norm = getClickNorm(e)
      if (!norm) return

      if (activePick) {
        const w = img.naturalWidth || img.width
        const h = img.naturalHeight || img.height
        if (!w || !h) return

        const x = Math.max(0, Math.min(w - 1, Math.floor(norm.nx * w)))
        const y = Math.max(0, Math.min(h - 1, Math.floor(norm.ny * h)))

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

          if (activePick === 'floor') {
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

          setLastPick({ rgb, hsv, target: activePick })
          onParamPatch(patch)
        } catch {
          // drawImage/getImageData can throw if the browser considers the image tainted.
        }
        return
      }

      if (activeMask === 'floor') {
        setDirty(true)
        setDraftFloor((prev) => [...prev, [roundNorm(norm.nx), roundNorm(norm.ny)]])
      } else if (activeMask === 'ball') {
        setDirty(true)
        setDraftBall((prev) => [...prev, [roundNorm(norm.nx), roundNorm(norm.ny)]])
      }
    },
    [activeMask, activePick, deltaH, deltaS, deltaV, getClickNorm, onParamPatch, videoEnabled],
  )

  const finishPolygon = useCallback(() => {
    if (!activeMask) return

    if (activeMask === 'floor') {
      if (draftFloor.length < 3) return
      setMask((prev) => ({
        ...prev,
        floor: { ...prev.floor, exclude_polys: [...prev.floor.exclude_polys, draftFloor] },
      }))
      setDraftFloor([])
      setDirty(true)
    } else {
      if (draftBall.length < 3) return
      setMask((prev) => ({
        ...prev,
        ball: { ...prev.ball, exclude_polys: [...prev.ball.exclude_polys, draftBall] },
      }))
      setDraftBall([])
      setDirty(true)
    }
  }, [activeMask, draftBall, draftFloor])

  const undoPoint = useCallback(() => {
    if (!activeMask) return
    if (activeMask === 'floor') setDraftFloor((prev) => prev.slice(0, -1))
    else setDraftBall((prev) => prev.slice(0, -1))
    setDirty(true)
  }, [activeMask])

  const deleteLastPolygon = useCallback(() => {
    if (!activeMask) return
    setDirty(true)
    setMask((prev) => {
      if (activeMask === 'floor') {
        return {
          ...prev,
          floor: { ...prev.floor, exclude_polys: prev.floor.exclude_polys.slice(0, -1) },
        }
      }
      return {
        ...prev,
        ball: { ...prev.ball, exclude_polys: prev.ball.exclude_polys.slice(0, -1) },
      }
    })
  }, [activeMask])

  const clearAll = useCallback(() => {
    if (!activeMask) return
    setDirty(true)
    if (activeMask === 'floor') setDraftFloor([])
    else setDraftBall([])
    setMask((prev) => ({
      ...prev,
      [activeMask]: { ...prev[activeMask], exclude_polys: [] },
    }))
  }, [activeMask])

  const canSave =
    dirty &&
    !isLoading &&
    !save.isPending &&
    !reset.isPending &&
    draftFloor.length === 0 &&
    draftBall.length === 0

  const handleSave = useCallback(async () => {
    const saved = await save.mutateAsync(mask)
    setMask(saved)
    setDirty(false)
  }, [mask, save])

  const handleReset = useCallback(async () => {
    const res = await reset.mutateAsync()
    setMask(res.mask)
    setDraftFloor([])
    setDraftBall([])
    setDirty(false)
  }, [reset])

  const cursor =
    tool === 'off'
      ? 'default'
      : tool.startsWith('pick_') || tool.startsWith('mask_')
        ? 'crosshair'
        : 'default'

  const floorPolys = mask.floor.exclude_polys
  const ballPolys = mask.ball.exclude_polys

  return (
    <div className={styles.card}>
      <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12 }}>
        <h3 style={{ marginBottom: 6 }}>Video + Eyedropper + Masks</h3>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <button type="button" disabled={!canSave} onClick={handleSave}>
            {save.isPending ? 'Saving…' : 'Save mask'}
          </button>
          <button type="button" disabled={reset.isPending} onClick={handleReset}>
            Reset mask
          </button>
          {dirty && <span className={`${styles.badge} ${styles.badgeYellow}`}>Unsaved</span>}
        </div>
      </div>

      {!visionAlive && (
        <div className={styles.mono} style={{ color: 'var(--red)', marginBottom: 8 }}>
          Vision worker is down — /video may be unavailable.
        </div>
      )}

      {error && (
        <div className={styles.mono} style={{ color: 'var(--red)', marginBottom: 8 }}>
          Failed to load vision mask ({String(error)})
        </div>
      )}

      {(save.isError || reset.isError) && (
        <div className={styles.mono} style={{ color: 'var(--red)', marginBottom: 8 }}>
          Mask update failed ({String(save.error ?? reset.error)})
        </div>
      )}

      {draftFloor.length > 0 || draftBall.length > 0 ? (
        <div className={styles.mono} style={{ color: 'var(--yellow)', marginBottom: 8 }}>
          Finish or clear the in-progress polygon before saving.
        </div>
      ) : null}

      <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap', alignItems: 'flex-start' }}>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
          {videoEnabled ? (
            <button
              type="button"
              aria-label="Video click tool"
              onClick={handleClick}
              onDoubleClick={finishPolygon}
              style={{
                padding: 0,
                borderRadius: 6,
                border: '1px solid #333',
                background: 'transparent',
                cursor,
                position: 'relative',
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

              {/* Overlay: normalized viewBox */}
              <svg
                viewBox="0 0 1 1"
                preserveAspectRatio="none"
                aria-hidden="true"
                focusable="false"
                style={{
                  position: 'absolute',
                  inset: 0,
                  width: '100%',
                  height: '100%',
                  pointerEvents: 'none',
                }}
              >
                {/* Clear-path ROI guides */}
                <line
                  x1={0}
                  y1={2 / 3}
                  x2={1}
                  y2={2 / 3}
                  stroke="rgba(255,255,255,0.35)"
                  strokeWidth={0.003}
                  vectorEffect="non-scaling-stroke"
                />
                <line
                  x1={1 / 3}
                  y1={2 / 3}
                  x2={1 / 3}
                  y2={1}
                  stroke="rgba(255,255,255,0.35)"
                  strokeWidth={0.003}
                  vectorEffect="non-scaling-stroke"
                />
                <line
                  x1={2 / 3}
                  y1={2 / 3}
                  x2={2 / 3}
                  y2={1}
                  stroke="rgba(255,255,255,0.35)"
                  strokeWidth={0.003}
                  vectorEffect="non-scaling-stroke"
                />

                {/* Floor polys */}
                {floorPolys.map((poly, i) => (
                  <polygon
                    // biome-ignore lint/suspicious/noArrayIndexKey: stable ordering is user-driven
                    key={`floor-${i}`}
                    points={pointsAttr(poly)}
                    fill={activeMask === 'floor' ? 'rgba(255,80,80,0.30)' : 'rgba(255,80,80,0.18)'}
                    stroke="rgba(255,80,80,0.85)"
                    strokeWidth={0.003}
                    vectorEffect="non-scaling-stroke"
                  />
                ))}

                {/* Ball polys */}
                {ballPolys.map((poly, i) => (
                  <polygon
                    // biome-ignore lint/suspicious/noArrayIndexKey: stable ordering is user-driven
                    key={`ball-${i}`}
                    points={pointsAttr(poly)}
                    fill={activeMask === 'ball' ? 'rgba(80,160,255,0.30)' : 'rgba(80,160,255,0.18)'}
                    stroke="rgba(80,160,255,0.85)"
                    strokeWidth={0.003}
                    vectorEffect="non-scaling-stroke"
                  />
                ))}

                {/* Draft polys */}
                {draftFloor.length > 0 && (
                  <>
                    <polyline
                      points={pointsAttr(draftFloor)}
                      fill="none"
                      stroke="rgba(255,80,80,1.0)"
                      strokeWidth={0.004}
                      vectorEffect="non-scaling-stroke"
                    />
                    {draftFloor.map(([x, y], i) => (
                      <circle
                        // biome-ignore lint/suspicious/noArrayIndexKey: draft points are append-only
                        key={`df-${i}`}
                        cx={x}
                        cy={y}
                        r={0.008}
                        fill="rgba(255,80,80,1.0)"
                      />
                    ))}
                  </>
                )}
                {draftBall.length > 0 && (
                  <>
                    <polyline
                      points={pointsAttr(draftBall)}
                      fill="none"
                      stroke="rgba(80,160,255,1.0)"
                      strokeWidth={0.004}
                      vectorEffect="non-scaling-stroke"
                    />
                    {draftBall.map(([x, y], i) => (
                      <circle
                        // biome-ignore lint/suspicious/noArrayIndexKey: draft points are append-only
                        key={`db-${i}`}
                        cx={x}
                        cy={y}
                        r={0.008}
                        fill="rgba(80,160,255,1.0)"
                      />
                    ))}
                  </>
                )}
              </svg>
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
            Tip: enable Video preview, select a tool, then click on the image.
          </div>
        </div>

        <div style={{ display: 'flex', flexDirection: 'column', gap: 10, minWidth: 260 }}>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
            <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap', alignItems: 'center' }}>
              <span style={{ color: 'var(--text-dim)', fontSize: 12 }}>Tool</span>
              <label style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
                <input type="radio" checked={tool === 'off'} onChange={() => setTool('off')} />
                Off
              </label>
              <label style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
                <input
                  type="radio"
                  checked={tool === 'mask_floor'}
                  onChange={() => setTool('mask_floor')}
                />
                Mask: Floor
              </label>
              <label style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
                <input
                  type="radio"
                  checked={tool === 'mask_ball'}
                  onChange={() => setTool('mask_ball')}
                />
                Mask: Ball
              </label>
              <label style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
                <input
                  type="radio"
                  checked={tool === 'pick_floor'}
                  onChange={() => setTool('pick_floor')}
                />
                Eyedropper: Floor
              </label>
              <label style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
                <input
                  type="radio"
                  checked={tool === 'pick_ball'}
                  onChange={() => setTool('pick_ball')}
                />
                Eyedropper: Ball
              </label>
            </div>

            <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap', alignItems: 'center' }}>
              <label style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                <input
                  type="checkbox"
                  checked={mask.floor.enabled}
                  onChange={(e) => {
                    setDirty(true)
                    setMask((prev) => ({
                      ...prev,
                      floor: { ...prev.floor, enabled: e.target.checked },
                    }))
                  }}
                />
                Floor enabled ({mask.floor.exclude_polys.length})
              </label>
              <label style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                <input
                  type="checkbox"
                  checked={mask.ball.enabled}
                  onChange={(e) => {
                    setDirty(true)
                    setMask((prev) => ({
                      ...prev,
                      ball: { ...prev.ball, enabled: e.target.checked },
                    }))
                  }}
                />
                Ball enabled ({mask.ball.exclude_polys.length})
              </label>
            </div>
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
                  {lastPick.target} rgb=({lastPick.rgb.join(',')}) hsv=({lastPick.hsv.h},
                  {lastPick.hsv.s},{lastPick.hsv.v})
                </div>
              </div>
            ) : (
              <div className={styles.mono} style={{ color: 'var(--text-dim)', fontSize: 12 }}>
                —
              </div>
            )}
          </div>

          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, alignItems: 'center' }}>
            <button type="button" disabled={!activeMask} onClick={finishPolygon}>
              Finish polygon
            </button>
            <button
              type="button"
              disabled={
                !activeMask ||
                (activeMask === 'floor' ? draftFloor.length === 0 : draftBall.length === 0)
              }
              onClick={undoPoint}
            >
              Undo point
            </button>
            <button
              type="button"
              disabled={
                !activeMask ||
                (activeMask === 'floor'
                  ? mask.floor.exclude_polys.length === 0
                  : mask.ball.exclude_polys.length === 0)
              }
              onClick={deleteLastPolygon}
            >
              Delete last polygon
            </button>
            <button type="button" disabled={!activeMask} onClick={clearAll}>
              Clear all
            </button>
          </div>

          <div className={styles.mono} style={{ fontSize: 11, color: 'var(--text-dim)' }}>
            Points are normalized to the processed frame (after rotation). Double-click finishes the
            current polygon.
          </div>

          {isLoading && (
            <div className={styles.mono} style={{ fontSize: 11, color: 'var(--text-dim)' }}>
              Loading mask…
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
