/** Shared recharts styling constants so the four chart components (MetricChart,
 * BloodPressureChart, SleepChart, CategoryMetricChart) don't each hand-roll an identical
 * axis/style block.
 */

import { formatAxisNumber } from '@/lib/formatNumber'

export const CHART_AXIS_TICK = { fontSize: 11 }
export const CHART_AXIS_STROKE = 'var(--muted-foreground)'

/** Spread onto `<CartesianGrid>` in every time-series chart.
 *
 * Horizontal guides only: the vertical ladder duplicates the X axis ticks and, across the
 * ~40 small cards on this dashboard, boxes every series into a cage louder than the data.
 * The remaining lines stay *solid* hairlines rather than dashed -- dashing is noisier, not
 * lighter, and in these charts it already means something specific: a dashed segment is a
 * partial bucket (see lib/partialBuckets.ts). Keeping the grid solid leaves that signal
 * unambiguous.
 */
export const CHART_GRID_PROPS = { className: 'stroke-border', vertical: false }

/** Spread onto the date `<XAxis>` in every time-series chart (not ECG, whose X axis is
 * seconds, not dates).
 *
 * `axisLine`/`tickLine` off: with horizontal gridlines the baseline is already implied, and
 * the tick stubs only add ink. `stroke` still sets the tick *text* color (recharts fills
 * tick labels with it), so the labels stay muted.
 */
export const CHART_X_AXIS_PROPS = {
  dataKey: 'date',
  tick: CHART_AXIS_TICK,
  minTickGap: 24,
  stroke: CHART_AXIS_STROKE,
  axisLine: false,
  tickLine: false,
}

/** Spread onto the value `<YAxis>`; each chart still sets its own `width`/`domain`. */
export const CHART_Y_AXIS_PROPS = {
  tick: CHART_AXIS_TICK,
  stroke: CHART_AXIS_STROKE,
  tickFormatter: formatAxisNumber,
  axisLine: false,
  tickLine: false,
}

/** Top stop of the gradient wash under a single-series line (fading to fully transparent at
 * the baseline). A wash, not a block: avg-mode charts zoom their Y axis to the data
 * (`fluctuationDomain`), so a solid fill would read as area-from-zero and overstate the
 * values. Fading out well before the axis keeps it a depth cue for the line.
 */
export const CHART_AREA_FILL_OPACITY = 0.18

/** recharts' default draw-in animation (~1500ms) makes a chart look like it's still loading
 * well after its data has actually arrived, which is especially noticeable when several
 * independent cards resolve their queries at slightly different times. A short duration keeps
 * a touch of polish without that "still loading" impression.
 *
 * Only the duration is set here, never `isAnimationActive`. recharts defaults it to `'auto'`,
 * which it resolves as `!isSsr && !prefersReducedMotion` (`animation/JavascriptAnimate.js`),
 * so a reader who asks their system for less motion already gets no draw-in at all. Passing
 * a boolean would *replace* that and hand us the job of re-deriving it -- which is a
 * subscription per series for an answer the library already has.
 */
export const CHART_ANIMATION_DURATION = 300

/** Caps bar thickness so a chart with few buckets (e.g. 12 monthly bars in a wide card)
 * doesn't balloon into a thick block -- dataviz mark spec is <=24px.
 */
export const CHART_MAX_BAR_SIZE = 24

/** Top corners rounded, square at the baseline -- bars always grow up from a zero baseline
 * in this app, so only the top two corners take the radius.
 */
export const CHART_BAR_RADIUS: [number, number, number, number] = [4, 4, 0, 0]

/** Zooms a line chart's Y axis to the data's actual fluctuation instead of recharts'
 * default zero-anchored domain. A zero baseline flattens physiological metrics (heart
 * rate, weight, HRV, blood pressure, ...) that never naturally approach zero into a thin
 * band near the top of the chart, hiding the day-to-day variation that's the whole point
 * of looking at a trend line. Only use this for avg-mode (rate / point-in-time) metrics --
 * cumulative sum-mode metrics (steps, energy, ...) must keep the zero baseline, since zero
 * is a real, meaningful value for them and truncating it would misrepresent magnitude,
 * same as it would for a bar chart.
 */
export function fluctuationDomain([dataMin, dataMax]: readonly [number, number]): [
  number,
  number,
] {
  if (!Number.isFinite(dataMin) || !Number.isFinite(dataMax)) {
    return [dataMin, dataMax]
  }
  const range = dataMax - dataMin
  const pad = range > 0 ? range * 0.15 : Math.max(Math.abs(dataMax) * 0.1, 1)
  return [dataMin - pad, dataMax + pad]
}
