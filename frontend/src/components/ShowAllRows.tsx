import { ChevronDown, ChevronUp } from 'lucide-react'
import { Button } from '@/components/ui/button'

/** The control under a previewed table (see hooks/useRowPreview).
 *
 * Names the total rather than the remainder -- "Show all 2,120 days" tells you how much
 * there is, where "Show 2,110 more" only tells you how much you're missing. Renders nothing
 * when the table already fits, so a short range doesn't grow a button that does nothing.
 */
export function ShowAllRows({
  hiddenCount,
  totalCount,
  isExpanded,
  onToggle,
  /** Plural noun for the rows, e.g. "workouts", "days", "metrics". */
  noun,
  expandLabel,
}: {
  hiddenCount: number
  totalCount: number
  isExpanded: boolean
  onToggle: () => void
  noun: string
  /** Replaces the default "Show all N <noun>" where the rows are a capped page rather than
   * the whole set -- a card holding the 50 most recent of 200 workouts must not offer to
   * show "all 50" of them.
   */
  expandLabel?: string
}) {
  if (hiddenCount === 0) return null

  const Icon = isExpanded ? ChevronUp : ChevronDown
  return (
    <div className="pt-2">
      <Button
        type="button"
        variant="ghost"
        size="sm"
        onClick={onToggle}
        // What tells a screen reader that the state changed, rather than only the label --
        // and ui/button.tsx hangs the ghost variant's expanded styling off it.
        aria-expanded={isExpanded}
        className="text-muted-foreground w-full"
      >
        <Icon aria-hidden />
        {isExpanded
          ? 'Show fewer'
          : (expandLabel ?? `Show all ${totalCount.toLocaleString('en-US')} ${noun}`)}
      </Button>
    </div>
  )
}
