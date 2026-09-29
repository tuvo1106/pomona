import { useQuery } from '@tanstack/react-query'
import { api } from '@/api/client'
import type { Bucket, DateRange } from '@/lib/timeRange'

export function useBloodPressure(range: DateRange, bucket: Bucket = 'day') {
  const params = { ...range, bucket }
  return useQuery({
    queryKey: ['blood-pressure', params],
    queryFn: () => api.bloodPressure(params),
  })
}
