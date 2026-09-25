import { useCallback, useMemo, useState } from 'react'

/** A long table shows its first rows and a "Show all" control, instead of scrolling inside
 * its own card.
 *
 * The scroll area it replaces was a real bug, not a style preference: a 360-420px
 * scrollable div inside a page that also scrolls swallows the wheel, and on a 40-row table
 * that div covers most of the card. During the UI review the page could not be scrolled at
 * all while the cursor sat over one. Browsers do chain the scroll to the page once the
 * inner box hits its end, but "scroll through 2,000 rows to get past this card" is the same
 * thing as trapped to anyone using it.
 *
 * Same shape as the dashboard's chart groups (useExpandedGroups): show a preview, name the
 * total on the control, and keep everything reachable in one click. The difference is that
 * this state is not persisted -- expanding a table is "let me look at the rest of this now",
 * where expanding a chart group is a standing choice about how someone reads their own
 * dashboard.
 */
export function useRowPreview<T>(rows: readonly T[], previewCount: number) {
  const [isExpanded, setIsExpanded] = useState(false)

  // Collapse when the underlying rows change -- switching the dashboard from 30 days to All
  // time on an expanded table would otherwise render ~2,000 rows nobody asked for in that
  // range, which is the card-swallows-the-page state this hook exists to avoid. Adjusting
  // state during render, rather than in an effect, so the table never paints expanded once
  // and then collapses. React Query's structural sharing keeps the array identity stable
  // across a background refetch that returns the same data, so this doesn't fire on its own.
  const [renderedRows, setRenderedRows] = useState(rows)
  if (renderedRows !== rows) {
    setRenderedRows(rows)
    setIsExpanded(false)
  }

  const visibleRows = useMemo(
    () => (isExpanded ? rows : rows.slice(0, previewCount)),
    [rows, previewCount, isExpanded],
  )

  const toggle = useCallback(() => setIsExpanded((previous) => !previous), [])

  return {
    visibleRows,
    /** How many rows the preview is holding back; 0 when everything already fits. */
    hiddenCount: Math.max(0, rows.length - previewCount),
    totalCount: rows.length,
    isExpanded,
    toggle,
  }
}
