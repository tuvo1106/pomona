import type { ReactNode } from 'react'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'
import { useContentFade } from '@/lib/transitions'

interface DataCardProps {
  title: ReactNode
  isLoading: boolean
  error: unknown
  isEmpty: boolean
  errorMessage: string
  emptyMessage: string
  /** Skeleton placeholder height while loading. A middle, not a measurement: these cards
   * hold tables whose height is the row count, so the same card is ~77px over a week and
   * ~372px over a year. No single number matches, and the alternative -- pinning the card
   * to its longest form -- would leave most ranges sitting in empty space.
   */
  skeletonHeight?: number
  children: ReactNode
}

/** Shared Card + loading/error/empty-state handling for the dashboard's table-style cards
 * (recent workouts, workout summary, all tracked metrics), so each one only needs to supply
 * its data-fetch and the actual <Table> for the "has data" case. The clinical page is not
 * one of these despite the shape -- its sections aren't cards and it builds its own states.
 *
 * There is deliberately no inner scroll area. A card that caps its own height and scrolls
 * swallows the wheel: the page underneath cannot move while the cursor is over the card,
 * which on a long table is most of it. Long tables show a preview and a "Show all" control
 * instead (hooks/useRowPreview, components/ShowAllRows).
 */
export function DataCard({
  title,
  isLoading,
  error,
  isEmpty,
  errorMessage,
  emptyMessage,
  skeletonHeight = 240,
  children,
}: DataCardProps) {
  const hasError = Boolean(error)
  const fade = useContentFade(isLoading)

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-sm font-medium">{title}</CardTitle>
      </CardHeader>
      <CardContent>
        {isLoading && <Skeleton className="w-full" style={{ height: skeletonHeight }} />}
        {!isLoading && hasError && <div className="text-destructive text-sm">{errorMessage}</div>}
        {!isLoading && !hasError && isEmpty && (
          <div className="text-muted-foreground text-sm">{emptyMessage}</div>
        )}
        {!isLoading && !hasError && !isEmpty && <div className={fade}>{children}</div>}
      </CardContent>
    </Card>
  )
}
