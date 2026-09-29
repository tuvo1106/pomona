"""Loads apple_health_export/clinical-records/*.json (FHIR R4 resources) into clinical_records.

Not *every* file: only the resource types in INGESTED_RESOURCE_TYPES are kept, and the row
count this returns is the file count minus whatever else the directory held. See pomona.clinical
for why that is an allowlist rather than a list of things to skip.

Each file is one small, flat FHIR resource (not a Bundle) — plain json.load per file is fine
at this volume (~100 files, well under 1MB total). Only fields useful for filtering/display are
flattened into columns; the full resource is kept in raw_json for anything else (e.g. a chat
question that needs a field we didn't flatten). The one exception is a DiagnosticReport's
result[] references, which are resolved against the other resources in the same directory and
flattened into results_json -- see _resolve_diagnostic_report_results.
"""

import json
import logging
import sqlite3
from pathlib import Path
from typing import Any

from pomona.clinical import INGESTED_RESOURCE_TYPES
from pomona.ingest.dates import parse_fhir_datetime

logger = logging.getLogger(__name__)

# Shape-tolerant accessors. A FHIR export can hold a field of the wrong JSON type -- a string
# where a CodeableConcept belongs, an object where a status string belongs -- and the
# extractors read every field through these, so a wrong-typed field flattens to None (the
# resource's raw_json still has it) instead of raising or reaching SQLite as an unbindable
# value. That keeps the extractors free of try/except: anything they *do* raise is a bug in
# this module, and it fails the ingest loudly rather than being counted as a skipped file.

_SQLITE_INT_MIN, _SQLITE_INT_MAX = -(2**63), 2**63 - 1


def _obj(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _first(value: Any) -> dict[str, Any]:
    """The first element of a JSON array, if it's an object; {} otherwise."""
    return _obj(value[0]) if isinstance(value, list) and value else {}


def _str(value: Any) -> str | None:
    return value if isinstance(value, str) else None


def _num(value: Any) -> int | float | None:
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    if isinstance(value, int) and not _SQLITE_INT_MIN <= value <= _SQLITE_INT_MAX:
        return float(value)
    return value


def _date(value: Any) -> int | None:
    return parse_fhir_datetime(_str(value))


def _code_fields(code: Any) -> tuple[str | None, str | None, str | None]:
    """Extracts (text, system, value) from a FHIR CodeableConcept."""
    code = _obj(code)
    text = _str(code.get("text"))
    first = _first(code.get("coding"))
    if first:
        return (
            text or _str(first.get("display")),
            _str(first.get("system")),
            _str(first.get("code")),
        )
    return text, None, None


def _status_code(codeable_concept: Any) -> str | None:
    codeable_concept = _obj(codeable_concept)
    first = _first(codeable_concept.get("coding"))
    if first:
        return _str(first.get("code"))
    return _str(codeable_concept.get("text"))


def _extract_observation(r: dict[str, Any]) -> dict[str, Any]:
    code_text, code_system, code_value = _code_fields(r.get("code"))
    vq = _obj(r.get("valueQuantity"))
    # A narrative/impression Observation (e.g. a radiology report's freeform findings, seen
    # via DiagnosticReport.result[] resolution) carries valueString instead of valueQuantity.
    return {
        "code_text": code_text,
        "code_system": code_system,
        "code_value": code_value,
        "status": _str(r.get("status")),
        "value_num": _num(vq.get("value")),
        "value_unit": _str(vq.get("unit")),
        "value_text": _str(r.get("valueString")),
        "effective_date": _date(r.get("effectiveDateTime") or r.get("issued")),
        "recorded_date": _date(r.get("issued")),
        "category": _str(_first(r.get("category")).get("text")),
    }


def _extract_condition(r: dict[str, Any]) -> dict[str, Any]:
    code_text, code_system, code_value = _code_fields(r.get("code"))
    return {
        "code_text": code_text,
        "code_system": code_system,
        "code_value": code_value,
        "status": _status_code(r.get("clinicalStatus")),
        "value_num": None,
        "value_unit": None,
        "value_text": None,
        "effective_date": _date(r.get("onsetDateTime")),
        "recorded_date": _date(r.get("recordedDate")),
        "category": None,
    }


def _extract_immunization(r: dict[str, Any]) -> dict[str, Any]:
    vaccine_text, vaccine_system, vaccine_code = _code_fields(r.get("vaccineCode"))
    return {
        "code_text": vaccine_text,
        "code_system": vaccine_system,
        "code_value": vaccine_code,
        "status": _str(r.get("status")),
        "value_num": None,
        "value_unit": None,
        "value_text": vaccine_text,
        "effective_date": _date(r.get("occurrenceDateTime")),
        "recorded_date": None,
        "category": None,
    }


def _resolve_diagnostic_report_results(
    r: dict[str, Any], lookup: dict[tuple[str, str], dict[str, Any]]
) -> str | None:
    """Resolves a DiagnosticReport's result[] references against other resources loaded in
    the same ingest (see ADR note in TODO.md). A reference that doesn't resolve -- the
    referenced Observation isn't in this export, or was dropped -- keeps its `display` text
    with null values rather than being omitted, since that's still useful to show.
    """
    results = r.get("result")
    if not isinstance(results, list) or not results:
        return None
    resolved = []
    for entry in results:
        entry = _obj(entry)
        resource_type, _, resource_id = (_str(entry.get("reference")) or "").partition("/")
        observation = lookup.get((resource_type, resource_id), _EMPTY_FIELDS)
        resolved.append(
            {
                "display": _str(entry.get("display")),
                "code_text": observation["code_text"],
                "value_num": observation["value_num"],
                "value_unit": observation["value_unit"],
                "value_text": observation["value_text"],
                "status": observation["status"],
            }
        )
    return json.dumps(resolved)


def _extract_diagnostic_report(r: dict[str, Any]) -> dict[str, Any]:
    code_text, code_system, code_value = _code_fields(r.get("code"))
    return {
        "code_text": code_text,
        "code_system": code_system,
        "code_value": code_value,
        "status": _str(r.get("status")),
        "value_num": None,
        "value_unit": None,
        "value_text": None,
        "effective_date": _date(r.get("effectiveDateTime") or r.get("issued")),
        "recorded_date": _date(r.get("issued")),
        "category": None,
    }


def _extract_document_reference(r: dict[str, Any]) -> dict[str, Any]:
    type_text, type_system, type_code = _code_fields(r.get("type"))
    return {
        "code_text": type_text,
        "code_system": type_system,
        "code_value": type_code,
        "status": _str(r.get("status")) or _str(r.get("docStatus")),
        "value_num": None,
        "value_unit": None,
        "value_text": None,
        "effective_date": _date(r.get("date")),
        "recorded_date": None,
        "category": None,
    }


EXTRACTORS = {
    "Observation": _extract_observation,
    "Condition": _extract_condition,
    "Immunization": _extract_immunization,
    "DiagnosticReport": _extract_diagnostic_report,
    "DocumentReference": _extract_document_reference,
}

# The allowlist decides what is stored; this decides what any of it means. Asserted rather than
# assumed, at import, because they are edited in different files and the failure is silent: a type
# added to the allowlist without an extractor here would be stored with all ten flattened columns
# empty -- precisely the outcome ADR-0005 exists to make impossible -- and the only visible
# symptom would be a section of blank rows. ADR-0005 anticipates adding types as the way features
# arrive, so this is a path someone will take.
if set(EXTRACTORS) != INGESTED_RESOURCE_TYPES:
    raise AssertionError(
        "EXTRACTORS and INGESTED_RESOURCE_TYPES disagree: "
        f"allowlisted with no extractor {sorted(INGESTED_RESOURCE_TYPES - set(EXTRACTORS))}, "
        f"extractor for a type never ingested {sorted(set(EXTRACTORS) - INGESTED_RESOURCE_TYPES)}"
    )

_EMPTY_FIELDS: dict[str, Any] = {
    "code_text": None,
    "code_system": None,
    "code_value": None,
    "status": None,
    "value_num": None,
    "value_unit": None,
    "value_text": None,
    "effective_date": None,
    "recorded_date": None,
    "category": None,
}

COLUMNS = [
    "resource_id",
    "resource_type",
    "code_text",
    "code_system",
    "code_value",
    "status",
    "value_num",
    "value_unit",
    "value_text",
    "effective_date",
    "recorded_date",
    "category",
    "results_json",
    "raw_json",
]
INSERT_SQL = (
    f"INSERT INTO clinical_records ({','.join(COLUMNS)}) VALUES ({','.join('?' * len(COLUMNS))})"
)


def _read_resource(path: Path) -> dict[str, Any] | str:
    """The file's parsed JSON object, or a short reason it can't be used.

    Parsed from bytes, not text, so json picks the encoding (UTF-8 with or without a BOM,
    UTF-16/32) rather than the platform's locale default.
    """
    try:
        resource = json.loads(path.read_bytes())
    except OSError as exc:
        return f"can't be read ({exc.strerror or exc})"
    except (ValueError, RecursionError) as exc:
        return f"isn't valid JSON ({exc})"
    if not isinstance(resource, dict):
        return "isn't a JSON object"
    return resource


def load_clinical_records(conn: sqlite3.Connection, clinical_dir: Path) -> tuple[int, int]:
    """Loads clinical_dir's *.json FHIR resources into clinical_records. Drop-and-reload.

    Returns (loaded, skipped). `loaded` is *not* the number of files read: only the
    resource types in INGESTED_RESOURCE_TYPES are kept, and the rest are dropped at the door
    and counted in neither. An export holding other types reports fewer records than files,
    by design.

    A missing clinical_dir is a no-op ((0, 0)) that leaves existing rows alone: the table is
    only cleared once there's a source directory to reload it from, so a mistyped path can't
    silently wipe previously-ingested clinical data.

    A file that can't be read or isn't a JSON object is skipped, logged and counted, not
    fatal -- same as load_workout_routes/load_ecg_recordings: this whole ingest runs inside
    one transaction, so one bad file must not discard everything else already loaded. Such a
    file's resource type is unknowable, so it's counted even if it would have been dropped by
    the allowlist anyway. A readable resource with wrong-typed fields isn't skipped at all:
    those fields flatten to None (see _obj/_str/_num above) and the rest of it still loads.
    """
    if not clinical_dir.exists():
        return 0, 0
    conn.execute("DELETE FROM clinical_records")

    # Fields are extracted upfront, for every resource, so DiagnosticReport.result[]
    # references can resolve against any other resource in this same directory, regardless
    # of file/glob order.
    resources = []
    fields_by_ref: dict[tuple[str, str], dict[str, Any]] = {}
    skipped = 0
    for path in sorted(clinical_dir.glob("*.json")):
        resource = _read_resource(path)
        if isinstance(resource, str):
            logger.warning("Skipping clinical record %s: it %s", path.name, resource)
            skipped += 1
            continue
        resource_type = _str(resource.get("resourceType"))
        if resource_type not in INGESTED_RESOURCE_TYPES:
            continue
        resource_id = _str(resource.get("id")) or path.stem
        fields = EXTRACTORS[resource_type](resource)
        resources.append((resource_id, resource_type, resource, fields))
        fields_by_ref[(resource_type, resource_id)] = fields

    rows = [
        (
            resource_id,
            resource_type,
            *(fields[column] for column in _EMPTY_FIELDS),
            (
                _resolve_diagnostic_report_results(resource, fields_by_ref)
                if resource_type == "DiagnosticReport"
                else None
            ),
            json.dumps(resource),
        )
        for resource_id, resource_type, resource, fields in resources
    ]

    conn.executemany(INSERT_SQL, rows)
    return len(rows), skipped
