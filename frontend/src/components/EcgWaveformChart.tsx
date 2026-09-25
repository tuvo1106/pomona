import { useMemo } from 'react'
import { Brush, CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import type { EcgPoint } from '@/api/client'
import { ChartStateWrapper } from '@/components/ChartStateWrapper'
import { ChartTooltip } from '@/components/ChartTooltip'
import { ClassificationTag } from '@/components/ClassificationTag'
import { useEcgRecording } from '@/hooks/useEcg'
import { CHART_AXIS_STROKE, CHART_AXIS_TICK } from '@/lib/chartStyle'
import {
  PAPER_SECONDS_MAJOR,
  PAPER_SECONDS_MINOR,
  paperAmplitudeAxis,
  paperAmplitudeSteps,
  paperGridCoordinates,
} from '@/lib/ecgPaperGrid'
import { formatAxisNumber } from '@/lib/formatNumber'

// A full ~30s recording rendered across the panel's own width squeezes every heartbeat into
// a handful of pixels -- consecutive beats visually smear into each other, unreadable as a
// waveform. Defaulting the visible window to 10s (like a standard 12-lead ECG paper strip)
// and letting the Brush below the chart scrub through the rest of the recording gives each
// beat enough room to actually read its shape.
const DEFAULT_WINDOW_SECONDS = 10

const BRUSH_HEIGHT = 40

/** Stable empty array: a fresh `[]` while the query is in flight would be a new identity
 * every render, which is exactly what the amplitude-axis memo below is avoiding.
 */
const NO_POINTS: EcgPoint[] = []

/** Axis ticks and the Brush's own labels: one decimal is all a 0.5s-ish tick spacing needs. */
function formatSeconds(value: unknown): string {
  return typeof value === 'number' ? `${value.toFixed(1)}s` : ''
}

/** The tooltip reads a single sample, and the grid it's read against is ruled every 0.04s,
 * so a second decimal is the difference between naming a point and naming a square.
 */
function formatSecondsPrecise(value: unknown): string {
  return typeof value === 'number' ? `${value.toFixed(2)}s` : ''
}

/** The Brush's grab handles. recharts' stock traveller is a hard-coded white-on-stroke bar,
 * which in this app's dark theme is a white slab; this is the accent colour the rest of the
 * UI uses for "you can move this", with a grip line so it reads as a handle and not as part
 * of the trace behind it.
 */
function EcgTraveller({
  x,
  y,
  width,
  height,
}: {
  x: number
  y: number
  width: number
  height: number
}) {
  const centre = x + width / 2
  return (
    <g>
      <rect x={x} y={y} width={width} height={height} rx={2} fill="var(--primary)" />
      <line
        x1={centre}
        y1={y + height * 0.3}
        x2={centre}
        y2={y + height * 0.7}
        stroke="var(--primary-foreground)"
        strokeWidth={1}
      />
    </g>
  )
}

export function EcgWaveformChart({ recordingId }: { recordingId: number | null }) {
  const { data, isLoading, error } = useEcgRecording(recordingId)

  const points = data?.points ?? NO_POINTS
  const amplitude = paperAmplitudeSteps(data?.unit)
  // Over the whole recording, not the visible window, so the gain stays put while the Brush
  // moves -- and memoized, because it walks every sample and the Brush re-renders this
  // component on each frame of a drag.
  const amplitudeAxis = useMemo(
    () => paperAmplitudeAxis(points.map((point) => point.value), amplitude.major),
    [points, amplitude.major],
  )

  if (recordingId == null) {
    return (
      <div className="text-muted-foreground flex h-full items-center justify-center text-sm">
        No recording selected.
      </div>
    )
  }

  const duration = data ? data.sample_count / data.sample_rate : 0
  const windowSeconds = Math.min(DEFAULT_WINDOW_SECONDS, duration || DEFAULT_WINDOW_SECONDS)
  const defaultEndIndex =
    points.length > 1 && duration > 0
      ? Math.max(1, Math.round((points.length - 1) * (windowSeconds / duration)))
      : points.length - 1

  return (
    <div className="flex h-full flex-col gap-3 p-4">
      {data && (
        <div className="flex flex-wrap items-center gap-3 text-sm">
          <ClassificationTag classification={data.classification} />
          {data.symptoms && <span className="text-muted-foreground">{data.symptoms}</span>}
          <span className="text-muted-foreground ml-auto">
            {data.lead ?? 'Lead I'} &middot; {data.sample_rate} Hz
          </span>
        </div>
      )}
      {/* min-h-0: a flex child's min-height defaults to auto, which would let the chart's
          own height push this past the panel border it sits inside instead of taking
          whatever height is left. The chart fills that, so the panel stays one screen's
          worth on a phone and 600px on a desktop without a second magic number here. */}
      <div className="min-h-0 flex-1">
        <ChartStateWrapper
          isLoading={isLoading}
          error={error}
          isEmpty={!data || points.length === 0}
          height="100%"
          errorMessage="Failed to load this ECG recording."
        >
          <ResponsiveContainer width="100%" height="100%">
            {/* key={recordingId}: Brush's startIndex/endIndex only seed its initial state, so
                without a remount here, switching recordings would keep the previous
                recording's scrub position/window instead of resetting to the new default. */}
            <LineChart key={recordingId} data={points}>
              {/* ECG paper: a fine mesh with every fifth line heavier, at fixed intervals in
                  seconds and millivolts rather than at whatever the axis ticks landed on --
                  see lib/ecgPaperGrid.ts for why that distinction is the point. Two grids
                  because recharts draws one stroke per grid; the minor one is declared (and
                  z-ordered) first so the major lines paint over it. */}
              <CartesianGrid
                zIndex={-102}
                stroke="var(--ecg-grid-minor)"
                verticalCoordinatesGenerator={({ xAxis }) =>
                  paperGridCoordinates(xAxis?.scale, PAPER_SECONDS_MINOR)
                }
                horizontalCoordinatesGenerator={({ yAxis }) =>
                  paperGridCoordinates(yAxis?.scale, amplitude.minor)
                }
              />
              <CartesianGrid
                zIndex={-101}
                stroke="var(--ecg-grid-major)"
                verticalCoordinatesGenerator={({ xAxis }) =>
                  paperGridCoordinates(xAxis?.scale, PAPER_SECONDS_MAJOR)
                }
                horizontalCoordinatesGenerator={({ yAxis }) =>
                  paperGridCoordinates(yAxis?.scale, amplitude.major)
                }
              />
              <XAxis
                dataKey="t"
                type="number"
                tick={CHART_AXIS_TICK}
                stroke={CHART_AXIS_STROKE}
                tickFormatter={formatSeconds}
                domain={['dataMin', 'dataMax']}
              />
              <YAxis
                tick={CHART_AXIS_TICK}
                width={48}
                stroke={CHART_AXIS_STROKE}
                tickFormatter={formatAxisNumber}
                // Pinned to the paper's heavy lines rather than left to recharts, which
                // would label 400µV intervals across a grid ruled at 500 and refit the
                // scale on every Brush move. See paperAmplitudeAxis.
                domain={amplitudeAxis?.domain}
                ticks={amplitudeAxis?.ticks}
                label={{ value: data?.unit ?? 'µV', angle: -90, position: 'insideLeft', fontSize: 11 }}
              />
              <Tooltip content={ChartTooltip} labelFormatter={formatSecondsPrecise} />
              {/* type="linear", not "monotone" like every other chart in this app -- monotone
                  curve-fitting would smooth over the actual waveform morphology (QRS spikes,
                  etc), which is the whole point of looking at an ECG trace. Don't "fix" this
                  back to monotone to match MetricChart.tsx.

                  --foreground, not --chart-1: on paper the trace is the ink and the grid is
                  the paper, and a blue line over a red mesh reads as two charts overlaid. */}
              <Line
                type="linear"
                dataKey="value"
                stroke="var(--foreground)"
                dot={false}
                isAnimationActive={false}
                strokeWidth={1.5}
              />
              <Brush
                dataKey="t"
                height={BRUSH_HEIGHT}
                startIndex={0}
                endIndex={defaultEndIndex}
                travellerWidth={10}
                tickFormatter={formatSeconds}
                // Sets the brush's frame *and* the fill of its drag labels (recharts uses
                // `stroke` for both), so it has to be readable text, not a hairline.
                stroke={CHART_AXIS_STROKE}
                fill="var(--card)"
                traveller={EcgTraveller}
              >
                {/* The whole recording in miniature, so the window being scrubbed has a
                    shape to be positioned against -- which beat you are on -- instead of the
                    flat bar this was. recharts clones this chart with the full dataset and
                    the brush's own box (its Panorama). */}
                <LineChart>
                  <Line
                    type="linear"
                    dataKey="value"
                    stroke="var(--muted-foreground)"
                    dot={false}
                    isAnimationActive={false}
                    strokeWidth={1}
                  />
                </LineChart>
              </Brush>
            </LineChart>
          </ResponsiveContainer>
        </ChartStateWrapper>
      </div>
    </div>
  )
}
