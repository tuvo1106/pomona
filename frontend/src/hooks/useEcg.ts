import { useQuery } from '@tanstack/react-query'
import { api } from '@/api/client'
import type { DateRange } from '@/lib/timeRange'

export function useEcgRecordings(range: DateRange, { enabled = true }: { enabled?: boolean } = {}) {
  return useQuery({
    queryKey: ['ecg', range],
    queryFn: () => api.ecgRecordings(range),
    enabled,
  })
}

export function useEcgRecording(id: number | null) {
  return useQuery({
    queryKey: ['ecg', 'detail', id],
    queryFn: () => api.ecgRecording(id as number),
    enabled: id != null,
  })
}
