import type { TimeseriesPoint } from '@/api/client'
import { formatAxisNumber } from '@/lib/formatNumber'

/** "Lines -> value at the end" / "Bars -> value on the cap" per dataviz mark spec: label the
 * one point that matters (the most recent value) rather than every point, which the spec
 * calls out directly as chaos that goes unread. These are recharts custom dot/label render
 * props -- called once per data point, and only draw anything at `labelIndex`. That's
 * normally the last point; a series with a partial last bucket passes the last *complete*
 * one instead (see lib/partialBuckets.ts), since the partial value is the misleading one.
 */

interface DotProps {
  cx?: number
  cy?: number
  index?: number
  /** An `<Area>` hands its dots `[baseValue, value]` rather than the bare number a `<Line>`
   * passes (recharts' `computeArea`), so every reader goes through `dotValue` below.
   */
  value?: number | readonly (number | null)[] | null
  payload?: TimeseriesPoint
}

/** The point's own value, whichever series shape produced it. Returns null for anything that
 * isn't a finite number, so a caller can treat "no value" and "not a number" alike.
 */
function dotValue(value: DotProps['value']): number | null {
  const raw = Array.isArray(value) ? value[value.length - 1] : value
  return typeof raw === 'number' && Number.isFinite(raw) ? raw : null
}

function endValueLabel(cx: number, cy: number, value: number) {
  // Flip the label below the point when it's close to the plot's top edge, so it
  // never gets clipped by the chart card's own boundary.
  const labelY = cy < 20 ? cy + 16 : cy - 10
  return (
    <text x={cx} y={labelY} textAnchor="end" fontSize={11} fontWeight={600} fill="var(--foreground)">
      {formatAxisNumber(value)}
    </text>
  )
}

export function makeLineEndDot(color: string, labelIndex: number) {
  return ({ cx, cy, index, value }: DotProps) => {
    const key = `end-dot-${index}`
    const point = dotValue(value)
    if (index !== labelIndex || cx == null || cy == null || point == null) {
      return <g key={key} />
    }
    return (
      <g key={key}>
        <circle cx={cx} cy={cy} r={4} fill={color} stroke="var(--card)" strokeWidth={2} />
        {endValueLabel(cx, cy, point)}
      </g>
    )
  }
}

/** Dot renderer for the dashed partial-bucket series: a hollow ring on each partial point (a
 * filled dot would read as a real, final value), and the end label too when every point is
 * partial and `labelIndex` therefore lands on one.
 */
export function makePartialDot(color: string, labelIndex: number) {
  return ({ cx, cy, index, value, payload }: DotProps) => {
    const key = `partial-dot-${index}`
    const point = dotValue(value)
    if (!payload?.partial || cx == null || cy == null || point == null) {
      return <g key={key} />
    }
    return (
      <g key={key}>
        <circle cx={cx} cy={cy} r={3.5} fill="var(--card)" stroke={color} strokeWidth={1.5} />
        {index === labelIndex && endValueLabel(cx, cy, point)}
      </g>
    )
  }
}

interface BarLabelProps {
  x?: string | number
  y?: string | number
  width?: string | number
  index?: number
  value?: string | number | boolean | null
}

export function barEndLabel(labelIndex: number) {
  return ({ x, y, width, index, value }: BarLabelProps) => {
    if (index !== labelIndex || x == null || y == null || width == null || value == null) {
      return null
    }
    const numX = Number(x)
    const numY = Number(y)
    const numWidth = Number(width)
    const numValue = Number(value)
    const labelY = numY < 14 ? numY + 14 : numY - 6
    // Right-aligned to the bar's right edge, never centered on it: centering spills past the
    // plot edge on the rightmost bar, and on a dense chart it overhangs the next bar along
    // (the faded partial one, when the label has moved back to the last complete bar). The
    // line label is end-anchored for the same reason.
    return (
      <text
        x={numX + numWidth}
        y={labelY}
        textAnchor="end"
        fontSize={11}
        fontWeight={600}
        fill="var(--foreground)"
      >
        {formatAxisNumber(numValue)}
      </text>
    )
  }
}
