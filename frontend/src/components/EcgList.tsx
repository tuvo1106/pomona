import type { EcgRecording } from '@/api/client'
import { ClassificationTag } from '@/components/ClassificationTag'
import { formatRecordedTime } from '@/lib/ecgTime'
import { formatFullDate } from '@/lib/formatDate'
import { selectableRowClass } from '@/lib/selectableRow'
import { cn } from '@/lib/utils'

interface EcgListProps {
  recordings: EcgRecording[]
  selectedId: number | null
  onSelect: (id: number) => void
}

export function EcgList({ recordings, selectedId, onSelect }: EcgListProps) {
  return (
    // Side by side with the waveform on a wide screen; above it, capped in height, on a
    // narrow one -- a full-height list stacked over the chart would be all you ever saw.
    // Same shape as RoutesList, one breakpoint later: a squeezed ECG is worse than a
    // squeezed map, because reading one means reading the shape of a beat 4px wide.
    <div className="border-border flex max-h-44 w-full shrink-0 flex-col overflow-y-auto border-b md:max-h-none md:w-64 md:border-r md:border-b-0">
      {/* No average heart rate on these rows, though it would belong here: Apple's ECG CSV
          carries only Name, Date of Birth, Recorded Date, Classification, Symptoms, Software
          Version, Device and Sample Rate (see ingest/ecg_loader.py), so there is no average
          HR in the export to store, let alone a column for /api/ecg to select. */}
      {recordings.map((recording) => {
        const time = formatRecordedTime(recording.recorded_date, recording.recorded_local_date)
        return (
          <button
            type="button"
            key={recording.id}
            onClick={() => onSelect(recording.id)}
            className={cn(
              'border-border flex w-full flex-col items-start gap-1 border-b px-3 py-2 text-left text-sm',
              selectableRowClass(selectedId === recording.id),
            )}
          >
            <span className="flex w-full items-baseline gap-2">
              <span className="flex-1 truncate">
                {formatFullDate(recording.recorded_local_date)}
              </span>
              {/* Absent rather than an em dash when the viewer's zone puts the recording on
                  another day -- see formatRecordedTime. Several ECGs in one day is the
                  normal way these get recorded, so the time is what tells the rows apart.

                  The title names the clock, because for a recording made in another zone
                  this is the right instant on the wrong wall clock and the row otherwise
                  gives no sign of it -- the export doesn't store the offset that would. */}
              {time && (
                <span
                  className="text-muted-foreground shrink-0 text-xs tabular-nums"
                  title="Shown in your timezone. The export records the instant and the calendar day, not the offset between them, so a recording made in another timezone reads as the same moment on your clock."
                >
                  {time}
                </span>
              )}
            </span>
            <ClassificationTag classification={recording.classification} />
          </button>
        )
      })}
    </div>
  )
}
