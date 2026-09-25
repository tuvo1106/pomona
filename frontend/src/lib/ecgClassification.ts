import type { badgeVariants } from '@/components/ui/badge'
import type { VariantProps } from 'class-variance-authority'

type BadgeVariant = NonNullable<VariantProps<typeof badgeVariants>['variant']>

export interface ClassificationDisplay {
  label: string
  /** Render as a muted dot and muted text instead of a filled badge. */
  quiet: boolean
  /** Only meaningful when `quiet` is false. */
  variant: BadgeVariant
}

/** How a recording's classification should be shown.
 *
 * The rule is one line: the normal result is stated quietly, everything else gets a badge.
 * Sinus Rhythm is what an Apple Watch ECG says almost every time, so a filled high-contrast
 * pill on it meant a list of forty identical badges -- the emphasis all landed on the
 * normal case, and an Atrial Fibrillation row had nothing to stand out against. Made quiet,
 * the badges left in the list are exactly the recordings worth a second look.
 *
 * Everything unrecognised is treated as worth showing rather than as normal, deliberately:
 * watchOS emits classifications this app has never seen (High Heart Rate, Low Heart Rate,
 * Unclassifiable, ...), and those are abnormal results far more often than not. Guessing
 * "normal" for an unknown string would be the one wrong way to be wrong here.
 */
export function classificationDisplay(classification: string | null): ClassificationDisplay {
  if (classification === 'Sinus Rhythm') {
    return { label: classification, quiet: true, variant: 'secondary' }
  }
  if (classification?.includes('Fibrillation')) {
    return { label: classification, quiet: false, variant: 'destructive' }
  }
  // Inconclusive, Poor Recording, and anything watchOS adds later. Filled but neutral:
  // "look at this" without --destructive's claim that something is wrong.
  return { label: classification ?? 'Unknown', quiet: false, variant: 'secondary' }
}
