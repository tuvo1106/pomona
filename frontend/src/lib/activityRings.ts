/** Shaping for the daily-activity card: the three rings for one day, and the calendar grid
 * behind them. Kept apart from the components so the goal/fallback rules and the week layout
 * are readable on their own -- they carry most of the card's real logic.
 */

import type { ActivitySummary } from '@/api/client'
import { parseLocalDate } from '@/lib/timeRange'

/** Apple's stock goals, used *only* where a day has no goal of its own stored. The export
 * carries the goal that was actually in force on each day, so a stored goal always wins --
 * someone who set Exercise to 45 min should not be measured against 30.
 *
 * There is deliberately no Move fallback: the Move goal is personal (it has no stock value
 * the way 30 min / 12 hr do), so a day without one has no completion rather than an invented
 * one. Such a day shows its Move value but an empty ring and an empty heatmap cell.
 */
const DEFAULT_EXERCISE_GOAL_MINUTES = 30
const DEFAULT_STAND_GOAL_HOURS = 12

export type RingKey = 'move' | 'exercise' | 'stand'

export interface Ring {
  key: RingKey
  label: string
  /** CSS custom property holding this ring's hue (see the --activity-* tokens in index.css). */
  color: string
  value: number | null
  goal: number | null
  unit: string
  /** value / goal, uncapped so 1.2 really means 120%; null when either side is missing. */
  completion: number | null
}

function completionOf(value: number | null, goal: number | null): number | null {
  if (value == null || goal == null || goal <= 0) return null
  return value / goal
}

/** The three rings for one day, always in Move / Exercise / Stand order (outermost first). */
export function ringsForDay(row: ActivitySummary | null | undefined): Ring[] {
  const moveGoal = row?.active_energy_burned_goal ?? null
  const exerciseGoal = row?.apple_exercise_time_goal ?? DEFAULT_EXERCISE_GOAL_MINUTES
  const standGoal = row?.apple_stand_hours_goal ?? DEFAULT_STAND_GOAL_HOURS
  const move = row?.active_energy_burned ?? null
  const exercise = row?.apple_exercise_time ?? null
  const stand = row?.apple_stand_hours ?? null

  return [
    {
      key: 'move',
      label: 'Move',
      color: 'var(--activity-move)',
      value: move,
      goal: moveGoal,
      unit: row?.active_energy_burned_unit ?? 'Cal',
      completion: completionOf(move, moveGoal),
    },
    {
      key: 'exercise',
      label: 'Exercise',
      color: 'var(--activity-exercise)',
      value: exercise,
      goal: exerciseGoal,
      unit: 'min',
      completion: completionOf(exercise, exerciseGoal),
    },
    {
      key: 'stand',
      label: 'Stand',
      color: 'var(--activity-stand)',
      value: stand,
      goal: standGoal,
      unit: 'hr',
      completion: completionOf(stand, standGoal),
    },
  ]
}

export function isClosed(ring: Ring): boolean {
  return ring.completion != null && ring.completion >= 1
}

/** True only when all three rings have a goal *and* met it -- a day missing the Move goal
 * can't be called closed, so it counts against the "N of M" denominator, not the numerator.
 */
export function allRingsClosed(row: ActivitySummary): boolean {
  return ringsForDay(row).every(isClosed)
}

export function moveCompletion(row: ActivitySummary | null | undefined): number | null {
  return ringsForDay(row)[0].completion
}

/** Heatmap intensity: 0 = no data or no Move goal (an empty cell), 1-4 = how much of the Move
 * goal the day reached. Four steps, not more: past ~7 classes adjacent shades stop reading
 * apart, and the cells here are small.
 */
export function heatBin(completion: number | null): 0 | 1 | 2 | 3 | 4 {
  if (completion == null || completion <= 0) return 0
  if (completion < 0.5) return 1
  if (completion < 0.8) return 2
  if (completion < 1) return 3
  return 4
}

export const HEAT_BIN_COLORS = [
  'var(--activity-heat-1)',
  'var(--activity-heat-2)',
  'var(--activity-heat-3)',
  'var(--activity-heat-4)',
] as const

export function heatBinColor(bin: number): string | null {
  return bin === 0 ? null : (HEAT_BIN_COLORS[bin - 1] ?? null)
}

export interface CalendarCell {
  date: string
  row: ActivitySummary | null
  /** Shade step and the all-rings-closed mark, resolved here rather than per render: hovering
   * re-renders every cell, and both of these allocate a Ring trio to answer.
   */
  bin: 0 | 1 | 2 | 3 | 4
  closed: boolean
}

export interface CalendarModel {
  /** weeks[weekIndex][weekday], weekday 0 = Sunday. Null where a week runs past either end
   * of the range (the leading days of the first week, the trailing days of the last).
   */
  weeks: (CalendarCell | null)[][]
  /** Month name per week column, for the strip above the grid. */
  monthLabels: { week: number; label: string }[]
  /** Set when the range was longer than MAX_CALENDAR_WEEKS and the grid shows only its most
   * recent weeks, so the card can say so. The rings and the closed-day count still cover the
   * whole range -- only this grid is windowed.
   */
  windowedFrom: string | null
}

/** A day grid stops being readable long before it stops being drawable. Beyond this the
 * calendar shows its most recent weeks and says so, rather than emitting a cell per day back
 * to the start of the export: "All time" on a real export is several thousand days, and
 * Apple's own exports carry placeholder activity rows dated to the Unix epoch, which would
 * otherwise stretch the grid across five decades of empty columns.
 */
export const MAX_CALENDAR_WEEKS = 53

function toDateString(d: Date): string {
  const year = d.getFullYear()
  const month = String(d.getMonth() + 1).padStart(2, '0')
  const day = String(d.getDate()).padStart(2, '0')
  return `${year}-${month}-${day}`
}

/** Lays the range out as week columns x weekday rows.
 *
 * The span comes from the range when it is bounded and from the data otherwise ("All time"
 * sends no start/end at all), so the grid always covers exactly what the filter selected --
 * days inside the range with no activity summary are real information and stay as empty cells.
 */
export function buildCalendar(
  rows: ActivitySummary[],
  range: { start?: string; end?: string },
): CalendarModel {
  const byDate = new Map(rows.map((row) => [row.date, row]))
  const dates = rows.map((row) => row.date).sort()
  const startStr = range.start || dates[0]
  const endStr = range.end || dates[dates.length - 1]
  if (!startStr || !endStr || startStr > endStr) {
    return { weeks: [], monthLabels: [], windowedFrom: null }
  }

  const end = parseLocalDate(endStr)
  const start = parseLocalDate(startStr)
  // Window long ranges back from the newest day: to the Sunday starting its week, then back
  // whole weeks, so the window begins on a column boundary and spans exactly
  // MAX_CALENDAR_WEEKS columns rather than opening on a part-week.
  const earliest = new Date(end)
  earliest.setDate(earliest.getDate() - end.getDay() - (MAX_CALENDAR_WEEKS - 1) * 7)
  const windowed = start < earliest
  if (windowed) start.setTime(earliest.getTime())
  const weeks: (CalendarCell | null)[][] = []
  const monthLabels: { week: number; label: string }[] = []

  let week: (CalendarCell | null)[] = Array.from({ length: start.getDay() }, () => null)
  let lastLabelledWeek = -Infinity
  let lastLabelledMonth = -1

  for (const cursor = new Date(start); cursor <= end; cursor.setDate(cursor.getDate() + 1)) {
    const date = toDateString(cursor)
    const row = byDate.get(date) ?? null
    week.push({
      date,
      row,
      bin: heatBin(moveCompletion(row)),
      closed: row != null && allRingsClosed(row),
    })

    // Label a column when a new month starts in it, but never two columns running: at one
    // column per week the labels would otherwise collide on short months.
    const month = cursor.getMonth()
    if (month !== lastLabelledMonth && weeks.length - lastLabelledWeek >= 2) {
      monthLabels.push({
        week: weeks.length,
        label: cursor.toLocaleDateString('en-US', { month: 'short' }),
      })
      lastLabelledWeek = weeks.length
      lastLabelledMonth = month
    }

    if (cursor.getDay() === 6) {
      weeks.push(week)
      week = []
    }
  }
  if (week.length > 0) {
    while (week.length < 7) week.push(null)
    weeks.push(week)
  }

  return { weeks, monthLabels, windowedFrom: windowed ? toDateString(start) : null }
}

/** "18 of 30 days" -- how often every ring closed, over the days that actually recorded
 * something. The denominator is days with data, not days in the range, so a range extending
 * past the export doesn't quietly drag the ratio down; it also excludes all-null rows, which
 * can never close a ring and would otherwise only inflate the total (Apple's exports carry
 * placeholder activity rows).
 */
export function closedDayCounts(rows: ActivitySummary[]): { closed: number; total: number } {
  const withData = rows.filter(hasAnyActivity)
  return {
    closed: withData.filter(allRingsClosed).length,
    total: withData.length,
  }
}

function hasAnyActivity(row: ActivitySummary): boolean {
  return (
    row.active_energy_burned != null ||
    row.apple_exercise_time != null ||
    row.apple_stand_hours != null
  )
}

/** The most recent day that has any activity data -- what the header rings show. */
export function latestDayWithData(rows: ActivitySummary[]): ActivitySummary | null {
  let latest: ActivitySummary | null = null
  for (const row of rows) {
    if (hasAnyActivity(row) && (latest == null || row.date > latest.date)) latest = row
  }
  return latest
}

/** A single day named with its weekday: "Mon, Feb 23, 2026". The weekday earns its space
 * where one day is called out on its own -- the rings caption, a heatmap cell's tooltip --
 * because which day of the week it was is half of what a daily-activity reading means. Table
 * cells use `formatFullDate` from `lib/formatDate` instead: a column of dates doesn't need
 * the weekday repeated down every row, and that's the shared form the other tables use.
 */
export function formatDayLabel(date: string): string {
  return parseLocalDate(date).toLocaleDateString('en-US', {
    weekday: 'short',
    month: 'short',
    day: 'numeric',
    year: 'numeric',
  })
}

/** "84%" for a ring's completion, capped in display at 999% so a freak day can't widen the
 * legend column. Null completion reads as an em dash.
 */
export function formatCompletion(completion: number | null): string {
  if (completion == null) return '—'
  return `${Math.min(999, Math.round(completion * 100))}%`
}
