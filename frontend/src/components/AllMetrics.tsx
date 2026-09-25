import { useQuery } from '@tanstack/react-query'
import { api, type MetricTypeInfo } from '@/api/client'
import { DataCard } from '@/components/DataCard'
import { ShowAllRows } from '@/components/ShowAllRows'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { useRowPreview } from '@/hooks/useRowPreview'
import { formatFullDate } from '@/lib/formatDate'
import { friendlyName } from '@/lib/metricNames'
import { displayUnit } from '@/lib/units'

/** Stable empty array: a fresh `[]` each render would re-slice the preview every time. */
const NO_METRICS: MetricTypeInfo[] = []

/** This list runs to ~100 types. It lives in a drawer that has to be opened deliberately,
 * so anyone here is looking something up -- show a screenful, then the rest on request.
 */
const PREVIEW_ROWS = 10

export function AllMetrics() {
  const { data, isLoading, error } = useQuery({
    queryKey: ['metric-types', 'all-time'],
    queryFn: () => api.metricTypes(),
  })
  const metrics = data ?? NO_METRICS
  const { visibleRows, hiddenCount, totalCount, isExpanded, toggle } = useRowPreview(
    metrics,
    PREVIEW_ROWS,
  )

  return (
    <DataCard
      title={`All tracked metrics${data ? ` (${data.length})` : ''}`}
      isLoading={isLoading}
      error={error}
      isEmpty={metrics.length === 0}
      errorMessage="Failed to load metric list."
      emptyMessage="No metrics found."
      skeletonHeight={300}
    >
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>Metric</TableHead>
            <TableHead numeric>Records</TableHead>
            <TableHead>Unit</TableHead>
            <TableHead>First</TableHead>
            <TableHead>Last</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {visibleRows.map((row) => (
            <TableRow key={row.type}>
              <TableCell>{friendlyName(row.type)}</TableCell>
              <TableCell numeric>{row.count.toLocaleString('en-US')}</TableCell>
              {/* No bucket here: this table counts records, it doesn't bucket them, so a
                  unit like "steps/wk" would be a claim about aggregation that isn't happening. */}
              <TableCell>{displayUnit({ type: row.type, unit: row.unit }) ?? '—'}</TableCell>
              <TableCell className="whitespace-nowrap">{formatFullDate(row.min_date)}</TableCell>
              <TableCell className="whitespace-nowrap">{formatFullDate(row.max_date)}</TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
      <ShowAllRows
        hiddenCount={hiddenCount}
        totalCount={totalCount}
        isExpanded={isExpanded}
        onToggle={toggle}
        noun="metrics"
      />
    </DataCard>
  )
}
