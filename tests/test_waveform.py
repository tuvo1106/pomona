from pomona.waveform import downsample_minmax


class TestDownsampleMinmax:
    def test_passthrough_when_under_the_cap(self):
        values = [1.0, 2.0, 3.0]
        assert downsample_minmax(values, 100) == [(0, 1.0), (1, 2.0), (2, 3.0)]

    def test_passthrough_when_exactly_at_the_cap(self):
        values = [1.0, 2.0, 3.0]
        assert downsample_minmax(values, 3) == [(0, 1.0), (1, 2.0), (2, 3.0)]

    def test_output_size_is_bounded_above_the_cap(self):
        values = [float(i % 7) for i in range(10_000)]
        out = downsample_minmax(values, 500)
        assert len(out) <= 500

    def test_first_and_last_samples_survive(self):
        values = list(range(1000))
        out = downsample_minmax([float(v) for v in values], 50)
        indices = [i for i, _ in out]
        assert indices[0] == 0
        assert indices[-1] == 999

    def test_a_spike_inside_a_large_bucket_survives(self):
        # A naive fixed-stride downsample (take every Nth sample) could skip a single-sample
        # spike entirely; min/max-per-bucket must not.
        values = [0.0] * 1000
        values[437] = 999.0
        out = downsample_minmax(values, 20)
        assert any(idx == 437 and value == 999.0 for idx, value in out)

    def test_output_stays_in_ascending_index_order(self):
        values = [float((i * 37) % 101) for i in range(2000)]
        out = downsample_minmax(values, 200)
        indices = [i for i, _ in out]
        assert indices == sorted(indices)

    def test_empty_input_returns_empty_output(self):
        assert downsample_minmax([], 100) == []

    def test_non_positive_max_points_returns_empty_not_the_full_list(self):
        # Bounded to "at most max_points" per the docstring -- 0 (or negative) must not fall
        # through to an unbounded passthrough of every sample.
        values = [1.0, 2.0, 3.0]
        assert downsample_minmax(values, 0) == []
        assert downsample_minmax(values, -5) == []
