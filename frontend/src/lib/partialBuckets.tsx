import { Rectangle, type BarShapeProps } from 'recharts'
import type { PartialKind, TimeseriesPoint } from '@/api/client'
import { formatAxisNumber } from '@/lib/formatNumber'

/** A point split into the two line series a chart draws: `solid` holds complete buckets,
 * `dashed` holds partial buckets plus the complete neighbour each one joins to, so the dashed
 * segment starts where the solid line ends. Null elsewhere, which recharts draws as a gap.
 */
export interface SplitPoint extends TimeseriesPoint {
  solid: number | null
  dashed: number | null
}

export function splitPartial(points: TimeseriesPoint[]): SplitPoint[] {
  return points.map((p, i) => {
    const touchesPartial =
      Boolean(p.partial) || Boolean(points[i - 1]?.partial) || Boolean(points[i + 1]?.partial)
    return {
      ...p,
      solid: p.partial ? null : p.value,
      dashed: touchesPartial ? p.value : null,
    }
  })
}

/** Index of the point to label: the last complete one, since a partial bucket's value is the
 * misleading one. Falls back to the last point with a value when every point is partial
 * (e.g. a single "Today" bucket), so the chart still shows its one number. -1 if none.
 */
export function labelIndex(points: TimeseriesPoint[]): number {
  for (let i = points.length - 1; i >= 0; i--) {
    if (!points[i].partial && points[i].value != null) return i
  }
  for (let i = points.length - 1; i >= 0; i--) {
    if (points[i].value != null) return i
  }
  return -1
}

export function partialNote(kind: PartialKind | null | undefined): string | null {
  if (kind === 'in_progress') return 'In progress'
  if (kind === 'truncated') return 'Partial period'
  return null
}

/** Table-view suffix so the table twin carries the same caveat as the chart. */
export function withPartialSuffix(text: string, kind: PartialKind | null | undefined): string {
  const note = partialNote(kind)
  return note ? `${text} (${note.toLowerCase()})` : text
}

/** A timeseries point's table cell: its value, noting a bucket still in progress. */
export function timeseriesCells(point: TimeseriesPoint): { value: string } {
  return {
    value:
      point.value != null ? withPartialSuffix(formatAxisNumber(point.value), point.partial) : '—',
  }
}

/** Opacity of a partial bucket's bar. Faded, not hidden: the value is real, just incomplete. */
const PARTIAL_BAR_OPACITY = 0.4

/** A `<Bar shape>` that draws a partial bucket at PARTIAL_BAR_OPACITY -- the bar-chart form of
 * the dashed tail `splitPartial` gives a line -- so its short bar doesn't read as a real drop.
 * A `shape` rather than per-bar `<Cell>`s, which recharts 3 deprecates.
 */
export function partialBarShape(props: BarShapeProps) {
  const partial = (props.payload as { partial?: unknown } | undefined)?.partial
  return <Rectangle {...props} fillOpacity={partial ? PARTIAL_BAR_OPACITY : 1} />
}
