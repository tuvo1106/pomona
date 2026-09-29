"""Flattening a stored FHIR resource into the shapes the clinical page displays.

Read at request time from `clinical_records.raw_json` rather than extracted into columns at
ingest, so a new display field needs no schema change and no re-ingest. Every function here
takes whatever the export contained and treats it as untrusted: a shape it doesn't expect
yields None, never an exception, because one malformed record must not 500 the whole page.
"""

import json
import math

# The ways a FHIR feed spells "this coding is LOINC". Used to pick the LOINC code out of a
# component's `coding[]`, which an EHR may fill with codings from several systems. The OID
# form is what older interfaces send, and both spellings identify the same code system.
LOINC_SYSTEMS = frozenset(
    {"http://loinc.org", "https://loinc.org", "urn:oid:2.16.840.1.113883.6.1"}
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
        code = code if isinstance(code, dict) else {}
        coding = code.get("coding")
        codings = [c for c in coding if isinstance(c, dict)] if isinstance(coding, list) else []
        label = code.get("text")
        if not _nonempty_str(label):
            label = next(
                (c["display"] for c in codings if _nonempty_str(c.get("display"))),
                None,
            )
        loinc = next(
            (
                c["code"]
                for c in codings
                if c.get("system") in LOINC_SYSTEMS and isinstance(c.get("code"), str)
            ),
            None,
        )
        value_num, value_unit = _quantity(component.get("valueQuantity"))
        value_text = component.get("valueString")
        if not _nonempty_str(value_text):
            value_text = None
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
    """A FHIR Quantity's numeric value and unit, or (None, None) if it isn't one."""
    if not isinstance(quantity, dict):
        return None, None
    value = quantity.get("value")
    if not _is_measurement(value):
        return None, None
    unit = quantity.get("unit")
    return value, unit if isinstance(unit, str) else None


def _nonempty_str(value: object) -> bool:
    return isinstance(value, str) and bool(value)


def _is_measurement(value: object) -> bool:
    # bool is an int subclass -- a malformed `"value": true` isn't a measurement. Nor is a
    # value like 1e999, which parses to inf: the response can't encode it, and one record
    # would 500 the whole clinical page. An int too big for a float encodes, but the browser
    # reads it back as Infinity -- and math.isfinite raises on it rather than answering.
    if not isinstance(value, int | float) or isinstance(value, bool):
        return False
    try:
        return math.isfinite(value)
    except OverflowError:
        return False
