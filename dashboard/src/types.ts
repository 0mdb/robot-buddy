// ---- Telemetry envelope from WS /ws ----

export interface WsEnvelope {
  schema: 'supervisor_ws_v2'
  type: 'telemetry'
  ts_ms: number
  payload: TelemetryPayload
}

// Combined RobotState + WorldState as sent by ws_hub
export interface TelemetryPayload {
  // Mode
  mode: string

  // Motion commands
  v_cmd: number
  w_cmd: number
  v_capped: number
  w_capped: number

  // Measured
  v_meas: number
  w_meas: number
  speed_l: number
  speed_r: number
  gyro_z: number

  // Sensors
  battery_mv: number
  range_mm: number
  range_status: number
  fault_flags: number

  // Connections
  reflex_connected: boolean
  face_connected: boolean
  reflex_seq: number
  reflex_rx_mono_ms: number
  face_seq: number
  face_rx_mono_ms: number

  // Face state
  face_mood: string
  face_gesture: string
  face_system_mode: string
  face_touch_active: boolean
  face_listening: boolean
  face_talking: boolean
  face_talking_energy: number
  face_manual_lock: boolean
  face_manual_flags: number
  face_last_button_id: number
  face_last_button_event: string
  face_last_button_state: number

  // Clock sync
  clock_sync: {
    reflex: ClockSyncInfo
    face: ClockSyncInfo
  }

  // Speed caps
  speed_caps: SpeedCap[]

  // Timing
  tick_dt_ms: number
  tick_mono_ms: number

  // Vision (WorldState)
  clear_conf: number
  ball_conf: number
  ball_bearing: number
  vision_fps: number
  vision_age_ms: number
  vision_frame_seq: number

  // Audio
  speaking: boolean
  current_energy: number
  ptt_active: boolean

  // Planner
  planner_connected: boolean
  planner_enabled: boolean
  active_skill: string | null
  last_plan_mono_ms: number
  last_plan_actions: number
  last_plan_error: string | null
  event_count: number

  // Workers
  worker_alive: Record<string, boolean>
  mic_link_up: boolean
  spk_link_up: boolean

  // Conversation
  session_id: string | null
  ai_state: string | null

  [key: string]: unknown
}

export interface ClockSyncInfo {
  state: string
  offset_ns: number
  rtt_min_us: number
  drift_us_per_s: number
  samples: number
  t_last_sync_ns: number
}

export interface SpeedCap {
  scale: number
  reason: string
}

// ---- Parameter registry ----

export interface ParamDef {
  name: string
  type: 'float' | 'int' | 'bool'
  min: number
  max: number
  step: number
  default: number
  value: number
  owner: 'supervisor' | 'reflex' | 'face' | 'vision'
  mutable: 'runtime' | 'boot_only'
  safety: 'safe' | 'risky'
  doc: string
}

export interface ParamUpdateResult {
  ok: boolean
  reason?: string
}

// ---- Debug endpoints ----

export interface DeviceDebug {
  reflex: ReflexDebug
  face: FaceDebug
}

export interface ReflexDebug {
  connected: boolean
  tx_packets: number
  rx_state_packets: number
  rx_bad_payload_packets: number
  rx_unknown_packets: number
  last_state_seq: number
  last_state_age_ms: number
  transport: TransportDebug
}

export interface FaceDebug {
  connected: boolean
  tx_packets: number
  rx_face_status_packets: number
  rx_touch_packets: number
  rx_button_packets: number
  rx_heartbeat_packets: number
  rx_bad_payload_packets: number
  rx_unknown_packets: number
  last_status_seq: number
  last_status_age_ms: number
  last_status_flags: number
  last_talking_energy_cmd: number
  last_render_flags_cmd: number
  last_button: {
    button_id: number
    event_type: string
    state: number
    timestamp_mono_ms: number
  }
  last_heartbeat: Record<string, unknown>
  transport: TransportDebug
}

export interface TransportDebug {
  port: string
  label: string
  connected: boolean
  dtr: boolean
  rts: boolean
  connect_count: number
  disconnect_count: number
  read_ops: number
  write_ops: number
  rx_bytes: number
  tx_bytes: number
  frames_ok: number
  frames_bad: number
  frames_too_long: number
  write_errors: number
  write_timeouts: number
  last_rx_mono_ms: number
  last_frame_mono_ms: number
  last_bad_frame: string
  last_error: string
}

export interface ClocksDebug {
  reflex: ClockSyncInfo
  face: ClockSyncInfo
}

// ---- System resources from /debug/system ----

export interface SystemDebug {
  cpu_percent: number
  cpu_count: number
  cpu_freq_mhz: number | null
  cpu_temp_c: number | null
  mem_total_mb: number
  mem_used_mb: number
  mem_percent: number
  disk_total_gb: number
  disk_used_gb: number
  disk_percent: number
  load_avg: [number, number, number]
  uptime_s: number
}

// ---- Worker debug from /debug/workers ----

export interface WorkerDebugEntry {
  alive: boolean
  restart_count: number
  last_seq: number
  pid: number | null
}

export type WorkersDebug = Record<string, WorkerDebugEntry>

// ---- Log entry from WS /ws/logs ----

export interface LogEntry {
  ts: number
  level: string
  name: string
  msg: string
}

// ---- Tab IDs ----

export type TabId =
  | 'drive'
  | 'telemetry'
  | 'devices'
  | 'logs'
  | 'protocol'
  | 'calibration'
  | 'params'
  | 'face'
  | 'monitor'
