import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useCallback, useEffect, useState } from 'react'
import { useSend } from '../hooks/useSend'
import { wsManager } from '../lib/wsManager'
import styles from '../styles/global.module.css'

interface GalleryPerson {
  count: number
}

interface GalleryResponse {
  people: Record<string, GalleryPerson>
}

export function FaceEnrollment() {
  const send = useSend()
  const queryClient = useQueryClient()
  const [name, setName] = useState('')
  const [status, setStatus] = useState<{ ok: boolean; message: string } | null>(null)
  const [videoEnabled, setVideoEnabled] = useState(false)
  const [capturing, setCapturing] = useState(false)

  const { data: gallery, isLoading } = useQuery<GalleryResponse>({
    queryKey: ['face-gallery'],
    queryFn: () => fetch('/face/gallery').then((r) => r.json()),
    refetchInterval: 5000,
  })

  const deleteMutation = useMutation({
    mutationFn: (personName: string) =>
      fetch(`/face/gallery/${encodeURIComponent(personName)}`, { method: 'DELETE' }).then((r) =>
        r.json(),
      ),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['face-gallery'] }),
  })

  useEffect(() => {
    const handler = (msg: Record<string, unknown>) => {
      if (msg.type !== 'face.enroll_result') return
      const payload = msg.payload as Record<string, unknown> | undefined
      if (!payload) return
      setCapturing(false)
      if (payload.ok) {
        setStatus({
          ok: true,
          message: `Enrolled "${payload.name}" (${payload.count} photo${(payload.count as number) !== 1 ? 's' : ''})`,
        })
        queryClient.invalidateQueries({ queryKey: ['face-gallery'] })
      } else {
        setStatus({ ok: false, message: (payload.error as string) ?? 'Enrollment failed' })
      }
    }
    wsManager.addListener(handler)
    return () => wsManager.removeListener(handler)
  }, [queryClient])

  const handleCapture = useCallback(() => {
    const trimmed = name.trim()
    if (!trimmed) {
      setStatus({ ok: false, message: 'Enter a name first' })
      return
    }
    setStatus(null)
    setCapturing(true)
    send({ type: 'face.enroll', name: trimmed })
  }, [name, send])

  const people = gallery?.people ?? {}

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      {/* Gallery */}
      <div>
        <h4 style={{ marginBottom: 8 }}>Enrolled Family Members</h4>
        {isLoading && <p style={{ color: '#888' }}>Loading...</p>}
        {Object.keys(people).length === 0 && !isLoading && (
          <p style={{ color: '#888' }}>No one enrolled yet. Capture photos below.</p>
        )}
        {Object.entries(people).map(([personName, info]) => (
          <div
            key={personName}
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: 12,
              padding: '8px 0',
              borderBottom: '1px solid var(--border)',
            }}
          >
            <span style={{ flex: 1, fontWeight: 600 }}>{personName}</span>
            <span style={{ color: 'var(--text-dim)' }}>
              {info.count} photo{info.count !== 1 ? 's' : ''}
            </span>
            <button
              type="button"
              onClick={() => {
                if (confirm(`Delete all photos for "${personName}"?`))
                  deleteMutation.mutate(personName)
              }}
              style={{
                color: 'var(--red)',
                background: 'none',
                border: '1px solid var(--red)',
                borderRadius: 4,
                padding: '4px 8px',
                cursor: 'pointer',
                fontSize: 12,
              }}
            >
              Delete
            </button>
          </div>
        ))}
      </div>

      {/* Enrollment */}
      <div>
        <h4 style={{ marginBottom: 8 }}>Capture New Photo</h4>
        <label style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8 }}>
          <input
            type="checkbox"
            checked={videoEnabled}
            onChange={(e) => setVideoEnabled(e.target.checked)}
          />
          Show camera preview
        </label>

        {videoEnabled && (
          <div style={{ marginBottom: 12 }}>
            <img
              src="/video"
              alt="Camera preview"
              style={{
                width: 360,
                borderRadius: 4,
                border: '1px solid var(--border)',
              }}
            />
          </div>
        )}

        <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
          <input
            type="text"
            placeholder="Name (e.g. Lily)"
            value={name}
            onChange={(e) => setName(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && handleCapture()}
            style={{
              flex: 1,
              padding: '6px 10px',
              borderRadius: 4,
              border: '1px solid var(--border)',
              background: 'var(--bg)',
              color: 'var(--text)',
            }}
          />
          <button
            type="button"
            className={styles.btnPrimary}
            onClick={handleCapture}
            disabled={!name.trim() || capturing}
            style={{ padding: '6px 16px' }}
          >
            {capturing ? 'Capturing...' : 'Capture'}
          </button>
        </div>

        {status && (
          <div
            style={{
              marginTop: 8,
              padding: '8px 12px',
              borderRadius: 4,
              background: status.ok ? 'rgba(76, 175, 80, 0.15)' : 'rgba(244, 67, 54, 0.15)',
              color: status.ok ? 'var(--green)' : 'var(--red)',
              fontSize: 13,
            }}
          >
            {status.message}
          </div>
        )}

        <p style={{ color: 'var(--text-dim)', fontSize: 13, marginTop: 8 }}>
          Position the person in front of the camera. Capture 5–8 photos with different angles and
          expressions for best recognition.
        </p>
      </div>
    </div>
  )
}
