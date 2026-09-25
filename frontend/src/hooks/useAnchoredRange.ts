import { useMemo } from 'react'
import { useQuery } from '@tanstack/react-query'
import { api } from '@/api/client'
import { useRangeParams } from '@/hooks/useSearchParamState'
import { computeDateRange, type RangeOption } from '@/lib/timeRange'

export function useDataMeta() {
  return useQuery({
    queryKey: ['meta'],
    queryFn: api.meta,
    // Every page's data queries wait on this one (see `ready` below). react-query's default
    // of 3 retries with backoff would hold them on skeletons for ~7s when it fails -- e.g.
    // the 503 for a missing database -- instead of letting each page show its error.
    retry: false,
    // Default staleTime (0) plus refetch-on-focus, like the data queries: after a re-ingest
    // and server restart, an already-open tab picks up the new anchor when it's refocused
    // rather than hiding the new data until a reload. A refetch that returns the same date
    // changes nothing, so it doesn't re-fire the data queries.
  })
}

/** Range-picker state plus the resolved {start, end}, with the relative ranges anchored to
 * the newest date that has data (see computeDateRange).
 *
 * `ready` is false until the anchor is known. Callers should hold off their data queries
 * until then: resolving the range against today first and then re-resolving it once the
 * anchor arrives would fire every query on the page twice. A *failed* meta request (e.g.
 * the 503 for a missing database) still counts as ready, falling back to today, so each
 * page gets to render its own error state rather than hanging on a skeleton.
 */
export function useAnchoredRange(defaultOption: RangeOption) {
  // In the URL rather than component state, so a reload, a shared link, or a trip through
  // another page and back all land on the range you picked (see useSearchParamState).
  // `defaultOption` applies only while the key is absent, so Dashboard's 30d and Routes'
  // 365d still differ until someone actually chooses.
  const { rangeOption, setRangeOption, customRange, setCustomRange } =
    useRangeParams(defaultOption)
  const meta = useDataMeta()
  const latestDate = meta.data?.latest_date ?? undefined
  const range = useMemo(
    () => computeDateRange(rangeOption, customRange, latestDate),
    [rangeOption, customRange, latestDate],
  )

  return {
    rangeOption,
    setRangeOption,
    customRange,
    setCustomRange,
    range,
    ready: !meta.isPending,
    latestDate,
    ingestedAt: meta.data?.ingested_at ?? undefined,
  }
}
