import { useTelemetry } from '../hooks/useTelemetry'
import { useWsMeta } from '../hooks/useWsMeta'
import styles from '../styles/header.module.css'
import { FaultBadges } from './FaultBadges'

export function Header() {
  const meta = useWsMeta()
  const faultFlags = useTelemetry((s) => (s.snapshot.fault_flags as number) ?? 0)
  const reflexConn = useTelemetry((s) => s.snapshot.reflex_connected as boolean | undefined)
  const faceConn = useTelemetry((s) => s.snapshot.face_connected as boolean | undefined)
  const mode = useTelemetry((s) => (s.snapshot.mode as string) ?? '—')

  const wsColor =
    meta.wsState === 'open'
      ? styles.dotGreen
      : meta.wsState === 'connecting'
        ? styles.dotYellow
        : styles.dotRed

  const ageClass =
    meta.telemetryAgeMs > 1000
      ? styles.metaError
      : meta.telemetryAgeMs > 200
        ? styles.metaWarn
        : styles.meta

  return (
    <div className={styles.header}>
      <span className={styles.title}>Robot Buddy</span>

      {/* WS status */}
      <span className={styles.pill}>
        <span className={`${styles.dot} ${wsColor}`} />
        WS
      </span>

      {/* Telemetry age */}
      <span className={`${styles.pill} ${ageClass}`}>
        {meta.lastRxMs > 0 ? `${Math.round(meta.telemetryAgeMs)}ms` : '—'}
      </span>

      {/* Seq gaps */}
      {meta.seqGaps > 0 && (
        <span className={styles.pill} style={{ color: 'var(--yellow)' }}>
          gaps:{meta.seqGaps}
        </span>
      )}

      {/* Reconnects */}
      {meta.reconnectCount > 0 && <span className={styles.pill}>reconn:{meta.reconnectCount}</span>}

      <span className={styles.spacer} />

      {/* Mode */}
      <span className={styles.pill}>{mode}</span>

      {/* Device pills */}
      <span className={styles.pill}>
        <span className={`${styles.dot} ${reflexConn ? styles.dotGreen : styles.dotRed}`} />
        Reflex
      </span>
      <span className={styles.pill}>
        <span className={`${styles.dot} ${faceConn ? styles.dotGreen : styles.dotRed}`} />
        Face
      </span>

      {/* Fault badges */}
      <FaultBadges flags={faultFlags} />
    </div>
  )
}
