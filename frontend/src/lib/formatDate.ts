import type { ReactNode } from 'react'
import { parseLocalDate, type Bucket } from '@/lib/timeRange'

/** Display formatting for the local calendar dates (`YYYY-MM-DD`) that every dashboard API
 * returns. ISO strings are precise but read as machine output; these are the forms a person
 * scans.
 *
 * Every helper parses through `parseLocalDate`, which splits the string. Handing a bare
 * `YYYY-MM-DD` to `new Date()` instead parses it as UTC midnight, which lands on the previous
 * day in any zone west of UTC -- the same trap ClinicalPage's own formatter documents. (That
 * one stays separate: clinical dates are epoch values deliberately rendered in UTC.)
 */

const ISO_DATE = /^\d{4}-\d{2}-\d{2}$/

const monthDayFormat = new Intl.DateTimeFormat('en-US', { month: 'short', day: 'numeric' })
const monthYearFormat = new Intl.DateTimeFormat('en-US', { month: 'short', year: 'numeric' })
const monthFormat = new Intl.DateTimeFormat('en-US', { month: 'short' })
const fullFormat = new Intl.DateTimeFormat('en-US', {
  month: 'short',
  day: 'numeric',
  year: 'numeric',
})

/** `2026-02-23` -> `Feb 2026`, for a month bucket. */
function formatMonthYear(value: string): string {
  return monthYearFormat.format(parseLocalDate(value))
}

/** `2026-02-23` -> `Feb 23, 2026`. The default for table and list cells, where there's room
 * for the year and rows may be far apart in time.
 */
export function formatFullDate(value: string): string {
  if (!ISO_DATE.test(value)) return value
  return fullFormat.format(parseLocalDate(value))
}

/** A bucket's first day, named the way the bucket actually reads: a week bucket covers the
 * seven days from its date, a month bucket the whole month. Used for tooltips and for the
 * Date column of each chart's table twin.
 */
export function formatBucketDate(value: string, bucket: Bucket): string {
  if (!ISO_DATE.test(value)) return value
  if (bucket === 'month') return formatMonthYear(value)
  if (bucket === 'week') return `Week of ${formatFullDate(value)}`
  return formatFullDate(value)
}

/** A tooltip `labelFormatter` for a bucketed series. recharts types the label as a
 * `ReactNode`; every chart here keys on the date string, and anything else passes through.
 */
export function makeDateLabelFormatter(bucket: Bucket): (label: ReactNode) => string {
  return (label) => {
    if (typeof label === 'string') return formatBucketDate(label, bucket)
    return label == null ? '' : String(label)
  }
}

/** True when the dates don't all fall in the same calendar year, in which case an axis tick
 * needs the year to stay unambiguous.
 */
function spansMultipleYears(dates: readonly string[]): boolean {
  if (dates.length === 0) return false
  const year = dates[0].slice(0, 4)
  return dates.some((date) => date.slice(0, 4) !== year)
}

/** An X-axis `tickFormatter` for the given series. Ticks are the tightest date form that's
 * still unambiguous -- no year while the series stays inside one (the range picker already
 * says which), a two-digit year once it crosses into another.
 */
export function makeDateTickFormatter(
  dates: readonly string[],
  bucket: Bucket,
): (value: string) => string {
  const withYear = spansMultipleYears(dates)
  return (value: string) => {
    if (!ISO_DATE.test(value)) return value
    const date = parseLocalDate(value)
    const stem = bucket === 'month' ? monthFormat.format(date) : monthDayFormat.format(date)
    return withYear ? `${stem} '${value.slice(2, 4)}` : stem
  }
}
