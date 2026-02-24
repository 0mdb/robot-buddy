/**
 * FaceMirrorCanvas — live face mirror driven by protocol TX stream.
 *
 * Renders the face sim at 320x240 on an HTML5 Canvas, scaled 2x via CSS.
 * Subscribes to useProtocolStore for face TX packets and applies them to
 * a local FaceState, which is animated and rendered at the chosen FPS.
 * Includes conversation border + corner button rendering.
 *
 * Phase 6: Live/Sandbox modes, deterministic PRNG toggle, FPS selector.
 */

import { useCallback, useEffect, useRef } from 'react'
import {
  type AnimFps,
  applyProtocolPacket,
  type BorderState,
  borderRender,
  borderRenderButtons,
  borderUpdate,
  createBorderState,
  createFaceState,
  type FaceState,
  faceSetFlags,
  faceStateUpdate,
  faceTriggerGesture,
  makePrng,
  renderFace,
  SCREEN_H,
  SCREEN_W,
} from '../face_sim'
import { borderSetEnergy } from '../face_sim/border'
import { type ConvState, MAX_GAZE, type Mood, SystemMode } from '../face_sim/constants'
import { useProtocolStore } from '../lib/wsProtocol'

// ── Types ─────────────────────────────────────────────────────

export type MirrorMode = 'live' | 'sandbox'

export interface SandboxDispatch {
  setMood(mood: number, intensity: number, brightness: number, gazeX: number, gazeY: number): void
  setFlags(flags: number): void
  setTalking(talking: boolean, energy: number): void
  triggerGesture(gestureId: number, durationMs: number): void
  setConvState(convState: number): void
  setSystem(mode: number, param: number): void
  reset(): void
}

interface Props {
  mode: MirrorMode
  fps: AnimFps
  deterministic: boolean
  detSeed?: number
  onSandboxDispatch?: (d: SandboxDispatch | null) => void
}

// ── Component ─────────────────────────────────────────────────

export default function FaceMirrorCanvas({
  mode,
  fps,
  deterministic,
  detSeed = 42,
  onSandboxDispatch,
}: Props) {
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const fsRef = useRef<FaceState>(createFaceState())
  const bsRef = useRef<BorderState>(createBorderState())
  const imageDataRef = useRef<ImageData | null>(null)
  const rafRef = useRef<number>(0)
  const lastFrameRef = useRef<number>(0)
  const lastPacketIdxRef = useRef<number>(0)
  const convTimerRef = useRef<number>(0)

  // Phase 6: simulation time + PRNG refs
  const simTimeRef = useRef<number>(0)
  const rngRef = useRef<() => number>(() => Math.random())

  // Mirror props into refs so the rAF closure sees current values
  const modeRef = useRef(mode)
  const fpsRef = useRef(fps)
  modeRef.current = mode
  fpsRef.current = fps

  // Reset RNG when deterministic/seed changes
  useEffect(() => {
    if (deterministic) {
      rngRef.current = makePrng(detSeed)
    } else {
      rngRef.current = () => Math.random()
    }
  }, [deterministic, detSeed])

  // Mode switching: sandbox→live resets state for clean re-sync
  const prevModeRef = useRef(mode)
  useEffect(() => {
    if (prevModeRef.current === 'sandbox' && mode === 'live') {
      fsRef.current = createFaceState()
      bsRef.current = createBorderState()
      simTimeRef.current = 0
      lastPacketIdxRef.current = 0
      convTimerRef.current = 0
      imageDataRef.current = null
      if (deterministic) {
        rngRef.current = makePrng(detSeed)
      }
    }
    prevModeRef.current = mode
  }, [mode, deterministic, detSeed])

  // Sandbox dispatch: expose imperative API when in sandbox mode
  useEffect(() => {
    if (!onSandboxDispatch) return
    if (mode !== 'sandbox') {
      onSandboxDispatch(null)
      return
    }
    const dispatch: SandboxDispatch = {
      setMood(moodId, intensity, brightness, gazeX, gazeY) {
        const fs = fsRef.current
        fs.mood = moodId as Mood
        fs.expression_intensity = intensity / 255.0
        fs.brightness = brightness / 255.0
        const gx = (gazeX / 127.0) * MAX_GAZE
        const gy = (gazeY / 127.0) * MAX_GAZE
        fs.eye_l.gaze_x_target = gx
        fs.eye_r.gaze_x_target = gx
        fs.eye_l.gaze_y_target = gy
        fs.eye_r.gaze_y_target = gy
      },
      setFlags(flags) {
        faceSetFlags(fsRef.current, flags)
      },
      setTalking(talking, energy) {
        const fs = fsRef.current
        fs.talking = talking
        fs.talking_energy = energy / 255.0
        borderSetEnergy(bsRef.current, energy / 255.0)
      },
      triggerGesture(gestureId, durationMs) {
        faceTriggerGesture(fsRef.current, gestureId, durationMs, simTimeRef.current)
      },
      setConvState(convState) {
        borderUpdate(bsRef.current, convState as ConvState, convTimerRef.current, 0)
      },
      setSystem(sysMode, param) {
        const fs = fsRef.current
        fs.system.mode = sysMode as SystemMode
        fs.system.param = param
        if (fs.system.mode !== SystemMode.NONE) {
          fs.system.timer = performance.now() / 1000.0
        }
      },
      reset() {
        fsRef.current = createFaceState()
        bsRef.current = createBorderState()
        simTimeRef.current = 0
        convTimerRef.current = 0
        imageDataRef.current = null
        if (deterministic) {
          rngRef.current = makePrng(detSeed)
        }
      },
    }
    onSandboxDispatch(dispatch)
  }, [mode, onSandboxDispatch, deterministic, detSeed])

  // Process new protocol packets each frame (live mode only)
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
      const currentFps = fpsRef.current
      const frameDuration = 1000.0 / currentFps
      const elapsed = timestamp - lastFrameRef.current

      if (elapsed >= frameDuration) {
        lastFrameRef.current = timestamp - (elapsed % frameDuration)

        // Process protocol packets in live mode only
        if (modeRef.current === 'live') {
          processPackets()
        }

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
        const dt = 1.0 / currentFps

        // Advance simulation time
        simTimeRef.current += dt

        // Update border state
        convTimerRef.current += dt
        borderUpdate(bs, bs._conv_state, convTimerRef.current, dt)

        // Update face state + render with border callbacks
        faceStateUpdate(fs, dt, simTimeRef.current, rngRef.current)
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

  const modeColor = mode === 'sandbox' ? '#ff9800' : '#4caf50'
  const modeLabel = mode === 'sandbox' ? 'Sandbox' : 'Live'

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
            background: modeColor,
          }}
        />
        <span>{modeLabel}</span>
        {deterministic && (
          <span
            style={{
              color: '#9c27b0',
              fontWeight: 600,
              fontSize: 10,
              border: '1px solid #9c27b0',
              borderRadius: 3,
              padding: '0 3px',
            }}
          >
            DET
          </span>
        )}
        <span style={{ color: '#555' }}>{fps} fps</span>
      </div>
    </div>
  )
}
