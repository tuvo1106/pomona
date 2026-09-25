import { useQuery } from '@tanstack/react-query'
import { api } from '@/api/client'
import type { DateRange } from '@/lib/timeRange'

export function useRoutes(range: DateRange, { enabled = true }: { enabled?: boolean } = {}) {
  return useQuery({
    queryKey: ['routes', range],
    queryFn: () => api.routes(range),
    enabled,
  })
}
