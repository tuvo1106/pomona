/** A legend for a multi-series chart, keyed by a short line swatch.
 *
 * recharts' default `<Legend>` paints each entry's *text* in that series' color, which is
 * the one thing this app's charts never do: identity rides on a mark beside the words, never
 * on the words themselves (see ChartTooltip, and the group dot in AllCharts). Colored label
 * text is also the first thing to fail for a reader who can't separate the two hues -- the
 * swatch survives where the tinted text doesn't, because it sits next to its own label.
 *
 * Pass it to recharts as an element -- `<Legend content={<ChartLegend entries={...} />} />`
 * -- so the entries are the ones given here, in that order, rather than whatever order the
 * `<Line>`s happen to be declared in.
 */

export interface LegendEntry {
  name: string
  color: string
}

export function ChartLegend({ entries }: { entries: LegendEntry[] }) {
  return (
    <ul className="text-muted-foreground flex list-none justify-center gap-4 text-xs">
      {entries.map((entry) => (
        <li key={entry.name} className="flex items-center gap-1.5">
          {/* Matches the tooltip's swatch: a 10x2 line, not a filled box, so it reads as
              "this line on the chart". */}
          <span
            aria-hidden
            className="inline-block h-0.5 w-2.5 shrink-0"
            style={{ backgroundColor: entry.color }}
          />
          {entry.name}
        </li>
      ))}
    </ul>
  )
}
