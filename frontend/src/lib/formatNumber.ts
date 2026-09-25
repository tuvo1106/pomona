/** Rounds to at most 2 decimal places, dropping trailing zeros (115.0 -> 115, 33.333... -> 33.33). */
export function round2(value: number): number {
  return Math.round(value * 100) / 100
}

/** For chart axis ticks / tooltips, where raw floating-point averages otherwise render as
 * long trails like 33.333333333333336. Thousands-comma'd per dataviz convention.
 */
export function formatAxisNumber(value: unknown): string {
  if (typeof value !== 'number' || !Number.isFinite(value)) return ''
  return round2(value).toLocaleString('en-US')
}
