"""Clinical records from the FHIR export, flattened for the clinical page."""

import json

from fastapi import APIRouter

from pomona import fhir
from pomona.api.dependencies import DbDep
from pomona.api.query import where_clause
from pomona.clinical import INGESTED_RESOURCE_TYPES

router = APIRouter(prefix="/api", tags=["clinical"])


@router.get("/clinical")
def clinical(
    conn: DbDep,
    resource_type: str | None = None,
    start: str | None = None,
    end: str | None = None,
) -> list[dict]:
    # An IN, not a NOT IN, and built from the shared allowlist rather than spelled out here.
    # A database built before a type was dropped from the ingest list still holds those rows
    # until the next drop-and-reload; asking for the types this app serves excludes them, and
    # excludes anything else unexpected in there, without having to know what it is.
    # See pomona.clinical for why both layers apply the policy.
    served = sorted(INGESTED_RESOURCE_TYPES)
    if not served:
        # `IN ()` is a SQLite syntax error, so an empty allowlist would turn every request into a
        # 500 rather than into an empty page. Nothing can be served, which is what this returns.
        return []
    conditions = [f"resource_type IN ({', '.join('?' * len(served))})"]
    condition_params = [*served]
    if resource_type:
        conditions.append("resource_type = ?")
        condition_params.append(resource_type)
    where_sql, params = where_clause(
        "date(effective_date, 'unixepoch')", start, end, conditions, condition_params
    )

    # raw_json only for Observations: it's the one type whose reference range and components
    # the page uses, and the other types' raw payloads (documents especially) can be large.
    rows = conn.execute(
        f"""
        SELECT id, resource_type, code_text, code_system, code_value, status,
               value_num, value_unit, value_text, effective_date, category, results_json,
               CASE WHEN resource_type = 'Observation' THEN raw_json END AS raw_json
        FROM clinical_records
        {where_sql}
        ORDER BY effective_date DESC
        """,
        params,
    ).fetchall()
    records = []
    for row in rows:
        record = dict(row)
        results_json = record.pop("results_json")
        # A database ingested before the loader dropped non-finite numbers can hold Infinity
        # or NaN in here, which the response can't encode; read them as missing instead.
        record["results"] = (
            json.loads(results_json, parse_constant=lambda _: None) if results_json else None
        )
        # Parsed once here, not once per helper: both read the same stored resource.
        resource = fhir.parse_resource(record.pop("raw_json"))
        record["reference_range"] = fhir.reference_range(resource)
        record["components"] = fhir.components(resource)
        records.append(record)
    return records
