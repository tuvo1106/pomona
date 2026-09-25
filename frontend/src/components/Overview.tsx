import { useQuery } from '@tanstack/react-query'
import { api, type Overview as OverviewData, type OverviewStats } from '@/api/client'
import { Card, CardContent } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'
import { CONTENT_FADE_IN } from '@/lib/transitions'
import { formatFullDate } from '@/lib/formatDate'
import { cn } from '@/lib/utils'
import { parseLocalDate, type DateRange } from '@/lib/timeRange'
import { displayUnit } from '@/lib/units'

/** Which way a change counts as an improvement. 'neutral' where it depends on the person
 * (weight, blood pressure, sleep): the delta is still shown, just never colored good or bad.
 */
type Better = 'up' | 'down' | 'neutral'

interface Formatted {
  value: string
  unit?: string
}

interface MetricSpec {
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

const METRICS: MetricSpec[] = [
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
    formatDelta: (d, s) => `${signed(d, 1)} ${s.avg_weight?.unit ?? ''}`.trim(),
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
    formatDelta: (d, s) => `${signed(d, 0)} ${s.avg_hrv?.unit ?? ''}`.trim(),
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

type Tone = 'good' | 'bad' | 'neutral'

function toneFor(delta: number, better: Better): Tone {
  if (better === 'neutral' || delta === 0) return 'neutral'
  return (delta > 0) === (better === 'up') ? 'good' : 'bad'
}

const TONE_CLASS: Record<Tone, string> = {
  good: 'text-positive',
  bad: 'text-destructive',
  neutral: 'text-muted-foreground',
}

interface DeltaInfo {
  text: string
  tone: Tone
  /** Screen-reader wording for the arrow, which is decorative. */
  direction: 'up' | 'down' | null
}

/** Why a card shows no delta, when it has something to say about it. */
type NoDeltaNote =
  | 'No earlier data to compare'
  | 'Day in progress'
  | 'No data last period'
  | 'Unit changed since last period'
  | 'Not comparable'

function DeltaLine({
  delta,
  previousLabel,
  note,
}: {
  delta: DeltaInfo | null
  previousLabel?: string
  note?: NoDeltaNote
}) {
  // Always rendered, even empty, so cards with and without a comparison stay the same height.
  if (!delta) {
    return <div className="text-muted-foreground mt-1 h-4 text-xs">{note ?? ' '}</div>
  }
  return (
    <div className="mt-1 flex h-4 items-center gap-1 text-xs tabular-nums">
      <span className={cn('font-medium', TONE_CLASS[delta.tone])}>
        {delta.direction && (
          <span aria-hidden>{delta.direction === 'up' ? '▲' : '▼'} </span>
        )}
        {delta.direction && <span className="sr-only">{delta.direction} </span>}
        {delta.text}
      </span>
      {previousLabel && <span className="text-muted-foreground">vs {previousLabel}</span>}
    </div>
  )
}

function StatCard({
  label,
  formatted,
  delta,
  previousLabel,
  note,
  title,
}: {
  label: string
  formatted: Formatted | null
  delta: DeltaInfo | null
  previousLabel?: string
  note?: NoDeltaNote
  title?: string
}) {
  return (
    <Card title={title}>
      <CardContent>
        <div className="text-muted-foreground text-xs font-medium tracking-wide uppercase">
          {label}
        </div>
        <div className="mt-1 flex items-baseline gap-1.5">
          <span className="text-2xl font-semibold tabular-nums">{formatted?.value ?? '—'}</span>
          {formatted?.unit && (
            <span className="text-muted-foreground text-sm">{formatted.unit}</span>
          )}
        </div>
        <DeltaLine delta={delta} previousLabel={previousLabel} note={note} />
      </CardContent>
    </Card>
  )
}

/** Mirrors StatCard's box row for row -- a 16px label, a 32px value line and the 16px delta
 * line, with the same mt-1 between them -- so the card is the same 104px before and after the
 * numbers arrive. Sizing the placeholder blocks alone isn't enough: a `space-y-2` stack of
 * them came to 100px, and four pixels per card is two shifted rows on a wide screen, on every
 * range change rather than only at startup.
 */
function StatCardSkeleton() {
  return (
    <Card>
      <CardContent>
        <div className="flex h-4 items-center">
          <Skeleton className="h-3 w-20" />
        </div>
        <div className="mt-1 flex h-8 items-center">
          <Skeleton className="h-6 w-24" />
        </div>
        <div className="mt-1 flex h-4 items-center">
          <Skeleton className="h-3 w-16" />
        </div>
      </CardContent>
    </Card>
  )
}

/** "prev. 30 days" -- how long the comparison window is, since it always matches the
 * selected range's length but the selector's label ("Last year") doesn't say so in days.
 */
function previousLabelFor(range: { start: string; end: string }): string {
  const days =
    Math.round((parseLocalDate(range.end).getTime() - parseLocalDate(range.start).getTime()) /
      86_400_000) + 1
  return days === 1 ? 'prev. day' : `prev. ${days.toLocaleString('en-US')} days`
}

// 8 cards: 2 columns on narrow screens, 4 from lg -- both divide 8 evenly, so no row ever
// ends in an orphan card.
const GRID_CLASS = 'grid grid-cols-2 gap-4 lg:grid-cols-4'

/** The overview row while it waits. Exported so the dashboard can show the same thing
 * before the range is even anchored: one definition of what this row looks like empty, and
 * one place for its height to stay in step with StatCard.
 */
export function OverviewSkeleton() {
  return (
    <section className={GRID_CLASS}>
      {Array.from({ length: 8 }, (_, i) => (
        <StatCardSkeleton key={i} />
      ))}
    </section>
  )
}

export function Overview({ range }: { range: DateRange }) {
  const { data, isLoading, error } = useQuery({
    queryKey: ['overview', range],
    queryFn: () => api.overview(range),
  })

  if (isLoading) return <OverviewSkeleton />
  if (error) return <div className="text-destructive text-sm">Failed to load overview.</div>
  if (!data) return null

  const previous = data.previous
  const previousRange = data.previous_range
  const previousLabel = previousRange ? previousLabelFor(previousRange) : undefined
  const previousSpan = previousRange
    ? `${formatFullDate(previousRange.start)} – ${formatFullDate(previousRange.end)}`
    : undefined

  const bp = data.avg_blood_pressure
  const prevBp = previous?.avg_blood_pressure
  const bpFormatted =
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
  const bpDelta: DeltaInfo | null =
    systolicDelta != null || diastolicDelta != null
      ? {
          text: `${systolicDelta ?? '—'}/${diastolicDelta ?? '—'}`,
          tone: 'neutral',
          direction: null,
        }
      : null
  const prevBpAny = prevBp && (prevBp.systolic != null || prevBp.diastolic != null)
  const bpNote = !bpFormatted
    ? undefined
    : noteForMissing(data, Boolean(prevBpAny), 'Not comparable')

  return (
    <section className={cn(GRID_CLASS, CONTENT_FADE_IN)}>
      {METRICS.map((metric) => {
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
        const title =
          previousSpan && previous && prior != null
            ? `Previous period (${previousSpan}): ${[
                metric.format(prior, previous).value,
                metric.format(prior, previous).unit,
              ]
                .filter(Boolean)
                .join(' ')}`
            : undefined
        return (
          <StatCard
            key={metric.label}
            label={metric.label}
            formatted={current != null ? metric.format(current, data) : null}
            delta={delta}
            previousLabel={previousLabel}
            note={note}
            title={title}
          />
        )
      })}
      <StatCard
        label="Avg blood pressure"
        formatted={bpFormatted}
        delta={bpDelta}
        previousLabel={previousLabel}
        note={bpNote}
        title={
          previousSpan && prevBpAny
            ? `Previous period (${previousSpan}): ${
                prevBp?.systolic != null ? Math.round(prevBp.systolic) : '—'
              }/${prevBp?.diastolic != null ? Math.round(prevBp.diastolic) : '—'} mmHg`
            : undefined
        }
      />
    </section>
  )
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
