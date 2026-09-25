import type { ReactNode } from 'react'
import { Maximize2 } from 'lucide-react'
import { BucketSelect } from '@/components/BucketSelect'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import {
  CHART_RANGE_OPTIONS,
  type ChartDialog,
  type ChartRangeChoice,
} from '@/hooks/useChartDialog'
import type { StatEntry } from '@/lib/seriesStats'

export interface TableColumn {
  key: string
  header: string
  /** Right-aligned with tabular figures, header included (see ui/table.tsx). */
  numeric?: boolean
}

interface ExpandableChartCardProps {
  title: string
  /** The metric's unit, already display-ready (see lib/units.ts). Shown beside the title in
   * muted text rather than parenthesised into it: the name is what a reader scans for
   * across ~40 cards, and "Steps (count)" buried it behind HealthKit's own bookkeeping.
   */
  unit?: string | null
  renderChart: (height: number) => ReactNode
  /** The same series as a table -- every chart's table-view twin, so a value is always
   * reachable without hovering (a tooltip must never be the only way to read a number).
   */
  tableColumns: TableColumn[]
  tableRows: Record<string, string | number>[]
  /** Open state plus the dialog's own range/bucket override (see useChartDialog). Held by
   * the caller because the caller is what runs the query these change.
   */
  dialog: ChartDialog
  /** Summary numbers for the strip above the expanded chart, formatted by the caller --
   * it owns the unit and the number format. Omit for a series with no single summary
   * (several stacked components, say), and the strip isn't rendered.
   */
  stats?: StatEntry[]
}

const PREVIEW_HEIGHT = 200
const EXPANDED_HEIGHT = 420

/** Title with its unit trailing in muted text. One component so the card and the expanded
 * dialog can't drift apart; the separator is a middle dot rather than parentheses, which
 * read as an aside about the title instead of a property of the numbers.
 */
function TitleWithUnit({ title, unit }: { title: string; unit?: string | null }) {
  return (
    <>
      {title}
      {unit && <span className="text-muted-foreground ml-1.5 font-normal">· {unit}</span>}
    </>
  )
}

/** Latest / min / max / mean across the top of the expanded chart. Plain columns rather
 * than four cards: they're one series read four ways, not four separate metrics.
 */
function SummaryStrip({ stats }: { stats: StatEntry[] }) {
  return (
    <dl className="border-border flex flex-wrap gap-x-8 gap-y-3 border-b pb-3">
      {stats.map((stat) => (
        <div key={stat.label}>
          <dt className="text-muted-foreground text-xs">{stat.label}</dt>
          <dd className="text-sm font-medium tabular-nums">{stat.value}</dd>
        </div>
      ))}
    </dl>
  )
}

/** The dialog's own range and bucket pickers, which move this one chart without moving the
 * dashboard under it. Defaults to "Dashboard range", so an expanded chart opens showing
 * exactly what its card showed.
 */
function RangeControls({ dialog }: { dialog: ChartDialog }) {
  return (
    <div className="flex flex-wrap items-center gap-2">
      {dialog.rangeChoice === 'custom' && (
        <div className="flex items-center gap-1">
          <input
            type="date"
            aria-label="Start date"
            value={dialog.customRange.start ?? ''}
            max={dialog.customRange.end}
            onChange={(e) =>
              dialog.setCustomRange({ ...dialog.customRange, start: e.target.value })
            }
            className="border-input bg-background h-8 rounded-md border px-2 text-sm"
          />
          <span className="text-muted-foreground text-sm">to</span>
          <input
            type="date"
            aria-label="End date"
            value={dialog.customRange.end ?? ''}
            min={dialog.customRange.start}
            onChange={(e) =>
              dialog.setCustomRange({ ...dialog.customRange, end: e.target.value })
            }
            className="border-input bg-background h-8 rounded-md border px-2 text-sm"
          />
        </div>
      )}
      <Select
        value={dialog.rangeChoice}
        onValueChange={(value) => dialog.setRangeChoice(value as ChartRangeChoice)}
      >
        <SelectTrigger className="w-[160px]" aria-label="Range for this chart">
          <SelectValue />
        </SelectTrigger>
        <SelectContent>
          {CHART_RANGE_OPTIONS.map((option) => (
            <SelectItem key={option.value} value={option.value}>
              {option.label}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
      <BucketSelect
        value={dialog.bucketChoice}
        onChange={dialog.setBucketChoice}
        aria-label="Bucket for this chart"
      />
      {/* Only once there's something to undo -- a permanently visible Reset reads as a
          control that does something, on a dialog that has just opened at its default. */}
      {dialog.overridden && (
        <Button type="button" variant="ghost" size="sm" onClick={dialog.reset}>
          Reset
        </Button>
      )}
    </div>
  )
}

export function ExpandableChartCard({
  title,
  unit,
  renderChart,
  tableColumns,
  tableRows,
  dialog,
  stats,
}: ExpandableChartCardProps) {
  return (
    <>
      <Card
        role="button"
        tabIndex={0}
        onClick={() => dialog.setOpen(true)}
        onKeyDown={(e) => {
          if (e.key === 'Enter' || e.key === ' ') {
            e.preventDefault()
            dialog.setOpen(true)
          }
        }}
        aria-label={`${title}: expand`}
        className="group hover:border-primary/50 focus-visible:border-ring focus-visible:ring-ring/50 relative cursor-pointer transition-shadow outline-none hover:shadow-md focus-visible:ring-3"
      >
        {/* pr-9 clears the expand icon below, which is absolutely positioned at the same
            top as this row -- a long title plus its unit would otherwise run under it in the
            three-column grid. DialogHeader carries the same allowance. */}
        <CardHeader className="pr-9">
          <CardTitle className="text-sm font-medium">
            <TitleWithUnit title={title} unit={unit} />
          </CardTitle>
        </CardHeader>
        {/* The card's only affordance used to be a hover shadow, which says "interactive"
            but not what the interaction is, and says nothing at all on a touch screen.
            aria-hidden: the card itself already carries the accessible name and the click
            handler, so announcing the icon would be a second control that isn't one. */}
        <Maximize2
          aria-hidden
          className="text-muted-foreground/60 group-hover:text-muted-foreground absolute top-4 right-4 size-3.5 transition-colors"
        />
        <CardContent>{renderChart(PREVIEW_HEIGHT)}</CardContent>
      </Card>

      <Dialog open={dialog.open} onOpenChange={dialog.setOpen}>
        <DialogContent className="sm:max-w-3xl">
          <DialogHeader className="space-y-0 pr-8">
            <DialogTitle>
              <TitleWithUnit title={title} unit={unit} />
            </DialogTitle>
          </DialogHeader>

          <Tabs defaultValue="chart" className="gap-4">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <RangeControls dialog={dialog} />
              <TabsList>
                <TabsTrigger value="chart">Chart</TabsTrigger>
                <TabsTrigger value="table">Table</TabsTrigger>
              </TabsList>
            </div>

            <TabsContent value="chart" className="space-y-4">
              {stats && stats.length > 0 && <SummaryStrip stats={stats} />}
              {renderChart(EXPANDED_HEIGHT)}
            </TabsContent>

            <TabsContent value="table">
              {/* This scroll area stays. A dialog is a bounded surface with no page scrolling
                  behind it to steal -- Radix locks the body while it's open -- so capping the
                  height here traps nothing, and without the cap a long series would run off
                  the bottom of the viewport with no way to reach it. The cap goes on the
                  table's own container rather than a wrapper around it, or the sticky header
                  below scrolls away with the rows (see ui/table.tsx). */}
              <Table containerClassName="max-h-[420px] overflow-y-auto">
                {/* Sticky head, because this one does scroll: the column names have to stay
                    with the numbers. bg-popover, not bg-card -- that's the dialog's own
                    surface (ui/dialog.tsx). The inset shadow stands in for the row's bottom
                    border, which a sticky <th> loses under border-collapse. */}
                <TableHeader className="[&_th]:bg-popover [&_th]:sticky [&_th]:top-0 [&_th]:z-10 [&_th]:shadow-[inset_0_-1px_0_var(--border)]">
                  <TableRow>
                    {tableColumns.map((col) => (
                      <TableHead key={col.key} numeric={col.numeric}>
                        {col.header}
                      </TableHead>
                    ))}
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {tableRows.length === 0 ? (
                    <TableRow>
                      <TableCell colSpan={tableColumns.length} className="text-muted-foreground">
                        No data in this range.
                      </TableCell>
                    </TableRow>
                  ) : (
                    tableRows.map((row, i) => (
                      <TableRow key={row.date ?? i}>
                        {tableColumns.map((col) => (
                          <TableCell key={col.key} numeric={col.numeric}>
                            {row[col.key]}
                          </TableCell>
                        ))}
                      </TableRow>
                    ))
                  )}
                </TableBody>
              </Table>
            </TabsContent>
          </Tabs>
        </DialogContent>
      </Dialog>
    </>
  )
}
