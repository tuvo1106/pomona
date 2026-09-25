# TODO

Deliberately deferred out of v1. Circle back here rather than re-discovering these later.

The frontend UI backlog is finished -- all twenty-six items shipped. What's left of that
file, [docs/UI-BACKLOG.md](docs/UI-BACKLOG.md), is how to verify frontend work and which
apparent inconsistencies are deliberate.

- **`export_cda.xml`** (513MB, HL7 CDA/C-CDA document, `<ClinicalDocument>` root) — evaluated,
  not worth parsing. It's Apple's clinical-interop re-encoding of a small slice of `records`:
  478,428 `<observation>` entries but only **8** distinct HealthKit types across all of them
  (`BloodPressureDiastolic/Systolic`, `BodyMass`, `DietaryWater`, `HeartRate`, `Height`,
  `OxygenSaturation`, `RespiratoryRate` — grep `<type>[^<]*</type>` to re-check against a new
  export). Every one of those types is already fully covered by `export.xml`'s `<Record>`
  elements (verify by comparing a `<value>`/`<effectiveTime><low value="...">` pair against
  the matching row in `records`) — no workouts, no activity summaries, no types absent from
  `export.xml`. Nothing to build here unless a future export's type list grows beyond these 8.
- **Multi-sport `WorkoutActivity` DTD element** — zero occurrences in the current export, not
  handled. Would be a gap if a future export uses Apple's newer multi-sport workout model.
- **Materialized rollup tables** — deliberately skipped; raw indexed queries are fast enough at
  this data volume. Revisit only if the dashboard is ever measurably slow.
- **`Correlation` elements** (e.g. blood-pressure groupings) — skipped since the underlying
  Records are already ingested individually. Revisit if grouped display is wanted.
- **Automated sync (webhook ingest)** — Apple exposes no public API to pull HealthKit data
  remotely; the only real automation path is the third-party **Health Auto Export** iOS app
  (paid), which reads HealthKit on-device and pushes JSON to a REST webhook on a schedule
  (roughly hourly — iOS background limits prevent real-time; it's a push, and pauses if the
  phone is offline). To use it: add an `/api/ingest` route that accepts Health Auto Export's
  JSON payload and **upserts** (not drop-and-reload — this is incremental, unlike the full
  XML export) into the same local SQLite DB, keyed to dedupe re-sent overlapping windows (e.g.
  on `(type, start_date, source_name)`). Requires installing/configuring Health Auto Export on
  the phone and network reachability from phone to this server (same Wi-Fi, or a tunnel like
  Tailscale for away-from-home use) — neither of those can be set up from this repo.
  Third-party projects doing roughly this (for reference, not adopted): `alphonsekoh/apple-health-mcp`,
  `mikipalet/apple-health-mcp` (the latter pushes to a remote Postgres via Vercel, not local).
  Until this exists, re-export manually from the Health app and re-run
  `pomona ingest` — it's idempotent (drop-and-reload) and safe to run anytime.
