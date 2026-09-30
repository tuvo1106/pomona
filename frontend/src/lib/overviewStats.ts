import type { Overview as OverviewData, OverviewStats } from '@/api/client'
import { formatFullDate } from '@/lib/formatDate'
import { parseLocalDate } from '@/lib/timeRange'
import { displayUnit } from '@/lib/units'

/** The overview row's numbers, worked out apart from how they're drawn: what each stat card
 * shows as its value, its change on the previous period, the note in place of a change, and
 * the hover title naming the previous period's value. See components/Overview.tsx.
 */

/** Which way a change counts as an improvement. 'neutral' where it depends on the person
 * (weight, blood pressure, sleep): the delta is still shown, just never colored good or bad.
 */
type Better = 'up' | 'down' | 'neutral'

export interface Formatted {
  value: string
  unit?: string
}

export interface MetricSpec {
  label: string
  better: Better
  /** Pulls this card's number out of a stats block (the current period or the previous one). */
  pick: (stats: OverviewStats) => number | null
  format: (value: number, stats: OverviewStats) => Formatted
  /** The change as display text, sign included -- e.g. "+1.2 lb", "−14m". */
  formatDelta: (delta: number, stats: OverviewStats) => string
  /** Rounded changes this small read as "no change" rather than "+0". */
  roundDelta: (delta: number) => number
  /** For stats whose unit comes from the data: two periods logged in different units (lb
   * then kg) can't be subtracted, so the delta is skipped when these differ.
   */
  unit?: (stats: OverviewStats) => string | null | undefined
}

function fixed(value: number, digits: number): string {
  return value.toLocaleString('en-US', {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  })
}

/** "+1.2" / "−1.2" with a real minus sign, so the sign lines up in tabular numerals. */
function signed(value: number, digits: number): string {
  const sign = value > 0 ? '+' : value < 0 ? '−' : ''
  return `${sign}${fixed(Math.abs(value), digits)}`
}

function roundTo(digits: number) {
  const factor = 10 ** digits
  return (value: number) => Math.round(value * factor) / factor
}

function hoursAndMinutes(hours: number): string {
  const minutes = Math.round(hours * 60)
  return `${Math.floor(minutes / 60)}h ${String(minutes % 60).padStart(2, '0')}m`
}

/** Units that arrive with the data (weight in lb or kg, HRV in ms, ...) go through the same
 * display mapping the charts use, so a raw HealthKit spelling can't reach a stat card by the
 * back door. No bucket: every card here is already an average over the whole range.
 */
function withUnit(unit: string | null | undefined): Formatted['unit'] {
  return displayUnit({ unit }) ?? undefined
}

export const METRICS: MetricSpec[] = [
  {
    label: 'Avg daily steps',
    better: 'up',
    pick: (s) => s.avg_daily_steps,
    format: (v) => ({ value: fixed(v, 0), unit: 'steps' }),
    formatDelta: (d) => signed(d, 0),
    roundDelta: roundTo(0),
  },
  {
    label: 'Avg weight',
    better: 'neutral',
    pick: (s) => s.avg_weight?.value ?? null,
    format: (v, s) => ({ value: fixed(v, 1), unit: withUnit(s.avg_weight?.unit) }),
    formatDelta: (d, s) => `${signed(d, 1)} ${withUnit(s.avg_weight?.unit) ?? ''}`.trim(),
    roundDelta: roundTo(1),
    unit: (s) => s.avg_weight?.unit,
  },
  {
    label: 'Avg resting HR',
    better: 'down',
    pick: (s) => s.avg_resting_hr,
    format: (v) => ({ value: fixed(v, 0), unit: 'bpm' }),
    formatDelta: (d) => `${signed(d, 1)} bpm`,
    roundDelta: roundTo(1),
  },
  {
    label: 'Avg HRV',
    better: 'up',
    pick: (s) => s.avg_hrv?.value ?? null,
    format: (v, s) => ({ value: fixed(v, 0), unit: withUnit(s.avg_hrv?.unit) }),
    formatDelta: (d, s) => `${signed(d, 0)} ${withUnit(s.avg_hrv?.unit) ?? ''}`.trim(),
    roundDelta: roundTo(0),
    unit: (s) => s.avg_hrv?.unit,
  },
  {
    label: 'Workouts',
    better: 'up',
    pick: (s) => s.workout_count,
    format: (v) => ({ value: fixed(v, 0) }),
    formatDelta: (d) => signed(d, 0),
    roundDelta: roundTo(0),
  },
  {
    label: 'Avg VO2 max',
    better: 'up',
    pick: (s) => s.avg_vo2_max?.value ?? null,
    format: (v, s) => ({ value: fixed(v, 1), unit: withUnit(s.avg_vo2_max?.unit) }),
    formatDelta: (d) => signed(d, 1),
    roundDelta: roundTo(1),
    unit: (s) => s.avg_vo2_max?.unit,
  },
  {
    label: 'Avg sleep',
    better: 'neutral',
    pick: (s) => s.avg_sleep_hours,
    format: (v) => ({ value: hoursAndMinutes(v), unit: 'per night' }),
    formatDelta: (d) => {
      const minutes = Math.round(d * 60)
      const sign = minutes > 0 ? '+' : '−'
      const abs = Math.abs(minutes)
      return abs < 60 ? `${sign}${abs}m` : `${sign}${Math.floor(abs / 60)}h ${String(abs % 60).padStart(2, '0')}m`
    },
    // Compared in whole minutes, the unit the delta is shown in.
    roundDelta: (d) => Math.round(d * 60) / 60,
  },
]

export type Tone = 'good' | 'bad' | 'neutral'

function toneFor(delta: number, better: Better): Tone {
  if (better === 'neutral' || delta === 0) return 'neutral'
  return (delta > 0) === (better === 'up') ? 'good' : 'bad'
}

export interface DeltaInfo {
  text: string
  tone: Tone
  /** Screen-reader wording for the arrow, which is decorative. */
  direction: 'up' | 'down' | null
}

/** Why a card shows no delta, when it has something to say about it. */
export type NoDeltaNote =
  | 'No earlier data to compare'
  | 'Day in progress'
  | 'No data last period'
  | 'Unit changed since last period'
  | 'Not comparable'

/** "prev. 30 days" -- how long the comparison window is, since it always matches the
 * selected range's length but the selector's label ("Last year") doesn't say so in days.
 */
export function previousLabelFor(range: { start: string; end: string }): string {
  const days =
    Math.round((parseLocalDate(range.end).getTime() - parseLocalDate(range.start).getTime()) /
      86_400_000) + 1
  return days === 1 ? 'prev. day' : `prev. ${days.toLocaleString('en-US')} days`
}

/** What one stat card shows. */
export interface StatCardContent {
  label: string
  formatted: Formatted | null
  delta: DeltaInfo | null
  note?: NoDeltaNote
  title?: string
}

/** "Previous period (Jan 1, 2026 – Jan 30, 2026)", for a card's hover title. */
function previousSpanFor(data: OverviewData): string | undefined {
  const range = data.previous_range
  return range ? `${formatFullDate(range.start)} – ${formatFullDate(range.end)}` : undefined
}

export function metricCard(metric: MetricSpec, data: OverviewData): StatCardContent {
  const previous = data.previous
  const previousSpan = previousSpanFor(data)
  const current = metric.pick(data)
  const prior = previous ? metric.pick(previous) : null
  const unitChanged =
    metric.unit != null &&
    previous != null &&
    prior != null &&
    metric.unit(data) !== metric.unit(previous)
  let delta: DeltaInfo | null = null
  if (current != null && prior != null && !unitChanged) {
    const change = metric.roundDelta(current - prior)
    delta =
      change === 0
        ? { text: 'No change', tone: 'neutral', direction: null }
        : {
            text: metric.formatDelta(change, data),
            tone: toneFor(change, metric.better),
            direction: change > 0 ? 'up' : 'down',
          }
  }
  const note =
    current == null
      ? undefined
      : noteForMissing(data, prior != null, 'Unit changed since last period')
  const priorFormatted = previous && prior != null ? metric.format(prior, previous) : null
  const title =
    previousSpan && priorFormatted
      ? `Previous period (${previousSpan}): ${[priorFormatted.value, priorFormatted.unit]
          .filter(Boolean)
          .join(' ')}`
      : undefined
  return {
    label: metric.label,
    formatted: current != null ? metric.format(current, data) : null,
    delta,
    note,
    title,
  }
}

export function bloodPressureCard(data: OverviewData): StatCardContent {
  const previousSpan = previousSpanFor(data)
  const bp = data.avg_blood_pressure
  const prevBp = data.previous?.avg_blood_pressure
  const formatted =
    bp && (bp.systolic != null || bp.diastolic != null)
      ? {
          value: `${bp.systolic != null ? Math.round(bp.systolic) : '—'}/${
            bp.diastolic != null ? Math.round(bp.diastolic) : '—'
          }`,
          unit: 'mmHg',
        }
      : null
  // Blood pressure is neutral like weight: each side's change is shown on its own, never
  // colored, and a side only one period has reads "—" rather than blanking the whole delta.
  const sideDelta = (now: number | null | undefined, then: number | null | undefined) =>
    now != null && then != null ? signed(Math.round(now) - Math.round(then), 0) : null
  const systolicDelta = sideDelta(bp?.systolic, prevBp?.systolic)
  const diastolicDelta = sideDelta(bp?.diastolic, prevBp?.diastolic)
  const delta: DeltaInfo | null =
    systolicDelta != null || diastolicDelta != null
      ? {
          text: `${systolicDelta ?? '—'}/${diastolicDelta ?? '—'}`,
          tone: 'neutral',
          direction: null,
        }
      : null
  const prevBpAny = prevBp && (prevBp.systolic != null || prevBp.diastolic != null)
  const note = !formatted ? undefined : noteForMissing(data, Boolean(prevBpAny), 'Not comparable')
  const title =
    previousSpan && prevBpAny
      ? `Previous period (${previousSpan}): ${
          prevBp?.systolic != null ? Math.round(prevBp.systolic) : '—'
        }/${prevBp?.diastolic != null ? Math.round(prevBp.diastolic) : '—'} mmHg`
      : undefined
  return { label: 'Avg blood pressure', formatted, delta, note, title }
}

/** The note a card shows when it has a value this period but no delta. Only consulted when
 * there is no delta, so `otherwise` covers the case where both periods have data but still
 * can't be compared (units differ, or blood pressure's sides don't overlap).
 */
function noteForMissing(
  data: OverviewData,
  hasPrior: boolean,
  otherwise: NoDeltaNote,
): NoDeltaNote | undefined {
  // "All time": there is no previous period at all, so say nothing.
  if (!data.previous_range) return undefined
  // The API withholds the comparison when the previous window isn't covered by the data, or
  // this is a single day that's likely still in progress (see /api/overview).
  if (!data.previous) {
    return data.previous_withheld === 'partial_day' ? 'Day in progress' : 'No earlier data to compare'
  }
  if (!hasPrior) return 'No data last period'
  return otherwise
}
