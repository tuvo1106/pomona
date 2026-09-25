import { useQuery } from '@tanstack/react-query'
import { api } from '@/api/client'
import type { DateRange } from '@/lib/timeRange'

export function useMetricTimeseries(
  metricType: string,
  params: DateRange & { bucket?: string } = {},
) {
  return useQuery({
    queryKey: ['metric-timeseries', metricType, params],
    queryFn: () => api.metricTimeseries(metricType, params),
  })
}
