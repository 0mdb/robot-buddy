import { useCallback, useEffect, useRef } from 'react'
import { throttle } from '../lib/throttle'

interface Props {
  size?: number
  /** Called at steady 10 Hz while dragging, immediately on release with (0,0) */
  onTwist: (v: number, w: number) => void
  maxV?: number
  maxW?: number
}

const DEAD_ZONE = 0.05 // 5% dead zone

export function Joystick({ size = 180, onTwist, maxV = 300, maxW = 2000 }: Props) {
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const stickRef = useRef({ x: 0, y: 0 }) // -1..1 normalized
  const activeRef = useRef(false)
  const lastSentRef = useRef({ v: 0, w: 0 })

  // Throttled send at 10 Hz — trailing edge guaranteed
  const throttledSend = useRef(
    throttle((v: number, w: number) => {
      onTwist(v, w)
      lastSentRef.current = { v, w }
    }, 100),
  ).current

  const draw = useCallback(() => {
    const canvas = canvasRef.current
    if (!canvas) return
    const ctx = canvas.getContext('2d')
    if (!ctx) return

    const r = size / 2
    const cx = r
    const cy = r

    ctx.clearRect(0, 0, size, size)

    // Outer ring
    ctx.beginPath()
    ctx.arc(cx, cy, r - 2, 0, Math.PI * 2)
    ctx.strokeStyle = '#0f3460'
    ctx.lineWidth = 2
    ctx.stroke()

    // Cross hairs
    ctx.beginPath()
    ctx.moveTo(cx, 4)
    ctx.lineTo(cx, size - 4)
    ctx.moveTo(4, cy)
    ctx.lineTo(size - 4, cy)
    ctx.strokeStyle = 'rgba(255,255,255,0.08)'
    ctx.lineWidth = 1
    ctx.stroke()

    // Stick position
    const sx = cx + stickRef.current.x * (r - 20)
    const sy = cy - stickRef.current.y * (r - 20) // y inverted

    // Stick shadow
    ctx.beginPath()
    ctx.arc(sx, sy, 18, 0, Math.PI * 2)
    ctx.fillStyle = activeRef.current ? '#e94560' : '#c73a52'
    ctx.fill()

    // Stick highlight
    ctx.beginPath()
    ctx.arc(sx, sy, 14, 0, Math.PI * 2)
    ctx.fillStyle = activeRef.current ? '#ff6b81' : '#e94560'
    ctx.fill()
  }, [size])

  const getPosition = useCallback(
    (clientX: number, clientY: number) => {
      const canvas = canvasRef.current
      if (!canvas) return { x: 0, y: 0 }
      const rect = canvas.getBoundingClientRect()
      const r = size / 2
      let x = (clientX - rect.left - r) / (r - 20)
      let y = -(clientY - rect.top - r) / (r - 20) // y inverted
      // Clamp to unit circle
      const mag = Math.sqrt(x * x + y * y)
      if (mag > 1) {
        x /= mag
        y /= mag
      }
      return { x, y }
    },
    [size],
  )

  const handleMove = useCallback(
    (x: number, y: number) => {
      stickRef.current = { x, y }
      draw()

      // Apply dead zone
      const ax = Math.abs(x) < DEAD_ZONE ? 0 : x
      const ay = Math.abs(y) < DEAD_ZONE ? 0 : y
      const v = Math.round(ay * maxV)
      const w = Math.round(-ax * maxW) // left stick = positive w

      // Skip if unchanged
      if (v === lastSentRef.current.v && w === lastSentRef.current.w) return
      throttledSend(v, w)
    },
    [draw, maxV, maxW, throttledSend],
  )

  const handleRelease = useCallback(() => {
    activeRef.current = false
    stickRef.current = { x: 0, y: 0 }
    draw()
    // Immediately send zero — bypass throttle
    throttledSend.cancel()
    onTwist(0, 0)
    lastSentRef.current = { v: 0, w: 0 }
  }, [draw, onTwist, throttledSend])

  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas) return

    const onPointerDown = (e: PointerEvent) => {
      activeRef.current = true
      canvas.setPointerCapture(e.pointerId)
      const pos = getPosition(e.clientX, e.clientY)
      handleMove(pos.x, pos.y)
    }

    const onPointerMove = (e: PointerEvent) => {
      if (!activeRef.current) return
      const pos = getPosition(e.clientX, e.clientY)
      handleMove(pos.x, pos.y)
    }

    const onPointerUp = () => {
      if (!activeRef.current) return
      handleRelease()
    }

    canvas.addEventListener('pointerdown', onPointerDown)
    canvas.addEventListener('pointermove', onPointerMove)
    canvas.addEventListener('pointerup', onPointerUp)
    canvas.addEventListener('pointercancel', onPointerUp)

    draw()

    return () => {
      canvas.removeEventListener('pointerdown', onPointerDown)
      canvas.removeEventListener('pointermove', onPointerMove)
      canvas.removeEventListener('pointerup', onPointerUp)
      canvas.removeEventListener('pointercancel', onPointerUp)
      throttledSend.cancel()
    }
  }, [draw, getPosition, handleMove, handleRelease, throttledSend])

  return (
    <canvas
      ref={canvasRef}
      width={size}
      height={size}
      style={{ touchAction: 'none', cursor: 'pointer' }}
    />
  )
}
