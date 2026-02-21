import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { List, useListRef } from 'react-window'
import { useLogStore } from '../lib/wsLogs'
import styles from '../styles/global.module.css'
import type { LogEntry } from '../types'

/* ---- constants ---- */

const ROW_HEIGHT = 24
const LEVELS = ['DEBUG', 'INFO', 'WARNING', 'ERROR'] as const
type Level = (typeof LEVELS)[number]

const LEVEL_COLORS: Record<Level, string> = {
  DEBUG: '#666',
  INFO: '#eee',
  WARNING: '#ff9800',
  ERROR: '#f44336',
}

const LEVEL_BG: Record<Level, string> = {
  DEBUG: 'transparent',
  INFO: 'transparent',
  WARNING: 'rgba(255,152,0,0.08)',
  ERROR: 'rgba(244,67,54,0.08)',
}

/* ---- helpers ---- */

function formatTs(ts: number): string {
  const d = new Date(ts * 1000)
  const hh = String(d.getHours()).padStart(2, '0')
  const mm = String(d.getMinutes()).padStart(2, '0')
  const ss = String(d.getSeconds()).padStart(2, '0')
  const ms = String(d.getMilliseconds()).padStart(3, '0')
  return `${hh}:${mm}:${ss}.${ms}`
}

/* ---- row renderer ---- */

interface LogRowProps {
  entries: LogEntry[]
  selectedIndex: number | null
  onSelect: (index: number) => void
}

function LogRow({
  index,
  style,
  entries,
  selectedIndex,
  onSelect,
}: {
  index: number
  style: React.CSSProperties
  ariaAttributes: Record<string, unknown>
} & LogRowProps) {
  const entry = entries[index]
  const level = entry.level.toUpperCase() as Level
  const color = LEVEL_COLORS[level] ?? '#eee'
  const bg = selectedIndex === index ? 'rgba(233,69,96,0.18)' : (LEVEL_BG[level] ?? 'transparent')

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
      <span
        style={{
          color: '#555',
          flexShrink: 0,
          width: 90,
          overflow: 'hidden',
          textOverflow: 'ellipsis',
          whiteSpace: 'nowrap',
        }}
      >
        {formatTs(entry.ts)}
      </span>
      <span
        style={{
          color: '#777',
          flexShrink: 0,
          width: 160,
          overflow: 'hidden',
          textOverflow: 'ellipsis',
          whiteSpace: 'nowrap',
        }}
      >
        {entry.name}
      </span>
      <span
        style={{
          color,
          flex: 1,
          overflow: 'hidden',
          textOverflow: 'ellipsis',
          whiteSpace: 'nowrap',
          minWidth: 0,
        }}
      >
        {entry.msg}
      </span>
    </div>
  )
}

/* ---- main tab ---- */

export default function LogsTab() {
  const entries = useLogStore((s) => s.entries)
  const connected = useLogStore((s) => s.connected)
  const clearStore = useLogStore((s) => s.clear)

  const [enabledLevels, setEnabledLevels] = useState<Set<Level>>(
    () => new Set(['DEBUG', 'INFO', 'WARNING', 'ERROR']),
  )
  const [search, setSearch] = useState('')
  const [pinned, setPinned] = useState(true)
  const [selectedIndex, setSelectedIndex] = useState<number | null>(null)

  const listRef = useListRef(null)
  const containerRef = useRef<HTMLDivElement>(null)

  const filtered = useMemo(() => {
    const searchLower = search.toLowerCase()
    return entries.filter((e) => {
      const lvl = e.level.toUpperCase() as Level
      if (!enabledLevels.has(lvl)) return false
      if (
        search &&
        !e.msg.toLowerCase().includes(searchLower) &&
        !e.name.toLowerCase().includes(searchLower)
      ) {
        return false
      }
      return true
    })
  }, [entries, enabledLevels, search])

  useEffect(() => {
    if (pinned && listRef.current && filtered.length > 0) {
      listRef.current.scrollToRow({ index: filtered.length - 1, align: 'end' })
    }
  }, [filtered.length, pinned, listRef])

  const handleRowsRendered = useCallback(
    (
      _visible: { startIndex: number; stopIndex: number },
      _all: { startIndex: number; stopIndex: number },
    ) => {
      // If user scrolled up manually, un-pin
      if (!pinned) return
      const el = listRef.current?.element
      if (!el) return
      const atBottom = el.scrollTop + el.clientHeight >= el.scrollHeight - ROW_HEIGHT
      if (!atBottom) {
        setPinned(false)
      }
    },
    [pinned, listRef],
  )

  const toggleLevel = (lvl: Level) => {
    setEnabledLevels((prev) => {
      const next = new Set(prev)
      if (next.has(lvl)) next.delete(lvl)
      else next.add(lvl)
      return next
    })
    setSelectedIndex(null)
  }

  const rowProps = useMemo(
    () => ({ entries: filtered, selectedIndex, onSelect: setSelectedIndex }),
    [filtered, selectedIndex],
  )

  const selectedEntry = selectedIndex !== null ? (filtered[selectedIndex] ?? null) : null
  const TOOLBAR_HEIGHT = 40
  const DETAIL_HEIGHT = selectedEntry ? 80 : 0

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%', padding: 12, gap: 0 }}>
      {/* toolbar */}
      <div
        style={{
          height: TOOLBAR_HEIGHT,
          display: 'flex',
          alignItems: 'center',
          gap: 8,
          flexShrink: 0,
          paddingBottom: 8,
        }}
      >
        {LEVELS.map((lvl) => {
          const active = enabledLevels.has(lvl)
          return (
            <button
              type="button"
              key={lvl}
              onClick={() => toggleLevel(lvl)}
              style={{
                padding: '3px 10px',
                fontSize: 11,
                fontWeight: 600,
                fontFamily: 'var(--font-mono)',
                border: `1px solid ${active ? LEVEL_COLORS[lvl] : '#333'}`,
                borderRadius: 4,
                background: active ? `${LEVEL_COLORS[lvl]}22` : '#1a1a2e',
                color: active ? LEVEL_COLORS[lvl] : '#555',
                cursor: 'pointer',
                textTransform: 'uppercase',
              }}
            >
              {lvl}
            </button>
          )
        })}

        <input
          type="text"
          placeholder="Search..."
          value={search}
          onChange={(e) => {
            setSearch(e.target.value)
            setSelectedIndex(null)
          }}
          style={{
            flex: 1,
            maxWidth: 260,
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
            setPinned((p) => !p)
            if (!pinned && listRef.current && filtered.length > 0)
              listRef.current.scrollToRow({ index: filtered.length - 1, align: 'end' })
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

        <span style={{ fontSize: 11, color: '#666', fontFamily: 'var(--font-mono)' }}>
          {filtered.length} / {entries.length}
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
        ref={containerRef}
        className={styles.card}
        style={{ flex: 1, minHeight: 0, padding: 0, overflow: 'hidden' }}
      >
        {filtered.length === 0 ? (
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
            {entries.length === 0 ? 'No log entries yet' : 'No matching entries'}
          </div>
        ) : (
          <List<LogRowProps>
            listRef={listRef}
            rowComponent={LogRow}
            rowCount={filtered.length}
            rowHeight={ROW_HEIGHT}
            rowProps={rowProps}
            overscanCount={20}
            onRowsRendered={handleRowsRendered}
            style={{ height: `calc(100% - ${DETAIL_HEIGHT}px)` }}
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
            marginTop: 8,
            padding: 10,
            overflow: 'auto',
            fontFamily: 'var(--font-mono)',
            fontSize: 12,
          }}
        >
          <div style={{ display: 'flex', gap: 12, marginBottom: 4 }}>
            <span style={{ color: '#555' }}>{formatTs(selectedEntry.ts)}</span>
            <span
              style={{
                color: LEVEL_COLORS[selectedEntry.level.toUpperCase() as Level] ?? '#eee',
                fontWeight: 600,
              }}
            >
              {selectedEntry.level.toUpperCase()}
            </span>
            <span style={{ color: '#777' }}>{selectedEntry.name}</span>
          </div>
          <div style={{ color: '#ddd', whiteSpace: 'pre-wrap', wordBreak: 'break-all' }}>
            {selectedEntry.msg}
          </div>
        </div>
      )}
    </div>
  )
}
