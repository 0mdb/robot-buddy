import { useEffect, useMemo, useRef, useState } from 'react'
import { Sparkline } from '../components/Sparkline'
import { TimeSeriesChart } from '../components/TimeSeriesChart'
import { FAULT_NAMES, RANGE_STATUS } from '../constants'
import { useClocks } from '../hooks/useClocks'
import { useDevices } from '../hooks/useDevices'
import { type MemoryEntry, useMemory, useResetMemory } from '../hooks/useMemory'
import { useSystem } from '../hooks/useSystem'
import { useTelemetry } from '../hooks/useTelemetry'
import { useWorkers } from '../hooks/useWorkers'
import styles from '../styles/global.module.css'
import m from '../styles/monitor.module.css'
import type {
  ClockSyncInfo,
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

function clockLevel(state: string): DiagLevel {
  if (state === 'synced') return 'ok'
  if (state === 'unsynced') return 'warn'
  if (state === 'degraded') return 'error'
  return 'stale'
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
  reflexConnected: boolean,
  faceConnected: boolean,
  faultFlags: number,
  devices: DeviceDebug | undefined,
  clocks: ClocksDebug | undefined,
  workers: WorkersDebug | undefined,
): DiagNode {
  const piLevel = computePiLevel(sys)
  const reflexLevel = computeReflexLevel(
    reflexConnected,
    faultFlags,
    devices?.reflex.last_state_age_ms,
  )
  const faceLevel = computeFaceLevel(faceConnected, devices?.face.last_status_age_ms)
  const workersLevel = computeWorkersLevel(workers)

  // Clock sub-levels
  const reflexClockLevel: DiagLevel = clocks ? clockLevel(clocks.reflex.state) : 'stale'
  const faceClockLevel: DiagLevel = clocks ? clockLevel(clocks.face.state) : 'stale'

  const piSummary = sys
    ? `CPU ${sys.cpu_percent}% | ${sys.cpu_temp_c ?? '--'}C | Mem ${sys.mem_percent}%`
    : 'unavailable'
  const reflexSummary = reflexConnected
    ? `age ${devices?.reflex.last_state_age_ms ?? '--'}ms | clk ${clocks?.reflex.state ?? '--'}`
    : 'disconnected'
  const faceSummary = faceConnected
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
            <StatusBadge level={clockLevel(clocks.reflex.state)} text={clocks.reflex.state} />
          ) : (
            '--'
          )
        }
      />
      <Row
        label="Face clock"
        value={
          clocks ? (
            <StatusBadge level={clockLevel(clocks.face.state)} text={clocks.face.state} />
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

function PowerPanel({
  batteryMv,
  reflexConnected,
}: {
  batteryMv: number
  reflexConnected: boolean
}) {
  if (!reflexConnected && batteryMv === 0) {
    return (
      <div className={styles.card}>
        <h3 className={m.sectionTitle}>Power</h3>
        <span className={styles.mono} style={{ color: 'var(--text-dim)' }}>
          No battery data (Reflex disconnected)
        </span>
      </div>
    )
  }

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
  tiltAngleDeg,
}: {
  faultFlags: number
  rangeStatus: number
  rangeMm: number
  visionFps: number
  visionAgeMs: number
  workerAlive: Record<string, boolean>
  tiltAngleDeg: number
}) {
  const imuFail = !!(faultFlags & (1 << 4))
  const imuLevel: DiagLevel = imuFail ? 'error' : 'ok'

  const rangeLevel: DiagLevel =
    rangeStatus === RANGE_STATUS.OK
      ? 'ok'
      : rangeStatus === RANGE_STATUS.TIMEOUT
        ? 'warn'
        : rangeStatus === RANGE_STATUS.OUT_OF_RANGE
          ? 'ok'
          : 'stale'

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
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <span className={styles.mono} style={{ fontSize: 12, color: 'var(--text-dim)' }}>
              {tiltAngleDeg >= 0 ? '+' : ''}
              {tiltAngleDeg.toFixed(1)}°
            </span>
            <StatusBadge level={imuLevel} text={imuLevel.toUpperCase()} />
          </div>
        </div>
        <Sparkline metric="gyro_z" color="var(--blue)" width={160} height={28} window={10} />
        <div style={{ marginTop: 4, fontSize: 11, color: 'var(--text-dim)' }}>gyro Z</div>
        <Sparkline metric="accel_z" color="var(--green)" width={160} height={28} window={10} />
        <div style={{ marginTop: 4, fontSize: 11, color: 'var(--text-dim)' }}>
          accel Z (≈1000 mg)
        </div>
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

function DeviceClockPanel({
  devices,
  clocks,
}: {
  devices: DeviceDebug | undefined
  clocks: ClocksDebug | undefined
}) {
  function ClockCard({
    label,
    clock,
    ageMs,
    seq,
  }: {
    label: string
    clock: ClockSyncInfo | undefined
    ageMs: number | undefined
    seq: number | undefined
  }) {
    const level: DiagLevel = clock ? clockLevel(clock.state) : 'stale'
    const offsetUs = clock ? Math.round(clock.offset_ns / 1000) : null
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
            {label}
          </h3>
          <StatusBadge level={level} text={clock?.state ?? 'stale'} />
        </div>
        <Row label="RTT min" value={clock ? `${fmt(clock.rtt_min_us)} µs` : '--'} />
        <Row
          label="Offset"
          value={offsetUs !== null ? `${offsetUs >= 0 ? '+' : ''}${fmt(offsetUs)} µs` : '--'}
        />
        <Row label="Drift" value={clock ? `${clock.drift_us_per_s.toFixed(2)} µs/s` : '--'} />
        <Row label="Samples" value={fmt(clock?.samples)} />
        <Row label="Data age" value={ageMs !== undefined ? `${fmt(ageMs)} ms` : '--'} />
        <Row label="Last seq" value={fmt(seq)} />
      </div>
    )
  }

  return (
    <div className={styles.grid2}>
      <ClockCard
        label="Reflex MCU Clock"
        clock={clocks?.reflex}
        ageMs={devices?.reflex.last_state_age_ms}
        seq={devices?.reflex.last_state_seq}
      />
      <ClockCard
        label="Face MCU Clock"
        clock={clocks?.face}
        ageMs={devices?.face.last_status_age_ms}
        seq={devices?.face.last_status_seq}
      />
    </div>
  )
}

/* ---- memory panel (PE spec S2 §8.5) ---- */

const CATEGORY_LABELS: Record<string, string> = {
  name: 'Name',
  ritual: 'Ritual',
  topic: 'Topic',
  tone: 'Tone',
  preference: 'Pref',
}

const CATEGORY_COLORS: Record<string, string> = {
  name: 'var(--blue)',
  ritual: 'var(--green)',
  topic: 'var(--text)',
  tone: 'var(--yellow)',
  preference: 'var(--red)',
}

function formatAge(ts: number): string {
  const age = Date.now() / 1000 - ts
  if (age < 60) return '<1m'
  if (age < 3600) return `${Math.floor(age / 60)}m`
  if (age < 86400) return `${Math.floor(age / 3600)}h`
  return `${Math.floor(age / 86400)}d`
}

function MemoryPanel() {
  const { data: memory } = useMemory()
  const resetMemory = useResetMemory()
  const [confirmReset, setConfirmReset] = useState(false)

  if (!memory) {
    return (
      <div className={styles.card}>
        <h3 className={m.sectionTitle}>Memory</h3>
        <span className={styles.mono} style={{ color: 'var(--text-dim)' }}>
          Loading...
        </span>
      </div>
    )
  }

  if (!memory.consent) {
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
            Memory
          </h3>
          <span className={`${styles.badge} ${styles.badgeDim}`}>disabled</span>
        </div>
        <span className={styles.mono} style={{ color: 'var(--text-dim)', fontSize: 12 }}>
          Memory storage requires parental consent. Set memory_consent: true in config.
        </span>
      </div>
    )
  }

  const entries: MemoryEntry[] = memory.entries ?? []
  const sorted = [...entries].sort((a, b) => b.current_strength - a.current_strength)

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
          Memory
        </h3>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <span className={`${styles.badge} ${styles.badgeGreen}`}>
            {memory.entry_count} entries
          </span>
          {confirmReset ? (
            <div style={{ display: 'flex', gap: 4 }}>
              <button
                type="button"
                className={`${styles.badge} ${styles.badgeRed}`}
                style={{ cursor: 'pointer', border: 'none' }}
                onClick={() => {
                  resetMemory.mutate()
                  setConfirmReset(false)
                }}
              >
                Confirm
              </button>
              <button
                type="button"
                className={`${styles.badge} ${styles.badgeDim}`}
                style={{ cursor: 'pointer', border: 'none' }}
                onClick={() => setConfirmReset(false)}
              >
                Cancel
              </button>
            </div>
          ) : (
            <button
              type="button"
              className={`${styles.badge} ${styles.badgeRed}`}
              style={{ cursor: 'pointer', border: 'none' }}
              onClick={() => setConfirmReset(true)}
            >
              Forget All
            </button>
          )}
        </div>
      </div>
      {sorted.length === 0 ? (
        <span className={styles.mono} style={{ color: 'var(--text-dim)', fontSize: 12 }}>
          No memories stored yet.
        </span>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
          {sorted.map((entry) => (
            <div
              key={entry.tag}
              style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 12 }}
            >
              <span
                className={`${styles.badge}`}
                style={{
                  background: CATEGORY_COLORS[entry.category] ?? 'var(--text-dim)',
                  color: '#000',
                  minWidth: 40,
                  textAlign: 'center',
                  fontSize: 10,
                }}
              >
                {CATEGORY_LABELS[entry.category] ?? entry.category}
              </span>
              <span className={styles.mono} style={{ flex: 1 }}>
                {entry.tag.replace(/_/g, ' ')}
              </span>
              <div style={{ width: 60 }}>
                <div style={{ background: '#333', borderRadius: 2, height: 6, overflow: 'hidden' }}>
                  <div
                    style={{
                      width: `${Math.round(entry.current_strength * 100)}%`,
                      height: '100%',
                      background: 'var(--green)',
                      borderRadius: 2,
                    }}
                  />
                </div>
              </div>
              <span
                className={styles.mono}
                style={{ color: 'var(--text-dim)', width: 35, textAlign: 'right' }}
              >
                {(entry.current_strength * 100).toFixed(0)}%
              </span>
              <span
                className={styles.mono}
                style={{ color: 'var(--text-dim)', width: 20, textAlign: 'right' }}
              >
                x{entry.reinforcement_count}
              </span>
              <span
                className={styles.mono}
                style={{ color: 'var(--text-dim)', width: 30, textAlign: 'right' }}
              >
                {formatAge(entry.last_reinforced_ts)}
              </span>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

/* ---- main tab ---- */

export default function MonitorTab() {
  const { data: sys } = useSystem()
  const { data: devices } = useDevices()
  const { data: clocks } = useClocks()
  const { data: workers } = useWorkers()

  const reflexConnected = useTelemetry(
    (s) => (s.snapshot as TelemetryPayload).reflex_connected ?? false,
    200,
  )
  const faceConnected = useTelemetry(
    (s) => (s.snapshot as TelemetryPayload).face_connected ?? false,
    200,
  )
  const faultFlags = useTelemetry((s) => (s.snapshot as TelemetryPayload).fault_flags ?? 0, 200)
  const batteryMv = useTelemetry((s) => (s.snapshot as TelemetryPayload).battery_mv ?? 0, 200)
  const rangeMm = useTelemetry((s) => (s.snapshot as TelemetryPayload).range_mm ?? 0, 200)
  const rangeStatus = useTelemetry((s) => (s.snapshot as TelemetryPayload).range_status ?? 0, 200)
  const visionFps = useTelemetry((s) => (s.snapshot as TelemetryPayload).vision_fps ?? 0, 200)
  const visionAgeMs = useTelemetry((s) => (s.snapshot as TelemetryPayload).vision_age_ms ?? 0, 200)
  const speedCaps = useTelemetry(
    (s) =>
      ((s.snapshot as TelemetryPayload).speed_caps ?? []) as {
        scale: number
        reason: string
      }[],
    200,
  )
  const workerAlive = useTelemetry(
    (s) => ((s.snapshot as TelemetryPayload).worker_alive ?? {}) as Record<string, boolean>,
    200,
  )
  const seqGaps = useTelemetry((s) => s.meta.seqGaps, 500)
  const tiltAngleDeg = useTelemetry(
    (s) => (s.snapshot as TelemetryPayload).tilt_angle_deg ?? 0,
    200,
  )

  const tree = useMemo(
    () => buildTree(sys, reflexConnected, faceConnected, faultFlags, devices, clocks, workers),
    [sys, reflexConnected, faceConnected, faultFlags, devices, clocks, workers],
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

      {/* Per-device clock health */}
      <DeviceClockPanel devices={devices} clocks={clocks} />

      {/* Power chart */}
      <PowerPanel batteryMv={batteryMv} reflexConnected={reflexConnected} />

      {/* Sensor health */}
      <SensorHealthPanel
        faultFlags={faultFlags}
        rangeStatus={rangeStatus}
        rangeMm={rangeMm}
        visionFps={visionFps}
        visionAgeMs={visionAgeMs}
        workerAlive={workerAlive}
        tiltAngleDeg={tiltAngleDeg}
      />

      {/* Drive health + Workers */}
      <div className={styles.grid2}>
        <DriveHealthPanel faultFlags={faultFlags} speedCaps={speedCaps} />
        <WorkerHealthPanel workers={workers} />
      </div>

      {/* Personality memory (PE spec S2 §8.5) */}
      <MemoryPanel />
    </div>
  )
}
