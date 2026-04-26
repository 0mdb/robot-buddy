/**
 * Read a value from a nested record by dot-path (e.g. "power.voltage_mv").
 * Returns undefined if any segment is missing or non-traversable.
 *
 * Used so chart series and gauge components can address fields nested under
 * the new `power` telemetry object (and any future nested groups) without
 * a special case in every consumer.
 */
export function getPath(obj: unknown, path: string): unknown {
  if (obj == null) return undefined
  let cur: unknown = obj
  for (const seg of path.split('.')) {
    if (cur == null || typeof cur !== 'object') return undefined
    cur = (cur as Record<string, unknown>)[seg]
  }
  return cur
}
