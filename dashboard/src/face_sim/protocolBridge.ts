/**
 * Protocol bridge — maps face TX packets to FaceState changes.
 *
 * Receives CapturedPacket from useProtocolStore and applies the
 * corresponding command to the local FaceState mirror.
 */

import {
  FLAG_AFTERGLOW,
  FLAG_AUTOBLINK,
  FLAG_EDGE_GLOW,
  FLAG_IDLE_WANDER,
  FLAG_SHOW_MOUTH,
  FLAG_SOLID_EYE,
  FLAG_SPARKLE,
  MAX_GAZE,
  SystemMode,
} from './constants'
import { faceSetFlags, faceTriggerGesture } from './state'
import type { FaceState } from './types'

/** Packet shape from useProtocolStore (subset of CapturedPacket). */
interface ProtocolPacket {
  direction: 'TX' | 'RX'
  device: string
  pkt_type: number
  type_name: string
  fields: Record<string, unknown>
}

// Face command type IDs (from supervisor/devices/protocol.py)
const SET_STATE = 0x20
const GESTURE = 0x21
const SET_SYSTEM = 0x22
const SET_TALKING = 0x23
const SET_FLAGS = 0x24
const SET_CONV_STATE = 0x25

/**
 * Apply a protocol TX packet to the face state.
 * Returns true if the packet was relevant and applied.
 */
export function applyProtocolPacket(fs: FaceState, pkt: ProtocolPacket): boolean {
  // Only process face TX packets
  if (pkt.device !== 'face' || pkt.direction !== 'TX') return false

  const f = pkt.fields
  const ptype = pkt.pkt_type

  if (ptype === SET_STATE) {
    // fields: {mood, intensity, gaze_x, gaze_y, brightness}
    const mood = f.mood as number | undefined
    const intensityU8 = f.intensity as number | undefined
    const gazeXI8 = f.gaze_x as number | undefined
    const gazeYI8 = f.gaze_y as number | undefined
    const brightnessU8 = f.brightness as number | undefined

    if (mood !== undefined) fs.mood = mood
    if (intensityU8 !== undefined) fs.expression_intensity = intensityU8 / 255.0
    if (gazeXI8 !== undefined) {
      const gx = (gazeXI8 / 127.0) * MAX_GAZE
      fs.eye_l.gaze_x_target = gx
      fs.eye_r.gaze_x_target = gx
    }
    if (gazeYI8 !== undefined) {
      const gy = (gazeYI8 / 127.0) * MAX_GAZE
      fs.eye_l.gaze_y_target = gy
      fs.eye_r.gaze_y_target = gy
    }
    if (brightnessU8 !== undefined) fs.brightness = brightnessU8 / 255.0
    return true
  }

  if (ptype === SET_FLAGS) {
    // fields: {flags} or individual booleans
    const flags = f.flags as number | undefined
    if (flags !== undefined) {
      faceSetFlags(fs, flags)
    } else {
      // Individual boolean fields
      let mask = 0
      if (f.idle_wander) mask |= FLAG_IDLE_WANDER
      if (f.autoblink) mask |= FLAG_AUTOBLINK
      if (f.solid_eye) mask |= FLAG_SOLID_EYE
      if (f.show_mouth) mask |= FLAG_SHOW_MOUTH
      if (f.edge_glow) mask |= FLAG_EDGE_GLOW
      if (f.sparkle) mask |= FLAG_SPARKLE
      if (f.afterglow) mask |= FLAG_AFTERGLOW
      faceSetFlags(fs, mask)
    }
    return true
  }

  if (ptype === SET_TALKING) {
    // fields: {talking, energy}
    fs.talking = !!(f.talking as boolean | number | undefined)
    const energy = f.energy as number | undefined
    if (energy !== undefined) fs.talking_energy = energy / 255.0
    return true
  }

  if (ptype === GESTURE) {
    // fields: {gesture_id, duration_ms} or {gesture, duration_ms}
    const gestureId = (f.gesture_id as number | undefined) ?? (f.gesture as number | undefined)
    const durationMs = (f.duration_ms as number | undefined) ?? 0
    if (gestureId !== undefined) {
      faceTriggerGesture(fs, gestureId, durationMs)
    }
    return true
  }

  if (ptype === SET_CONV_STATE) {
    // fields: {conv_state}
    // Conversation border rendering is deferred (Phase 5).
    // Store the value for future use.
    return true
  }

  if (ptype === SET_SYSTEM) {
    // fields: {mode, param} or {system_mode, param}
    const mode = (f.mode as number | undefined) ?? (f.system_mode as number | undefined)
    if (mode !== undefined) {
      fs.system.mode = mode as SystemMode
      fs.system.param = (f.param as number | undefined) ?? 0
      if (fs.system.mode !== SystemMode.NONE) {
        fs.system.timer = performance.now() / 1000.0
      }
    }
    return true
  }

  return false
}
