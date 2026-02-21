import { useEffect, useRef } from 'react'
import uPlot from 'uplot'
import 'uplot/dist/uPlot.min.css'
import { useTelemetryStore } from '../stores/telemetryStore'

interface SeriesDef {
  metric: string
  label: string
  color: string
  width?: number
  dash?: number[]
}

interface Props {
  title: string
  series: SeriesDef[]
  /** Y-axis label */
  yLabel?: string
  /** Display window in seconds */
  window?: number
  /** Height in pixels */
  height?: number
  /** Horizontal threshold lines */
  thresholds?: { value: number; color: string; label?: string }[]
}

/**
 * Full telemetry time-series chart using uPlot.
 * Subscribes directly to the Zustand store — React only manages mount/unmount.
 */
export function TimeSeriesChart({
  title,
  series,
  yLabel,
  window: windowSec = 60,
  height = 200,
  thresholds,
}: Props) {
  const containerRef = useRef<HTMLDivElement>(null)
  const plotRef = useRef<uPlot | null>(null)
  const pausedRef = useRef(false)

  useEffect(() => {
    if (!containerRef.current) return

    const container = containerRef.current
    const w = container.clientWidth || 600

    const uSeries: uPlot.Series[] = [
      { label: 'Time' },
      ...series.map((s) => ({
        label: s.label,
        stroke: s.color,
        width: s.width ?? 1.5,
        dash: s.dash,
      })),
    ]

    // Draw threshold lines via hooks
    const drawHooks: uPlot.Plugin['hooks'] = {}
    if (thresholds?.length) {
      drawHooks.draw = [
        (u: uPlot) => {
          const ctx = u.ctx
          for (const th of thresholds) {
            const y = u.valToPos(th.value, 'y', true)
            if (y === undefined || Number.isNaN(y)) continue
            ctx.save()
            ctx.strokeStyle = th.color
            ctx.lineWidth = 1
            ctx.setLineDash([4, 4])
            ctx.beginPath()
            ctx.moveTo(u.bbox.left, y)
            ctx.lineTo(u.bbox.left + u.bbox.width, y)
            ctx.stroke()
            if (th.label) {
              ctx.fillStyle = th.color
              ctx.font = '10px sans-serif'
              ctx.fillText(th.label, u.bbox.left + 4, y - 3)
            }
            ctx.restore()
          }
        },
      ]
    }

    const opts: uPlot.Options = {
      width: w,
      height,
      title,
      cursor: { show: true, drag: { x: false, y: false } },
      scales: {
        x: { time: false },
      },
      axes: [{ label: 'seconds' }, { label: yLabel, size: 60 }],
      series: uSeries,
      hooks: drawHooks as uPlot.Options['hooks'],
    }

    const emptyData: uPlot.AlignedData = [
      new Float64Array(0),
      ...series.map(() => new Float64Array(0)),
    ]

    const plot = new uPlot(opts, emptyData, container)
    plotRef.current = plot

    // Resize observer
    const ro = new ResizeObserver((entries) => {
      const entry = entries[0]
      if (entry && plotRef.current) {
        plotRef.current.setSize({
          width: entry.contentRect.width,
          height,
        })
      }
    })
    ro.observe(container)

    // Transient subscription — bypasses React entirely
    let lastUpdate = 0
    const unsub = useTelemetryStore.subscribe(() => {
      if (pausedRef.current) return
      const now = performance.now()
      if (now - lastUpdate < 200) return // 5 Hz
      lastUpdate = now
      updateChart()
    })

    function updateChart() {
      if (!plotRef.current) return

      // Use the first series' timestamps as the x-axis
      const ring0 = useTelemetryStore.getState().ring(series[0].metric)
      const { timestamps } = ring0.toArrays()
      if (timestamps.length === 0) return

      const tLast = timestamps[timestamps.length - 1]
      const tStart = tLast - windowSec * 1000
      const relTs = timestamps.map((t) => (t - tStart) / 1000)

      const data: (number[] | Float64Array)[] = [relTs]
      for (const s of series) {
        const r = useTelemetryStore.getState().ring(s.metric)
        const { values } = r.toArrays()
        data.push(values)
      }

      plotRef.current.setData(data as uPlot.AlignedData)
    }

    // Visibility handler — force redraw on foreground
    const onVis = () => {
      if (!document.hidden) updateChart()
    }
    document.addEventListener('visibilitychange', onVis)

    return () => {
      unsub()
      ro.disconnect()
      document.removeEventListener('visibilitychange', onVis)
      plot.destroy()
      plotRef.current = null
    }
  }, [title, series, yLabel, windowSec, height, thresholds])

  return (
    <div style={{ position: 'relative' }}>
      <div ref={containerRef} />
      <button
        type="button"
        style={{
          position: 'absolute',
          top: 4,
          right: 4,
          fontSize: 11,
          padding: '2px 8px',
          opacity: 0.7,
        }}
        onClick={() => {
          pausedRef.current = !pausedRef.current
        }}
      >
        {pausedRef.current ? '▶' : '⏸'}
      </button>
    </div>
  )
}
