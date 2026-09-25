import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { BUCKET_OPTIONS, type BucketOption } from '@/lib/timeRange'

interface BucketSelectProps {
  value: BucketOption
  onChange: (value: BucketOption) => void
  /** Without one a screen reader announces only the value ("Auto"), which says nothing about
   * what it buckets -- and in the chart dialog this sits right beside a labelled select.
   */
  'aria-label'?: string
}

export function BucketSelect({ value, onChange, 'aria-label': ariaLabel }: BucketSelectProps) {
  return (
    <Select value={value} onValueChange={(v) => onChange(v as BucketOption)}>
      <SelectTrigger className="w-[110px]" aria-label={ariaLabel ?? 'Bucket size'}>
        <SelectValue />
      </SelectTrigger>
      <SelectContent>
        {BUCKET_OPTIONS.map((opt) => (
          <SelectItem key={opt.value} value={opt.value}>
            {opt.label}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  )
}
