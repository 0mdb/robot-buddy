import { useParamsList, useUpdateParams } from '../hooks/useParams'
import styles from '../styles/global.module.css'
import m from '../styles/monitor.module.css'

export const QUIET_MODE_PARAM = 'conversation.quiet_mode'

/** Quiet mode: Buddy stops making unprompted remarks but still answers and still warns about
 * battery and faults (supervisor param `conversation.quiet_mode`). */
export function QuietModePanel() {
  const { data: paramsList } = useParamsList()
  const updateParams = useUpdateParams()
  const param = paramsList?.find((p) => p.name === QUIET_MODE_PARAM)
  if (!param) return null
  const quiet = !!param.value

  return (
    <div className={styles.card}>
      <label
        style={{ display: 'flex', alignItems: 'center', gap: 10, cursor: 'pointer' }}
        title={param.doc}
      >
        <input
          type="checkbox"
          checked={quiet}
          disabled={updateParams.isPending}
          onChange={(e) => updateParams.mutate({ [QUIET_MODE_PARAM]: e.target.checked })}
        />
        <h3 className={m.sectionTitle} style={{ marginBottom: 0 }}>
          Quiet mode
        </h3>
        <span style={{ color: 'var(--text-dim)', fontSize: 12 }}>
          {quiet
            ? 'On: no unprompted remarks. Buddy still answers, and still warns about battery and faults.'
            : 'Off: Buddy comments on what he sees and does.'}
        </span>
      </label>
    </div>
  )
}
