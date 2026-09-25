import { ChartStateWrapper } from '@/components/ChartStateWrapper'
import { DataFreshness } from '@/components/DataFreshness'
import { EcgList } from '@/components/EcgList'
import { EcgWaveformChart } from '@/components/EcgWaveformChart'
import { TimeRangeSelect } from '@/components/TimeRangeSelect'
import { useAnchoredRange } from '@/hooks/useAnchoredRange'
import { useEcgRecordings } from '@/hooks/useEcg'
import { useSearchParamId } from '@/hooks/useSearchParamState'
import { cn } from '@/lib/utils'

/** Viewport-relative until the layout goes side-by-side, then the fixed height the panel
 * has always had. A flat 600px on a phone -- where the list sits *above* the chart rather
 * than beside it -- left the waveform a strip at the bottom of a box taller than the
 * screen. Same shape as the routes map's frame, one breakpoint later (see EcgList) and
 * with a higher floor, because here the stacked list takes ~176px off the top before the
 * waveform gets any of it.
 */
const PANEL_FRAME = 'h-[70vh] min-h-[440px] md:h-[600px]'

export function EcgPage() {
  // Defaults to the last year, not the dashboard-wide 30 days -- ECGs are recorded
  // on-demand, not continuously, so a 30-day window is often empty.
  const {
    rangeOption,
    setRangeOption,
    customRange,
    setCustomRange,
    range,
    ready,
    latestDate,
    ingestedAt,
  } = useAnchoredRange('365d')
  const { data, isLoading, error } = useEcgRecordings(range, { enabled: ready })
  const recordings = data ?? []

  // In the URL: a reload, or a link kept for later, lands on the same recording.
  const [selectedId, setSelectedId] = useSearchParamId('ecg')
  // Derived, not stored separately: if the selected recording fell out of the current range
  // (e.g. the date picker changed), treat the selection as cleared rather than pointing at a
  // recording that's no longer in `recordings`.
  //
  // Cleared then falls back to the newest recording -- /api/ecg is already sorted
  // newest-first -- rather than to nothing, so the page opens on a waveform instead of an
  // empty "select a recording" pane. Keeping it derived rather than seeding the state in an
  // effect means a range change lands on the newest recording *of the new range*, and one
  // less thing can be stale.
  const activeId =
    (recordings.some((r) => r.id === selectedId) ? selectedId : null) ?? recordings[0]?.id ?? null

  return (
    <main className="mx-auto flex max-w-6xl flex-col gap-6 px-6 py-8">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <h2 className="text-foreground text-base font-semibold">ECG</h2>
          <p className="text-muted-foreground text-xs">
            Apple Watch single-lead ECG recordings.
          </p>
        </div>
        <div className="flex flex-wrap items-center justify-end gap-x-4 gap-y-2">
          <DataFreshness latestDate={latestDate} ingestedAt={ingestedAt} />
          <TimeRangeSelect
            value={rangeOption}
            onChange={setRangeOption}
            custom={customRange}
            onCustomChange={setCustomRange}
          />
        </div>
      </div>

      <div className={cn('border-border overflow-hidden rounded-lg border', PANEL_FRAME)}>
        <ChartStateWrapper
          isLoading={isLoading || !ready}
          error={error}
          isEmpty={recordings.length === 0}
          height="100%"
          errorMessage="Failed to load ECG recordings."
        >
          <div className="flex h-full flex-col md:flex-row">
            <EcgList recordings={recordings} selectedId={activeId} onSelect={setSelectedId} />
            {/* min-h-0: a flex child defaults to min-height:auto, which would let the chart
                size itself and push the frame taller than the border around it. */}
            <div className="min-h-0 flex-1">
              <EcgWaveformChart recordingId={activeId} />
            </div>
          </div>
        </ChartStateWrapper>
      </div>
    </main>
  )
}
