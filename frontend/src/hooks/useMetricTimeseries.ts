import { useQuery } from '@tanstack/react-query'
import { api } from '@/api/client'
import type { Bucket, DateRange } from '@/lib/timeRange'

export function useMetricTimeseries(
  metricType: string,
  params: DateRange & { bucket?: Bucket } = {},
) {
  return useQuery({
    queryKey: ['metric-timeseries', metricType, params],
    queryFn: () => api.metricTimeseries(metricType, params),
  })
}
