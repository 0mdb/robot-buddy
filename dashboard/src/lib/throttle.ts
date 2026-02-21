/**
 * Throttle that emits at a steady rate while active.
 * Guarantees the final call is always delivered (trailing edge).
 * Used for joystick — ensures {v:0, w:0} on release.
 */
// eslint-disable-next-line @typescript-eslint/no-explicit-any
export function throttle<T extends (...args: any[]) => void>(
  fn: T,
  intervalMs: number,
): T & { flush(): void; cancel(): void } {
  let lastCallTime = 0
  let timerId: ReturnType<typeof setTimeout> | null = null
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  let lastArgs: any[] | null = null

  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const throttled = ((...args: any[]) => {
    lastArgs = args
    const now = performance.now()
    const remaining = intervalMs - (now - lastCallTime)

    if (remaining <= 0) {
      if (timerId !== null) {
        clearTimeout(timerId)
        timerId = null
      }
      lastCallTime = now
      lastArgs = null
      fn(...args)
    } else if (timerId === null) {
      timerId = setTimeout(() => {
        lastCallTime = performance.now()
        timerId = null
        if (lastArgs !== null) {
          const a = lastArgs
          lastArgs = null
          fn(...a)
        }
      }, remaining)
    }
  }) as T & { flush(): void; cancel(): void }

  throttled.flush = () => {
    if (timerId !== null) {
      clearTimeout(timerId)
      timerId = null
    }
    if (lastArgs !== null) {
      const a = lastArgs
      lastArgs = null
      lastCallTime = performance.now()
      fn(...a)
    }
  }

  throttled.cancel = () => {
    if (timerId !== null) {
      clearTimeout(timerId)
      timerId = null
    }
    lastArgs = null
  }

  return throttled
}
