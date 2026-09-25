/** Time-of-day for an ECG recording. Separate from lib/formatDate.ts, which formats the
 * `YYYY-MM-DD` local calendar dates the dashboard APIs return; this one starts from an
 * epoch, as ClinicalPage's own formatter does -- though not in that one's zone. Clinical
 * dates are pinned to UTC because a FHIR date-only value is stored as UTC midnight and any
 * zone behind UTC would shift it a day; an ECG carries a real instant, and the question
 * here is which clock to show it on. See below.
 */

const timeFormat = new Intl.DateTimeFormat('en-US', { hour: 'numeric', minute: '2-digit' })

function localIsoDate(at: Date): string {
  const month = String(at.getMonth() + 1).padStart(2, '0')
  const day = String(at.getDate()).padStart(2, '0')
  return `${at.getFullYear()}-${month}-${day}`
}

/** The clock time a recording was taken, or null when it can't be shown honestly.
 *
 * `/api/ecg` returns two time fields and neither is a local wall clock: `recorded_date` is
 * epoch seconds in UTC, and `recorded_local_date` is the calendar day in whatever zone the
 * watch was in. The offset between them isn't stored -- ingest/dates.py derives the day
 * from it and keeps only these two -- so the recording's own local time is not recoverable,
 * and there is no column to add to the query that would recover it.
 *
 * What's left is to render the epoch in the *viewer's* zone. For anyone reading their own
 * dashboard in the zone they recorded in, which is the ordinary case, that is the true
 * time; elsewhere it's the same instant expressed locally, which still orders a day's
 * recordings correctly.
 *
 * The guard below only catches the case that would print a visible contradiction: when the
 * epoch lands on a different calendar day in the viewer's zone than the row's own date -- a
 * recording made far enough away, near enough midnight -- a time beside that date would be
 * read as a time *on* it. Return null there and let the caller show the date alone.
 *
 * It does *not* catch a smaller shift. A recording made in London at 11:00 PM, read from
 * New York, still falls on the London date and renders as 6:00 PM: the same instant, the
 * right day, the wrong wall clock, and nothing on the row says so. That can't be fixed
 * here, because the offset that would fix it was never stored -- so the caller names the
 * clock instead (see EcgList), which is the most this can honestly claim.
 */
export function formatRecordedTime(
  recordedDate: number,
  recordedLocalDate: string,
): string | null {
  const at = new Date(recordedDate * 1000)
  if (Number.isNaN(at.getTime())) return null
  if (localIsoDate(at) !== recordedLocalDate) return null
  return timeFormat.format(at)
}
