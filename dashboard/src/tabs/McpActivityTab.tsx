import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react'
import { List, useListRef } from 'react-window'
import { useMcpDebug } from '../hooks/useMcpDebug'
import { countVisiblePrepends, isAtPinnedEdge } from '../lib/liveListPinning'
import { useMcpStore } from '../lib/wsMcp'
import styles from '../styles/global.module.css'
import type { McpAuditEntry, McpToolStats } from '../types'

/* ---- constants ---- */

const ROW_HEIGHT = 24
const TOOLBAR_HEIGHT = 40
const CARDS_HEIGHT = 88

/* ---- helpers ---- */

function formatWallClockFromMono(tsMono: number): string {
  // ts_mono is process-monotonic seconds (supervisor uses time.monotonic()),
  // so we can't render a wall-clock date. Format as HH:MM:SS.mmm-since-boot
  // to keep the row dense but still readable.
  const totalMs = Math.max(0, Math.floor(tsMono * 1000))
  const ms = totalMs % 1000
  const totalS = Math.floor(totalMs / 1000)
  const s = totalS % 60
  const totalM = Math.floor(totalS / 60)
  const m = totalM % 60
  const h = Math.floor(totalM / 60)
  return `${String(h).padStart(2, '0')}:${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}.${String(ms).padStart(3, '0')}`
}

function medianLatency(entries: McpAuditEntry[], tool: string, window = 20): number | null {
  const latest: number[] = []
  for (let i = entries.length - 1; i >= 0 && latest.length < window; i--) {
    if (entries[i].tool === tool) latest.push(entries[i].latency_ms)
  }
  if (latest.length === 0) return null
  latest.sort((a, b) => a - b)
  const mid = Math.floor(latest.length / 2)
  return latest.length % 2 === 0 ? (latest[mid - 1] + latest[mid]) / 2 : latest[mid]
}

/* ---- metric cards ---- */

interface MetricCardProps {
  tool: string
  stats: McpToolStats
  medianMs: number | null
}

function MetricCard({ tool, stats, medianMs }: MetricCardProps) {
  const ratePct = Math.round(stats.rate * 100)
  const isHealthy = stats.rate >= 0.85
  const badgeClass =
    stats.total === 0 ? styles.badgeDim : isHealthy ? styles.badgeGreen : styles.badgeRed
  const badgeText = stats.total === 0 ? '—' : `${ratePct}%`

  return (
    <div
      className={styles.card}
      style={{
        padding: 10,
        minWidth: 160,
        display: 'flex',
        flexDirection: 'column',
        gap: 4,
      }}
    >
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
        <span
          style={{ fontFamily: 'var(--font-mono)', fontSize: 12, color: '#ddd', fontWeight: 600 }}
        >
          {tool}
        </span>
        <span className={`${styles.badge} ${badgeClass}`}>{badgeText}</span>
      </div>
      <div style={{ display: 'flex', gap: 12, fontSize: 11, color: '#888' }}>
        <span title="total calls">
          n=<span style={{ color: '#ddd' }}>{stats.total}</span>
        </span>
        <span title="failures">
          fail=<span style={{ color: stats.fail > 0 ? '#f44336' : '#ddd' }}>{stats.fail}</span>
        </span>
        <span title="median latency over last 20 calls (client-computed)">
          p50=
          {medianMs !== null ? <span style={{ color: '#ddd' }}>{medianMs.toFixed(1)}ms</span> : '—'}
        </span>
      </div>
    </div>
  )
}

/* ---- row renderer ---- */

interface RowProps {
  entries: McpAuditEntry[]
  selectedIndex: number | null
  onSelect: (index: number) => void
}

function McpRow({
  index,
  style,
  entries,
  selectedIndex,
  onSelect,
}: {
  index: number
  style: React.CSSProperties
  ariaAttributes: Record<string, unknown>
} & RowProps) {
  const entry = entries[index]
  const selected = selectedIndex === index
  const bg = selected ? 'rgba(233,69,96,0.18)' : entry.ok ? 'transparent' : 'rgba(244,67,54,0.08)'
  const statusColor = entry.ok ? '#4caf50' : '#f44336'

  return (
    <div
      role="option"
      tabIndex={0}
      style={{
        ...style,
        display: 'flex',
        alignItems: 'center',
        gap: 8,
        padding: '0 8px',
        cursor: 'pointer',
        background: bg,
        fontFamily: 'var(--font-mono)',
        fontSize: 12,
        lineHeight: `${ROW_HEIGHT}px`,
        borderBottom: '1px solid rgba(255,255,255,0.03)',
      }}
      onClick={() => onSelect(index)}
      onKeyDown={(e) => {
        if (e.key === 'Enter' || e.key === ' ') onSelect(index)
      }}
    >
      <span style={{ color: '#555', flexShrink: 0, width: 100 }}>
        {formatWallClockFromMono(entry.ts_mono)}
      </span>
      <span
        style={{
          color: '#ce93d8',
          flexShrink: 0,
          width: 140,
          overflow: 'hidden',
          textOverflow: 'ellipsis',
          whiteSpace: 'nowrap',
        }}
      >
        {entry.tool}
      </span>
      <span
        style={{
          color: statusColor,
          flexShrink: 0,
          width: 40,
          fontWeight: 600,
          fontSize: 10,
          textTransform: 'uppercase',
        }}
      >
        {entry.ok ? 'ok' : 'fail'}
      </span>
      <span
        style={{
          color: '#888',
          flexShrink: 0,
          width: 64,
          textAlign: 'right',
        }}
      >
        {entry.latency_ms.toFixed(1)}ms
      </span>
      <span
        style={{
          color: entry.ok ? '#ddd' : '#f88',
          flex: 1,
          overflow: 'hidden',
          textOverflow: 'ellipsis',
          whiteSpace: 'nowrap',
          minWidth: 0,
        }}
      >
        {entry.ok ? entry.result_summary || '—' : entry.error || '(unknown error)'}
      </span>
    </div>
  )
}

/* ---- main tab ---- */

export default function McpActivityTab() {
  const entries = useMcpStore((s) => s.entries)
  const version = useMcpStore((s) => s.version)
  const connected = useMcpStore((s) => s.connected)
  const clearStore = useMcpStore((s) => s.clear)

  const { data: debug } = useMcpDebug()

  // Filters
  const [enabledTools, setEnabledTools] = useState<Set<string>>(() => new Set())
  const [search, setSearch] = useState('')
  const [showOk, setShowOk] = useState(true)
  const [showFail, setShowFail] = useState(true)
  const [newestFirst, setNewestFirst] = useState(true)
  const [pinned, setPinned] = useState(true)
  const [selectedIndex, setSelectedIndex] = useState<number | null>(null)

  const listRef = useListRef(null)
  const prevVersionRef = useRef(version)

  // Union of tools we've seen — prefer the server's authoritative list
  // (/debug/mcp success_rate keys) so tools with zero calls still render a
  // chip and a card; fall back to the entries if the hook hasn't loaded yet.
  const knownTools = useMemo(() => {
    const set = new Set<string>()
    if (debug?.success_rate) {
      for (const t of Object.keys(debug.success_rate)) set.add(t)
    }
    for (const e of entries) set.add(e.tool)
    return [...set].sort()
  }, [debug, entries])

  const matchesEntry = useCallback(
    (e: McpAuditEntry): boolean => {
      if (enabledTools.size > 0 && !enabledTools.has(e.tool)) return false
      if (!showOk && e.ok) return false
      if (!showFail && !e.ok) return false
      if (search) {
        const needle = search.toLowerCase()
        const hay =
          `${e.tool} ${e.result_summary} ${e.error} ${JSON.stringify(e.args)}`.toLowerCase()
        if (!hay.includes(needle)) return false
      }
      return true
    },
    [enabledTools, search, showOk, showFail],
  )

  const filtered = useMemo(() => entries.filter(matchesEntry), [entries, matchesEntry])

  useLayoutEffect(() => {
    const prevVersion = prevVersionRef.current
    const versionDelta = version - prevVersion
    prevVersionRef.current = version

    const prependCount = countVisiblePrepends({
      pinned,
      newestFirst,
      versionDelta,
      entries,
      matches: matchesEntry,
    })
    if (prependCount <= 0) return

    const el = listRef.current?.element
    if (!el) return
    el.scrollTop += prependCount * ROW_HEIGHT
  }, [entries, listRef, matchesEntry, newestFirst, pinned, version])

  const displayed = useMemo(
    () => (newestFirst ? [...filtered].reverse() : filtered),
    [filtered, newestFirst],
  )

  useEffect(() => {
    if (!pinned || !listRef.current || displayed.length === 0) return
    if (newestFirst) {
      listRef.current.scrollToRow({ index: 0, align: 'start' })
      return
    }
    listRef.current.scrollToRow({ index: displayed.length - 1, align: 'end' })
  }, [displayed.length, pinned, newestFirst, listRef])

  const handleRowsRendered = useCallback(() => {
    if (!pinned) return
    const el = listRef.current?.element
    if (!el) return
    const atPinned = isAtPinnedEdge({
      scrollTop: el.scrollTop,
      clientHeight: el.clientHeight,
      scrollHeight: el.scrollHeight,
      rowHeight: ROW_HEIGHT,
      newestFirst,
    })
    if (!atPinned) setPinned(false)
  }, [newestFirst, pinned, listRef])

  const snapToPinnedEdge = useCallback(() => {
    if (!listRef.current || displayed.length === 0) return
    if (newestFirst) {
      listRef.current.scrollToRow({ index: 0, align: 'start' })
      return
    }
    listRef.current.scrollToRow({ index: displayed.length - 1, align: 'end' })
  }, [displayed.length, listRef, newestFirst])

  const toggleTool = (tool: string) => {
    setEnabledTools((prev) => {
      const next = new Set(prev)
      if (next.has(tool)) next.delete(tool)
      else next.add(tool)
      return next
    })
    setSelectedIndex(null)
  }

  const rowProps = useMemo(
    () => ({ entries: displayed, selectedIndex, onSelect: setSelectedIndex }),
    [displayed, selectedIndex],
  )

  const selectedEntry = selectedIndex !== null ? (displayed[selectedIndex] ?? null) : null
  const DETAIL_HEIGHT = selectedEntry ? 140 : 0

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%', padding: 12, gap: 8 }}>
      {/* top strip: per-tool metric cards */}
      <div
        style={{
          height: CARDS_HEIGHT,
          flexShrink: 0,
          display: 'flex',
          gap: 8,
          overflowX: 'auto',
          paddingBottom: 4,
        }}
      >
        {knownTools.length === 0 ? (
          <div
            className={styles.card}
            style={{
              flex: 1,
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              color: '#555',
              fontFamily: 'var(--font-mono)',
              fontSize: 12,
            }}
          >
            No MCP tools have been called yet.
          </div>
        ) : (
          knownTools.map((tool) => {
            const stats = debug?.success_rate[tool] ?? { success: 0, fail: 0, total: 0, rate: 0 }
            return (
              <MetricCard
                key={tool}
                tool={tool}
                stats={stats}
                medianMs={medianLatency(entries, tool)}
              />
            )
          })
        )}
      </div>

      {/* toolbar */}
      <div
        style={{
          height: TOOLBAR_HEIGHT,
          display: 'flex',
          alignItems: 'center',
          gap: 8,
          flexShrink: 0,
          flexWrap: 'wrap',
        }}
      >
        {knownTools.map((tool) => {
          const active = enabledTools.size === 0 || enabledTools.has(tool)
          return (
            <button
              type="button"
              key={tool}
              onClick={() => toggleTool(tool)}
              title={
                enabledTools.size === 0
                  ? 'click to filter to this tool only'
                  : active
                    ? 'click to hide this tool'
                    : 'click to show this tool'
              }
              style={{
                padding: '3px 10px',
                fontSize: 11,
                fontWeight: 600,
                fontFamily: 'var(--font-mono)',
                border: `1px solid ${active ? '#ce93d8' : '#333'}`,
                borderRadius: 4,
                background: active ? 'rgba(206,147,216,0.15)' : '#1a1a2e',
                color: active ? '#ce93d8' : '#555',
                cursor: 'pointer',
              }}
            >
              {tool}
            </button>
          )
        })}

        <input
          type="text"
          placeholder="Search args, result, error..."
          value={search}
          onChange={(e) => {
            setSearch(e.target.value)
            setSelectedIndex(null)
          }}
          style={{
            flex: 1,
            maxWidth: 280,
            padding: '4px 8px',
            fontSize: 12,
            fontFamily: 'var(--font-mono)',
            background: '#1a1a2e',
            border: '1px solid #0f3460',
            borderRadius: 4,
            color: '#eee',
            outline: 'none',
          }}
        />

        <button
          type="button"
          onClick={() => {
            setShowOk((v) => !v)
            setSelectedIndex(null)
          }}
          style={{
            padding: '3px 10px',
            fontSize: 11,
            border: `1px solid ${showOk ? '#4caf50' : '#333'}`,
            borderRadius: 4,
            background: showOk ? 'rgba(76,175,80,0.15)' : '#1a1a2e',
            color: showOk ? '#4caf50' : '#555',
            cursor: 'pointer',
          }}
        >
          ok
        </button>

        <button
          type="button"
          onClick={() => {
            setShowFail((v) => !v)
            setSelectedIndex(null)
          }}
          style={{
            padding: '3px 10px',
            fontSize: 11,
            border: `1px solid ${showFail ? '#f44336' : '#333'}`,
            borderRadius: 4,
            background: showFail ? 'rgba(244,67,54,0.15)' : '#1a1a2e',
            color: showFail ? '#f44336' : '#555',
            cursor: 'pointer',
          }}
        >
          fail
        </button>

        <button
          type="button"
          onClick={() => {
            clearStore()
            setSelectedIndex(null)
          }}
          style={{
            padding: '3px 10px',
            fontSize: 11,
            border: '1px solid #333',
            borderRadius: 4,
            background: '#1a1a2e',
            color: '#aaa',
            cursor: 'pointer',
          }}
        >
          Clear
        </button>

        <button
          type="button"
          onClick={() => {
            setNewestFirst((n) => !n)
            setSelectedIndex(null)
          }}
          style={{
            padding: '3px 10px',
            fontSize: 11,
            border: `1px solid ${newestFirst ? '#9c27b0' : '#333'}`,
            borderRadius: 4,
            background: newestFirst ? 'rgba(156,39,176,0.15)' : '#1a1a2e',
            color: newestFirst ? '#ce93d8' : '#888',
            cursor: 'pointer',
          }}
        >
          {newestFirst ? 'Newest' : 'Oldest'}
        </button>

        <button
          type="button"
          onClick={() => {
            setPinned((prev) => {
              const next = !prev
              if (next) snapToPinnedEdge()
              return next
            })
          }}
          style={{
            padding: '3px 10px',
            fontSize: 11,
            border: `1px solid ${pinned ? '#4caf50' : '#333'}`,
            borderRadius: 4,
            background: pinned ? 'rgba(76,175,80,0.15)' : '#1a1a2e',
            color: pinned ? '#4caf50' : '#888',
            cursor: 'pointer',
          }}
        >
          {pinned ? 'Pinned' : 'Unpinned'}
        </button>

        <button
          type="button"
          disabled
          title="Kill switch for active MCP scenes — coming in Phase 2 with play_scene"
          style={{
            padding: '3px 10px',
            fontSize: 11,
            border: '1px solid #333',
            borderRadius: 4,
            background: '#1a1a2e',
            color: '#555',
            cursor: 'not-allowed',
            opacity: 0.5,
          }}
        >
          Pause
        </button>

        <span style={{ fontSize: 11, color: '#666', fontFamily: 'var(--font-mono)' }}>
          {displayed.length} / {entries.length}
        </span>

        <span
          title={connected ? 'WS connected' : 'WS disconnected'}
          style={{
            width: 8,
            height: 8,
            borderRadius: '50%',
            background: connected ? '#4caf50' : '#f44336',
            flexShrink: 0,
          }}
        />
      </div>

      {/* list */}
      <div
        className={styles.card}
        style={{ flex: 1, minHeight: 0, padding: 0, overflow: 'hidden' }}
      >
        {displayed.length === 0 ? (
          <div
            style={{
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              height: '100%',
              color: '#555',
              fontFamily: 'var(--font-mono)',
              fontSize: 13,
            }}
          >
            {entries.length === 0 ? 'No MCP tool calls yet' : 'No matching entries'}
          </div>
        ) : (
          <List<RowProps>
            listRef={listRef}
            rowComponent={McpRow}
            rowCount={displayed.length}
            rowHeight={ROW_HEIGHT}
            rowProps={rowProps}
            overscanCount={20}
            onRowsRendered={handleRowsRendered}
            style={{ height: '100%' }}
          />
        )}
      </div>

      {/* detail panel */}
      {selectedEntry && (
        <div
          className={styles.card}
          style={{
            height: DETAIL_HEIGHT,
            flexShrink: 0,
            padding: 10,
            overflow: 'auto',
            fontFamily: 'var(--font-mono)',
            fontSize: 12,
          }}
        >
          <div style={{ display: 'flex', gap: 12, marginBottom: 6 }}>
            <span style={{ color: '#555' }}>{formatWallClockFromMono(selectedEntry.ts_mono)}</span>
            <span style={{ color: '#ce93d8', fontWeight: 600 }}>{selectedEntry.tool}</span>
            <span
              className={`${styles.badge} ${selectedEntry.ok ? styles.badgeGreen : styles.badgeRed}`}
            >
              {selectedEntry.ok ? 'ok' : 'fail'}
            </span>
            <span style={{ color: '#888' }}>{selectedEntry.latency_ms.toFixed(2)}ms</span>
          </div>
          <div style={{ color: '#aaa', marginBottom: 2 }}>
            args: <span style={{ color: '#ddd' }}>{JSON.stringify(selectedEntry.args)}</span>
          </div>
          {selectedEntry.ok ? (
            <div style={{ color: '#aaa' }}>
              result:{' '}
              <span style={{ color: '#ddd', whiteSpace: 'pre-wrap', wordBreak: 'break-all' }}>
                {selectedEntry.result_summary || '—'}
              </span>
            </div>
          ) : (
            <div style={{ color: '#aaa' }}>
              error:{' '}
              <span style={{ color: '#f88', whiteSpace: 'pre-wrap', wordBreak: 'break-all' }}>
                {selectedEntry.error || '(unknown)'}
              </span>
            </div>
          )}
        </div>
      )}
    </div>
  )
}
