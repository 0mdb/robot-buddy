/**
 * FaceMirrorCanvas — live face mirror driven by protocol TX stream.
 *
 * Renders the face sim at 320x240 on an HTML5 Canvas, scaled 2x via CSS.
 * Subscribes to useProtocolStore for face TX packets and applies them to
 * a local FaceState, which is animated and rendered at 30fps.
 * Includes conversation border + corner button rendering.
 */

import { useCallback, useEffect, useRef } from 'react'
import {
  ANIM_FPS,
  applyProtocolPacket,
  type BorderState,
  borderRender,
  borderRenderButtons,
  borderUpdate,
  createBorderState,
  createFaceState,
  type FaceState,
  faceStateUpdate,
  renderFace,
  SCREEN_H,
  SCREEN_W,
} from '../face_sim'
import { useProtocolStore } from '../lib/wsProtocol'

export default function FaceMirrorCanvas() {
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const fsRef = useRef<FaceState>(createFaceState())
  const bsRef = useRef<BorderState>(createBorderState())
  const imageDataRef = useRef<ImageData | null>(null)
  const rafRef = useRef<number>(0)
  const lastFrameRef = useRef<number>(0)
  const lastPacketIdxRef = useRef<number>(0)
  const convTimerRef = useRef<number>(0)

  // Process new protocol packets each frame
  const processPackets = useCallback(() => {
    const fs = fsRef.current
    const bs = bsRef.current
    const packets = useProtocolStore.getState().packets
    const startIdx = lastPacketIdxRef.current

    for (let i = startIdx; i < packets.length; i++) {
      const pkt = packets[i]
      if (pkt.device === 'face' && pkt.direction === 'TX') {
        applyProtocolPacket(fs, pkt, bs)
      }
    }
    lastPacketIdxRef.current = packets.length
  }, [])

  // Animation loop
  const tick = useCallback(
    (timestamp: number) => {
      const frameDuration = 1000.0 / ANIM_FPS
      const elapsed = timestamp - lastFrameRef.current

      if (elapsed >= frameDuration) {
        lastFrameRef.current = timestamp - (elapsed % frameDuration)

        processPackets()

        const canvas = canvasRef.current
        if (!canvas) {
          rafRef.current = requestAnimationFrame(tick)
          return
        }
        const ctx = canvas.getContext('2d', { willReadFrequently: true })
        if (!ctx) {
          rafRef.current = requestAnimationFrame(tick)
          return
        }

        if (!imageDataRef.current) {
          imageDataRef.current = ctx.createImageData(SCREEN_W, SCREEN_H)
        }

        const fs = fsRef.current
        const bs = bsRef.current
        const dt = 1.0 / ANIM_FPS

        // Update border state
        convTimerRef.current += dt
        borderUpdate(bs, bs._conv_state, convTimerRef.current, dt)

        // Update face state + render with border callbacks
        faceStateUpdate(fs, dt)
        renderFace(
          fs,
          imageDataRef.current,
          (buf) => borderRender(bs, buf),
          (buf) => borderRenderButtons(bs, buf),
        )
        ctx.putImageData(imageDataRef.current, 0, 0)
      }

      rafRef.current = requestAnimationFrame(tick)
    },
    [processPackets],
  )

  useEffect(() => {
    lastFrameRef.current = performance.now()
    rafRef.current = requestAnimationFrame(tick)
    return () => {
      if (rafRef.current) cancelAnimationFrame(rafRef.current)
    }
  }, [tick])

  useEffect(() => {
    return useProtocolStore.subscribe((state) => {
      if (state.packets.length < lastPacketIdxRef.current) {
        lastPacketIdxRef.current = 0
      }
    })
  }, [])

  return (
    <div
      style={{
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        gap: 6,
      }}
    >
      <canvas
        ref={canvasRef}
        width={SCREEN_W}
        height={SCREEN_H}
        style={{
          width: SCREEN_W * 2,
          height: SCREEN_H * 2,
          imageRendering: 'pixelated',
          borderRadius: 8,
          border: '1px solid rgba(255,255,255,0.08)',
          background: '#000',
        }}
      />
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: 8,
          fontSize: 11,
          color: '#888',
        }}
      >
        <span>Face Mirror</span>
        <span
          style={{
            display: 'inline-block',
            width: 6,
            height: 6,
            borderRadius: '50%',
            background: '#4caf50',
          }}
        />
        <span>Live</span>
        <span style={{ color: '#555' }}>{ANIM_FPS} fps</span>
      </div>
    </div>
  )
}
