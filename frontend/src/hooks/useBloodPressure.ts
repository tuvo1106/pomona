import { useQuery } from '@tanstack/react-query'
import { api } from '@/api/client'
import type { DateRange } from '@/lib/timeRange'

export function useBloodPressure(range: DateRange, bucket: 'day' | 'week' | 'month' = 'day') {
  const params = { ...range, bucket }
  return useQuery({
    queryKey: ['blood-pressure', params],
    queryFn: () => api.bloodPressure(params),
  })
}
