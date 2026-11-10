import { useState } from 'react'
import {
  type MemberKind,
  useAddMember,
  useForgetEveryone,
  useHousehold,
  useRemoveMember,
  useSetHouseholdEnabled,
} from '../hooks/useHousehold'
import styles from '../styles/global.module.css'
import m from '../styles/monitor.module.css'

const KIND_LABEL: Record<MemberKind, string> = { kid: 'Child', adult: 'Adult', animal: 'Pet' }

/** Parent-managed household roster: enrol, see, delete. Robot-local, off by default. */
export function HouseholdPanel() {
  const { data, error } = useHousehold()
  const setEnabled = useSetHouseholdEnabled()
  const add = useAddMember()
  const remove = useRemoveMember()
  const forget = useForgetEveryone()
  const [confirmForget, setConfirmForget] = useState(false)
  const [name, setName] = useState('')
  const [kind, setKind] = useState<MemberKind>('kid')
  const [age, setAge] = useState('')

  const failure = (error ?? setEnabled.error ?? add.error ?? remove.error ?? forget.error) as
    | Error
    | null
    | undefined

  const submit = (e: React.FormEvent) => {
    e.preventDefault()
    add.mutate(
      { name, kind, ...(kind !== 'animal' && age !== '' ? { age: Number(age) } : {}) },
      {
        onSuccess: () => {
          setName('')
          setAge('')
        },
      },
    )
  }

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
          Household
        </h3>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <label style={{ display: 'flex', alignItems: 'center', gap: 4, fontSize: 12 }}>
            <input
              type="checkbox"
              checked={data?.enabled ?? false}
              disabled={!data}
              onChange={(e) => setEnabled.mutate(e.target.checked)}
            />
            Use roster
          </label>
          {confirmForget ? (
            <div style={{ display: 'flex', gap: 4 }}>
              <button
                type="button"
                className={`${styles.badge} ${styles.badgeRed}`}
                style={{ cursor: 'pointer', border: 'none' }}
                onClick={() => {
                  forget.mutate(undefined)
                  setConfirmForget(false)
                }}
              >
                Confirm
              </button>
              <button
                type="button"
                className={`${styles.badge} ${styles.badgeDim}`}
                style={{ cursor: 'pointer', border: 'none' }}
                onClick={() => setConfirmForget(false)}
              >
                Cancel
              </button>
            </div>
          ) : (
            <button
              type="button"
              className={`${styles.badge} ${styles.badgeRed}`}
              style={{ cursor: 'pointer', border: 'none' }}
              onClick={() => setConfirmForget(true)}
            >
              Forget everyone
            </button>
          )}
        </div>
      </div>

      <p style={{ color: 'var(--text-dim)', fontSize: 12, margin: '0 0 8px' }}>
        Stored only on this robot. With the roster on, Buddy speaks to anyone it does not recognise
        as it would to the youngest child listed. Only that age is sent to the conversation server;
        names stay here.
      </p>

      {failure && (
        <div role="alert" style={{ color: 'var(--red, #f44336)', fontSize: 12, marginBottom: 8 }}>
          {failure.message}
        </div>
      )}

      {data && data.members.length > 0 && (
        <table style={{ width: '100%', fontSize: 13, marginBottom: 8 }}>
          <tbody>
            {data.members.map((mem) => (
              <tr key={mem.id}>
                <td>{mem.name}</td>
                <td style={{ color: 'var(--text-dim)' }}>
                  {KIND_LABEL[mem.kind]}
                  {mem.age !== undefined ? `, ${mem.age}` : ''}
                </td>
                <td style={{ textAlign: 'right' }}>
                  <button
                    type="button"
                    className={`${styles.badge} ${styles.badgeDim}`}
                    style={{ cursor: 'pointer', border: 'none' }}
                    aria-label={`Remove ${mem.name}`}
                    onClick={() => remove.mutate(mem.id)}
                  >
                    Remove
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      <form onSubmit={submit} style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
        <input
          aria-label="Name"
          placeholder="Name"
          maxLength={40}
          value={name}
          onChange={(e) => setName(e.target.value)}
          required
        />
        <select
          aria-label="Kind"
          value={kind}
          onChange={(e) => setKind(e.target.value as MemberKind)}
        >
          <option value="kid">Child</option>
          <option value="adult">Adult</option>
          <option value="animal">Pet</option>
        </select>
        {kind !== 'animal' && (
          <input
            aria-label="Age"
            placeholder={kind === 'kid' ? 'Age' : 'Age (optional)'}
            type="number"
            min={kind === 'kid' ? 1 : 18}
            max={kind === 'kid' ? 17 : 120}
            style={{ width: 90 }}
            value={age}
            onChange={(e) => setAge(e.target.value)}
            required={kind === 'kid'}
          />
        )}
        <button type="submit" disabled={add.isPending}>
          Add
        </button>
      </form>
    </div>
  )
}
