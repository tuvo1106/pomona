/** Y-axis domain + explicit ticks for the time-series charts, so every axis reads in round
 * numbers ("40 / 45 / 50 / 55") instead of whatever recharts derives from raw padded data
 * ("41.37 / 44.37 / 47.37"), and never prints the same label twice after rounding.
 *
 * Computed per series in the chart component (from its points) and handed to <YAxis> as
 * `domain` + `ticks` + `tickFormatter`, which makes recharts render exactly these ticks.
 */

import { fluctuationDomain } from '@/lib/chartStyle'

export interface AxisScale {
  domain: [number, number]
  ticks: number[]
  format: (value: unknown) => string
}

interface AxisScaleOptions {
  /** Anchor the axis at 0 -- bars and cumulative (sum-mode) lines, where zero is a real value
   * and truncating it would misrepresent magnitude. Otherwise the axis zooms to the data's
   * fluctuation (see fluctuationDomain).
   */
  zeroBaseline: boolean
  /** Whole-number series (event counts): ticks are never fractional. */
  integer?: boolean
  /** Target number of intervals between ticks; the result lands within one of this. */
  intervals?: number
}

const INTEGER_STEPS = [1, 2, 5, 10]
const DECIMAL_STEPS = [1, 2, 2.5, 5, 10]

/** Smallest "nice" step (1, 2, 2.5 or 5 x 10^n) that is at least `rawStep`. */
function niceStep(rawStep: number, integer: boolean): number {
  if (!(rawStep > 0)) return 1
  const magnitude = 10 ** Math.floor(Math.log10(rawStep))
  const normalized = rawStep / magnitude
  const candidates = integer && magnitude < 10 ? INTEGER_STEPS : DECIMAL_STEPS
  const nice = candidates.find((c) => normalized <= c + 1e-9) ?? 10
  const step = nice * magnitude
  return integer ? Math.max(1, Math.round(step)) : step
}

/** Fraction digits needed to print multiples of `step` exactly (2.5 -> 1, 0.005 -> 3). */
function decimalsFor(step: number): number {
  for (let d = 0; d <= 6; d++) {
    const scaled = step * 10 ** d
    if (Math.abs(scaled - Math.round(scaled)) < 1e-6) return d
  }
  return 6
}

/** Tick labels whose precision follows the step: a 0.005 step shows 3 decimals, a 5 step
 * none, so adjacent ticks can never round to the same label. Ticks of 10,000 and up switch
 * to compact notation ("100K") so the label fits the fixed-width axis instead of clipping.
 */
function makeFormatter(step: number, maxAbs: number): (value: unknown) => string {
  if (maxAbs >= 10_000) {
    // Intl picks the suffix per value (K below 1M, M below 1B), so one axis can mix K and M
    // ticks. The largest suffix needs the most decimals to keep a step distinct; the same
    // maximumFractionDigits on smaller-suffix ticks only trims trailing zeros.
    const unit = maxAbs >= 1e9 ? 1e9 : maxAbs >= 1e6 ? 1e6 : 1e3
    const digits = decimalsFor(step / unit)
    // A step too fine for a short compact label (a zoomed axis over large values) falls
    // through to plain, full-precision numbers rather than repeating labels.
    if (digits <= 2) {
      const compact = new Intl.NumberFormat('en-US', {
        notation: 'compact',
        minimumFractionDigits: 0,
        maximumFractionDigits: digits,
      })
      return (value) => (typeof value === 'number' ? compact.format(value) : '')
    }
  }
  const digits = decimalsFor(step)
  const plain = new Intl.NumberFormat('en-US', { maximumFractionDigits: digits })
  return (value) => (typeof value === 'number' ? plain.format(value) : '')
}

/** Returns undefined when there is nothing finite to scale -- the caller then falls back to
 * recharts' own axis (the chart shows its empty state anyway).
 */
export function axisScale(
  values: readonly (number | null | undefined)[],
  { zeroBaseline, integer = false, intervals = 4 }: AxisScaleOptions,
): AxisScale | undefined {
  const finite = values.filter((v): v is number => typeof v === 'number' && Number.isFinite(v))
  if (finite.length === 0) return undefined
  const dataMin = Math.min(...finite)
  const dataMax = Math.max(...finite)
  if (zeroBaseline && dataMin === 0 && dataMax === 0) {
    return { domain: [0, 1], ticks: [0, 1], format: makeFormatter(1, 1) }
  }

  let [lo, hi] = zeroBaseline
    ? [Math.min(0, dataMin), dataMax]
    : fluctuationDomain([dataMin, dataMax])
  // Padding below a non-negative series (a percentage near 0%) would put a meaningless
  // negative tick on the axis.
  if (dataMin >= 0 && lo < 0) lo = 0
  if (hi <= lo) hi = lo + 1

  const step = niceStep((hi - lo) / intervals, integer)
  lo = Math.floor(lo / step + 1e-9) * step
  hi = Math.ceil(hi / step - 1e-9) * step
  if (hi <= lo) hi = lo + step

  const digits = decimalsFor(step)
  const ticks: number[] = []
  for (let t = lo; t <= hi + step / 2; t += step) {
    ticks.push(Number(t.toFixed(digits)))
  }
  const maxAbs = Math.max(Math.abs(ticks[0]), Math.abs(ticks[ticks.length - 1]))
  return { domain: [ticks[0], ticks[ticks.length - 1]], ticks, format: makeFormatter(step, maxAbs) }
}
