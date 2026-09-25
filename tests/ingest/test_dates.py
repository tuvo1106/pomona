from datetime import UTC, datetime

from pomona.ingest.dates import parse_apple_date, parse_fhir_datetime


class TestParseAppleDate:
    def test_local_date_follows_the_string_own_offset_not_utc(self):
        # 2026-08-02 00:30:00 -0700 is still 2026-08-01 in UTC (07:30 UTC), but the
        # local calendar date the user experienced this at is 2026-08-02.
        epoch, local_date = parse_apple_date("2026-08-02 00:30:00 -0700")
        assert local_date == "2026-08-02"
        assert datetime.fromtimestamp(epoch, tz=UTC).isoformat() == "2026-08-02T07:30:00+00:00"

    def test_positive_offset(self):
        epoch, local_date = parse_apple_date("2026-03-10 07:00:00 +0100")
        assert local_date == "2026-03-10"
        assert datetime.fromtimestamp(epoch, tz=UTC).isoformat() == "2026-03-10T06:00:00+00:00"

    def test_two_different_offsets_for_the_same_utc_instant_can_yield_different_local_dates(self):
        # Same UTC instant, different reported offsets -> different local calendar dates.
        # This is exactly the timezone-travel case start_local_date exists to handle correctly.
        epoch_a, local_a = parse_apple_date("2026-08-02 01:00:00 +0000")
        epoch_b, local_b = parse_apple_date("2026-08-01 20:00:00 -0500")
        assert epoch_a == epoch_b
        assert local_a == "2026-08-02"
        assert local_b == "2026-08-01"


class TestParseFhirDatetime:
    def test_date_only(self):
        epoch = parse_fhir_datetime("2020-05-01")
        assert datetime.fromtimestamp(epoch, tz=UTC).date().isoformat() == "2020-05-01"

    def test_datetime_with_offset(self):
        epoch = parse_fhir_datetime("2020-05-01T10:00:00-05:00")
        assert datetime.fromtimestamp(epoch, tz=UTC).isoformat() == "2020-05-01T15:00:00+00:00"

    def test_datetime_with_zulu_suffix(self):
        epoch = parse_fhir_datetime("2020-05-01T10:00:00Z")
        assert datetime.fromtimestamp(epoch, tz=UTC).isoformat() == "2020-05-01T10:00:00+00:00"

    def test_none_input_returns_none(self):
        assert parse_fhir_datetime(None) is None

    def test_empty_string_returns_none(self):
        assert parse_fhir_datetime("") is None

    def test_malformed_string_returns_none_not_raises(self):
        assert parse_fhir_datetime("not-a-date") is None
