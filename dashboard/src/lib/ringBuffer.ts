/**
 * Fixed-size circular buffer backed by Float64Array.
 * Zero GC pressure during 20 Hz telemetry ingestion.
 */
export class RingBuffer {
  private readonly buf: Float64Array
  private readonly timestamps: Float64Array
  private head = 0 // next write index
  private count = 0 // number of valid samples

  constructor(readonly capacity: number) {
    this.buf = new Float64Array(capacity)
    this.timestamps = new Float64Array(capacity)
  }

  push(value: number, timestamp: number): void {
    this.buf[this.head] = value
    this.timestamps[this.head] = timestamp
    this.head = (this.head + 1) % this.capacity
    if (this.count < this.capacity) this.count++
  }

  /** Number of valid samples. */
  get length(): number {
    return this.count
  }

  /** Most recent value, or 0 if empty. */
  last(): number {
    if (this.count === 0) return 0
    const idx = (this.head - 1 + this.capacity) % this.capacity
    return this.buf[idx]
  }

  /**
   * Copy valid samples into output arrays (oldest first).
   * Returns the number of samples copied.
   * Callers should pre-allocate and reuse the output arrays.
   */
  copyTo(outValues: Float64Array, outTimestamps: Float64Array): number {
    const n = this.count
    if (n === 0) return 0
    const start = (this.head - n + this.capacity) % this.capacity
    for (let i = 0; i < n; i++) {
      const idx = (start + i) % this.capacity
      outValues[i] = this.buf[idx]
      outTimestamps[i] = this.timestamps[idx]
    }
    return n
  }

  /**
   * Return a snapshot as plain number arrays (allocates — use for initial chart render or infrequent reads).
   */
  toArrays(): { values: number[]; timestamps: number[] } {
    const n = this.count
    const values: number[] = new Array(n)
    const ts: number[] = new Array(n)
    const start = (this.head - n + this.capacity) % this.capacity
    for (let i = 0; i < n; i++) {
      const idx = (start + i) % this.capacity
      values[i] = this.buf[idx]
      ts[i] = this.timestamps[idx]
    }
    return { values, timestamps: ts }
  }

  clear(): void {
    this.head = 0
    this.count = 0
  }
}
