import { useQuery } from '@tanstack/react-query'
import { api } from '@/api/client'
import type { DateRange } from '@/lib/timeRange'

export function useWorkouts(range: DateRange, params: { activity_type?: string; limit?: number } = {}) {
  const merged = { ...range, ...params }
  return useQuery({
    queryKey: ['workouts', merged],
    queryFn: () => api.workouts(merged),
  })
}

export function useWorkoutsSummary(range: DateRange) {
  return useQuery({
    queryKey: ['workouts-summary', range],
    queryFn: () => api.workoutsSummary(range),
  })
}
