import { Badge } from '@/components/ui/badge'
import { classificationDisplay } from '@/lib/ecgClassification'

/** A recording's rhythm classification, shown the way lib/ecgClassification.ts decides:
 * quietly for the normal result, as a badge for anything else. Shared by the list rows and
 * the waveform's own header so a recording can't be loud in one place and quiet in the
 * other.
 */
export function ClassificationTag({ classification }: { classification: string | null }) {
  const { label, quiet, variant } = classificationDisplay(classification)

  if (quiet) {
    return (
      <span className="text-muted-foreground flex items-center gap-1.5 text-xs">
        {/* A dot, not a bare line of text: it holds the same left edge as the badges on the
            rows around it, so the column reads as one column. */}
        <span aria-hidden className="bg-muted-foreground/50 size-1.5 shrink-0 rounded-full" />
        {label}
      </span>
    )
  }

  return <Badge variant={variant}>{label}</Badge>
}
