export type RangeOption = '1d' | '7d' | '30d' | '90d' | '365d' | 'all' | 'custom'

export const RANGE_OPTIONS: { value: RangeOption; label: string }[] = [
  // "Today", not "Last 24 hours": records are bucketed by their local calendar date, so this
  // range is start === end === today -- at 09:00 that's 9 hours of data, not 24.
  { value: '1d', label: 'Today' },
  { value: '7d', label: 'Last 7 days' },
  { value: '30d', label: 'Last 30 days' },
  { value: '90d', label: 'Last 90 days' },
  { value: '365d', label: 'Last year' },
  { value: 'all', label: 'All time' },
  { value: 'custom', label: 'Custom range' },
]

const RANGE_VALUES = new Set<string>(RANGE_OPTIONS.map((option) => option.value))

/** A URL can say anything, so a `?range=` is checked rather than cast -- an unrecognised or
 * stale value falls back to the page's default instead of reaching computeDateRange. Lives
 * here, beside the list it checks against, so there is one source for what's valid rather
 * than a copy in each page that reads the param.
 */
export function isRangeOption(value: string): value is RangeOption {
  return RANGE_VALUES.has(value)
}

const RANGE_DAYS: Record<'1d' | '7d' | '30d' | '90d' | '365d', number> = {
  '1d': 1,
  '7d': 7,
  '30d': 30,
  '90d': 90,
  '365d': 365,
}

function toLocalDateString(d: Date): string {
  const year = d.getFullYear()
  const month = String(d.getMonth() + 1).padStart(2, '0')
  const day = String(d.getDate()).padStart(2, '0')
  return `${year}-${month}-${day}`
}

/** Parses a YYYY-MM-DD local date string as local midnight. `new Date('2026-08-20')` would
 * parse it as UTC midnight instead, which lands on the previous day in any zone west of UTC.
 */
export function parseLocalDate(value: string): Date {
  const [year, month, day] = value.split('-').map(Number)
  return new Date(year, month - 1, day)
}

export function todayLocalDateString(): string {
  return toLocalDateString(new Date())
}

export interface DateRange {
  start?: string
  end?: string
}

/** Converts a RangeOption into {start, end} date strings, inclusive.
 *
 * The relative ranges ("Last 30 days", ...) end on `anchor` -- the newest date that has data
 * -- when that's earlier than today. Data only arrives with a manual re-export, so "today" is
 * usually past the end of it, and a window ending today would come up empty whenever the
 * last export is over a month old. With a same-day export the anchor *is* today, so nothing
 * changes. "Today" keeps its literal meaning regardless of the anchor.
 *
 * For 'custom', returns the given custom dates as-is (may be partial/empty while the
 * user is still picking them -- an empty string is treated as "no bound" by the API).
 */
export function computeDateRange(
  option: RangeOption,
  custom?: DateRange,
  anchor?: string,
): DateRange {
  if (option === 'custom') return { start: custom?.start || undefined, end: custom?.end || undefined }
  if (option === 'all') return {}
  const today = todayLocalDateString()
  // Plain string comparison is a valid date comparison for zero-padded YYYY-MM-DD.
  const end = option !== '1d' && anchor && anchor < today ? anchor : today
  const start = parseLocalDate(end)
  start.setDate(start.getDate() - (RANGE_DAYS[option] - 1))
  return { start: toLocalDateString(start), end }
}

export type Bucket = 'day' | 'week' | 'month'
export type BucketOption = 'auto' | Bucket

export const BUCKET_OPTIONS: { value: BucketOption; label: string }[] = [
  { value: 'auto', label: 'Auto' },
  { value: 'day', label: 'Daily' },
  { value: 'week', label: 'Weekly' },
  { value: 'month', label: 'Monthly' },
]

/** A coarser bucket keeps wide ranges readable rather than a dense wall of points. Based on
 * the range's actual span so it works for custom ranges too, not just the preset options.
 * This is only the 'auto' default -- the user can override it via the bucket selector.
 */
const BUCKET_VALUES = new Set<string>(BUCKET_OPTIONS.map((option) => option.value))

/** The bucket's equivalent of isRangeOption. */
export function isBucketOption(value: string): value is BucketOption {
  return BUCKET_VALUES.has(value)
}

/** YYYY-MM-DD, the only shape the custom-range dates are ever allowed to take. The API
 * compares dates as strings, so anything else reaching it matches nothing and reads as an
 * empty range rather than as an error.
 */
export function isIsoDate(value: string): boolean {
  return /^\d{4}-\d{2}-\d{2}$/.test(value)
}

export function bucketForRange(range: DateRange): Bucket {
  if (!range.start || !range.end) return 'month' // unbounded (e.g. all-time, or an incomplete custom range)
  const days = (new Date(range.end).getTime() - new Date(range.start).getTime()) / 86_400_000
  if (days <= 35) return 'day'
  if (days <= 370) return 'week'
  return 'month'
}

export function resolveBucket(range: DateRange, override: BucketOption): Bucket {
  return override === 'auto' ? bucketForRange(range) : override
}
