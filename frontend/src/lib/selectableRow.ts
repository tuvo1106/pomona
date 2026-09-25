/** Shared selected/hover/focus styling for the clickable master-list rows on the Routes and ECG
 * pages. Selection is the accent tint plus a 2px accent bar on the leading edge -- the bar
 * keeps the selected row identifiable by shape, not only by a pale background tint.
 */
export function selectableRowClass(selected: boolean): string {
  return [
    'focus-visible:ring-ring/50 outline-none focus-visible:ring-2 focus-visible:ring-inset',
    selected
      ? 'bg-accent text-accent-foreground shadow-[inset_2px_0_0_var(--color-primary)]'
      : 'hover:bg-accent/50',
  ].join(' ')
}
