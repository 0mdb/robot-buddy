import { useState } from 'react'
import {
  type MemberKind,
  useAddMember,
  useEnrollFace,
  useForgetEveryone,
  useForgetFace,
  useHousehold,
  useHouseholdFaces,
  useRemoveMember,
  useSetHouseholdEnabled,
} from '../hooks/useHousehold'
import { useTelemetry } from '../hooks/useTelemetry'
import styles from '../styles/global.module.css'
import m from '../styles/monitor.module.css'
import type { TelemetryPayload } from '../types'

const KIND_LABEL: Record<MemberKind, string> = { kid: 'Child', adult: 'Adult', animal: 'Pet' }

/** Parent-managed household roster: enrol, see, delete. Robot-local, off by default. */
export function HouseholdPanel() {
  const { data, error } = useHousehold()
  const setEnabled = useSetHouseholdEnabled()
  const add = useAddMember()
  const remove = useRemoveMember()
  const forget = useForgetEveryone()
  const faces = useHouseholdFaces()
  const enroll = useEnrollFace()
  const forgetFace = useForgetFace()
  // Whose face is being captured (the request runs up to ~25 s), and the last outcome.
  const [capturing, setCapturing] = useState<string | null>(null)
  const [faceNote, setFaceNote] = useState<{ id: string; ok: boolean; text: string } | null>(null)
  // Live camera beside the list, to line up a face before pressing "Add face".
  const [showCamera, setShowCamera] = useState(false)

  const captureFace = (id: string) => {
    setCapturing(id)
    setFaceNote(null)
    enroll.mutate(id, {
      onSuccess: (r) =>
        setFaceNote({ id, ok: true, text: `Face saved (${r.samples ?? 0} samples)` }),
      onError: (e) => setFaceNote({ id, ok: false, text: (e as Error).message }),
      onSettled: () => setCapturing(null),
    })
  }
  const [confirmForget, setConfirmForget] = useState(false)
  const [name, setName] = useState('')
  const [kind, setKind] = useState<MemberKind>('kid')
  const [age, setAge] = useState('')
  const [species, setSpecies] = useState('')

  const failure = (error ?? setEnabled.error ?? add.error ?? remove.error ?? forget.error) as
    | Error
    | null
    | undefined

  const submit = (e: React.FormEvent) => {
    e.preventDefault()
    add.mutate(
      {
        name,
        kind,
        ...(kind !== 'animal' && age !== '' ? { age: Number(age) } : {}),
        ...(kind === 'animal' && species.trim() !== '' ? { species: species.trim() } : {}),
      },
      {
        onSuccess: () => {
          setName('')
          setAge('')
          setSpecies('')
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
        Stored on this robot. With the roster on, Buddy knows who lives here and speaks to anyone it
        does not recognise as it would to the oldest child listed. Names go to Buddy&apos;s own
        conversation server on your network, never to outside services. Faces let Buddy recognise
        people (and use adult speed limits near adults); face prints stay on the robot and are
        deleted with the person.
      </p>

      {failure && (
        <div role="alert" style={{ color: 'var(--red, #f44336)', fontSize: 12, marginBottom: 8 }}>
          {failure.message}
        </div>
      )}

      <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap', alignItems: 'flex-start' }}>
        <div style={{ flex: '1 1 280px', minWidth: 0 }}>
          {data?.members.some((x) => x.kind !== 'animal') && (
            <button
              type="button"
              className={`${styles.badge} ${showCamera ? styles.badgeGreen : styles.badgeDim}`}
              style={{ cursor: 'pointer', border: 'none', marginBottom: 6 }}
              aria-pressed={showCamera}
              onClick={() => setShowCamera((v) => !v)}
            >
              {showCamera ? 'Hide camera' : 'Show camera'}
            </button>
          )}
          {data && data.members.length > 0 && (
            <table style={{ width: '100%', fontSize: 13, marginBottom: 8 }}>
              <tbody>
                {data.members.map((mem) => (
                  <tr key={mem.id}>
                    <td>{mem.name}</td>
                    <td style={{ color: 'var(--text-dim)' }}>
                      {mem.species ?? KIND_LABEL[mem.kind]}
                      {mem.age !== undefined ? `, ${mem.age}` : ''}
                    </td>
                    <td style={{ textAlign: 'right', whiteSpace: 'nowrap' }}>
                      {mem.kind !== 'animal' && (
                        <FaceControls
                          name={mem.name}
                          samples={faces.data?.samples?.[mem.id] ?? 0}
                          busy={capturing !== null}
                          capturingThis={capturing === mem.id}
                          onCapture={() => captureFace(mem.id)}
                          onForget={() => {
                            setFaceNote(null)
                            forgetFace.mutate(mem.id)
                          }}
                        />
                      )}{' '}
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

          {capturing !== null && (
            <div style={{ marginBottom: 8 }}>
              <p style={{ fontSize: 12, margin: '0 0 4px' }}>
                Capturing {data?.members.find((x) => x.id === capturing)?.name ?? ''}&apos;s face:
                stand alone in front of Buddy, within about 2 m, and turn your head slowly a little
                left, right, up and down. Takes a few seconds. Adding more later, in other spots and
                light, helps most.
              </p>
            </div>
          )}

          {faceNote && (
            <output
              style={{
                display: 'block',
                fontSize: 12,
                marginBottom: 8,
                color: faceNote.ok ? 'var(--green, #4caf50)' : 'var(--red, #f44336)',
              }}
            >
              {data?.members.find((x) => x.id === faceNote.id)?.name}: {faceNote.text}
            </output>
          )}
        </div>
        {(showCamera || capturing !== null) && <CameraPreview />}
      </div>

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
        {kind === 'animal' && (
          <input
            aria-label="Pet type"
            placeholder="Type (cat, dog...)"
            maxLength={20}
            style={{ width: 130 }}
            value={species}
            onChange={(e) => setSpecies(e.target.value)}
          />
        )}
        <button type="submit" disabled={add.isPending}>
          Add
        </button>
      </form>
    </div>
  )
}

/** Face status and actions for one person: "Add face" / "Add more" (samples accumulate, up to 20), "Forget face". */
function FaceControls(props: {
  name: string
  samples: number
  busy: boolean
  capturingThis: boolean
  onCapture: () => void
  onForget: () => void
}) {
  const { name, samples, busy, capturingThis, onCapture, onForget } = props
  return (
    <>
      <span
        className={`${styles.badge} ${samples > 0 ? styles.badgeGreen : styles.badgeDim}`}
        title={samples > 0 ? `${samples} face samples stored` : 'No face stored'}
      >
        {samples > 0 ? 'Face ✓' : 'No face'}
      </span>{' '}
      <button
        type="button"
        className={`${styles.badge} ${styles.badgeDim}`}
        style={{ cursor: busy ? 'default' : 'pointer', border: 'none' }}
        aria-label={`${samples > 0 ? 'Add more face samples' : 'Add face'} for ${name}`}
        disabled={busy}
        onClick={onCapture}
      >
        {capturingThis ? 'Capturing…' : samples > 0 ? 'Add more' : 'Add face'}
      </button>
      {samples > 0 && (
        <>
          {' '}
          <button
            type="button"
            className={`${styles.badge} ${styles.badgeDim}`}
            style={{ cursor: busy ? 'default' : 'pointer', border: 'none' }}
            aria-label={`Forget face for ${name}`}
            disabled={busy}
            onClick={onForget}
          >
            Forget face
          </button>
        </>
      )}
    </>
  )
}

/** The live camera and whether exactly one face is in view (what a capture needs). */
function CameraPreview() {
  const count = useTelemetry((s) => (s.snapshot as TelemetryPayload).face_count, 250)
  const [hint, ok] =
    count === undefined
      ? ['', false]
      : count === 1
        ? ['One face in view: ready', true]
        : count === 0
          ? ['No face seen: step into view, facing Buddy', false]
          : [`${count} faces: only the person being added`, false]
  return (
    <div style={{ flex: '0 1 320px', marginBottom: 8 }}>
      <img
        src="/video"
        alt="Camera view"
        style={{ width: '100%', maxWidth: 320, borderRadius: 4, display: 'block' }}
      />
      {hint && (
        <div
          style={{
            fontSize: 12,
            marginTop: 4,
            color: ok ? 'var(--green, #4caf50)' : 'var(--text-dim)',
          }}
        >
          {hint}
        </div>
      )}
    </div>
  )
}
