# Changelog

All notable changes to this project are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this
project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- **Running mileage** — a dashboard card with the total distance and run count for the
  selected range, and a bar per month under it, with months still in progress drawn faded.
  Distances recorded in both km and mi (or m, yd) are converted to the unit most runs used,
  rather than added together, and runs with no usable distance are called out instead of
  silently left out. No schema change, so no need to delete your database.
- **"This year" range** — calendar year to date, alongside the rolling "Last year".

### Changed

- **An invalid `bucket` or `mode` API parameter is now a 422, not a 400,** the same status the API
  already gave every other invalid parameter. Only matters if you call the API directly.
- **A clinical record's name and status come from the first coding that has one.** Ingest used
  to read only the first coding, so a record whose first coding had no name, or a condition whose
  first status coding had no code, showed as "—" even when a later coding (or the status text)
  had it. Names now follow the same rule as the parts of a blood-pressure panel, and an empty
  text value is stored as no value rather than shown as a blank. Re-run `pomona ingest` to pick
  it up; no need to delete your database.

### Removed

- **The `daily_resting_hr` and `daily_weight` SQL views.** Nothing in the app read them. Your next
  `pomona ingest` drops them from an existing database; no table changed, so you don't need to
  delete it.

### Fixed

- **A malformed clinical record no longer aborts the whole ingest.** One bad file in
  `clinical-records/` used to roll back everything, `export.xml` included. A file that can't be
  read or isn't valid JSON is now skipped, named on stderr and counted in the ingest summary,
  the same way bad GPX and ECG files already were. A record with a field of an unexpected type
  still loads, with that field left empty. Files saved with a UTF-8 byte-order mark now load.
- **Two clinical records with the same type and id each keep their own values.** Previously both
  were stored with the second file's code, value and status, so a lab result could show another
  record's value. No schema change, so no need to delete your database.
- **One odd clinical record can no longer take down the clinical page or the ingest.** A value
  or range bound too large to hold (`1e999`, or an integer hundreds of digits long) is now left
  empty. Before, the first made the whole clinical page fail to load and the second aborted the
  ingest. A record nested deeply enough to overflow the parser no longer breaks the page either.
  No need to delete your database or re-ingest.
- **Reference ranges and blood-pressure-style panels display more safely.** A range unit that
  isn't text is ignored rather than shown as `[object Object]`, which also silently stopped the
  result from being flagged. A panel part with no label and no value is dropped instead of shown
  as a blank part.

## [0.1.0] - 2026-09-25

First public release. Pomona reads an Apple Health export into a local SQLite database and
serves a dashboard over it, on your own machine.

### Added

- **Ingest** — `pomona ingest` streams `export.xml` (1.5GB and millions of records is normal)
  into SQLite, along with FHIR clinical records, GPX workout routes and ECG recordings from the
  sibling directories. Drop-and-reload inside one transaction, so it is safe to re-run and a
  crash leaves the previous database untouched. About a minute for 3.4 million records.
- **Dashboard** — every metric type the export contains, grouped into eight sections, with a
  range filter (Today, 7 / 30 / 90 days, last year, all time, custom) that drives every chart
  and lives in the URL. Daily activity as Move/Exercise/Stand rings and a calendar heatmap,
  blood pressure as a paired series, sleep by stage, and an overview that compares each figure
  against the preceding period.
- **Workouts, Routes, ECG and Clinical tabs** — workouts with per-activity summaries; GPS
  tracks drawn on a map, matched to their workout by time overlap; single-lead ECG waveforms on
  paper-grid axes; and labs, conditions and immunizations from `clinical-records/`, including
  panels whose values live in FHIR `component[]` rather than a top-level value.
- **Deduplication** — iPhone and Apple Watch both log steps, distance and energy, overlapping.
  Summing them double-counts, so overlapping windows are resolved before any total is shown.
- **A synthetic demo export** — `scripts/make_demo_export.py` generates a full export from a
  seeded PRNG, so the app can be run and screenshotted without anyone's real data.

### Deliberate limits

Each of these is a decision with an ADR in [`docs/adr/`](docs/adr/), not an oversight:

- **The routes basemap is off until you turn it on.** Map tiles are the only thing this app
  fetches from anywhere else, and a tile request tells that server roughly where you walk.
  With it off, nothing leaves your machine (ADR-0004).
- **Clinical resource types are an allowlist.** Five types are ingested from
  `clinical-records/` — `Observation`, `Condition`, `Immunization`, `DiagnosticReport`,
  `DocumentReference` — and everything else your provider exported is dropped as the directory
  is read, rather than stored and then shown as a pane headed by a raw FHIR type name. The
  `Patient` record holding your name and date of birth is not among them (ADR-0005).
- **No schema migrations.** The database is a derived artifact; a schema change means deleting
  the file and re-ingesting, which the CLI tells you when it happens (ADR-0003).
- **`export_cda.xml` is ignored.** It re-encodes a small slice of data `export.xml` already
  carries in full, at ~520MB.
