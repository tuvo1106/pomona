/** How a metric's unit is written for a reader, in one place.
 *
 * HealthKit's units are storage units, not display ones: they include placeholders for
 * "this has no unit" (`count`, `events`), spell beats-per-minute as `count/min`, and write
 * sound level as `dBASPL`. Printing them raw is how a chart ends up titled "Steps (count)".
 *
 * This is also where a bucket becomes part of the unit. A summed series shows a *total per
 * bucket*, so on a week bucket "75,000 steps" is a week's worth -- without the `/wk` the
 * number reads as an impossible day. Averaged series never take the suffix: an average over
 * a week is still an average, not a rate.
 */

import type { Bucket } from '@/lib/timeRange'

/* These are all Maps and Sets rather than object literals because every key looked up here
 * comes from the export: `unit` and `type` are read straight out of `export.xml`. An object
 * literal resolves inherited keys, so a record whose unit was "constructor" would return a
 * function, which then reaches React as a child and takes the page down. */

/** HealthKit's placeholders for "no unit". Hidden rather than printed: a chart titled
 * "Stand hours · events" is worse than one with no unit at all.
 */
const PSEUDO_UNITS = new Set(['count', 'events'])

/** Raw unit -> how it's written, for units that mean the same thing on every metric. */
const UNIT_DISPLAY = new Map([
  ['dBASPL', 'dB'],
  ['degF', '°F'],
  ['degC', '°C'],
])

/** Where the raw unit is a placeholder but the series still counts something nameable, so
 * the reader gets "steps/wk" rather than a bare "per wk".
 */
const COUNT_NOUNS = new Map([
  ['HKQuantityTypeIdentifierStepCount', 'steps'],
  ['HKQuantityTypeIdentifierFlightsClimbed', 'flights'],
])

/** `count/min` doesn't name a quantity by itself -- it's beats per minute on a heart
 * metric, breaths on respiratory rate, revolutions on a cycling cadence sensor. So it's
 * resolved per type rather than mapped globally, and a type that isn't listed keeps the raw
 * `count/min`: unhelpful, but it can't state the wrong quantity, which is the failure that
 * matters. Add a type here rather than widening this to a blanket "bpm".
 */
const PER_MINUTE_RAW = 'count/min'
const PER_MINUTE_UNITS = new Map([
  ['HKQuantityTypeIdentifierHeartRate', 'bpm'],
  ['HKQuantityTypeIdentifierRestingHeartRate', 'bpm'],
  ['HKQuantityTypeIdentifierWalkingHeartRateAverage', 'bpm'],
  ['HKQuantityTypeIdentifierHeartRateRecoveryOneMinute', 'bpm'],
  ['HKQuantityTypeIdentifierRespiratoryRate', 'breaths/min'],
])

/** Appended to a summed series' unit. Short forms: these sit in a card title beside the
 * metric name, where "per week" would crowd out the name itself.
 */
const BUCKET_SUFFIX: Record<Bucket, string> = {
  day: '',
  week: '/wk',
  month: '/mo',
}

/** Said in full where there is no unit noun to hang the suffix off ("Stand hours · per
 * week"), since a bare "/wk" reads as a unit with a missing numerator.
 */
const BARE_BUCKET_LABEL: Record<Bucket, string> = {
  day: '',
  week: 'per week',
  month: 'per month',
}

export interface UnitContext {
  /** The HealthKit type, for units whose meaning depends on it (see PER_MINUTE_UNITS and
   * COUNT_NOUNS above).
   */
  type?: string | null
  /** The unit as the API reports it. */
  unit?: string | null
  /** How the series is aggregated into each bucket. Only 'sum' takes a bucket suffix. */
  mode?: 'sum' | 'avg' | null
  /** Omit outside a bucketed series (a list of metric types, a stat card): no suffix. */
  bucket?: Bucket | null
}

/** The unit as it should be shown, or null when the metric has none worth printing. */
export function displayUnit({ type, unit, mode, bucket }: UnitContext): string | null {
  const base = baseUnit(type, unit)
  if (mode !== 'sum' || !bucket || bucket === 'day') return base
  return base ? `${base}${BUCKET_SUFFIX[bucket]}` : BARE_BUCKET_LABEL[bucket] || null
}

function baseUnit(type: string | null | undefined, unit: string | null | undefined): string | null {
  if (unit == null || unit === '') return null
  if (unit === PER_MINUTE_RAW) return (type && PER_MINUTE_UNITS.get(type)) ?? unit
  if (PSEUDO_UNITS.has(unit)) return (type && COUNT_NOUNS.get(type)) ?? null
  return UNIT_DISPLAY.get(unit) ?? unit
}

/** The table twin's value-column header, e.g. "Value (steps/wk)". Kept here so the column
 * and the card title can never disagree about what the numbers are measured in.
 */
export function valueColumnHeader(ctx: UnitContext): string {
  const unit = displayUnit(ctx)
  return unit ? `Value (${unit})` : 'Value'
}
