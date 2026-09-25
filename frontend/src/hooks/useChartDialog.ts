import { useCallback, useMemo, useState } from 'react'
import { useDataMeta } from '@/hooks/useAnchoredRange'
import {
  bucketForRange,
  computeDateRange,
  RANGE_OPTIONS,
  type Bucket,
  type BucketOption,
  type DateRange,
  type RangeOption,
} from '@/lib/timeRange'

/** 'inherit' means "whatever the dashboard is showing" -- the state an unopened dialog is
 * always in, and the one the Reset button returns to.
 */
export type ChartRangeChoice = 'inherit' | RangeOption

export const CHART_RANGE_OPTIONS: { value: ChartRangeChoice; label: string }[] = [
  { value: 'inherit', label: 'Dashboard range' },
  ...RANGE_OPTIONS,
]

export interface ChartDialog {
  open: boolean
  setOpen: (open: boolean) => void
  /** What the chart should actually fetch and draw. Equal to the dashboard's own range and
   * bucket unless the dialog is open *and* something has been overridden.
   */
  range: DateRange
  bucket: Bucket
  rangeChoice: ChartRangeChoice
  setRangeChoice: (choice: ChartRangeChoice) => void
  customRange: DateRange
  setCustomRange: (range: DateRange) => void
  bucketChoice: BucketOption
  setBucketChoice: (choice: BucketOption) => void
  overridden: boolean
  reset: () => void
}

/** Lets an expanded chart show a different range from the rest of the dashboard.
 *
 * The state lives here, above the caller's data query, rather than inside
 * ExpandableChartCard: each chart component fetches its own series, so the override has to
 * be readable before that query is built. The card renders the controls this returns.
 *
 * Two deliberate limits:
 *
 * The override applies only while the dialog is *open*. A card in the grid that quietly
 * covered a different period than its forty neighbours would make the dashboard lie by
 * comparison -- the whole point of a grid is that the cards are on the same axis.
 *
 * One visible seam comes with that: the card and the dialog draw from one query, so while
 * the dialog is open the preview behind it redraws at the override too, and the overlay is
 * dim rather than opaque -- pick "Today" on a card near the edge of the dialog and you can
 * watch it empty out behind. Closing restores it from cache. Separating them means a second
 * query per chart, kept alive for a dialog that is usually shut, on a page that already
 * runs forty of them; the seam is the cheaper side of that trade.
 *
 * And closing resets it. A remembered override would be silently stale the moment the
 * dashboard's own range changed under it.
 */
export function useChartDialog(range: DateRange, bucket: Bucket): ChartDialog {
  const [open, setOpenState] = useState(false)
  const [rangeChoice, setRangeChoice] = useState<ChartRangeChoice>('inherit')
  const [customRange, setCustomRange] = useState<DateRange>({})
  const [bucketChoice, setBucketChoice] = useState<BucketOption>('auto')

  // Shared with the dashboard's own range picker via react-query's cache (one ['meta']
  // query however many charts subscribe), so the dialog's relative ranges anchor to the
  // newest date with data exactly as the dashboard's do.
  const { data: meta } = useDataMeta()
  const anchor = meta?.latest_date ?? undefined

  const chosenRange = useMemo(
    () =>
      rangeChoice === 'inherit' ? range : computeDateRange(rangeChoice, customRange, anchor),
    [rangeChoice, range, customRange, anchor],
  )
  // 'auto' while inheriting means the dashboard's own resolved bucket, not a fresh
  // derivation -- the dashboard's may itself be a manual override, and re-deriving it here
  // would silently change the bucket on a chart nobody asked to change.
  const chosenBucket = useMemo(() => {
    if (bucketChoice !== 'auto') return bucketChoice
    return rangeChoice === 'inherit' ? bucket : bucketForRange(chosenRange)
  }, [bucketChoice, rangeChoice, bucket, chosenRange])

  // "Custom range" is chosen before its dates are, and an empty custom range resolves to
  // {} -- the whole history, bucketed monthly, which for a summed metric is the most
  // expensive query this app makes. On the dashboard that's a deliberate whole-page action;
  // here it would be a side effect of opening a dropdown. Keep showing the dashboard's range
  // until at least one bound exists.
  const customPending = rangeChoice === 'custom' && !customRange.start && !customRange.end

  // Compared on the resolved range and bucket, not on the choice. Picking the range the
  // dashboard is already showing changes nothing, and offering to undo nothing is noise.
  const overridden =
    !customPending &&
    (chosenRange.start !== range.start ||
      chosenRange.end !== range.end ||
      chosenBucket !== bucket)

  const reset = useCallback(() => {
    setRangeChoice('inherit')
    setCustomRange({})
    setBucketChoice('auto')
  }, [])

  const setOpen = useCallback(
    (next: boolean) => {
      setOpenState(next)
      if (!next) reset()
    },
    [reset],
  )

  const active = open && overridden

  return {
    open,
    setOpen,
    range: active ? chosenRange : range,
    bucket: active ? chosenBucket : bucket,
    rangeChoice,
    setRangeChoice,
    customRange,
    setCustomRange,
    bucketChoice,
    setBucketChoice,
    overridden,
    reset,
  }
}
