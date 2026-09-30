"""Reading FHIR resources: the shape-tolerant accessors that ingest and the API both read
fields through, and the flattening of a stored resource into what the clinical page displays.

Every function here takes whatever the export contained and treats it as untrusted: a shape
it doesn't expect yields None (or {}), never an exception. At ingest that keeps one odd field
from aborting the load; at request time it keeps one malformed record from 500ing the page.
One set of accessors for both, so a field can't read one way when stored and another when
served.

The flattening is read at request time from `clinical_records.raw_json` rather than
extracted into columns at ingest, so a new display field needs no schema change and no
re-ingest.
"""

import json
import math
from typing import Any

# The ways a FHIR feed spells "this coding is LOINC". Used to pick the LOINC code out of a
# component's `coding[]`, which an EHR may fill with codings from several systems. The OID
# form is what older interfaces send, and both spellings identify the same code system.
LOINC_SYSTEMS = frozenset(
    {"http://loinc.org", "https://loinc.org", "urn:oid:2.16.840.1.113883.6.1"}
)


# SQLite's INTEGER range. A JSON int outside it can't be bound as one, so as_number reads it
# as a float instead -- and every value it returns can be both stored and served.
_SQLITE_INT_MIN, _SQLITE_INT_MAX = -(2**63), 2**63 - 1


def as_dict(value: Any) -> dict[str, Any]:
    """`value` if it's a JSON object, else {} -- so a chain of `.get`s can't raise."""
    return value if isinstance(value, dict) else {}


def first_dict(value: Any) -> dict[str, Any]:
    """The first element of a JSON array, if it's an object; {} otherwise."""
    return as_dict(value[0]) if isinstance(value, list) and value else {}


def as_str(value: Any) -> str | None:
    return value if isinstance(value, str) else None


def as_nonempty_str(value: Any) -> str | None:
    """A string with something in it, else None: an empty label or value says nothing."""
    return value if isinstance(value, str) and value else None


def as_number(value: Any) -> int | float | None:
    """A JSON number the app can store and serve, else None.

    Not a bool, which is an int subclass: a malformed `"value": true` isn't a measurement.
    Not non-finite: a value like 1e999 parses to inf, which the API's JSON responses can't
    encode, so one record would 500 the whole clinical page. An int outside SQLite's range
    comes back as a float, and one too big even for that is None -- converting it would
    raise, and at ingest that would abort the whole load.
    """
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    if isinstance(value, int) and not _SQLITE_INT_MIN <= value <= _SQLITE_INT_MAX:
        try:
            value = float(value)
        except OverflowError:
            return None
    return value if math.isfinite(value) else None


def _codings(code: Any) -> list[dict[str, Any]]:
    """A CodeableConcept's `coding[]` entries that are objects."""
    coding = as_dict(code).get("coding")
    return [c for c in coding if isinstance(c, dict)] if isinstance(coding, list) else []


def code_label(code: Any) -> str | None:
    """A CodeableConcept's human-readable name: its `text`, else the first coding that has
    a `display`. Empty strings are skipped, since they name nothing.
    """
    return as_nonempty_str(as_dict(code).get("text")) or next(
        (display for c in _codings(code) if (display := as_nonempty_str(c.get("display")))),
        None,
    )


def parse_resource(raw_json: str | None) -> dict | None:
    """The stored FHIR resource as a dict, or None if it isn't one."""
    if not raw_json:
        return None
    try:
        resource = json.loads(raw_json)
    # RecursionError as well as bad JSON, like the ingest-side parser: a deeply nested payload
    # that parsed at ingest can still exceed the stack of a request-handling thread.
    except (ValueError, RecursionError):
        return None
    return resource if isinstance(resource, dict) else None


def reference_range(resource: dict | None) -> dict | None:
    """The first FHIR `referenceRange` on an Observation, flattened for display.

    `low`/`high` are only populated when the bound is a number; a text-only range
    ("Negative", "See comment") comes back with just `text`, and the frontend shows it
    without flagging anything.
    """
    return _flatten_range(resource.get("referenceRange")) if resource else None


def components(resource: dict | None) -> list[dict] | None:
    """An Observation's FHIR `component[]` entries, flattened for display.

    A panel measured in parts -- blood pressure above all -- carries no top-level `value[x]`
    at all: each part is a `component` with its own code, value and (sometimes) reference
    range, so `value_num`/`value_text` on the row are both null and the page has nothing to
    show without this.

    None rather than `[]` for the ordinary single-valued Observation, so the frontend can
    test one field for "this row is a panel". Entries with neither a label nor a value are
    dropped; the order is the resource's, which FHIR does not constrain -- callers that care
    which part is which (systolic vs diastolic) must look at `code`, not the position.
    """
    entries = resource.get("component") if resource else None
    if not isinstance(entries, list):
        return None

    flattened = []
    for component in entries:
        if not isinstance(component, dict):
            continue
        code = component.get("code")
        label = code_label(code)
        loinc = next(
            (
                c["code"]
                for c in _codings(code)
                if c.get("system") in LOINC_SYSTEMS and isinstance(c.get("code"), str)
            ),
            None,
        )
        value_num, value_unit = _quantity(component.get("valueQuantity"))
        value_text = as_nonempty_str(component.get("valueString"))
        if label is None and value_num is None and value_text is None:
            continue
        flattened.append(
            {
                "label": label,
                "code": loinc,
                "value_num": value_num,
                "value_unit": value_unit,
                "value_text": value_text,
                "reference_range": _flatten_range(component.get("referenceRange")),
            }
        )
    return flattened or None


def _flatten_range(ranges: object) -> dict | None:
    if not isinstance(ranges, list) or not ranges or not isinstance(ranges[0], dict):
        return None
    first = ranges[0]
    # A FHIR range bound is a SimpleQuantity, so it's read the same way as a value.
    low, low_unit = _quantity(first.get("low"))
    high, high_unit = _quantity(first.get("high"))
    text = first.get("text") if isinstance(first.get("text"), str) else None
    if low is None and high is None and text is None:
        return None
    return {"low": low, "high": high, "unit": low_unit or high_unit, "text": text}


def _quantity(quantity: object) -> tuple[float | None, str | None]:
    """A FHIR Quantity's numeric value and unit, or (None, None) if it has no usable value.

    The unit goes with the value here, unlike the ingested columns (which keep a unit as
    recorded): a displayed part or range bound with no number has nothing for its unit to
    qualify, and a stray unit would decide which unit a range is compared in.
    """
    quantity = as_dict(quantity)
    value = as_number(quantity.get("value"))
    if value is None:
        return None, None
    return value, as_str(quantity.get("unit"))
