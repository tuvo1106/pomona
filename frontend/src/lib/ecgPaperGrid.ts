/** Fixed-interval grid coordinates for the ECG chart, so its background is ECG paper rather
 * than a generic chart grid.
 *
 * Clinical ECG paper runs at 25 mm/s and 10 mm/mV. That makes one 1 mm square 0.04 s wide
 * and 0.1 mV tall, with every fifth line heavier at 0.2 s / 0.5 mV -- the intervals are the
 * whole point of the thing, because they're what turns "that spike looks wide" into a QRS
 * duration you can count off in squares. A grid drawn at recharts' own axis ticks can't do
 * that: its spacing is whatever the current domain rounded to, and it changes as the Brush
 * zooms.
 */

export const PAPER_SECONDS_MINOR = 0.04
export const PAPER_SECONDS_MAJOR = 0.2

/** Amplitude intervals in the recording's own unit.
 *
 * Apple exports single-lead ECG samples in µV and `/api/ecg/{id}` passes that unit straight
 * through, so the mV intervals above are converted rather than assumed -- an export that
 * ever arrives in mV would otherwise draw its minor lines 1000x apart and show no grid at
 * all. Anything unrecognised is treated as µV, which is what every Apple Watch export has
 * been.
 */
export function paperAmplitudeSteps(unit: string | null | undefined): {
  minor: number
  major: number
} {
  const perMillivolt = unit != null && /^\s*mv\s*$/i.test(unit) ? 1 : 1000
  return { minor: 0.1 * perMillivolt, major: 0.5 * perMillivolt }
}

/** Below this many pixels apart, a mesh stops being a mesh: the lines close up into a solid
 * wash and the trace ends up sitting on a block of colour. Dropping that weight entirely is
 * better than drawing it -- the heavier lines are still there to measure against, and they
 * are five times further apart.
 *
 * 3 rather than something safer because of what the number has to clear: printed ECG paper
 * at 96dpi puts its 1 mm lines 3.78px apart, and the default 10 s window across a desktop
 * panel lands just under that. A higher floor drops the fine mesh exactly where the chart
 * is closest to real paper, which is the one place it's most worth having.
 */
const MIN_LINE_SPACING = 3

/** At most this many labelled ticks down the Y axis before they start being thinned to
 * every second major line, every third, and so on. A noisy recording can span twenty
 * millivolt-halves, and twenty numbers down the side is a ladder, not an axis.
 */
const MAX_AMPLITUDE_TICKS = 10

/** A Y domain and tick set that land on the paper's own heavy lines.
 *
 * Two jobs in one pass. The domain is the whole recording's range snapped outward to a
 * major interval and held *fixed*, rather than recharts' default of refitting to whatever
 * the Brush currently shows: an ECG's gain is part of what's being read, and a scale that
 * silently restretched as you scrubbed would draw two beats the same height when one is
 * twice the other. The ticks then sit on major lines, so the numbers name the grid instead
 * of cutting across it at 400 µV intervals while the paper is ruled at 500.
 *
 * Not lib/axisScale.ts, which every other chart uses: that one's job is to *choose* a nice
 * step (1, 2, 2.5 or 5 x 10^n) for the data it's given, and here the step isn't ours to
 * choose -- it's whatever the paper is ruled at, or the numbers stop naming the grid.
 *
 * Returns null for an empty or non-finite series, where the caller should leave the axis
 * to recharts.
 */
export function paperAmplitudeAxis(
  values: readonly number[],
  step: number,
): { domain: [number, number]; ticks: number[] } | null {
  if (values.length === 0 || !(step > 0)) return null

  let min = Infinity
  let max = -Infinity
  for (const value of values) {
    if (!Number.isFinite(value)) continue
    if (value < min) min = value
    if (value > max) max = value
  }
  if (!Number.isFinite(min) || !Number.isFinite(max)) return null

  // Slack as in paperGridCoordinates below: a value sitting exactly on a major line should
  // not open a whole spare square beyond it.
  let low = Math.floor(min / step + 1e-9)
  let high = Math.ceil(max / step - 1e-9)
  // A flat trace (every sample identical, which a disconnected lead gives) snaps to a
  // zero-height domain; open it to one square so there is still a chart to draw.
  if (low === high) {
    low -= 1
    high += 1
  }

  // Thinned ticks start from a multiple of `every`, not from `low`, so the sequence stays
  // anchored at zero the way the mesh itself is. Starting at `low` pins the numbers to an
  // arbitrary offset, and the one they then tend to miss is 0 µV -- the isoelectric
  // baseline, which is the line an ECG is actually read against. (A noisy recording
  // spanning -1800…12400 µV lands on low -4, high 25, every 3, and labels -2000, -500,
  // 1000, … — everything except the baseline.) `every` is 1 in the ordinary case, where
  // this is a no-op.
  const every = Math.max(1, Math.ceil((high - low) / MAX_AMPLITUDE_TICKS))
  const ticks: number[] = []
  for (let i = Math.ceil(low / every) * every; i <= high; i += every) ticks.push(i * step)

  return { domain: [low * step, high * step], ticks }
}

/** The part of recharts' internal axis scale this needs. Declared structurally rather than
 * imported: recharts exports the type only from a deep internal path.
 */
interface GridScale {
  domain(): ReadonlyArray<unknown>
  range(): ReadonlyArray<number>
  map(value: unknown): number | undefined
}

/** Pixel positions for a grid line at every multiple of `step` inside the axis's current
 * domain. Anchored to zero, so the lines stay on the same data values (and the same
 * spacing) as the Brush zooms in and out, which is what makes them measurable.
 *
 * Returns `[]` when the lines would be too dense to read, which also bounds the loop: the
 * spacing check rejects anything finer than one line per MIN_LINE_SPACING pixels, so at
 * most `range width / MIN_LINE_SPACING` lines are ever generated however wide the domain
 * gets.
 *
 * Pass as `verticalCoordinatesGenerator` / `horizontalCoordinatesGenerator` to
 * `<CartesianGrid>`; recharts hands those the live axis, which is why this needs no state
 * of its own to follow the Brush.
 */
export function paperGridCoordinates(scale: GridScale | undefined, step: number): number[] {
  if (!scale || !(step > 0)) return []

  const domain = scale.domain()
  const min = Number(domain[0])
  const max = Number(domain[domain.length - 1])
  const range = scale.range()
  const span = Math.abs(Number(range[range.length - 1]) - Number(range[0]))
  if (!Number.isFinite(min) || !Number.isFinite(max) || max <= min) return []
  if (!Number.isFinite(span) || span <= 0) return []
  if (span / ((max - min) / step) < MIN_LINE_SPACING) return []

  // The 1e-9 slack (the same lib/axisScale.ts uses) keeps a line that sits exactly on the
  // domain edge: neither 0.04 nor 0.2 is exact in binary, so e.g. 0.3 / 0.1 comes out as
  // 2.9999999999999996 and a bare floor() would drop the last line of the mesh.
  const first = Math.ceil(min / step - 1e-9)
  const last = Math.floor(max / step + 1e-9)

  const coordinates: number[] = []
  for (let i = first; i <= last; i += 1) {
    // i * step, not a running total: 0.04 has no exact binary form, and accumulating it
    // across a few hundred lines drifts the whole mesh off the ticks it lines up with.
    const pixel = scale.map(i * step)
    if (pixel != null && Number.isFinite(pixel)) coordinates.push(pixel)
  }
  return coordinates
}
