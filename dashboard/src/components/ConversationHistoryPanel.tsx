import { useState } from 'react'
import {
  groupVisits,
  type HistoryEntry,
  useClearConversations,
  useConversations,
  useHistorySettings,
} from '../hooks/useConversations'
import styles from '../styles/global.module.css'
import m from '../styles/monitor.module.css'

const DAY_CHOICES = [1, 3, 7, 14]

const SOURCE_LABEL: Record<string, string> = {
  greeter: 'greeting',
  planner: 'on its own',
  speech_policy: 'remark',
}

function clock(t: number) {
  return new Date(t * 1000).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
}

function day(t: number) {
  return new Date(t * 1000).toLocaleDateString([], {
    weekday: 'short',
    month: 'short',
    day: 'numeric',
  })
}

/** What the children said and what Buddy said back, for a parent's review and tuning.
 * Off by default; kept on the robot only and deleted after a few days. */
export function ConversationHistoryPanel() {
  const { data, error } = useConversations()
  const settings = useHistorySettings()
  const clear = useClearConversations()
  const [confirmClear, setConfirmClear] = useState(false)
  const [ownLines, setOwnLines] = useState(true)

  const entries = (data?.entries ?? []).filter(
    (e) => ownLines || !(e.role === 'buddy' && e.source && e.source !== 'conversation'),
  )
  const visits = groupVisits(entries)

  return (
    <div className={styles.card}>
      <div
        style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          flexWrap: 'wrap',
          gap: 8,
          marginBottom: 8,
        }}
      >
        <h3 className={m.sectionTitle} style={{ marginBottom: 0 }}>
          Conversation history
        </h3>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 12 }}>
          <label style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
            <input
              type="checkbox"
              checked={data?.enabled ?? false}
              disabled={!data}
              onChange={(e) =>
                settings.mutate({ 'conversation.history_enabled': e.target.checked })
              }
            />
            Keep history
          </label>
          <label style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
            for
            <select
              aria-label="Days kept"
              value={data?.days ?? 3}
              disabled={!data}
              onChange={(e) =>
                settings.mutate({ 'conversation.history_days': Number(e.target.value) })
              }
            >
              {DAY_CHOICES.map((d) => (
                <option key={d} value={d}>
                  {d} {d === 1 ? 'day' : 'days'}
                </option>
              ))}
            </select>
          </label>
          {confirmClear ? (
            <>
              <button
                type="button"
                className={`${styles.badge} ${styles.badgeRed}`}
                style={{ cursor: 'pointer', border: 'none' }}
                onClick={() => {
                  clear.mutate()
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
            </>
          ) : (
            <button
              type="button"
              className={`${styles.badge} ${styles.badgeRed}`}
              style={{ cursor: 'pointer', border: 'none' }}
              onClick={() => setConfirmClear(true)}
            >
              Clear all
            </button>
          )}
        </div>
      </div>

      <p style={{ color: 'var(--text-dim)', fontSize: 12, margin: '0 0 8px' }}>
        Off unless you turn it on. Kept on this robot only, never in its logs, and deleted after the
        days you choose (and with &quot;Forget everyone&quot;). Children&apos;s words are as Buddy
        heard them, so mistakes here are speech-recognition mistakes.
      </p>

      <label style={{ display: 'flex', alignItems: 'center', gap: 4, fontSize: 12 }}>
        <input type="checkbox" checked={ownLines} onChange={(e) => setOwnLines(e.target.checked)} />
        Show Buddy&apos;s own lines (greetings, remarks)
      </label>

      {error && (
        <div role="alert" style={{ color: 'var(--red, #f44336)', fontSize: 12, marginTop: 8 }}>
          {(error as Error).message}
        </div>
      )}

      {data && visits.length === 0 && (
        <p style={{ fontSize: 12, color: 'var(--text-dim)' }}>
          {data.enabled ? 'Nothing yet.' : 'History is off.'}
        </p>
      )}

      <div style={{ maxHeight: 520, overflowY: 'auto', marginTop: 8 }}>
        {visits.map((v) => (
          <section key={v[0].t} style={{ marginBottom: 12 }}>
            <div style={{ fontSize: 11, color: 'var(--text-dim)', marginBottom: 4 }}>
              {day(v[0].t)} {clock(v[0].t)}
            </div>
            {v.map((e, i) => (
              <Line key={`${e.t}-${i}`} e={e} />
            ))}
          </section>
        ))}
      </div>
    </div>
  )
}

function Line({ e }: { e: HistoryEntry }) {
  if (e.role === 'timing') {
    return (
      <div style={{ fontSize: 11, color: 'var(--text-dim)', margin: '0 0 2px 16px' }}>
        replied after {((e.reply_ms ?? 0) / 1000).toFixed(1)} s
        {e.late_resumes ? `, kept listening ${e.late_resumes}×` : ''}
      </div>
    )
  }
  const buddy = e.role === 'buddy'
  const who = buddy ? 'Buddy' : e.role === 'typed' ? 'Typed' : (e.who?.join(' / ') ?? '') || 'Child'
  const tag =
    buddy && e.source && e.source !== 'conversation' ? (SOURCE_LABEL[e.source] ?? e.source) : ''
  return (
    <div style={{ display: 'flex', gap: 8, fontSize: 13, marginBottom: 3 }}>
      <span style={{ color: 'var(--text-dim)', fontSize: 11, minWidth: 40 }}>{clock(e.t)}</span>
      <span
        style={{
          fontWeight: 600,
          minWidth: 56,
          color: buddy ? 'var(--accent, #4fc3f7)' : undefined,
        }}
      >
        {who}
      </span>
      <span style={{ flex: 1 }}>
        {e.text}
        {e.emotion && (
          <span className={`${styles.badge} ${styles.badgeDim}`} style={{ marginLeft: 6 }}>
            {e.emotion}
          </span>
        )}
        {tag && (
          <span className={`${styles.badge} ${styles.badgeDim}`} style={{ marginLeft: 6 }}>
            {tag}
          </span>
        )}
      </span>
    </div>
  )
}
