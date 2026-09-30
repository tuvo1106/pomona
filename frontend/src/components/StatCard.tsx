import { Card, CardContent } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'
import type { StatCardContent, Tone } from '@/lib/overviewStats'
import { cn } from '@/lib/utils'

const TONE_CLASS: Record<Tone, string> = {
  good: 'text-positive',
  bad: 'text-destructive',
  neutral: 'text-muted-foreground',
}

function DeltaLine({
  delta,
  previousLabel,
  note,
}: Pick<StatCardContent, 'delta' | 'note'> & { previousLabel?: string }) {
  // Always rendered, even empty, so cards with and without a comparison stay the same height.
  if (!delta) {
    return <div className="text-muted-foreground mt-1 h-4 text-xs">{note ?? ' '}</div>
  }
  return (
    <div className="mt-1 flex h-4 items-center gap-1 text-xs tabular-nums">
      <span className={cn('font-medium', TONE_CLASS[delta.tone])}>
        {delta.direction && (
          <span aria-hidden>{delta.direction === 'up' ? '▲' : '▼'} </span>
        )}
        {delta.direction && <span className="sr-only">{delta.direction} </span>}
        {delta.text}
      </span>
      {previousLabel && <span className="text-muted-foreground">vs {previousLabel}</span>}
    </div>
  )
}

export function StatCard({
  label,
  formatted,
  delta,
  previousLabel,
  note,
  title,
}: StatCardContent & { previousLabel?: string }) {
  return (
    <Card title={title}>
      <CardContent>
        <div className="text-muted-foreground text-xs font-medium tracking-wide uppercase">
          {label}
        </div>
        <div className="mt-1 flex items-baseline gap-1.5">
          <span className="text-2xl font-semibold tabular-nums">{formatted?.value ?? '—'}</span>
          {formatted?.unit && (
            <span className="text-muted-foreground text-sm">{formatted.unit}</span>
          )}
        </div>
        <DeltaLine delta={delta} previousLabel={previousLabel} note={note} />
      </CardContent>
    </Card>
  )
}

/** Mirrors StatCard's box row for row -- a 16px label, a 32px value line and the 16px delta
 * line, with the same mt-1 between them -- so the card is the same 104px before and after the
 * numbers arrive. Sizing the placeholder blocks alone isn't enough: a `space-y-2` stack of
 * them came to 100px, and four pixels per card is two shifted rows on a wide screen, on every
 * range change rather than only at startup.
 */
export function StatCardSkeleton() {
  return (
    <Card>
      <CardContent>
        <div className="flex h-4 items-center">
          <Skeleton className="h-3 w-20" />
        </div>
        <div className="mt-1 flex h-8 items-center">
          <Skeleton className="h-6 w-24" />
        </div>
        <div className="mt-1 flex h-4 items-center">
          <Skeleton className="h-3 w-16" />
        </div>
      </CardContent>
    </Card>
  )
}
