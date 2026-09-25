"""Downsampling for ECG waveform charting.

An ECG recording is ~15,360 raw samples (30s at 512Hz) -- a Recharts line chart over that
many points needs downsampling for a reasonable render (see TODO.md's electrocardiograms/
entry). Applied at request time in the API, not precomputed at ingest: this is a
single-user local SQLite app, samples_json is ~100-150KB per recording, and a JSON decode
plus one pass over the array is sub-millisecond -- there's no volume here that would justify
caching a derived copy.
"""

from math import ceil


def downsample_minmax(values: list[float], max_points: int) -> list[tuple[int, float]]:
    """Reduces `values` to at most `max_points` (index, value) pairs using min/max-per-bucket
    decimation, so a waveform feature (e.g. a QRS spike) survives even though most samples
    are dropped -- naive fixed-stride downsampling can skip a spike outright if it falls
    between sampled indices. Each bucket contributes up to two points, the min and max
    sample in that bucket, emitted in whichever order they actually occur (not always
    min-then-max) so the trace's left-to-right shape stays faithful to the original signal.
    """
    n = len(values)
    if max_points <= 0:
        return []
    if n <= max_points:
        return list(enumerate(values))

    bucket_count = max(1, max_points // 2)
    bucket_size = ceil(n / bucket_count)

    out: list[tuple[int, float]] = []
    for start in range(0, n, bucket_size):
        bucket = values[start : start + bucket_size]
        if not bucket:
            continue
        min_offset = min(range(len(bucket)), key=lambda i: bucket[i])
        max_offset = max(range(len(bucket)), key=lambda i: bucket[i])
        first_offset, second_offset = sorted((min_offset, max_offset))
        out.append((start + first_offset, bucket[first_offset]))
        if second_offset != first_offset:
            out.append((start + second_offset, bucket[second_offset]))

    return out
