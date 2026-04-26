import { useEffect, useRef } from 'react'
import uPlot from 'uplot'
import 'uplot/dist/uPlot.min.css'
import { useTelemetryStore } from '../stores/telemetryStore'

interface Props {
  metric: string
  width?: number
  height?: number
  color?: string
  /** Number of seconds to display */
  window?: number
  /** Multiplied into raw ring values before plotting (e.g. 0.001 to plot mV as V). */
  scale?: number
}

/**
 * Tiny sparkline chart using uPlot.
 * Subscribes directly to the store — bypasses React for data updates.
 */
export function Sparkline({
  metric,
  width = 120,
  height = 32,
  color = '#e94560',
  window: windowSec = 5,
  scale = 1,
}: Props) {
  const containerRef = useRef<HTMLDivElement>(null)
  const plotRef = useRef<uPlot | null>(null)

  useEffect(() => {
    if (!containerRef.current) return

    const opts: uPlot.Options = {
      width,
      height,
      cursor: { show: false },
      legend: { show: false },
      axes: [{ show: false }, { show: false }],
      scales: {
        x: { time: false },
      },
      series: [
        {},
        {
          stroke: color,
          width: 1.5,
          fill: `${color}22`,
        },
      ],
    }

    const plot = new uPlot(opts, [[], []], containerRef.current)
    plotRef.current = plot

    // Transient subscription — bypasses React
    let lastUpdate = 0
    const unsub = useTelemetryStore.subscribe(() => {
      const now = performance.now()
      if (now - lastUpdate < 200) return // 5 Hz
      lastUpdate = now

      const ring = useTelemetryStore.getState().ring(metric)
      const { values, timestamps } = ring.toArrays()
      if (values.length === 0) return

      // Convert timestamps to relative seconds
      const tLast = timestamps[timestamps.length - 1]
      const tStart = tLast - windowSec * 1000
      const relTs = timestamps.map((t) => (t - tStart) / 1000)
      const scaled = scale === 1 ? values : Float64Array.from(values, (v) => v * scale)

      plot.setData([relTs, scaled])
    })

    // Visibility handler
    const onVis = () => {
      if (!document.hidden && plotRef.current) {
        const ring = useTelemetryStore.getState().ring(metric)
        const { values, timestamps } = ring.toArrays()
        if (values.length > 0) {
          const tLast = timestamps[timestamps.length - 1]
          const tStart = tLast - windowSec * 1000
          const relTs = timestamps.map((t) => (t - tStart) / 1000)
          const scaled = scale === 1 ? values : Float64Array.from(values, (v) => v * scale)
          plotRef.current.setData([relTs, scaled])
        }
      }
    }
    document.addEventListener('visibilitychange', onVis)

    return () => {
      unsub()
      document.removeEventListener('visibilitychange', onVis)
      plot.destroy()
      plotRef.current = null
    }
  }, [metric, width, height, color, windowSec, scale])

  return <div ref={containerRef} />
}
