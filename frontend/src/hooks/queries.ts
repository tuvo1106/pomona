import { keepPreviousData, useQuery } from '@tanstack/react-query'
import { api, type CategoryMetricMode } from '@/api/client'
import { queryKeys } from '@/api/queryKeys'
import type { Bucket, DateRange } from '@/lib/timeRange'

// Every data query the app makes, so a component never builds a key or calls the API itself.
// One shape throughout: whatever identifies the series first (a metric type, a mode), then
// the date range, then an options object -- `bucket` for bucketed series, `enabled` for a
// query that has to wait (see useAnchoredRange's `ready`).

interface QueryOptions {
  enabled?: boolean
}

interface BucketedOptions extends QueryOptions {
  bucket?: Bucket
}

export function useDataMeta() {
  return useQuery({
    queryKey: queryKeys.meta(),
    queryFn: api.meta,
    // Every page's data queries wait on this one (see `ready` in useAnchoredRange).
    // react-query's default of 3 retries with backoff would hold them on skeletons for ~7s
    // when it fails -- e.g. the 503 for a missing database -- instead of letting each page
    // show its error.
    retry: false,
    // Default staleTime (0) plus refetch-on-focus, like the data queries: after a re-ingest
    // and server restart, an already-open tab picks up the new anchor when it's refocused
    // rather than hiding the new data until a reload. A refetch that returns the same date
    // changes nothing, so it doesn't re-fire the data queries.
  })
}

export function useOverview(range: DateRange, { enabled = true }: QueryOptions = {}) {
  return useQuery({
    queryKey: queryKeys.overview(range),
    queryFn: () => api.overview(range),
    enabled,
  })
}

export function useActivitySummary(range: DateRange, { enabled = true }: QueryOptions = {}) {
  return useQuery({
    queryKey: queryKeys.activitySummary(range),
    queryFn: () => api.activitySummary(range),
    enabled,
  })
}

/** Which metric types have data in `range`, or at all when `range` is omitted. */
export function useMetricTypes(range?: DateRange, { enabled = true }: QueryOptions = {}) {
  return useQuery({
    queryKey: queryKeys.metricTypes(range),
    queryFn: () => api.metricTypes(range),
    enabled,
    // Keep the previous range's groups on screen while the new ones load. Without this,
    // every range change tore the dashboard's whole Trends region down to six skeletons and
    // rebuilt it -- forty cards and their section headings, a several-thousand-pixel collapse
    // and re-expansion -- which no amount of fading the individual cards back in can soften.
    // Safe to show stale here in a way it wouldn't be for the overview: this query returns
    // which metric types exist, not any of their values, so the worst case is a card that
    // appears and then goes away because the new range has no data for it. Each chart's own
    // query still reloads underneath, with its own skeleton.
    placeholderData: keepPreviousData,
  })
}

export function useMetricTimeseries(
  metricType: string,
  range: DateRange,
  { bucket, enabled = true }: BucketedOptions = {},
) {
  const params = { ...range, bucket }
  return useQuery({
    queryKey: queryKeys.metricTimeseries(metricType, params),
    queryFn: () => api.metricTimeseries(metricType, params),
    enabled,
  })
}

export function useCategoryMetricTimeseries(
  metricType: string,
  mode: CategoryMetricMode,
  range: DateRange,
  { bucket, valuePrefix, enabled = true }: BucketedOptions & { valuePrefix?: string } = {},
) {
  const params = { ...range, bucket, value_prefix: valuePrefix }
  return useQuery({
    queryKey: queryKeys.categoryMetricTimeseries(metricType, mode, params),
    queryFn: () => api.categoryMetricTimeseries(metricType, mode, params),
    enabled,
  })
}

export function useSleep(range: DateRange, { bucket = 'day', enabled = true }: BucketedOptions = {}) {
  const params = { ...range, bucket }
  return useQuery({
    queryKey: queryKeys.sleep(params),
    queryFn: () => api.sleep(params),
    enabled,
  })
}

export function useBloodPressure(
  range: DateRange,
  { bucket = 'day', enabled = true }: BucketedOptions = {},
) {
  const params = { ...range, bucket }
  return useQuery({
    queryKey: queryKeys.bloodPressure(params),
    queryFn: () => api.bloodPressure(params),
    enabled,
  })
}

export function useWorkouts(
  range: DateRange,
  {
    activityType,
    limit,
    enabled = true,
  }: QueryOptions & { activityType?: string; limit?: number } = {},
) {
  const params = { ...range, activity_type: activityType, limit }
  return useQuery({
    queryKey: queryKeys.workouts(params),
    queryFn: () => api.workouts(params),
    enabled,
  })
}

export function useWorkoutsSummary(range: DateRange, { enabled = true }: QueryOptions = {}) {
  return useQuery({
    queryKey: queryKeys.workoutsSummary(range),
    queryFn: () => api.workoutsSummary(range),
    enabled,
  })
}

export function useRunningMileage(range: DateRange, { enabled = true }: QueryOptions = {}) {
  return useQuery({
    queryKey: queryKeys.runningMileage(range),
    queryFn: () => api.runningMileage(range),
    enabled,
  })
}

export function useRoutes(range: DateRange, { enabled = true }: QueryOptions = {}) {
  return useQuery({
    queryKey: queryKeys.routes(range),
    queryFn: () => api.routes(range),
    enabled,
  })
}

export function useEcgRecordings(range: DateRange, { enabled = true }: QueryOptions = {}) {
  return useQuery({
    queryKey: queryKeys.ecgRecordings(range),
    queryFn: () => api.ecgRecordings(range),
    enabled,
  })
}

/** One recording's full waveform; waits while `id` is null (nothing selected). */
export function useEcgRecording(id: number | null) {
  return useQuery({
    queryKey: queryKeys.ecgRecording(id),
    queryFn: () => api.ecgRecording(id as number),
    enabled: id != null,
  })
}

/** Every clinical record. The page filters client-side, so there's no range here. */
export function useClinical() {
  return useQuery({
    queryKey: queryKeys.clinical(),
    queryFn: () => api.clinical({}),
  })
}
