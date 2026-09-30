import { useMemo, useState } from 'react'
import type { ClinicalRecord } from '@/api/client'
import { ClinicalSection } from '@/components/ClinicalSection'
import { Skeleton } from '@/components/ui/skeleton'
import { useClinical } from '@/hooks/queries'
import {
  matchesFilter,
  SECTION_ORDER,
  SECTION_TITLES,
  sectionId,
} from '@/lib/clinicalText'
import { useContentFade } from '@/lib/transitions'
import { cn } from '@/lib/utils'

// Clinical records (conditions, immunizations, labs) are mostly one-time facts, not
// trends -- so this page shows everything regardless of the dashboard's date-range picker,
// grouped by resource type in a fixed clinical-relevance order (SECTION_ORDER).

export function ClinicalPage() {
  const { data, isLoading, error } = useClinical()
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
