/**
 * Debounce — delays execution until `delayMs` after the last call.
 * Used for param sliders, face controls, etc.
 */
// eslint-disable-next-line @typescript-eslint/no-explicit-any
export function debounce<T extends (...args: any[]) => void>(
  fn: T,
  delayMs: number,
): T & { cancel(): void } {
  let timerId: ReturnType<typeof setTimeout> | null = null

  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const debounced = ((...args: any[]) => {
    if (timerId !== null) clearTimeout(timerId)
    timerId = setTimeout(() => {
      timerId = null
      fn(...args)
    }, delayMs)
  }) as T & { cancel(): void }

  debounced.cancel = () => {
    if (timerId !== null) {
      clearTimeout(timerId)
      timerId = null
    }
  }

  return debounced
}
