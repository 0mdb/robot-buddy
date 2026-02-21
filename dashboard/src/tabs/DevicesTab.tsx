import { useClocks } from '../hooks/useClocks'
import { useDevices } from '../hooks/useDevices'
import styles from '../styles/global.module.css'
import type { ClockSyncInfo, FaceDebug, ReflexDebug, TransportDebug } from '../types'

/* ---- helpers ---- */

function ConnBadge({ connected }: { connected: boolean }) {
  return (
    <span className={`${styles.badge} ${connected ? styles.badgeGreen : styles.badgeRed}`}>
      {connected ? 'connected' : 'disconnected'}
    </span>
  )
}

function SyncBadge({ state }: { state: string }) {
  const cls =
    state === 'synced'
      ? styles.badgeGreen
      : state === 'degraded'
        ? styles.badgeYellow
        : styles.badgeRed
  return <span className={`${styles.badge} ${cls}`}>{state}</span>
}

function Row({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div style={{ display: 'flex', justifyContent: 'space-between', padding: '2px 0' }}>
      <span style={{ color: '#888', fontSize: 12 }}>{label}</span>
      <span className={styles.mono} style={{ fontSize: 12 }}>
        {value}
      </span>
    </div>
  )
}

function fmt(n: number | undefined | null): string {
  if (n === undefined || n === null) return '--'
  return n.toLocaleString()
}

/* ---- sub-cards ---- */

function ReflexCard({ data }: { data: ReflexDebug }) {
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
        <h3 style={{ margin: 0 }}>Reflex MCU</h3>
        <ConnBadge connected={data.connected} />
      </div>
      <Row label="TX packets" value={fmt(data.tx_packets)} />
      <Row label="RX state" value={fmt(data.rx_state_packets)} />
      <Row label="RX bad payload" value={fmt(data.rx_bad_payload_packets)} />
      <Row label="RX unknown" value={fmt(data.rx_unknown_packets)} />
      <Row label="Last seq" value={fmt(data.last_state_seq)} />
      <Row label="Last age" value={`${fmt(data.last_state_age_ms)} ms`} />
    </div>
  )
}

function FaceCard({ data }: { data: FaceDebug }) {
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
        <h3 style={{ margin: 0 }}>Face MCU</h3>
        <ConnBadge connected={data.connected} />
      </div>
      <Row label="TX packets" value={fmt(data.tx_packets)} />
      <Row label="RX face status" value={fmt(data.rx_face_status_packets)} />
      <Row label="RX touch" value={fmt(data.rx_touch_packets)} />
      <Row label="RX button" value={fmt(data.rx_button_packets)} />
      <Row label="RX heartbeat" value={fmt(data.rx_heartbeat_packets)} />
      <Row label="RX bad payload" value={fmt(data.rx_bad_payload_packets)} />
      <Row label="RX unknown" value={fmt(data.rx_unknown_packets)} />
      <Row label="Last seq" value={fmt(data.last_status_seq)} />
      <Row label="Last age" value={`${fmt(data.last_status_age_ms)} ms`} />
    </div>
  )
}

function ClockCard({ label, data }: { label: string; data: ClockSyncInfo }) {
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
        <h3 style={{ margin: 0 }}>{label} Clock Sync</h3>
        <SyncBadge state={data.state} />
      </div>
      <Row label="Offset" value={`${fmt(data.offset_ns)} ns`} />
      <Row label="RTT min" value={`${fmt(data.rtt_min_us)} us`} />
      <Row label="Drift" value={`${data.drift_us_per_s.toFixed(3)} us/s`} />
      <Row label="Samples" value={fmt(data.samples)} />
    </div>
  )
}

function TransportCard({ label, data }: { label: string; data: TransportDebug }) {
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
        <h3 style={{ margin: 0 }}>{label} Transport</h3>
        <ConnBadge connected={data.connected} />
      </div>
      <Row label="Port" value={data.port} />
      <Row label="Connects" value={fmt(data.connect_count)} />
      <Row label="Disconnects" value={fmt(data.disconnect_count)} />
      <Row label="RX bytes" value={fmt(data.rx_bytes)} />
      <Row label="TX bytes" value={fmt(data.tx_bytes)} />
      <Row label="Frames OK" value={fmt(data.frames_ok)} />
      <Row label="Frames bad" value={fmt(data.frames_bad)} />
      <Row label="Frames too long" value={fmt(data.frames_too_long)} />
      <Row label="Write errors" value={fmt(data.write_errors)} />
      {data.last_error && (
        <Row
          label="Last error"
          value={
            <span style={{ color: '#f44336', wordBreak: 'break-all' }}>{data.last_error}</span>
          }
        />
      )}
      {data.last_bad_frame && (
        <Row
          label="Last bad frame"
          value={
            <span
              style={{
                color: '#ff9800',
                wordBreak: 'break-all',
                maxWidth: 200,
                display: 'inline-block',
                textAlign: 'right',
              }}
            >
              {data.last_bad_frame}
            </span>
          }
        />
      )}
    </div>
  )
}

/* ---- main tab ---- */

export default function DevicesTab() {
  const { data: devices, isLoading: devLoading, error: devError } = useDevices()
  const { data: clocks, isLoading: clkLoading, error: clkError } = useClocks()

  if (devLoading || clkLoading) {
    return (
      <div className={styles.mono} style={{ padding: 24, color: '#888' }}>
        Loading device data...
      </div>
    )
  }

  if (devError || clkError) {
    return (
      <div className={styles.mono} style={{ padding: 24, color: '#f44336' }}>
        Error: {(devError as Error)?.message ?? (clkError as Error)?.message ?? 'unknown'}
      </div>
    )
  }

  if (!devices || !clocks) return null

  return (
    <div
      className={styles.mono}
      style={{ display: 'flex', flexDirection: 'column', gap: 12, padding: 12 }}
    >
      {/* MCU status cards */}
      <div className={styles.grid2}>
        <ReflexCard data={devices.reflex} />
        <FaceCard data={devices.face} />
      </div>

      {/* Clock sync cards */}
      <div className={styles.grid2}>
        <ClockCard label="Reflex" data={clocks.reflex} />
        <ClockCard label="Face" data={clocks.face} />
      </div>

      {/* Transport cards */}
      <div className={styles.grid2}>
        <TransportCard label="Reflex" data={devices.reflex.transport} />
        <TransportCard label="Face" data={devices.face.transport} />
      </div>
    </div>
  )
}
