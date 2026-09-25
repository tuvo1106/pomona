import { formatCompletion, isClosed, type Ring } from '@/lib/activityRings'

/** Three concentric progress arcs, Move outermost. Deliberately not animated: a draw-in is
 * rAF-driven, that loop is suspended entirely in a hidden document (see "Verifying your
 * work" in docs/UI-BACKLOG.md), and an arc left part-way round reads as a real value rather
 * than as an unfinished animation -- a ring is a quantity, not a decoration.
 */
export function ActivityRingsGlyph({
  rings,
  size = 116,
  strokeWidth = 11,
  gap = 3,
}: {
  rings: Ring[]
  size?: number
  strokeWidth?: number
  gap?: number
}) {
  const center = size / 2
  const label = rings
    .map((ring) => `${ring.label} ${formatCompletion(ring.completion)} of goal`)
    .join(', ')

  return (
    <svg
      width={size}
      height={size}
      viewBox={`0 0 ${size} ${size}`}
      role="img"
      aria-label={label}
      className="shrink-0"
    >
      {/* -90deg so every arc starts at 12 o'clock rather than 3 o'clock. */}
      <g transform={`rotate(-90 ${center} ${center})`}>
        {rings.map((ring, i) => {
          const radius = center - strokeWidth / 2 - i * (strokeWidth + gap)
          if (radius <= 0) return null
          // Arcs are capped at one full turn: past 100% an uncapped arc would lap the track
          // and read as a *lower* value than it is. The legend carries the real percentage.
          const fraction = Math.max(0, Math.min(1, ring.completion ?? 0))
          return (
            <g key={ring.key}>
              {/* Track: the same hue, faded -- a lighter step of the ring's own ramp, so an
                  unclosed ring still reads as belonging to its metric. */}
              <circle
                cx={center}
                cy={center}
                r={radius}
                fill="none"
                stroke={ring.color}
                strokeWidth={strokeWidth}
                opacity={0.18}
              />
              {fraction > 0 && (
                // pathLength=1 lets the dash array be the completion fraction directly,
                // with no 2*pi*r arithmetic to keep in step with the radius above.
                <circle
                  cx={center}
                  cy={center}
                  r={radius}
                  fill="none"
                  stroke={ring.color}
                  strokeWidth={strokeWidth}
                  strokeLinecap="round"
                  pathLength={1}
                  strokeDasharray={`${fraction} 1`}
                />
              )}
            </g>
          )
        })}
      </g>
    </svg>
  )
}

/** The rings' legend: identity is never color alone, so each row pairs the swatch with a
 * name and the value that the arc encodes.
 */
export function ActivityRingsLegend({ rings }: { rings: Ring[] }) {
  return (
    <dl className="grid flex-1 grid-cols-[auto_1fr_auto] items-baseline gap-x-3 gap-y-1.5 text-sm">
      {rings.map((ring) => (
        <div key={ring.key} className="contents">
          <dt className="flex items-center gap-2">
            <span
              aria-hidden
              className="size-2.5 rounded-full"
              style={{ backgroundColor: ring.color }}
            />
            <span className="text-foreground">{ring.label}</span>
          </dt>
          <dd className="text-muted-foreground tabular-nums">
            {ring.value != null ? Math.round(ring.value).toLocaleString('en-US') : '—'}
            {ring.goal != null && ` / ${Math.round(ring.goal).toLocaleString('en-US')}`}{' '}
            {ring.unit}
          </dd>
          <dd className="text-foreground text-right font-medium tabular-nums">
            {formatCompletion(ring.completion)}
            {isClosed(ring) && (
              <>
                <span aria-hidden> ✓</span>
                <span className="sr-only"> (closed)</span>
              </>
            )}
          </dd>
        </div>
      ))}
    </dl>
  )
}
