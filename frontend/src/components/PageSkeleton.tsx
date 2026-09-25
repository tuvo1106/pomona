import { Skeleton } from '@/components/ui/skeleton'

/** Stand-in while a route's chunk downloads (see the lazy imports in App.tsx).
 *
 * Deliberately generic rather than per-page: the point is to hold the space under the
 * header for the fraction of a second a chunk takes off localhost, and a shape that guessed
 * at one page's layout would be wrong on the other three.
 */
export function PageSkeleton() {
  return (
    <main className="mx-auto max-w-7xl space-y-6 px-6 py-6">
      <div className="space-y-2">
        <Skeleton className="h-6 w-48" />
        <Skeleton className="h-4 w-64" />
      </div>
      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        {Array.from({ length: 4 }, (_, i) => (
          <Skeleton key={i} className="h-24 w-full" />
        ))}
      </div>
      <Skeleton className="h-64 w-full" />
    </main>
  )
}
