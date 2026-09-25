# AGENTS.md

Working notes for anyone (human or AI) contributing to this repo — how to work in the code,
and why things are the way they are. `DESIGN.md`/`ARCHITECTURE.md` (if this project has one)
is the source of truth for *what* we're building; this file is *how*.

## Conventions

- Commit messages: [Conventional Commits](https://www.conventionalcommits.org/)
  (`type(scope): subject`); no `Co-Authored-By` trailer. Enforced by a
  `commit-msg` hook — run `lefthook install` once after cloning. See
  [CONTRIBUTING.md](CONTRIBUTING.md) for the full commit/PR/ADR process.
- **Never commit directly to `main`.** One PR per feature. Branch prefixes:
  `feat/<slug>`, `fix/<slug>`, `chore/<slug>`, `docs/<slug>`.
- **Build as if this repo were public.** No secrets, credentials, tokens, or
  real user data committed — ever, not "temporarily," not in a branch you plan
  to squash. Config comes from environment variables (`.env`, gitignored). A
  `no-secrets` pre-commit hook backs this up but isn't a substitute for not
  doing it in the first place.

## Database schema

**There is no migration system, and the schema is not versioned.** The database
is a derived artifact: `pomona ingest` is drop-and-reload, rebuilding
every table from `export.xml` and `clinical-records/` on each run (see
[ADR-0002](docs/adr/0002-sqlite-storage-streaming-ingestion-no-in-app-chat.md)).
Nothing in it is authored in-app, so nothing is lost by discarding it.

The catch: `db.py` creates tables with `CREATE TABLE IF NOT EXISTS`, which is a
no-op against a database that already has a table of that name — **including one
built from an older schema**. So a schema change doesn't reach an existing
database at all, and the next ingest fails on the mismatch, e.g.:

```
OperationalError: table clinical_records has no column named resource_id
```

If you change `SCHEMA`, delete your database file before re-ingesting, and say
so in `CHANGELOG.md` so other people know to do the same. There's no
version-and-migrate path to reach for — that's the deliberate trade for the
drop-and-reload model, not an oversight to work around. See
[ADR-0003](docs/adr/0003-synthetic-row-ids-and-no-schema-migrations.md) for the
reasoning and for when it should be revisited.
