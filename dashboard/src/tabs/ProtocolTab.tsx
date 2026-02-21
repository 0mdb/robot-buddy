import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { List, useListRef } from 'react-window'
import type { CapturedPacket } from '../lib/wsProtocol'
import { useProtocolStore } from '../lib/wsProtocol'
import styles from '../styles/global.module.css'

/* ---- constants ---- */

const ROW_HEIGHT = 24

const DIRECTIONS = ['TX', 'RX'] as const
type Direction = (typeof DIRECTIONS)[number]

const DEVICES = ['reflex', 'face'] as const
type Device = (typeof DEVICES)[number]

const DIR_COLORS: Record<Direction, string> = {
  TX: '#42a5f5',
  RX: '#66bb6a',
}

const DIR_BG: Record<Direction, string> = {
  TX: 'rgba(66,165,245,0.06)',
  RX: 'transparent',
}

const ERROR_TYPES = new Set(['STOP', 'ESTOP'])

/* ---- helpers ---- */

function formatRelativeTs(ms: number, baseMs: number): string {
  const elapsed = Math.max(0, ms - baseMs)
  const totalSec = elapsed / 1000
  const m = String(Math.floor(totalSec / 60)).padStart(2, '0')
  const s = String(Math.floor(totalSec) % 60).padStart(2, '0')
  const frac = String(Math.round((totalSec % 1) * 1000)).padStart(3, '0')
  return `${m}:${s}.${frac}`
}

function compactFields(fields: Record<string, unknown>): string {
  return Object.entries(fields)
    .map(([k, v]) => `${k}=${typeof v === 'object' ? JSON.stringify(v) : String(v)}`)
    .join('  ')
}

/* ---- row renderer ---- */

interface RowProps {
  packets: CapturedPacket[]
  baseTs: number
  selectedIndex: number | null
  onSelect: (index: number) => void
}

function ProtocolRow({
  index,
  style,
  packets,
  baseTs,
  selectedIndex,
  onSelect,
}: {
  index: number
  style: React.CSSProperties
  ariaAttributes: Record<string, unknown>
} & RowProps) {
  const pkt = packets[index]
  const dir = pkt.direction as Direction
  const isError = ERROR_TYPES.has(pkt.type_name)
  const bg =
    selectedIndex === index
      ? 'rgba(233,69,96,0.18)'
      : isError
        ? 'rgba(244,67,54,0.10)'
        : (DIR_BG[dir] ?? 'transparent')

  return (
    <div
      role="option"
      tabIndex={0}
      style={{
        ...style,
        display: 'flex',
        alignItems: 'center',
        gap: 6,
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
      {/* Time */}
      <span style={{ color: '#555', flexShrink: 0, width: 80 }}>
        {formatRelativeTs(pkt.ts_mono_ms, baseTs)}
      </span>
      {/* Direction */}
      <span
        style={{
          color: DIR_COLORS[dir] ?? '#eee',
          fontWeight: 600,
          flexShrink: 0,
          width: 22,
        }}
      >
        {dir}
      </span>
      {/* Device */}
      <span style={{ color: '#777', flexShrink: 0, width: 46 }}>{pkt.device}</span>
      {/* Type */}
      <span
        style={{
          color: isError ? '#f44336' : '#ccc',
          fontWeight: isError ? 700 : 400,
          flexShrink: 0,
          width: 110,
          overflow: 'hidden',
          textOverflow: 'ellipsis',
          whiteSpace: 'nowrap',
        }}
      >
        {pkt.type_name}
      </span>
      {/* Seq */}
      <span style={{ color: '#555', flexShrink: 0, width: 28, textAlign: 'right' }}>{pkt.seq}</span>
      {/* Decoded fields */}
      <span
        style={{
          color: '#999',
          flex: 1,
          overflow: 'hidden',
          textOverflow: 'ellipsis',
          whiteSpace: 'nowrap',
          minWidth: 0,
        }}
      >
        {compactFields(pkt.fields)}
      </span>
      {/* Size */}
      <span style={{ color: '#555', flexShrink: 0, width: 28, textAlign: 'right' }}>
        {pkt.size}
      </span>
    </div>
  )
}

/* ---- main tab ---- */

export default function ProtocolTab() {
  const packets = useProtocolStore((s) => s.packets)
  const connected = useProtocolStore((s) => s.connected)
  const paused = useProtocolStore((s) => s.paused)
  const clearStore = useProtocolStore((s) => s.clear)
  const setPaused = useProtocolStore((s) => s.setPaused)

  const [enabledDirs, setEnabledDirs] = useState<Set<Direction>>(() => new Set(['TX', 'RX']))
  const [enabledDevices, setEnabledDevices] = useState<Set<Device>>(
    () => new Set(['reflex', 'face']),
  )
  const [typeFilter, setTypeFilter] = useState('')
  const [search, setSearch] = useState('')
  const [pinned, setPinned] = useState(true)
  const [selectedIndex, setSelectedIndex] = useState<number | null>(null)

  const listRef = useListRef(null)
  const containerRef = useRef<HTMLDivElement>(null)

  // Base timestamp for relative time display (anchored to first packet)
  const firstTs = packets.length > 0 ? packets[0].ts_mono_ms : 0
  const baseTs = useMemo(() => firstTs, [firstTs])

  const filtered = useMemo(() => {
    const searchLower = search.toLowerCase()
    const typeFilterUpper = typeFilter.toUpperCase()
    return packets.filter((p) => {
      if (!enabledDirs.has(p.direction as Direction)) return false
      if (!enabledDevices.has(p.device as Device)) return false
      if (typeFilterUpper && !p.type_name.toUpperCase().includes(typeFilterUpper)) return false
      if (search) {
        const fieldsStr = compactFields(p.fields).toLowerCase()
        if (!fieldsStr.includes(searchLower) && !p.type_name.toLowerCase().includes(searchLower)) {
          return false
        }
      }
      return true
    })
  }, [packets, enabledDirs, enabledDevices, typeFilter, search])

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

  const toggleDir = (d: Direction) => {
    setEnabledDirs((prev) => {
      const next = new Set(prev)
      if (next.has(d)) next.delete(d)
      else next.add(d)
      return next
    })
    setSelectedIndex(null)
  }

  const toggleDevice = (d: Device) => {
    setEnabledDevices((prev) => {
      const next = new Set(prev)
      if (next.has(d)) next.delete(d)
      else next.add(d)
      return next
    })
    setSelectedIndex(null)
  }

  const rowProps = useMemo(
    () => ({ packets: filtered, baseTs, selectedIndex, onSelect: setSelectedIndex }),
    [filtered, baseTs, selectedIndex],
  )

  const selectedPkt = selectedIndex !== null ? (filtered[selectedIndex] ?? null) : null
  const TOOLBAR_HEIGHT = 40
  const DETAIL_HEIGHT = selectedPkt ? 120 : 0

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%', padding: 12, gap: 0 }}>
      {/* toolbar */}
      <div
        style={{
          height: TOOLBAR_HEIGHT,
          display: 'flex',
          alignItems: 'center',
          gap: 6,
          flexShrink: 0,
          paddingBottom: 8,
          flexWrap: 'wrap',
        }}
      >
        {/* Direction filters */}
        {DIRECTIONS.map((d) => {
          const active = enabledDirs.has(d)
          return (
            <button
              type="button"
              key={d}
              onClick={() => toggleDir(d)}
              style={{
                padding: '3px 8px',
                fontSize: 11,
                fontWeight: 600,
                fontFamily: 'var(--font-mono)',
                border: `1px solid ${active ? DIR_COLORS[d] : '#333'}`,
                borderRadius: 4,
                background: active ? `${DIR_COLORS[d]}22` : '#1a1a2e',
                color: active ? DIR_COLORS[d] : '#555',
                cursor: 'pointer',
              }}
            >
              {d}
            </button>
          )
        })}

        <span style={{ width: 1, height: 18, background: '#333', flexShrink: 0 }} />

        {/* Device filters */}
        {DEVICES.map((d) => {
          const active = enabledDevices.has(d)
          return (
            <button
              type="button"
              key={d}
              onClick={() => toggleDevice(d)}
              style={{
                padding: '3px 8px',
                fontSize: 11,
                fontWeight: 600,
                fontFamily: 'var(--font-mono)',
                border: `1px solid ${active ? '#aaa' : '#333'}`,
                borderRadius: 4,
                background: active ? 'rgba(170,170,170,0.12)' : '#1a1a2e',
                color: active ? '#ccc' : '#555',
                cursor: 'pointer',
                textTransform: 'capitalize',
              }}
            >
              {d}
            </button>
          )
        })}

        <span style={{ width: 1, height: 18, background: '#333', flexShrink: 0 }} />

        {/* Type filter */}
        <input
          type="text"
          placeholder="Type..."
          value={typeFilter}
          onChange={(e) => {
            setTypeFilter(e.target.value)
            setSelectedIndex(null)
          }}
          style={{
            width: 90,
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

        {/* Search */}
        <input
          type="text"
          placeholder="Search fields..."
          value={search}
          onChange={(e) => {
            setSearch(e.target.value)
            setSelectedIndex(null)
          }}
          style={{
            flex: 1,
            maxWidth: 200,
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
            setPaused(!paused)
          }}
          style={{
            padding: '3px 10px',
            fontSize: 11,
            border: `1px solid ${paused ? '#ff9800' : '#333'}`,
            borderRadius: 4,
            background: paused ? 'rgba(255,152,0,0.15)' : '#1a1a2e',
            color: paused ? '#ff9800' : '#888',
            cursor: 'pointer',
          }}
        >
          {paused ? 'Paused' : 'Live'}
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
          {filtered.length} / {packets.length}
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

      {/* column header */}
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: 6,
          padding: '0 8px',
          height: 20,
          fontFamily: 'var(--font-mono)',
          fontSize: 10,
          color: '#555',
          borderBottom: '1px solid #333',
          flexShrink: 0,
        }}
      >
        <span style={{ width: 80 }}>Time</span>
        <span style={{ width: 22 }}>Dir</span>
        <span style={{ width: 46 }}>Dev</span>
        <span style={{ width: 110 }}>Type</span>
        <span style={{ width: 28, textAlign: 'right' }}>Seq</span>
        <span style={{ flex: 1 }}>Fields</span>
        <span style={{ width: 28, textAlign: 'right' }}>B</span>
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
            {packets.length === 0 ? 'No protocol packets captured yet' : 'No matching packets'}
          </div>
        ) : (
          <List<RowProps>
            listRef={listRef}
            rowComponent={ProtocolRow}
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
      {selectedPkt && (
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
          <div style={{ display: 'flex', gap: 12, marginBottom: 6 }}>
            <span style={{ color: '#555' }}>
              {formatRelativeTs(selectedPkt.ts_mono_ms, baseTs)}
            </span>
            <span
              style={{
                color: DIR_COLORS[selectedPkt.direction as Direction] ?? '#eee',
                fontWeight: 600,
              }}
            >
              {selectedPkt.direction}
            </span>
            <span style={{ color: '#777' }}>{selectedPkt.device}</span>
            <span style={{ color: '#ccc', fontWeight: 600 }}>{selectedPkt.type_name}</span>
            <span style={{ color: '#555' }}>
              seq={selectedPkt.seq} size={selectedPkt.size}B
            </span>
          </div>
          <div style={{ color: '#ddd', marginBottom: 6 }}>
            {JSON.stringify(selectedPkt.fields, null, 2)}
          </div>
          <div style={{ color: '#666', wordBreak: 'break-all' }}>
            hex: {selectedPkt.raw_hex.match(/.{1,2}/g)?.join(' ') ?? selectedPkt.raw_hex}
          </div>
        </div>
      )}
    </div>
  )
}
