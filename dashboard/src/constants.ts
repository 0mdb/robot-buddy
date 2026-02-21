import type { TabId } from './types'

// ---- Fault flags (bit positions) ----

export const FAULT_NAMES: Record<number, string> = {
  0: 'CMD_TIMEOUT',
  1: 'ESTOP',
  2: 'TILT',
  3: 'STALL',
  4: 'IMU_FAIL',
  5: 'BROWNOUT',
  6: 'OBSTACLE',
}

export function decodeFaults(flags: number): string[] {
  const active: string[] = []
  for (const [bit, name] of Object.entries(FAULT_NAMES)) {
    if (flags & (1 << Number(bit))) active.push(name)
  }
  return active
}

// ---- Face moods ----

export const MOODS = [
  'neutral',
  'happy',
  'excited',
  'curious',
  'sad',
  'scared',
  'angry',
  'surprised',
  'sleepy',
  'love',
  'silly',
  'thinking',
] as const

// ---- Face gestures ----

export const GESTURES = [
  'blink',
  'wink_l',
  'wink_r',
  'confused',
  'laugh',
  'surprise',
  'heart',
  'x_eyes',
  'sleepy',
  'rage',
  'nod',
  'headshake',
  'wiggle',
] as const

// ---- Face flags (bit positions) ----

export const FACE_FLAGS = [
  { bit: 0, name: 'idle', label: 'Idle Wander' },
  { bit: 1, name: 'autoblink', label: 'Autoblink' },
  { bit: 2, name: 'solid_eye', label: 'Solid Eyes' },
  { bit: 3, name: 'show_mouth', label: 'Show Mouth' },
  { bit: 4, name: 'edge_glow', label: 'Edge Glow' },
  { bit: 5, name: 'sparkle', label: 'Sparkle' },
  { bit: 6, name: 'afterglow', label: 'Afterglow' },
] as const

// ---- System modes ----

export const SYSTEM_MODES = [
  'NONE',
  'BOOTING',
  'ERROR_DISPLAY',
  'LOW_BATTERY',
  'UPDATING',
  'SHUTTING_DOWN',
] as const

// ---- Robot modes ----

export const ROBOT_MODES = ['IDLE', 'TELEOP', 'WANDER'] as const

// ---- Tab definitions ----

export const TABS: { id: TabId; label: string }[] = [
  { id: 'drive', label: 'Drive' },
  { id: 'telemetry', label: 'Telemetry' },
  { id: 'devices', label: 'Devices' },
  { id: 'logs', label: 'Logs' },
  { id: 'calibration', label: 'Calibration' },
  { id: 'params', label: 'Parameters' },
  { id: 'face', label: 'Face' },
]

// ---- Telemetry ring buffer metrics ----
// These are the numeric fields we track in ring buffers for charts/sparklines

export const RING_METRICS = [
  'speed_l',
  'speed_r',
  'v_meas',
  'w_meas',
  'v_cmd',
  'w_cmd',
  'v_capped',
  'w_capped',
  'gyro_z',
  'range_mm',
  'battery_mv',
  'tick_dt_ms',
  'clear_conf',
  'ball_conf',
  'vision_fps',
] as const

export type RingMetric = (typeof RING_METRICS)[number]
