import { useEffect, useMemo, useRef, useState, type MouseEvent } from 'react'
import type { ActivitySummary } from '@/api/client'
import {
  buildCalendar,
  formatCompletion,
  formatDayLabel,
  heatBinColor,
  HEAT_BIN_COLORS,
  ringsForDay,
  type CalendarCell,
} from '@/lib/activityRings'

const CELL_GAP = 3
/** Room for the Mon/Wed/Fri labels down the left, and the month strip across the top. */
const LEFT_GUTTER = 30
const TOP_GUTTER = 16
/** Sunday-first, labelling alternate rows only -- seven labels in a small row would collide. */
const WEEKDAY_LABELS = [null, 'Mon', null, 'Wed', null, 'Fri', null]

/** Roughly the card's inner width at the dashboard's max width; only used to decide how big
 * the cells may grow, so it doesn't need to be exact.
 */
const TARGET_WIDTH = 900
const MIN_CELL = 11
const MAX_CELL = 26
/** Widest rendered month abbreviation at 10px, used only to decide whether one still fits. */
const MONTH_LABEL_WIDTH = 22

/** Cells grow to fill the card on short ranges and shrink towards a still-clickable floor as
 * the column count rises (MAX_CALENDAR_WEEKS caps that at a year's worth); where the grid
 * still doesn't fit -- a narrow screen -- it scrolls sideways rather than shrinking further.
 * Derived from the column count rather than a measured container, so there's no resize
 * observer in the render path.
 */
function cellSizeFor(weeks: number): number {
  if (weeks <= 0) return MAX_CELL
  const fit = Math.floor((TARGET_WIDTH - LEFT_GUTTER) / weeks) - CELL_GAP
  return Math.max(MIN_CELL, Math.min(MAX_CELL, fit))
}

/** Enough for the widest row the tooltip renders ("12,345 / 12,345 Cal" plus its label and
 * percentage). Only used to decide which side of the cell to open on, so an approximation is
 * fine -- and the box is `whitespace-nowrap`, so it never exceeds this by much.
 */
const TOOLTIP_WIDTH = 230

interface HoverState {
  cell: CalendarCell
  /** Offsets within the card, not within the SVG: the grid sits in a horizontally scrollable
   * box while the tooltip is anchored outside it, so an SVG x would drift by the scroll
   * offset once a long calendar is scrolled. `left` is measured from the card's left edge,
   * `right` from its right, so either side can anchor the box.
   */
  left: number
  right: number
  y: number
  flip: boolean
}

export function ActivityHeatmap({
  rows,
  range,
}: {
  rows: ActivitySummary[]
  range: { start?: string; end?: string }
}) {
  const { weeks, monthLabels, windowedFrom } = useMemo(
    () => buildCalendar(rows, range),
    [rows, range],
  )
  const [hover, setHover] = useState<HoverState | null>(null)
  const wrapper = useRef<HTMLDivElement>(null)
  const scroller = useRef<HTMLDivElement>(null)

  // Open on the newest weeks, not the oldest. A calendar wider than its card starts at
  // scrollLeft 0, which on a long range lands the reader a year back and leaves today off
  // screen -- the opposite of every other card here, which all end at the newest data. Keyed
  // on the week count so a range change re-pins the scroll instead of keeping the old offset.
  useEffect(() => {
    const box = scroller.current
    if (box) box.scrollLeft = box.scrollWidth
  }, [weeks.length])

  function showTooltip(event: MouseEvent<SVGGElement>, day: CalendarCell) {
    const box = wrapper.current?.getBoundingClientRect()
    if (!box) return
    // The tooltip is positioned inside `box`, but what can actually clip it is the card --
    // it's the `overflow-hidden` ancestor. Those used to be the same rectangle; since this
    // component became a flex item sharing its row with the rings summary, `box` can end
    // well short of the card's edge. Deciding the flip on `box` would turn it on for cells
    // with plenty of room to their right and swing the panel back over the summary.
    const clip = wrapper.current?.closest('[data-slot="card-content"]')?.getBoundingClientRect()
    const limit = clip ?? box
    // currentTarget, not target: the group also holds the all-rings-closed dot, and entering
    // over the dot would otherwise measure the dot instead of the cell.
    const target = event.currentTarget.getBoundingClientRect()
    setHover({
      cell: day,
      left: target.right - box.left,
      right: box.right - target.left,
      y: target.top - box.top,
      // Flip to the left of the cell when a right-hand tooltip would run past the card, which
      // clips it: Card is overflow-hidden, and the rightmost column -- the newest days, the
      // ones most worth hovering -- sits at the very edge on a full-width calendar.
      flip: limit.right - target.right < TOOLTIP_WIDTH + 12,
    })
  }

  if (weeks.length === 0) return null

  const cell = cellSizeFor(weeks.length)
  const step = cell + CELL_GAP
  const width = LEFT_GUTTER + weeks.length * step
  const height = TOP_GUTTER + 7 * step

  return (
    // `width` as the flex basis, so the card's row can lay this out against the summary
    // beside it: a short range is narrow enough to sit next to it, a long one asks for more
    // than is left and wraps to a row of its own. `flexGrow` lets it take the slack rather
    // than leaving a gap, and `minWidth: 0` lets it be squeezed below its basis on a narrow
    // screen instead of forcing the card wider -- the scroller below handles the overflow.
    <div
      className="relative"
      ref={wrapper}
      style={{ flexBasis: width, flexGrow: 1, minWidth: 0 }}
    >
      {/* A full-width calendar doesn't fit a phone, so the grid scrolls sideways rather than
          shrinking its cells below a clickable size. */}
      <div className="overflow-x-auto pb-1" ref={scroller}>
        {/* `mx-auto` centres the grid in a box wider than it is -- which is the usual case
            once flexGrow hands it the row's slack. An auto margin resolves to zero when the
            child overflows, so a calendar too wide for its box still starts flush left and
            scrolls from there. */}
        <svg
          className="mx-auto block"
          width={width}
          height={height}
          viewBox={`0 0 ${width} ${height}`}
          role="img"
          aria-label={`Calendar of daily Move goal completion, ${weeks.length} weeks`}
          onMouseLeave={() => setHover(null)}
        >
          {monthLabels.map(({ week, label }) => {
            const labelX = LEFT_GUTTER + week * step
            // A month starting in one of the last columns has no room left for its name, and
            // the svg clips at `width`; drop it rather than render a cropped "Se".
            if (labelX + MONTH_LABEL_WIDTH > width) return null
            return (
              <text
                key={`${week}-${label}`}
                x={labelX}
                y={TOP_GUTTER - 6}
                fontSize={10}
                fill="var(--muted-foreground)"
              >
                {label}
              </text>
            )
          })}

          {WEEKDAY_LABELS.map((label, weekday) =>
            label ? (
              <text
                key={label}
                x={0}
                y={TOP_GUTTER + weekday * step + cell / 2 + 3}
                fontSize={10}
                fill="var(--muted-foreground)"
              >
                {label}
              </text>
            ) : null,
          )}

          {weeks.map((week, weekIndex) =>
            week.map((day, weekday) => {
              if (!day) return null
              const x = LEFT_GUTTER + weekIndex * step
              const y = TOP_GUTTER + weekday * step
              const fill = heatBinColor(day.bin)
              return (
                <g key={day.date} onMouseEnter={(event) => showTooltip(event, day)}>
                  <rect
                    x={x}
                    y={y}
                    width={cell}
                    height={cell}
                    rx={2}
                    fill={fill ?? 'var(--muted)'}
                    className={fill ? undefined : 'stroke-border'}
                    strokeWidth={fill ? 0 : 1}
                  />
                  {/* All three rings closed. The dot can only land on the ramp's strongest
                      step (a closed Move ring is by definition >=100%), so a card-coloured
                      dot always has the contrast to read. */}
                  {day.closed && (
                    <circle
                      cx={x + cell / 2}
                      cy={y + cell / 2}
                      r={Math.max(2, cell * 0.16)}
                      fill="var(--card)"
                      pointerEvents="none"
                      aria-hidden
                    />
                  )}
                </g>
              )
            }),
          )}
        </svg>
      </div>

      <HeatmapScale windowedFrom={windowedFrom} />

      {hover && <HeatmapTooltip hover={hover} />}
    </div>
  )
}

function HeatmapScale({ windowedFrom }: { windowedFrom: string | null }) {
  return (
    // Centred to share the grid's own centre line: the grid is centred in a box that is
    // usually wider than it, and a left-aligned caption under it reads as belonging to
    // something else. Both fall flush left together once the grid fills the box.
    <div className="text-muted-foreground mt-2 flex flex-wrap items-center justify-center gap-x-4 gap-y-1 text-xs">
      <span className="flex items-center gap-1.5">
        Less
        <span
          className="border-border size-2.5 rounded-[2px] border"
          style={{ backgroundColor: 'var(--muted)' }}
        />
        {HEAT_BIN_COLORS.map((color) => (
          <span
            key={color}
            className="size-2.5 rounded-[2px]"
            style={{ backgroundColor: color }}
          />
        ))}
        More
      </span>
      <span className="flex items-center gap-1.5">
        <span
          className="flex size-2.5 items-center justify-center rounded-[2px]"
          style={{ backgroundColor: 'var(--activity-heat-4)' }}
        >
          <span className="size-1 rounded-full" style={{ backgroundColor: 'var(--card)' }} />
        </span>
        All rings closed
      </span>
      <span>
        Shade shows Move goal completion.
        {windowedFrom &&
          ` Calendar starts ${formatDayLabel(windowedFrom)}; the rings and the closed-day count cover the whole range.`}
      </span>
    </div>
  )
}

function HeatmapTooltip({ hover }: { hover: HoverState }) {
  const { cell } = hover
  const rings = ringsForDay(cell.row)
  return (
    <div
      className="bg-popover text-popover-foreground border-border pointer-events-none absolute z-10 rounded-md border px-3 py-2 text-xs shadow-md"
      style={
        hover.flip
          ? { right: hover.right + 8, top: hover.y, maxWidth: TOOLTIP_WIDTH }
          : { left: hover.left + 8, top: hover.y, maxWidth: TOOLTIP_WIDTH }
      }
    >
      <div className="font-medium">{formatDayLabel(cell.date)}</div>
      {cell.row == null ? (
        <div className="text-muted-foreground mt-1">No activity data</div>
      ) : (
        <dl className="mt-1 grid grid-cols-[auto_1fr_auto] items-baseline gap-x-2 gap-y-0.5">
          {rings.map((ring) => (
            <div key={ring.key} className="contents">
              <dt className="flex items-center gap-1.5">
                <span
                  aria-hidden
                  className="size-2 rounded-full"
                  style={{ backgroundColor: ring.color }}
                />
                {ring.label}
              </dt>
              <dd className="text-muted-foreground tabular-nums whitespace-nowrap">
                {ring.value != null ? Math.round(ring.value).toLocaleString('en-US') : '—'}
                {ring.goal != null && ` / ${Math.round(ring.goal).toLocaleString('en-US')}`}{' '}
                {ring.unit}
              </dd>
              <dd className="text-right tabular-nums">{formatCompletion(ring.completion)}</dd>
            </div>
          ))}
        </dl>
      )}
    </div>
  )
}
