from datetime import UTC, datetime


def parse_apple_date(value: str) -> tuple[int, str]:
    """Parses Apple Health's "YYYY-MM-DD HH:MM:SS ±HHMM" format.

    Returns (epoch_seconds_utc, local_date) where local_date is derived from the
    string's own UTC offset, not a server timezone or a UTC-converted date — this
    matters for correct day-bucketing across timezone travel.
    """
    dt = datetime.strptime(value, "%Y-%m-%d %H:%M:%S %z")
    return int(dt.timestamp()), dt.date().isoformat()


def parse_fhir_datetime(value: str | None) -> int | None:
    """Parses a FHIR dateTime/date/instant string into epoch seconds (UTC), or None."""
    if not value:
        return None
    try:
        if len(value) == 10:
            dt = datetime.strptime(value, "%Y-%m-%d").replace(tzinfo=UTC)
        else:
            dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=UTC)
        return int(dt.timestamp())
    except ValueError:
        return None
