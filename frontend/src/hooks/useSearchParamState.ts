import { useCallback, useLayoutEffect, useMemo, useRef } from 'react'
import { useSearchParams } from 'react-router-dom'
import {
  isBucketOption,
  isIsoDate,
  isRangeOption,
  type DateRange,
  type RangeOption,
} from '@/lib/timeRange'

/** Keys that describe *what you're looking at* rather than which page you're on, so they
 * follow you across the nav (see navSearch), each with the check that says whether a value
 * is usable. Page-specific keys -- a selected recording, a selected route -- deliberately
 * don't travel.
 */
const SHARED_PARAMS: { key: string; isValid: (value: string) => boolean }[] = [
  { key: 'range', isValid: isRangeOption },
  { key: 'from', isValid: isIsoDate },
  { key: 'to', isValid: isIsoDate },
  { key: 'bucket', isValid: isBucketOption },
]

/** The query string a nav link should carry.
 *
 * Without this, URL state doesn't actually fix what UI-21 describes: going Dashboard →
 * Clinical → Dashboard would drop the query on the way out and land back on the default,
 * which is the reset it was meant to stop.
 *
 * Only values that survive their own check travel. A URL carrying a stale `?range=6mo`
 * would otherwise mean one thing on the dashboard (fall back to 30 days) and another on
 * Routes (fall back to a year), so one link would describe two different views depending on
 * where it was opened, and re-sharing would spread the bad value.
 */
export function navSearch(params: URLSearchParams): string {
  const carried = new URLSearchParams()
  const range = params.get('range')
  for (const { key, isValid } of SHARED_PARAMS) {
    // The two custom dates are only meaningful alongside range=custom. Carried past a
    // switch to a preset they'd pre-fill another page's picker with dates nobody chose
    // there, and a shared link would advertise a range it isn't showing.
    if ((key === 'from' || key === 'to') && range !== 'custom') continue
    const value = params.get(key)
    if (value != null && isValid(value)) carried.set(key, value)
  }
  const search = carried.toString()
  return search ? `?${search}` : ''
}

/** Writes to the query string, with a setter whose identity never changes.
 *
 * `useSearchParams`' own setter is memoized on the current params, so it takes a new
 * identity every time the URL moves. A setter passed down to a memoized row would then
 * change on every write, re-rendering all ~80 of them to move one highlight -- exactly what
 * those memos exist to prevent (see RouteRow). Reading the current params from a ref instead
 * keeps the setters stable for the life of the component.
 *
 * Writes `replace`, not `push`. Back should return to the page you came from, not walk
 * backwards through your own filtering: the custom-range date inputs alone fire per
 * keystroke, so a history entry per write would bury the previous page under half-typed
 * dates.
 */
function useParamWriter(): (mutate: (params: URLSearchParams) => void) => void {
  const [params, setParams] = useSearchParams()
  const latest = useRef({ params, setParams })
  // Layout, not passive: it runs before the browser can deliver the next event, so a handler
  // never reads a pair from a render that has already been replaced.
  useLayoutEffect(() => {
    latest.current = { params, setParams }
  }, [params, setParams])

  return useCallback((mutate: (params: URLSearchParams) => void) => {
    const updated = new URLSearchParams(latest.current.params)
    mutate(updated)
    latest.current.setParams(updated, { replace: true })
    // Kept in step so two writes in one handler compose rather than the second reading the
    // params as they were before the first and undoing it.
    latest.current = { ...latest.current, params: updated }
  }, [])
}

/** `useState`, backed by a search param.
 *
 * The default is what the *absence* of the key means, which is what lets two pages default
 * differently while sharing one key, and what keeps a fresh `/` from becoming
 * `/?range=30d&bucket=auto` before anyone has touched anything.
 *
 * Choosing the default is not the same as never having chosen, though, so a choice is
 * always written -- including one that happens to equal the default. Deleting the key
 * instead would make "Last 30 days", picked deliberately on the dashboard, indistinguishable
 * from an untouched picker, and Routes would then open on its own year default. Which of
 * your choices followed you across the nav would depend on whether the value you picked
 * happened to be that page's default.
 */
export function useSearchParamState<T extends string>(
  key: string,
  defaultValue: T,
  isValid: (value: string) => value is T,
): [T, (next: T) => void] {
  const [params] = useSearchParams()
  const write = useParamWriter()
  const raw = params.get(key)
  const value = raw != null && isValid(raw) ? raw : defaultValue

  const setValue = useCallback(
    (next: T) => {
      write((updated) => updated.set(key, next))
    },
    [key, write],
  )

  return [value, setValue]
}

/** A numeric id in the URL, or null. Used for "which row is selected" state, which is worth
 * keeping in the URL so a reload -- or a link you send yourself -- lands on the same one.
 * Null is absence rather than a value, so it clears the key.
 */
export function useSearchParamId(key: string): [number | null, (next: number | null) => void] {
  const [params] = useSearchParams()
  const write = useParamWriter()
  const raw = params.get(key)
  const parsed = raw == null ? null : Number(raw)
  const value = parsed != null && Number.isInteger(parsed) && parsed > 0 ? parsed : null

  const setValue = useCallback(
    (next: number | null) => {
      write((updated) => {
        if (next == null) updated.delete(key)
        else updated.set(key, String(next))
      })
    },
    [key, write],
  )

  return [value, setValue]
}

/** The two custom dates, dropped unless they're usable.
 *
 * An unparseable date would reach the API verbatim, and the date comparison there is a
 * string comparison -- `start_local_date >= 'yesterday'` matches nothing -- so every card
 * would read as empty with no error to explain it, and `<input type="date">` renders an
 * unparseable value as blank, so the picker couldn't show what was wrong either. An inverted
 * pair goes too: the two inputs constrain each other with `min`/`max`, so it isn't a state
 * the UI can produce.
 */
function validCustomRange(from: string | null, to: string | null): DateRange {
  const start = from != null && isIsoDate(from) ? from : undefined
  const end = to != null && isIsoDate(to) ? to : undefined
  if (start != null && end != null && start > end) return {}
  return { start, end }
}

/** The range and its two custom dates, which are one piece of state in three keys: leaving
 * `custom` has to clear the dates in the same write that sets the range.
 */
export function useRangeParams(defaultOption: RangeOption): {
  rangeOption: RangeOption
  setRangeOption: (next: RangeOption) => void
  customRange: DateRange
  setCustomRange: (next: DateRange) => void
} {
  const [params] = useSearchParams()
  const write = useParamWriter()

  const raw = params.get('range')
  const rangeOption = raw != null && isRangeOption(raw) ? raw : defaultOption

  const from = params.get('from')
  const to = params.get('to')
  const customRange = useMemo(() => validCustomRange(from, to), [from, to])

  const setRangeOption = useCallback(
    (next: RangeOption) => {
      write((updated) => {
        updated.set('range', next)
        if (next !== 'custom') {
          updated.delete('from')
          updated.delete('to')
        }
      })
    },
    [write],
  )

  const setCustomRange = useCallback(
    (next: DateRange) => {
      write((updated) => {
        for (const [key, value] of [
          ['from', next.start],
          ['to', next.end],
        ] as const) {
          if (value) updated.set(key, value)
          else updated.delete(key)
        }
      })
    },
    [write],
  )

  return { rangeOption, setRangeOption, customRange, setCustomRange }
}
