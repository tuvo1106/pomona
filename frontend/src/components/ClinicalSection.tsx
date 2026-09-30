import type { ClinicalRecord, DiagnosticReportResult, ObservationComponent } from '@/api/client'
import { Badge } from '@/components/ui/badge'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import {
  bloodPressureText,
  componentFlag,
  componentLabel,
  componentValue,
  EMPTY,
  factsKey,
  formatClinicalDate,
  formatQuantity,
  groupRepeated,
  hasNumericValue,
  partLabel,
  rangeFlag,
  rangeText,
  recordName,
  resultLabel,
  resultValue,
  scalarText,
  SECTION_TITLES,
  sectionId,
  sharedValue,
  valueText,
  type RangeFlag,
} from '@/lib/clinicalText'
import { cn } from '@/lib/utils'

// Rows that repeat the same value, status and date (a panel of results from one test, say)
// read better as a list of names with the shared facts stated once -- but only with enough
// of them for the repetition to be noise. Two identical rows are still easier as a table.
const MIN_ROWS_FOR_CHIPS = 3

// Status is a FHIR code, so its meaning is fixed: "active" is the one worth drawing the
// eye to; resolved/inactive states recede; entered-in-error is a warning. Record-lifecycle
// codes (final, completed, current, ...) are the normal case for their types and stay
// neutral rather than pretending to be good news.
function StatusBadge({ status }: { status: string }) {
  const code = status.toLowerCase()
  if (code === 'active') {
    return (
      <Badge variant="outline" className="border-primary/30 bg-primary/10 text-primary">
        {status}
      </Badge>
    )
  }
  if (['resolved', 'inactive', 'remission', 'refuted', 'superseded'].includes(code)) {
    return <Badge variant="secondary">{status}</Badge>
  }
  if (['entered-in-error', 'cancelled'].includes(code)) {
    return <Badge variant="destructive">{status}</Badge>
  }
  return (
    <Badge variant="outline" className="text-muted-foreground">
      {status}
    </Badge>
  )
}

function ResultsList({ results }: { results: DiagnosticReportResult[] | null }) {
  if (!results || results.length === 0) return <>{EMPTY}</>
  return (
    <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1">
      {results.map((result, i) => (
        <div key={i} className="contents">
          <dt className="text-muted-foreground">{resultLabel(result)}</dt>
          <dd className="whitespace-pre-line tabular-nums">{resultValue(result) ?? EMPTY}</dd>
        </div>
      ))}
    </dl>
  )
}

function FlagBadge({ flag, label }: { flag: RangeFlag; label?: string }) {
  if (!flag) return null
  const word = flag === 'high' ? 'High' : 'Low'
  return (
    <Badge
      variant="destructive"
      aria-label={`Outside reference range: ${label ? `${label} ` : ''}${flag}`}
    >
      {label ? `${label} ${word.toLowerCase()}` : word}
    </Badge>
  )
}

/** A panel's parts. Blood pressure collapses to one reading; anything else is a labelled
 * list. Reference ranges sit on the parts, not the record, so each is flagged on its own.
 */
function ComponentsValue({ components }: { components: ObservationComponent[] }) {
  const bloodPressure = bloodPressureText(components)

  if (bloodPressure) {
    // One reading, so the parts' flags and ranges have to name which part they belong to.
    const flagged = components
      .map((component) => ({ component, flag: componentFlag(component) }))
      .filter(({ flag }) => flag)
    const ranges = components
      .map((component) => ({
        label: partLabel(component),
        text: rangeText(component.reference_range),
      }))
      .filter(({ text }) => text)
    return (
      <div className="flex flex-col items-end gap-0.5">
        <span className="flex flex-wrap items-center justify-end gap-2">
          {flagged.map(({ component, flag }, i) => (
            <FlagBadge key={i} flag={flag} label={partLabel(component)} />
          ))}
          <span className={cn('tabular-nums', flagged.length > 0 && 'font-semibold')}>
            {bloodPressure}
          </span>
        </span>
        {ranges.map(({ label, text }, i) => (
          <span key={i} className="text-muted-foreground text-xs">
            Ref {label.toLowerCase()} {text}
          </span>
        ))}
      </div>
    )
  }

  return (
    <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1 text-left">
      {components.map((component, i) => {
        const range = rangeText(component.reference_range)
        return (
          <div key={i} className="contents">
            <dt className="text-muted-foreground">{componentLabel(component)}</dt>
            <dd className="flex flex-wrap items-baseline gap-x-2 tabular-nums">
              <FlagBadge flag={componentFlag(component)} />
              <span>{componentValue(component) ?? EMPTY}</span>
              {range && <span className="text-muted-foreground text-xs">Ref {range}</span>}
            </dd>
          </div>
        )
      })}
    </dl>
  )
}

/** The record's own `value[x]`, with its flag and reference range. */
function ScalarValue({ record }: { record: ClinicalRecord }) {
  // Text values stay left-aligned even in a mostly-numeric column: a wrapped sentence
  // right-aligned is hard to read.
  if (record.value_num == null) return <div className="text-left">{scalarText(record)}</div>

  const flag = rangeFlag(record.value_num, record.value_unit, record.reference_range)
  const range = rangeText(record.reference_range)
  return (
    <div className="flex flex-col items-end gap-0.5">
      <span className="flex items-center gap-2">
        <FlagBadge flag={flag} />
        <span className={cn('tabular-nums', flag && 'font-semibold')}>
          {formatQuantity(record.value_num, record.value_unit)}
        </span>
      </span>
      {range && <span className="text-muted-foreground text-xs">Ref {range}</span>}
    </div>
  )
}

function ValueCell({ record }: { record: ClinicalRecord }) {
  if (record.resource_type === 'DiagnosticReport') return <ResultsList results={record.results} />
  // Before the value_num branch: a panel's parts carry the numbers, and its own value_num is
  // normally null. When FHIR's other permitted shape turns up -- a record with both -- the
  // record's own value is shown above its parts rather than being dropped.
  if (record.components?.length) {
    return (
      <div className="flex flex-col items-end gap-1">
        {scalarText(record) !== EMPTY && <ScalarValue record={record} />}
        <ComponentsValue components={record.components} />
      </div>
    )
  }
  return <ScalarValue record={record} />
}

function SharedFacts({
  value,
  status,
  date,
  count,
}: {
  value: string
  status: string | null
  date: string
  count: number
}) {
  const parts = [value, date].filter((part) => part !== EMPTY)
  return (
    <div className="text-muted-foreground flex flex-wrap items-center gap-2 text-xs">
      <span className="text-foreground font-medium tabular-nums">{count}</span>
      {parts.length > 0 && <span>{parts.join(' · ')}</span>}
      {status && <StatusBadge status={status} />}
    </div>
  )
}

export function ClinicalSection({
  resourceType,
  records,
  visible,
}: {
  resourceType: string
  /** Every record of this type -- the layout decisions are made on these, so filtering
   * doesn't flip a section between chips and a table as you type. */
  records: ClinicalRecord[]
  /** The subset that matches the current filter. */
  visible: ClinicalRecord[]
}) {
  // A status every row shares is stated once in the header instead of repeated per row.
  const sharedStatus = sharedValue(records, (r) => r.status)
  // A group is only worth chipping when its names differ -- three chips all reading
  // "Progress notes" say less than three table rows with their own lines.
  // Rows with a reference range never chip: each is judged against its own range, and a
  // chip has nowhere to show that range or an out-of-range flag. Panels are held out for the
  // same reason -- their ranges sit on the parts, so the record's own is usually null.
  const groupable = records.filter((r) => r.reference_range == null && !r.components?.length)
  const groups = groupRepeated(groupable, factsKey, MIN_ROWS_FOR_CHIPS).groups.filter(
    (group) => new Set(group.items.map(recordName)).size === group.items.length,
  )
  const chipped = new Set(groups.flatMap((group) => group.items.map((r) => r.id)))
  const rest = records.filter((r) => !chipped.has(r.id))
  const isVisible = new Set(visible.map((r) => r.id))
  const visibleGroups = groups
    .map((group) => ({ ...group, items: group.items.filter((r) => isVisible.has(r.id)) }))
    .filter((group) => group.items.length > 0)
  const visibleRest = rest.filter((r) => isVisible.has(r.id))

  // Column choices look at the table's own rows (not the chipped ones) across the whole
  // section, so they don't change as the filter narrows the list.
  const showValue = rest.some((r) => valueText(r) !== EMPTY)
  const showStatus = sharedStatus === undefined && rest.some((r) => r.status)
  const showDate = rest.some((r) => r.effective_date != null)
  const numericValues = rest.filter(hasNumericValue).length > rest.length / 2

  const title = SECTION_TITLES[resourceType] ?? resourceType
  const count =
    visible.length === records.length ? `${records.length}` : `${visible.length} of ${records.length}`

  return (
    <Card id={sectionId(resourceType)} className="scroll-mt-20">
      <CardHeader>
        <CardTitle className="flex flex-wrap items-center gap-2 text-sm font-medium">
          {title}
          <span className="text-muted-foreground font-normal tabular-nums">{count}</span>
          {sharedStatus && <StatusBadge status={sharedStatus} />}
        </CardTitle>
      </CardHeader>
      <CardContent className="flex flex-col gap-5">
        {visibleGroups.map((group) => {
          const sample = group.items[0]
          return (
            <div key={group.key} className="flex flex-col gap-2">
              <SharedFacts
                value={valueText(sample)}
                // Already in the header when the whole section shares it.
                status={sharedStatus === undefined ? sample.status : null}
                date={formatClinicalDate(sample.effective_date)}
                count={group.items.length}
              />
              <ul className="flex flex-wrap gap-2">
                {group.items.map((r) => (
                  <li key={r.id} className="border-border rounded-md border px-2.5 py-1 text-sm">
                    {recordName(r)}
                  </li>
                ))}
              </ul>
            </div>
          )
        })}
        {visibleRest.length > 0 && (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Description</TableHead>
                {showValue && (
                  <TableHead numeric={numericValues}>Value</TableHead>
                )}
                {showStatus && <TableHead>Status</TableHead>}
                {showDate && <TableHead>Date</TableHead>}
              </TableRow>
            </TableHeader>
            <TableBody>
              {visibleRest.map((r) => (
                <TableRow key={r.id}>
                  <TableCell className="whitespace-normal">{recordName(r)}</TableCell>
                  {showValue && (
                    <TableCell className="max-w-md whitespace-normal" numeric={numericValues}>
                      <ValueCell record={r} />
                    </TableCell>
                  )}
                  {showStatus && (
                    <TableCell>{r.status ? <StatusBadge status={r.status} /> : EMPTY}</TableCell>
                  )}
                  {showDate && (
                    <TableCell className="whitespace-nowrap">
                      {formatClinicalDate(r.effective_date)}
                    </TableCell>
                  )}
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </CardContent>
    </Card>
  )
}
