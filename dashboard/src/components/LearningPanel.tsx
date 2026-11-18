import { useState } from 'react'
import {
  type Grade,
  type LearningChild,
  type LearningSkill,
  useLearning,
  useResetLearning,
  useSetCeiling,
} from '../hooks/useLearning'
import styles from '../styles/global.module.css'
import m from '../styles/monitor.module.css'

const SKILL_LABEL: Record<string, string> = {
  add_sub_facts: 'Adding and subtracting (Rocket Math)',
  sounds: 'Word sounds (Sound Swap)',
  place_value: 'Place value (Number Detective)',
}

const pct = (x: number | null) => (x === null ? '—' : `${Math.round(x * 100)}%`)

/** Per-child learning progress and the grade ceiling (docs/learning-games.md §2). */
export function LearningPanel() {
  const { data, error } = useLearning()
  const setCeiling = useSetCeiling()
  const reset = useResetLearning()
  const failure = (error ?? setCeiling.error ?? reset.error) as Error | null | undefined
  const gradeName = (g: Grade) => data?.grades.find((x) => x.id === g)?.name ?? g

  return (
    <div className={styles.card}>
      <h3 className={m.sectionTitle}>Learning</h3>
      <p style={{ color: 'var(--text-dim)', fontSize: 12, margin: '0 0 8px' }}>
        Progress in Buddy&apos;s learning games, per child, stored on this robot. Answers are
        checked by code, not by the language model. A skill moves up a grade after 80% or better in
        3 games on 3 different days, and never above the ceiling you set. Buddy only mentions a
        child&apos;s progress for skills shown as <b>confident</b>. Note: the dashboard has no login
        yet, so anyone on the home network can change these settings.
      </p>

      {failure && (
        <div role="alert" style={{ color: 'var(--red, #f44336)', fontSize: 12, marginBottom: 8 }}>
          {failure.message}
        </div>
      )}

      {data && data.children.length === 0 && (
        <p style={{ fontSize: 12 }}>Add children (with their ages) in Household above.</p>
      )}

      {data?.children.map((child) => (
        <ChildProgress
          key={child.member_id}
          child={child}
          grades={data.grades}
          gradeName={gradeName}
          onCeiling={(ceiling) => setCeiling.mutate({ id: child.member_id, ceiling })}
          onReset={() => reset.mutate(child.member_id)}
        />
      ))}
    </div>
  )
}

function ChildProgress(props: {
  child: LearningChild
  grades: { id: Grade; name: string }[]
  gradeName: (g: Grade) => string
  onCeiling: (g: Grade | null) => void
  onReset: () => void
}) {
  const { child, grades, gradeName } = props
  const [confirm, setConfirm] = useState(false)
  return (
    <div style={{ borderTop: '1px solid var(--border, #333)', padding: '8px 0' }}>
      <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
        <b>{child.name}</b>
        <span style={{ color: 'var(--text-dim)', fontSize: 12 }}>
          {child.age !== undefined ? `${child.age}, ` : ''}starts at {gradeName(child.base)}
        </span>
        <label style={{ fontSize: 12, marginLeft: 'auto' }}>
          Up to{' '}
          <select
            aria-label={`Grade ceiling for ${child.name}`}
            value={child.ceiling_is_default ? '' : child.ceiling}
            onChange={(e) =>
              props.onCeiling(e.target.value === '' ? null : (e.target.value as Grade))
            }
          >
            <option value="">
              {child.ceiling_is_default
                ? `Default (${gradeName(child.ceiling)})`
                : 'Default (one grade above start)'}
            </option>
            {grades.map((g) => (
              <option key={g.id} value={g.id}>
                {g.name}
              </option>
            ))}
          </select>
        </label>
        {confirm ? (
          <span style={{ display: 'flex', gap: 4 }}>
            <button
              type="button"
              className={`${styles.badge} ${styles.badgeRed}`}
              style={{ cursor: 'pointer', border: 'none' }}
              onClick={() => {
                props.onReset()
                setConfirm(false)
              }}
            >
              Confirm reset
            </button>
            <button
              type="button"
              className={`${styles.badge} ${styles.badgeDim}`}
              style={{ cursor: 'pointer', border: 'none' }}
              onClick={() => setConfirm(false)}
            >
              Cancel
            </button>
          </span>
        ) : (
          <button
            type="button"
            className={`${styles.badge} ${styles.badgeDim}`}
            style={{ cursor: 'pointer', border: 'none' }}
            aria-label={`Reset progress for ${child.name}`}
            onClick={() => setConfirm(true)}
          >
            Reset progress
          </button>
        )}
      </div>

      {child.skills.length === 0 ? (
        <p style={{ fontSize: 12, color: 'var(--text-dim)', margin: '4px 0 0' }}>
          No games played yet.
        </p>
      ) : (
        <table style={{ width: '100%', fontSize: 12, marginTop: 6 }}>
          <thead>
            <tr style={{ color: 'var(--text-dim)', textAlign: 'left' }}>
              <th>Skill</th>
              <th>Now at</th>
              <th>Last games</th>
              <th>Trend</th>
              <th title="Share of answers checked by code (not by the language model)">Checked</th>
              <th>Missed most</th>
            </tr>
          </thead>
          <tbody>
            {child.skills.map((s) => (
              <SkillRow key={s.skill} skill={s} gradeName={gradeName} />
            ))}
          </tbody>
        </table>
      )}
    </div>
  )
}

function SkillRow({ skill, gradeName }: { skill: LearningSkill; gradeName: (g: Grade) => string }) {
  return (
    <tr>
      <td>
        {SKILL_LABEL[skill.skill] ?? skill.skill}
        {skill.confident && (
          <span className={`${styles.badge} ${styles.badgeGreen}`} style={{ marginLeft: 4 }}>
            confident
          </span>
        )}
      </td>
      <td>
        {gradeName(skill.step)}
        {skill.mastered.length > 0 && (
          <span style={{ color: 'var(--text-dim)' }}>
            {' '}
            (mastered {skill.mastered.map(gradeName).join(', ')})
          </span>
        )}
      </td>
      <td>
        {skill.games.length === 0
          ? '—'
          : skill.games
              .slice(-5)
              .map((g) => `${g.right}/${g.of}`)
              .join(' · ')}
      </td>
      <td>{pct(skill.trend)}</td>
      <td>{pct(skill.code_share)}</td>
      <td style={{ color: 'var(--text-dim)' }}>{skill.missed_most.join('; ') || '—'}</td>
    </tr>
  )
}
