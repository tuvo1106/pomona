import type { TooltipContentProps } from 'recharts'
import type { NameType, ValueType } from 'recharts/types/component/DefaultTooltipContent'
import type { TimeseriesPoint } from '@/api/client'
import { formatAxisNumber } from '@/lib/formatNumber'
import { partialNote } from '@/lib/partialBuckets'

/** recharts' default tooltip content tints the whole row -- both the series name AND the
 * value -- in the series color, which violates "text never wears the data color" and buries
 * the value (the thing the reader actually wants) at the same visual weight as its label.
 * This renders the value in normal text-token color as the strong element, the label
 * secondary, and keys identity with a short line swatch instead of a filled box.
 */
export function ChartTooltip({
  active,
  payload,
  label,
  labelFormatter,
}: TooltipContentProps<ValueType, NameType>) {
  if (!active || !payload || payload.length === 0) return null

  // A series drawn as two lines -- solid for complete buckets, dashed for partial ones (see
  // lib/partialBuckets.ts) -- has both at the point where they join. They share a `name`, so
  // keep the first entry per name and show the value once.
  const seen = new Set<unknown>()
  const entries = payload.filter((entry) => {
    if (seen.has(entry.name)) return false
    seen.add(entry.name)
    return true
  })
  const singleSeries = entries.length === 1
  // Recharts only auto-applies labelFormatter to its own default tooltip content -- a
  // custom `content` component (this one) gets the raw label and must apply it itself.
  const displayLabel = labelFormatter ? labelFormatter(label, payload) : label
  const note = partialNote((payload[0]?.payload as TimeseriesPoint | undefined)?.partial)

  return (
    <div
      style={{
        background: 'var(--popover)',
        color: 'var(--popover-foreground)',
        border: '1px solid var(--border)',
        borderRadius: 'var(--radius-md)',
        fontSize: 12,
        padding: '8px 10px',
        minWidth: 96,
      }}
    >
      <div style={{ color: 'var(--muted-foreground)', marginBottom: 4 }}>{displayLabel}</div>
      {entries.map((entry, i) => {
        const value = typeof entry.value === 'number' ? formatAxisNumber(entry.value) : entry.value
        return (
          <div
            key={typeof entry.dataKey === 'function' ? i : (entry.dataKey ?? i)}
            style={{ display: 'flex', alignItems: 'center', gap: 6 }}
          >
            <span
              aria-hidden
              style={{
                display: 'inline-block',
                width: 10,
                height: 2,
                background: entry.color,
                flexShrink: 0,
              }}
            />
            {!singleSeries && (
              <span style={{ color: 'var(--muted-foreground)' }}>{entry.name}</span>
            )}
            <span style={{ marginLeft: 'auto', fontWeight: 600 }}>{value}</span>
          </div>
        )
      })}
      {note && (
        <div style={{ color: 'var(--muted-foreground)', marginTop: 4, fontStyle: 'italic' }}>
          {note}
        </div>
      )}
    </div>
  )
}
