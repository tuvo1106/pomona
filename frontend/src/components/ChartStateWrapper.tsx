import type { ReactNode } from 'react'
import { Skeleton } from '@/components/ui/skeleton'
import { useContentFade } from '@/lib/transitions'
import { cn } from '@/lib/utils'

interface ChartStateWrapperProps {
  isLoading: boolean
  error: unknown
  isEmpty: boolean
  /** Any CSS length. A number is px, as charts give it; '100%' is for a caller whose frame
   * is already sized (the routes map), so the placeholder fills the frame instead of
   * standing a fixed 600px tall inside a shorter one.
   */
  height: number | string
  errorMessage: string
  children: ReactNode
}

/** Shared loading/error/empty-state handling for chart components, so each chart only needs
 * to supply its own data-fetch and the actual chart JSX for the "has data" case.
 */
export function ChartStateWrapper({
  isLoading,
  error,
  isEmpty,
  height,
  errorMessage,
  children,
}: ChartStateWrapperProps) {
  const fade = useContentFade(isLoading)

  if (isLoading) return <Skeleton className="w-full" style={{ height }} />
  if (error) return <div className="text-destructive text-sm">{errorMessage}</div>
  if (isEmpty) {
    return (
      <div
        className="text-muted-foreground flex items-center justify-center text-sm"
        style={{ height }}
      >
        No data in this range.
      </div>
    )
  }
  // h-full so a caller whose frame is already sized (height="100%": the routes map, the ECG
  // panel) still has a full-height parent for its own h-full child. On a card, whose height
  // is auto, `height: 100%` resolves to auto and the wrapper is inert.
  return <div className={cn('h-full', fade)}>{children}</div>
}
