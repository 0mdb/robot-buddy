import { useEffect, useMemo, useRef, useState } from 'react'
import { Sparkline } from '../components/Sparkline'
import { TimeSeriesChart } from '../components/TimeSeriesChart'
import { FAULT_NAMES } from '../constants'
import { useClocks } from '../hooks/useClocks'
import { useDevices } from '../hooks/useDevices'
import { useSystem } from '../hooks/useSystem'
import { useTelemetry } from '../hooks/useTelemetry'
import { useWorkers } from '../hooks/useWorkers'
import styles from '../styles/global.module.css'
import m from '../styles/monitor.module.css'
import type {
  ClocksDebug,
  DeviceDebug,
  SystemDebug,
  TelemetryPayload,
  WorkersDebug,
} from '../types'

/* ---- diagnostic level logic ---- */

type DiagLevel = 'ok' | 'warn' | 'error' | 'stale'

const LEVEL_PRIORITY: Record<DiagLevel, number> = { ok: 0, warn: 1, error: 2, stale: 3 }

function worstLevel(levels: DiagLevel[]): DiagLevel {
  let worst: DiagLevel = 'ok'
  for (const l of levels) {
    if (LEVEL_PRIORITY[l] > LEVEL_PRIORITY[worst]) worst = l
  }
  return worst
}

function dotClass(level: DiagLevel): string {
  return `${m.dot} ${level === 'ok' ? m.dotOk : level === 'warn' ? m.dotWarn : level === 'error' ? m.dotError : m.dotStale}`
}

function levelBadgeClass(level: DiagLevel): string {
  return `${styles.badge} ${level === 'ok' ? styles.badgeGreen : level === 'warn' ? styles.badgeYellow : level === 'error' ? styles.badgeRed : styles.badgeDim}`
}

/* ---- diagnostic node computation ---- */

interface DiagNode {
  id: string
  label: string
  level: DiagLevel
  summary: string
  children?: DiagNode[]
}

function computePiLevel(sys: SystemDebug | undefined): DiagLevel {
  if (!sys) return 'stale'
  const levels: DiagLevel[] = []
  // CPU
  levels.push(sys.cpu_percent > 95 ? 'error' : sys.cpu_percent > 80 ? 'warn' : 'ok')
  // Temp
  if (sys.cpu_temp_c !== null) {
    levels.push(sys.cpu_temp_c > 80 ? 'error' : sys.cpu_temp_c > 70 ? 'warn' : 'ok')
  }
  // Memory
  levels.push(sys.mem_percent > 90 ? 'error' : sys.mem_percent > 80 ? 'warn' : 'ok')
  // Disk
  levels.push(sys.disk_percent > 90 ? 'error' : sys.disk_percent > 80 ? 'warn' : 'ok')
  return worstLevel(levels)
}

function computeReflexLevel(
  connected: boolean,
  faultFlags: number,
  ageMs: number | undefined,
): DiagLevel {
  if (!connected) return 'error'
  if (ageMs !== undefined && ageMs > 2000) return 'stale'
  if (faultFlags !== 0) return 'error'
  if (ageMs !== undefined && ageMs > 200) return 'warn'
  return 'ok'
}

function computeFaceLevel(connected: boolean, ageMs: number | undefined): DiagLevel {
  if (!connected) return 'error'
  if (ageMs !== undefined && ageMs > 2000) return 'stale'
  if (ageMs !== undefined && ageMs > 200) return 'warn'
  return 'ok'
}

function computeWorkersLevel(workers: WorkersDebug | undefined): DiagLevel {
  if (!workers) return 'stale'
  const entries = Object.values(workers)
  if (entries.length === 0) return 'ok'
  const levels: DiagLevel[] = entries.map((w) => {
    if (!w.alive) return 'error'
    if (w.restart_count > 0) return 'warn'
    return 'ok'
  })
  return worstLevel(levels)
}

function buildTree(
  sys: SystemDebug | undefined,
  tel: Pick<
    TelemetryPayload,
    | 'reflex_connected'
    | 'face_connected'
    | 'fault_flags'
    | 'battery_mv'
    | 'vision_fps'
    | 'vision_age_ms'
  >,
  devices: DeviceDebug | undefined,
  clocks: ClocksDebug | undefined,
  workers: WorkersDebug | undefined,
): DiagNode {
  const piLevel = computePiLevel(sys)
  const reflexLevel = computeReflexLevel(
    tel.reflex_connected,
    tel.fault_flags,
    devices?.reflex.last_state_age_ms,
  )
  const faceLevel = computeFaceLevel(tel.face_connected, devices?.face.last_status_age_ms)
  const workersLevel = computeWorkersLevel(workers)

  // Clock sub-levels
  const reflexClockLevel: DiagLevel = clocks
    ? clocks.reflex.state === 'SYNCED'
      ? 'ok'
      : clocks.reflex.state === 'CONVERGING'
        ? 'warn'
        : 'error'
    : 'stale'
  const faceClockLevel: DiagLevel = clocks
    ? clocks.face.state === 'SYNCED'
      ? 'ok'
      : clocks.face.state === 'CONVERGING'
        ? 'warn'
        : 'error'
    : 'stale'

  const piSummary = sys
    ? `CPU ${sys.cpu_percent}% | ${sys.cpu_temp_c ?? '--'}C | Mem ${sys.mem_percent}%`
    : 'unavailable'
  const reflexSummary = tel.reflex_connected
    ? `age ${devices?.reflex.last_state_age_ms ?? '--'}ms | clk ${clocks?.reflex.state ?? '--'}`
    : 'disconnected'
  const faceSummary = tel.face_connected
    ? `age ${devices?.face.last_status_age_ms ?? '--'}ms | clk ${clocks?.face.state ?? '--'}`
    : 'disconnected'
  const workersSummary = workers
    ? Object.entries(workers)
        .map(([k, v]) => `${k}:${v.alive ? 'up' : 'DOWN'}`)
        .join(' ')
    : 'unavailable'

  return {
    id: 'system',
    label: 'System',
    level: worstLevel([
      piLevel,
      worstLevel([reflexLevel, reflexClockLevel]),
      worstLevel([faceLevel, faceClockLevel]),
      workersLevel,
    ]),
    summary: '',
    children: [
      { id: 'pi', label: 'Raspberry Pi', level: piLevel, summary: piSummary },
      {
        id: 'reflex',
        label: 'Reflex MCU',
        level: worstLevel([reflexLevel, reflexClockLevel]),
        summary: reflexSummary,
      },
      {
        id: 'face',
        label: 'Face MCU',
        level: worstLevel([faceLevel, faceClockLevel]),
        summary: faceSummary,
      },
      { id: 'workers', label: 'Workers', level: workersLevel, summary: workersSummary },
    ],
  }
}

/* ---- helpers ---- */

function Row({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className={m.metricRow}>
      <span className={m.metricLabel}>{label}</span>
      <span className={m.metricValue}>{value}</span>
    </div>
  )
}

function fmt(n: number | undefined | null): string {
  if (n === undefined || n === null) return '--'
  return n.toLocaleString()
}

function ProgressBar({ percent, thresholds }: { percent: number; thresholds?: [number, number] }) {
  const [warnAt, errorAt] = thresholds ?? [80, 90]
  const color =
    percent > errorAt ? 'var(--red)' : percent > warnAt ? 'var(--yellow)' : 'var(--green)'
  return (
    <div className={m.progressTrack}>
      <div
        className={m.progressFill}
        style={{ width: `${Math.min(percent, 100)}%`, background: color }}
      />
    </div>
  )
}

function StatusBadge({ level, text }: { level: DiagLevel; text: string }) {
  return <span className={levelBadgeClass(level)}>{text}</span>
}

function formatUptime(seconds: number): string {
  const h = Math.floor(seconds / 3600)
  const min = Math.floor((seconds % 3600) / 60)
  return h > 0 ? `${h}h ${min}m` : `${min}m`
}

/* ---- diagnostic tree component ---- */

function DiagnosticTree({ root }: { root: DiagNode }) {
  const [expanded, setExpanded] = useState<Set<string>>(new Set(['system']))

  function toggle(id: string) {
    setExpanded((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }

  function renderNode(node: DiagNode, depth: number) {
    const hasChildren = node.children && node.children.length > 0
    const isExpanded = expanded.has(node.id)
    return (
      <div key={node.id}>
        <button
          type="button"
          className={m.treeRow}
          style={{ paddingLeft: 8 + depth * 20 }}
          onClick={() => hasChildren && toggle(node.id)}
        >
          <span className={m.treeToggle}>
            {hasChildren ? (isExpanded ? '\u25BE' : '\u25B8') : ''}
          </span>
          <span className={dotClass(node.level)} />
          <span className={m.treeLabel}>{node.label}</span>
          <span className={m.treeSummary}>{node.summary}</span>
          <StatusBadge level={node.level} text={node.level.toUpperCase()} />
        </button>
        {hasChildren && isExpanded && node.children!.map((c) => renderNode(c, depth + 1))}
      </div>
    )
  }

  return <div className={m.treeContainer}>{renderNode(root, 0)}</div>
}

/* ---- panel components ---- */

function SystemResourcesPanel({ sys }: { sys: SystemDebug | undefined }) {
  if (!sys) {
    return (
      <div className={styles.card}>
        <h3 className={m.sectionTitle}>Raspberry Pi</h3>
        <span className={styles.mono} style={{ color: 'var(--text-dim)' }}>
          System info unavailable
        </span>
      </div>
    )
  }

  return (
    <div className={styles.card}>
      <h3 className={m.sectionTitle}>Raspberry Pi</h3>
      <div className={m.metricRow}>
        <span className={m.metricLabel}>CPU</span>
        <ProgressBar percent={sys.cpu_percent} thresholds={[80, 95]} />
        <span className={m.metricValue} style={{ width: 45, textAlign: 'right' }}>
          {sys.cpu_percent.toFixed(0)}%
        </span>
      </div>
      <Row
        label="Temperature"
        value={
          <span
            style={{
              color:
                sys.cpu_temp_c === null
                  ? 'var(--text-dim)'
                  : sys.cpu_temp_c > 80
                    ? 'var(--red)'
                    : sys.cpu_temp_c > 70
                      ? 'var(--yellow)'
                      : 'var(--text)',
            }}
          >
            {sys.cpu_temp_c !== null ? `${sys.cpu_temp_c} C` : '--'}
          </span>
        }
      />
      <div className={m.metricRow}>
        <span className={m.metricLabel}>Memory</span>
        <ProgressBar percent={sys.mem_percent} />
        <span className={m.metricValue} style={{ width: 95, textAlign: 'right' }}>
          {sys.mem_used_mb}/{sys.mem_total_mb} MB
        </span>
      </div>
      <div className={m.metricRow}>
        <span className={m.metricLabel}>Disk</span>
        <ProgressBar percent={sys.disk_percent} />
        <span className={m.metricValue} style={{ width: 95, textAlign: 'right' }}>
          {sys.disk_used_gb}/{sys.disk_total_gb} GB
        </span>
      </div>
      <Row label="Load avg" value={sys.load_avg.map((v) => v.toFixed(2)).join('  ')} />
      <Row label="Uptime" value={formatUptime(sys.uptime_s)} />
    </div>
  )
}

function CommunicationPanel({
  devices,
  clocks,
  seqGaps,
}: {
  devices: DeviceDebug | undefined
  clocks: ClocksDebug | undefined
  seqGaps: number
}) {
  // Compute packet rates from delta between polls
  const prevRef = useRef<{ reflex_rx: number; face_rx: number; ts: number } | null>(null)
  const [rates, setRates] = useState({ reflexRx: 0, faceRx: 0 })

  useEffect(() => {
    if (!devices) return
    const now = performance.now()
    const reflexRx = devices.reflex.rx_state_packets
    const faceRx =
      devices.face.rx_face_status_packets +
      devices.face.rx_touch_packets +
      devices.face.rx_button_packets +
      devices.face.rx_heartbeat_packets
    const prev = prevRef.current
    if (prev) {
      const dt = (now - prev.ts) / 1000
      if (dt > 0.5) {
        setRates({
          reflexRx: Math.round((reflexRx - prev.reflex_rx) / dt),
          faceRx: Math.round((faceRx - prev.face_rx) / dt),
        })
      }
    }
    prevRef.current = { reflex_rx: reflexRx, face_rx: faceRx, ts: now }
  }, [devices])

  const reflexErrRate =
    devices && devices.reflex.rx_state_packets > 0
      ? (
          (devices.reflex.rx_bad_payload_packets /
            (devices.reflex.rx_state_packets + devices.reflex.rx_bad_payload_packets)) *
          100
        ).toFixed(1)
      : '0.0'
  const faceTotal =
    (devices?.face.rx_face_status_packets ?? 0) + (devices?.face.rx_bad_payload_packets ?? 0)
  const faceErrRate =
    devices && faceTotal > 0
      ? ((devices.face.rx_bad_payload_packets / faceTotal) * 100).toFixed(1)
      : '0.0'

  return (
    <div className={styles.card}>
      <h3 className={m.sectionTitle}>Communication</h3>
      <Row label="Reflex RX" value={`${rates.reflexRx} pkt/s | ${reflexErrRate}% err`} />
      <Row label="Face RX" value={`${rates.faceRx} pkt/s | ${faceErrRate}% err`} />
      <Row label="Seq gaps" value={fmt(seqGaps)} />
      <Row
        label="Reflex clock"
        value={
          clocks ? (
            <StatusBadge
              level={
                clocks.reflex.state === 'SYNCED'
                  ? 'ok'
                  : clocks.reflex.state === 'CONVERGING'
                    ? 'warn'
                    : 'error'
              }
              text={clocks.reflex.state}
            />
          ) : (
            '--'
          )
        }
      />
      <Row
        label="Face clock"
        value={
          clocks ? (
            <StatusBadge
              level={
                clocks.face.state === 'SYNCED'
                  ? 'ok'
                  : clocks.face.state === 'CONVERGING'
                    ? 'warn'
                    : 'error'
              }
              text={clocks.face.state}
            />
          ) : (
            '--'
          )
        }
      />
      {clocks && (
        <>
          <Row label="Reflex RTT" value={`${fmt(clocks.reflex.rtt_min_us)} us`} />
          <Row label="Face RTT" value={`${fmt(clocks.face.rtt_min_us)} us`} />
        </>
      )}
    </div>
  )
}

const BATTERY_SERIES = [{ metric: 'battery_mv', label: 'Battery', color: '#eab308' }]
const BATTERY_THRESHOLDS = [
  { value: 7000, color: '#4caf50', label: 'OK' },
  { value: 6500, color: '#f44336', label: 'Low' },
]

function PowerPanel({ batteryMv }: { batteryMv: number }) {
  const level: DiagLevel = batteryMv > 7000 ? 'ok' : batteryMv > 6500 ? 'warn' : 'error'
  return (
    <div className={styles.card}>
      <div
        style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          marginBottom: 8,
        }}
      >
        <h3 className={m.sectionTitle} style={{ marginBottom: 0 }}>
          Power
        </h3>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <span className={styles.mono} style={{ fontSize: 16, fontWeight: 700 }}>
            {fmt(batteryMv)} mV
          </span>
          <StatusBadge level={level} text={level.toUpperCase()} />
        </div>
      </div>
      <TimeSeriesChart
        title=""
        yLabel="mV"
        window={60}
        height={140}
        series={BATTERY_SERIES}
        thresholds={BATTERY_THRESHOLDS}
      />
    </div>
  )
}

function SensorHealthPanel({
  faultFlags,
  rangeStatus,
  rangeMm,
  visionFps,
  visionAgeMs,
  workerAlive,
}: {
  faultFlags: number
  rangeStatus: number
  rangeMm: number
  visionFps: number
  visionAgeMs: number
  workerAlive: Record<string, boolean>
}) {
  const imuFail = !!(faultFlags & (1 << 4))
  const imuLevel: DiagLevel = imuFail ? 'error' : 'ok'

  // range_status: 0=OK in protocol (based on the supervisor mapping)
  const rangeLevel: DiagLevel =
    rangeStatus === 0 ? 'ok' : rangeStatus === 1 ? 'warn' : rangeStatus === 2 ? 'ok' : 'stale'

  const visionLevel: DiagLevel =
    visionAgeMs > 5000
      ? 'stale'
      : visionFps === 0 || workerAlive.vision === false
        ? 'error'
        : visionFps < 5
          ? 'warn'
          : 'ok'

  return (
    <div className={styles.grid3}>
      <div className={styles.card}>
        <div
          style={{
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center',
            marginBottom: 6,
          }}
        >
          <h3 className={m.sectionTitle} style={{ marginBottom: 0 }}>
            IMU
          </h3>
          <StatusBadge level={imuLevel} text={imuLevel.toUpperCase()} />
        </div>
        <Sparkline metric="gyro_z" color="var(--blue)" width={160} height={36} window={10} />
      </div>
      <div className={styles.card}>
        <div
          style={{
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center',
            marginBottom: 6,
          }}
        >
          <h3 className={m.sectionTitle} style={{ marginBottom: 0 }}>
            Range
          </h3>
          <StatusBadge level={rangeLevel} text={`${fmt(rangeMm)} mm`} />
        </div>
        <Sparkline metric="range_mm" color="var(--yellow)" width={160} height={36} window={10} />
      </div>
      <div className={styles.card}>
        <div
          style={{
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center',
            marginBottom: 6,
          }}
        >
          <h3 className={m.sectionTitle} style={{ marginBottom: 0 }}>
            Vision
          </h3>
          <StatusBadge level={visionLevel} text={`${visionFps.toFixed(1)} FPS`} />
        </div>
        <Sparkline metric="vision_fps" color="var(--green)" width={160} height={36} window={10} />
      </div>
    </div>
  )
}

function DriveHealthPanel({
  faultFlags,
  speedCaps,
}: {
  faultFlags: number
  speedCaps: { scale: number; reason: string }[]
}) {
  return (
    <div className={styles.card}>
      <h3 className={m.sectionTitle}>Faults & Speed Caps</h3>
      <div className={m.faultGrid}>
        {Object.entries(FAULT_NAMES).map(([bit, name]) => {
          const active = !!(faultFlags & (1 << Number(bit)))
          return (
            <div key={bit} className={m.faultItem}>
              <span className={m.faultDot} style={{ background: active ? 'var(--red)' : '#333' }} />
              <span style={{ color: active ? 'var(--red)' : 'var(--text-dim)' }}>{name}</span>
            </div>
          )
        })}
      </div>
      {speedCaps.length > 0 && (
        <div style={{ marginTop: 10 }}>
          <span className={m.metricLabel}>Active speed caps:</span>
          {speedCaps.map((cap) => (
            <div key={`${cap.reason}-${cap.scale}`} className={m.capItem}>
              <span className={m.capScale}>{(cap.scale * 100).toFixed(0)}%</span>
              <span className={m.capReason}>{cap.reason}</span>
            </div>
          ))}
        </div>
      )}
      {speedCaps.length === 0 && (
        <div style={{ marginTop: 8, fontSize: 12, color: 'var(--green)' }}>
          No active speed caps
        </div>
      )}
    </div>
  )
}

function WorkerHealthPanel({ workers }: { workers: WorkersDebug | undefined }) {
  if (!workers || Object.keys(workers).length === 0) {
    return (
      <div className={styles.card}>
        <h3 className={m.sectionTitle}>Workers</h3>
        <span className={styles.mono} style={{ color: 'var(--text-dim)' }}>
          No worker data
        </span>
      </div>
    )
  }
  return (
    <div className={styles.card}>
      <h3 className={m.sectionTitle}>Workers</h3>
      {Object.entries(workers).map(([name, w]) => (
        <div key={name} className={m.workerRow}>
          <span className={m.workerName}>{name}</span>
          <span className={`${styles.badge} ${w.alive ? styles.badgeGreen : styles.badgeRed}`}>
            {w.alive ? 'alive' : 'dead'}
          </span>
          <span style={{ color: 'var(--text-dim)' }}>pid={w.pid ?? '--'}</span>
          <span style={{ color: w.restart_count > 0 ? 'var(--yellow)' : 'var(--text-dim)' }}>
            restarts={w.restart_count}
          </span>
        </div>
      ))}
    </div>
  )
}

/* ---- main tab ---- */

export default function MonitorTab() {
  const { data: sys } = useSystem()
  const { data: devices } = useDevices()
  const { data: clocks } = useClocks()
  const { data: workers } = useWorkers()

  const tel = useTelemetry(
    (s) => ({
      reflex_connected: (s.snapshot as TelemetryPayload).reflex_connected ?? false,
      face_connected: (s.snapshot as TelemetryPayload).face_connected ?? false,
      fault_flags: (s.snapshot as TelemetryPayload).fault_flags ?? 0,
      battery_mv: (s.snapshot as TelemetryPayload).battery_mv ?? 0,
      range_mm: (s.snapshot as TelemetryPayload).range_mm ?? 0,
      range_status: (s.snapshot as TelemetryPayload).range_status ?? 0,
      vision_fps: (s.snapshot as TelemetryPayload).vision_fps ?? 0,
      vision_age_ms: (s.snapshot as TelemetryPayload).vision_age_ms ?? 0,
      speed_caps: ((s.snapshot as TelemetryPayload).speed_caps ?? []) as {
        scale: number
        reason: string
      }[],
      worker_alive: ((s.snapshot as TelemetryPayload).worker_alive ?? {}) as Record<
        string,
        boolean
      >,
    }),
    200,
  )

  const seqGaps = useTelemetry((s) => s.meta.seqGaps, 500)

  const tree = useMemo(
    () => buildTree(sys, tel, devices, clocks, workers),
    [sys, tel, devices, clocks, workers],
  )

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
      {/* Diagnostic tree */}
      <div className={styles.card}>
        <DiagnosticTree root={tree} />
      </div>

      {/* Pi resources + Communication */}
      <div className={styles.grid2}>
        <SystemResourcesPanel sys={sys} />
        <CommunicationPanel devices={devices} clocks={clocks} seqGaps={seqGaps} />
      </div>

      {/* Power chart */}
      <PowerPanel batteryMv={tel.battery_mv} />

      {/* Sensor health */}
      <SensorHealthPanel
        faultFlags={tel.fault_flags}
        rangeStatus={tel.range_status}
        rangeMm={tel.range_mm}
        visionFps={tel.vision_fps}
        visionAgeMs={tel.vision_age_ms}
        workerAlive={tel.worker_alive}
      />

      {/* Drive health + Workers */}
      <div className={styles.grid2}>
        <DriveHealthPanel faultFlags={tel.fault_flags} speedCaps={tel.speed_caps} />
        <WorkerHealthPanel workers={workers} />
      </div>
    </div>
  )
}
