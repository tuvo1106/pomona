import { useMemo, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import {
  api,
  type ClinicalRecord,
  type DiagnosticReportResult,
  type ObservationComponent,
  type ReferenceRange,
} from '@/api/client'
import { Badge } from '@/components/ui/badge'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'
import { useContentFade } from '@/lib/transitions'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import {
  displayClinicalText,
  displayUnit,
  groupRepeated,
  rangeFlag,
  sharedValue,
  type RangeFlag,
} from '@/lib/clinicalText'
import { cn } from '@/lib/utils'

// Clinical records (conditions, immunizations, labs) are mostly one-time facts, not
// trends -- so this page shows everything regardless of the dashboard's date-range picker,
// grouped by resource type in this fixed clinical-relevance order.
//
// This list mirrors the ingest allowlist (pomona/clinical.py): a type not ingested has nothing
// to order or title here. Keep them in step -- a type that reached the database without a place
// in this list would still render, as its own raw-named section.
const SECTION_ORDER = [
  'Condition',
  'Immunization',
  'Observation',
  'DiagnosticReport',
  'DocumentReference',
]

const SECTION_TITLES: Record<string, string> = {
  Condition: 'Conditions',
  Immunization: 'Immunizations',
  Observation: 'Labs & observations',
  DiagnosticReport: 'Diagnostic reports',
  DocumentReference: 'Documents',
}

// Rows that repeat the same value, status and date (a panel of results from one test, say)
// read better as a list of names with the shared facts stated once -- but only with enough
// of them for the repetition to be noise. Two identical rows are still easier as a table.
const MIN_ROWS_FOR_CHIPS = 3

const EMPTY = '—'

// Rendered in UTC, not local time: FHIR clinical dates are commonly date-only ("2024-01-10"
// for an immunization or a condition onset), and the ingest stores those as UTC midnight.
// Formatting that in a zone behind UTC would shift every such date a day earlier.
function formatDate(epoch: number | null): string {
  if (epoch == null) return EMPTY
  return new Date(epoch * 1000).toLocaleDateString('en-US', {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
    timeZone: 'UTC',
  })
}

function formatQuantity(value: number, unit: string | null): string {
  return `${value} ${displayUnit(unit) ?? ''}`.trim()
}

function sectionId(resourceType: string): string {
  return `clinical-${resourceType}`
}

function describe(record: ClinicalRecord): string {
  return record.code_text ? displayClinicalText(record.code_text) : EMPTY
}

function resultLabel(result: DiagnosticReportResult): string {
  return displayClinicalText(result.code_text ?? result.display ?? 'Component')
}

function resultValue(result: DiagnosticReportResult): string | null {
  return result.value_num != null
    ? formatQuantity(result.value_num, result.value_unit)
    : result.value_text
}

// LOINC codes for the two parts of a blood-pressure panel. Matched by code and never by
// position: FHIR puts no order on `component[]`, and sources do send diastolic first.
const LOINC_SYSTOLIC = '8480-6'
const LOINC_DIASTOLIC = '8462-4'

// The panel's own names for its parts are long ("Systolic blood pressure"); beside a
// "120/80 mmHg" reading, which part is which is clear from one word.
const BP_PART_LABELS: Record<string, string> = {
  [LOINC_SYSTOLIC]: 'Systolic',
  [LOINC_DIASTOLIC]: 'Diastolic',
}

function componentLabel(component: ObservationComponent): string {
  return component.label ? displayClinicalText(component.label) : 'Component'
}

function partLabel(component: ObservationComponent): string {
  return (component.code && BP_PART_LABELS[component.code]) || componentLabel(component)
}

function componentValue(component: ObservationComponent): string | null {
  return component.value_num != null
    ? formatQuantity(component.value_num, component.value_unit)
    : component.value_text
}

/** "120/80 mmHg" when the panel is *exactly* a numeric systolic and diastolic, else null --
 * any other panel reads as a labelled list instead. A panel that carries a third part (mean
 * arterial pressure, heart rate, body position) is not collapsed: the extra part's value has
 * nowhere to go in one reading, and dropping it would hide it from the flag beside it and
 * from the page's filter.
 */
function bloodPressureText(components: ObservationComponent[]): string | null {
  if (components.length !== 2) return null
  const systolic = components.find((c) => c.code === LOINC_SYSTOLIC)
  const diastolic = components.find((c) => c.code === LOINC_DIASTOLIC)
  if (systolic?.value_num == null || diastolic?.value_num == null) return null
  const unit = systolic.value_unit ?? diastolic.value_unit
  return `${systolic.value_num}/${formatQuantity(diastolic.value_num, unit)}`
}

function componentsText(components: ObservationComponent[]): string {
  return (
    bloodPressureText(components) ??
    components
      .map((component) => {
        const value = componentValue(component)
        return value ? `${componentLabel(component)}: ${value}` : componentLabel(component)
      })
      .join('; ')
  )
}

function componentFlag(component: ObservationComponent): RangeFlag {
  return rangeFlag(component.value_num, component.value_unit, component.reference_range)
}

/** Whether the row shows a number -- a panel's numbers live in its parts. Decides whether
 * the section's Value column is right-aligned. */
function hasNumericValue(record: ClinicalRecord): boolean {
  if (record.components?.length) return record.components.some((c) => c.value_num != null)
  return record.value_num != null
}

/** The record's value as plain text: used for the "every row shares it" check and for
 * the filter, so both see exactly what the page shows.
 */
/** The record's own `value[x]` as text, ignoring any components. */
function scalarText(record: ClinicalRecord): string {
  if (record.value_num != null) return formatQuantity(record.value_num, record.value_unit)
  // Some sources repeat the name as the value (immunizations often do) -- showing it twice
  // adds nothing, so treat it as no value.
  if (!record.value_text || record.value_text === record.code_text) return EMPTY
  return record.value_text
}

function valueText(record: ClinicalRecord): string {
  if (record.resource_type === 'DiagnosticReport') {
    const results = record.results ?? []
    if (results.length === 0) return EMPTY
    return results
      .map((result) => {
        const value = resultValue(result)
        return value ? `${resultLabel(result)}: ${value}` : resultLabel(result)
      })
      .join('; ')
  }
  const scalar = scalarText(record)
  // A panel measured in parts usually carries no top-level value at all -- its numbers are
  // in components, which is why these rows used to read as "—" everywhere. FHIR does allow
  // both, though, so when a record has both they're shown together rather than one winning.
  if (record.components?.length) {
    const parts = componentsText(record.components)
    return scalar === EMPTY ? parts : `${scalar}; ${parts}`
  }
  return scalar
}

function rangeText(range: ReferenceRange | null): string | null {
  if (!range) return null
  if (range.text) return range.text
  if (range.low != null && range.high != null) {
    return `${range.low}–${formatQuantity(range.high, range.unit)}`
  }
  if (range.low != null) return `≥ ${formatQuantity(range.low, range.unit)}`
  if (range.high != null) return `≤ ${formatQuantity(range.high, range.unit)}`
  return null
}

function matchesFilter(record: ClinicalRecord, needle: string): boolean {
  if (!needle) return true
  const haystack = [
    describe(record),
    valueText(record),
    record.status,
    formatDate(record.effective_date),
    rangeText(record.reference_range),
    ...(record.components ?? []).map((c) => rangeText(c.reference_range)),
  ]
    .filter(Boolean)
    .join(' ')
    .toLowerCase()
  return haystack.includes(needle)
}

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

/** Groups rows that repeat the same value, status and date -- what the page states once
 * above a chip list rather than on every row. */
function factsKey(record: ClinicalRecord): string {
  return JSON.stringify([valueText(record), record.status, formatDate(record.effective_date)])
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

function ClinicalSection({
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
    (group) => new Set(group.items.map(describe)).size === group.items.length,
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
                date={formatDate(sample.effective_date)}
                count={group.items.length}
              />
              <ul className="flex flex-wrap gap-2">
                {group.items.map((r) => (
                  <li key={r.id} className="border-border rounded-md border px-2.5 py-1 text-sm">
                    {describe(r)}
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
                  <TableCell className="whitespace-normal">{describe(r)}</TableCell>
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
                      {formatDate(r.effective_date)}
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

export function ClinicalPage() {
  const { data, isLoading, error } = useQuery({
    queryKey: ['clinical', 'all'],
    queryFn: () => api.clinical({}),
  })
  const fade = useContentFade(isLoading)
  const [filter, setFilter] = useState('')
  const needle = filter.trim().toLowerCase()

  const grouped = useMemo(() => {
    const byType = new Map<string, ClinicalRecord[]>()
    for (const record of data ?? []) {
      const list = byType.get(record.resource_type) ?? []
      list.push(record)
      byType.set(record.resource_type, list)
    }
    for (const list of byType.values()) {
      list.sort((a, b) => (b.effective_date ?? 0) - (a.effective_date ?? 0))
    }
    return byType
  }, [data])

  const orderedTypes = [
    ...SECTION_ORDER.filter((t) => grouped.has(t)),
    ...[...grouped.keys()].filter((t) => !SECTION_ORDER.includes(t)),
  ]
  const sections = orderedTypes
    .map((resourceType) => {
      const records = grouped.get(resourceType)!
      return { resourceType, records, visible: records.filter((r) => matchesFilter(r, needle)) }
    })
    .filter((section) => section.visible.length > 0)
  const hasError = Boolean(error)
  const hasRecords = orderedTypes.length > 0

  return (
    <main className="mx-auto flex max-w-6xl flex-col gap-6 px-6 py-8">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h2 className="text-foreground text-base font-semibold">Clinical records</h2>
          <p className="text-muted-foreground text-xs">
            Conditions, immunizations, and labs from your Apple Health clinical records
            export.
          </p>
        </div>
        {hasRecords && (
          <input
            type="search"
            value={filter}
            onChange={(e) => setFilter(e.target.value)}
            placeholder="Filter records"
            aria-label="Filter clinical records"
            className="border-input placeholder:text-muted-foreground focus-visible:border-ring focus-visible:ring-ring/50 h-8 w-full rounded-md border bg-transparent px-2.5 text-sm outline-none focus-visible:ring-3 sm:w-64"
          />
        )}
      </div>

      {hasRecords && sections.length > 0 && (
        <nav aria-label="Clinical record sections" className="flex flex-wrap gap-2">
          {sections.map(({ resourceType, visible }) => (
            <a
              key={resourceType}
              href={`#${sectionId(resourceType)}`}
              className="border-border hover:bg-accent focus-visible:ring-ring/50 rounded-full border px-3 py-1 text-xs font-medium outline-none focus-visible:ring-3"
            >
              {SECTION_TITLES[resourceType] ?? resourceType}
              <span className="text-muted-foreground ml-1.5 tabular-nums">{visible.length}</span>
            </a>
          ))}
        </nav>
      )}

      {isLoading && (
        <div className="flex flex-col gap-4">
          <Skeleton className="h-40 w-full" />
          <Skeleton className="h-40 w-full" />
        </div>
      )}
      {!isLoading && hasError && (
        <div className="text-destructive text-sm">Failed to load clinical records.</div>
      )}
      {!isLoading && !hasError && !hasRecords && (
        <div className="text-muted-foreground text-sm">No clinical records found.</div>
      )}
      {!isLoading && !hasError && hasRecords && sections.length === 0 && (
        <div className="text-muted-foreground text-sm">No records match “{filter.trim()}”.</div>
      )}
      {/* The sections' own wrapper, which main's gap-6 would otherwise provide: they need a
          single element to fade in together, and this page is the one place the content
          doesn't arrive through DataCard or ChartStateWrapper. */}
      {!isLoading && !hasError && sections.length > 0 && (
        <div className={cn('flex flex-col gap-6', fade)}>
          {sections.map(({ resourceType, records, visible }) => (
            <ClinicalSection
              key={resourceType}
              resourceType={resourceType}
              records={records}
              visible={visible}
            />
          ))}
        </div>
      )}
    </main>
  )
}
