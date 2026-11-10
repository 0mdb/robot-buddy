import { useState } from 'react'
import {
  useClearAlerts,
  useDeleteAlert,
  useMarkReviewed,
  useParentAlerts,
  useSetAlertsEnabled,
} from '../hooks/useParentAlerts'
import styles from '../styles/global.module.css'
import m from '../styles/monitor.module.css'

function when(ts: number): string {
  return new Date(ts * 1000).toLocaleString(undefined, {
    weekday: 'short',
    hour: 'numeric',
    minute: '2-digit',
  })
}

/** Quiet alerts for parents. Buddy says nothing to the child about these. */
export function ParentAlertsPanel() {
  const { data, error } = useParentAlerts()
  const mark = useMarkReviewed()
  const del = useDeleteAlert()
  const clear = useClearAlerts()
  const setEnabled = useSetAlertsEnabled()
  const [confirmClear, setConfirmClear] = useState(false)
  const failure = (error ?? mark.error ?? del.error ?? clear.error ?? setEnabled.error) as
    | Error
    | null
    | undefined

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
          For parents
        </h3>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          {data && data.unreviewed > 0 && (
            <span className={`${styles.badge} ${styles.badgeRed}`}>{data.unreviewed} new</span>
          )}
          <span className={`${styles.badge} ${styles.badgeDim}`}>
            phone push {data?.push ? 'on' : 'off'}
          </span>
          <label style={{ display: 'flex', alignItems: 'center', gap: 4, fontSize: 12 }}>
            <input
              type="checkbox"
              checked={data?.enabled ?? false}
              disabled={!data}
              onChange={(e) => setEnabled.mutate(e.target.checked)}
            />
            Alerts on
          </label>
          {data &&
            data.alerts.length > 0 &&
            (confirmClear ? (
              <div style={{ display: 'flex', gap: 4 }}>
                <button
                  type="button"
                  className={`${styles.badge} ${styles.badgeRed}`}
                  style={{ cursor: 'pointer', border: 'none' }}
                  onClick={() => {
                    clear.mutate(undefined)
                    setConfirmClear(false)
                  }}
                >
                  Confirm
                </button>
                <button
                  type="button"
                  className={`${styles.badge} ${styles.badgeDim}`}
                  style={{ cursor: 'pointer', border: 'none' }}
                  onClick={() => setConfirmClear(false)}
                >
                  Cancel
                </button>
              </div>
            ) : (
              <button
                type="button"
                className={`${styles.badge} ${styles.badgeRed}`}
                style={{ cursor: 'pointer', border: 'none' }}
                onClick={() => setConfirmClear(true)}
              >
                Clear all
              </button>
            ))}
        </div>
      </div>

      <p style={{ color: 'var(--text-dim)', fontSize: 12, margin: '0 0 8px' }}>
        When a child asks Buddy to keep a secret, or mentions a stranger, unwanted touching, being
        hurt, or being bullied, it is noted here so you can follow up. Buddy says nothing to the
        child about it. The words stay on this robot; a phone push says only what kind and when.
      </p>

      {failure && (
        <div role="alert" style={{ color: 'var(--red, #f44336)', fontSize: 12, marginBottom: 8 }}>
          {failure.message}
        </div>
      )}

      {data && data.alerts.length === 0 && (
        <span className={styles.mono} style={{ color: 'var(--text-dim)', fontSize: 12 }}>
          Nothing to follow up.
        </span>
      )}

      {data?.alerts.map((a) => (
        <div
          key={a.id}
          data-testid="parent-alert"
          style={{
            borderTop: '1px solid var(--border, #333)',
            padding: '6px 0',
            opacity: a.reviewed ? 0.6 : 1,
          }}
        >
          <div style={{ display: 'flex', justifyContent: 'space-between', gap: 8 }}>
            <strong style={{ fontSize: 13 }}>
              {when(a.ts)} — a child {a.summary}
            </strong>
            <div style={{ display: 'flex', gap: 4 }}>
              <button
                type="button"
                className={`${styles.badge} ${styles.badgeDim}`}
                style={{ cursor: 'pointer', border: 'none' }}
                onClick={() => mark.mutate({ id: a.id, reviewed: !a.reviewed })}
              >
                {a.reviewed ? 'Mark new' : 'Mark reviewed'}
              </button>
              <button
                type="button"
                className={`${styles.badge} ${styles.badgeDim}`}
                style={{ cursor: 'pointer', border: 'none' }}
                aria-label="Delete alert"
                onClick={() => del.mutate(a.id)}
              >
                Delete
              </button>
            </div>
          </div>
          <div style={{ fontSize: 13, marginTop: 2 }}>Child: “{a.child_text}”</div>
          {a.buddy_reply && (
            <div style={{ fontSize: 13, color: 'var(--text-dim)' }}>Buddy: “{a.buddy_reply}”</div>
          )}
        </div>
      ))}
    </div>
  )
}
