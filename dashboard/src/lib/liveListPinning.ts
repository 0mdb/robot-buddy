export interface PinEdgeParams {
  scrollTop: number
  clientHeight: number
  scrollHeight: number
  rowHeight: number
  newestFirst: boolean
}

export interface VisiblePrependParams<T> {
  pinned: boolean
  newestFirst: boolean
  versionDelta: number
  entries: readonly T[]
  matches: (entry: T) => boolean
}

export function isAtPinnedEdge({
  scrollTop,
  clientHeight,
  scrollHeight,
  rowHeight,
  newestFirst,
}: PinEdgeParams): boolean {
  if (newestFirst) {
    return scrollTop <= rowHeight
  }
  return scrollTop + clientHeight >= scrollHeight - rowHeight
}

export function countVisiblePrepends<T>({
  pinned,
  newestFirst,
  versionDelta,
  entries,
  matches,
}: VisiblePrependParams<T>): number {
  if (pinned || !newestFirst || versionDelta <= 0 || entries.length === 0) {
    return 0
  }

  const inserted = Math.min(versionDelta, entries.length)
  if (inserted <= 0) {
    return 0
  }

  let visible = 0
  const start = entries.length - inserted
  for (let i = start; i < entries.length; i++) {
    if (matches(entries[i])) {
      visible += 1
    }
  }
  return visible
}
