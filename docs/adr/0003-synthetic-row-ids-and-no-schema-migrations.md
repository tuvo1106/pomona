# ADR-0003: Synthetic row ids for clinical records; no schema migrations

- **Status:** Accepted
- **Date:** 2026-08-20

## Context

`clinical_records` was originally keyed `id TEXT PRIMARY KEY`, populated from the FHIR
resource's own `id` field. That assumes a FHIR `id` is globally unique. It isn't. A FHIR
`id` is unique only within a resource type on a single issuing server, so an export can
legitimately contain a `Condition` and an `Observation` both numbered `"1"`, and two
provider servers can each issue an `Observation/1`. Real exports aggregate records from
multiple providers, so both cases are reachable.

The failure was not a wrong row — it was `sqlite3.IntegrityError` raised inside
`executemany`, propagating out of `cli.ingest`, rolling back the single wrapping
transaction and discarding **the entire ingest**, XML records included. One duplicated
id in ~100 clinical JSON files threw away a 1.5GB import.

Fixing the key means changing `SCHEMA` in `db.py`, which forces a second decision: this
project has no migration system, and had no stated position on whether it should get one.

## Decision

**Key `clinical_records` on a synthetic row id.** `id INTEGER PRIMARY KEY` (SQLite's
rowid), with the FHIR resource's own id kept as an ordinary, non-unique `resource_id
TEXT NOT NULL` column. Nothing in the application needs the FHIR id to be unique; it is
looked up, displayed, and used to resolve references, never used as an identity
constraint.

**No migration system, and the schema stays unversioned.** The database is a derived
artifact — `ingest` is drop-and-reload (ADR-0002), rebuilding every table from
`export.xml` and `clinical-records/` on each run. Nothing in it is authored in-app, so
discarding it loses nothing that cannot be regenerated. A schema change is therefore
handled by deleting the database file and re-ingesting, documented under **Database
schema** in `AGENTS.md`.

## Alternatives considered

| Option | Why not |
|---|---|
| Composite `PRIMARY KEY (resource_type, id)` | The fix proposed in review, and it does resolve the cross-type collision. But it still rejects the same `Observation/1` issued by two different provider servers — the harder half of the problem — and it keeps `id` non-unique across a result set that spans resource types, which the clinical table relies on for its React keys. Same breaking schema change, less of the problem solved. |
| `INSERT OR REPLACE` on the existing key | Converts a hard failure into silent data loss: two genuinely distinct resources that happen to share an id, and the second overwrites the first with no signal. |
| Store `id` as the FHIR relative reference (`"Observation/1"`) | Canonical FHIR, and avoids any schema change at all since the column stays `TEXT`. Rejected because it encodes a compound key in a string — sorting, joining, and filtering all have to parse it back apart — and it still collides across provider servers. |
| Version the schema and write migrations | Real cost — a version table, an ordered migration runner, and a migration authored per schema change — to preserve a file that is fully reproducible from the export in one command. Worth revisiting only if the database ever holds data that isn't derived from an export (see `TODO.md`: incremental webhook ingest would put authored data in the DB and change this calculus). |

## Consequences

Duplicate FHIR ids across any dimension are now a non-event; the `resource_id` column
carries the original value for display and for resolving `DiagnosticReport.result[]`
references later. `/api/clinical` returns a genuinely unique `id`, so the frontend's
table keys are sound across resource types.

The cost is a breaking change with no migration path: an ingest against a database built
before this lands fails with `table clinical_records has no column named resource_id`,
because `CREATE TABLE IF NOT EXISTS` is a no-op against an existing table. The fix is to
delete the file. That is cheap here precisely because of ADR-0002's drop-and-reload
model — but it means every future schema change carries the same one-line release note,
and the error a stale database produces is a confusing one that has to be explained
rather than handled. If that becomes a recurring cost, or if the database ever holds
non-derived data, this decision should be revisited in favour of real migrations.
