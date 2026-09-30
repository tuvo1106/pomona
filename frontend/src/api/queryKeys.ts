import type { CategoryMetricMode } from '@/api/client'
import type { Bucket, DateRange } from '@/lib/timeRange'

/** Every react-query key the app uses, in one place, so two hooks can't collide on a key or
 * drift apart on one they mean to share. Each key's parameters are the request's, so a
 * change of range or bucket is a different cache entry. Only the hooks in hooks/queries.ts
 * should need these.
 */
export const queryKeys = {
  meta: () => ['meta'] as const,
  overview: (range: DateRange) => ['overview', range] as const,
  activitySummary: (range: DateRange) => ['activity-summary', range] as const,
  /** No range is every metric type with data at all, for the all-metrics list. */
  metricTypes: (range?: DateRange) => ['metric-types', range ?? 'all-time'] as const,
  metricTimeseries: (metricType: string, params: DateRange & { bucket?: Bucket }) =>
    ['metric-timeseries', metricType, params] as const,
  categoryMetricTimeseries: (
    metricType: string,
    mode: CategoryMetricMode,
    params: DateRange & { bucket?: Bucket; value_prefix?: string },
  ) => ['category-metric-timeseries', metricType, mode, params] as const,
  sleep: (params: DateRange & { bucket: Bucket }) => ['sleep', params] as const,
  bloodPressure: (params: DateRange & { bucket: Bucket }) => ['blood-pressure', params] as const,
  workouts: (params: DateRange & { activity_type?: string; limit?: number }) =>
    ['workouts', params] as const,
  workoutsSummary: (range: DateRange) => ['workouts-summary', range] as const,
  runningMileage: (range: DateRange) => ['running-mileage', range] as const,
  routes: (range: DateRange) => ['routes', range] as const,
  ecgRecordings: (range: DateRange) => ['ecg', range] as const,
  ecgRecording: (id: number | null) => ['ecg', 'detail', id] as const,
  clinical: () => ['clinical', 'all'] as const,
}
