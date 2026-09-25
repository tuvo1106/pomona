import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { RANGE_OPTIONS, type DateRange, type RangeOption } from '@/lib/timeRange'

interface TimeRangeSelectProps {
  value: RangeOption
  onChange: (value: RangeOption) => void
  custom: DateRange
  onCustomChange: (custom: DateRange) => void
}

export function TimeRangeSelect({ value, onChange, custom, onCustomChange }: TimeRangeSelectProps) {
  return (
    <div className="flex items-center gap-2">
      {value === 'custom' && (
        <div className="flex items-center gap-1">
          <input
            type="date"
            aria-label="Start date"
            value={custom.start ?? ''}
            max={custom.end}
            onChange={(e) => onCustomChange({ ...custom, start: e.target.value })}
            className="border-input bg-background h-9 rounded-md border px-2 text-sm"
          />
          <span className="text-muted-foreground text-sm">to</span>
          <input
            type="date"
            aria-label="End date"
            value={custom.end ?? ''}
            min={custom.start}
            onChange={(e) => onCustomChange({ ...custom, end: e.target.value })}
            className="border-input bg-background h-9 rounded-md border px-2 text-sm"
          />
        </div>
      )}
      <Select value={value} onValueChange={(v) => onChange(v as RangeOption)}>
        <SelectTrigger className="w-[160px]">
          <SelectValue />
        </SelectTrigger>
        <SelectContent>
          {RANGE_OPTIONS.map((opt) => (
            <SelectItem key={opt.value} value={opt.value}>
              {opt.label}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
    </div>
  )
}
