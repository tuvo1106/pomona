# ADR-0002: Local SQLite storage with streaming ingestion; no in-app chat

- **Status:** Accepted
- **Date:** 2026-08-19

## Context

The Apple Health export (`export.xml`) is 1.5GB with 3.4M+ `<Record>` elements, plus a small
`clinical-records/` directory of FHIR JSON files. The dashboard needs fast, ad-hoc,
filterable/aggregatable queries over this data, entirely locally, with no server to operate.
Loading the whole XML file into memory (DOM parsing) is not viable at this size. Separately, the
project needs a way to answer natural-language questions about the data (e.g. "what was my
average resting heart rate last month?").

## Decision

**Storage and ingestion:**
- **SQLite** as the storage engine: a single local file, zero setup, fast enough for this data
  volume with the right indexes, and trivially inspectable with the ubiquitous `sqlite3` CLI (or
  by any LLM agent with shell access — see below).
- **Streaming ingest**: `xml.etree.ElementTree.iterparse` over `(start, end)` events, clearing
  each element (and periodically the root) as it's consumed, so peak memory stays flat regardless
  of file size. No `lxml` dependency — stdlib is sufficient for this access pattern.
- **Drop-and-reload, not upsert**: Apple Health records carry no stable ID across exports, and a
  re-export is always a full fresh dump, not incremental. `DELETE` + reinsert inside one
  transaction means a crash mid-ingest leaves the previous good database untouched, and there's no
  merge/upsert logic to get wrong.
- **Clinical records ingested separately**: `clinical-records/` is ~96 small flat JSON files
  (~452KB total) — plain `json.load` per file, no streaming needed. Kept in its own loader module
  since it's a structurally different pipeline (many small files vs. one huge file).

**Natural-language questions — no in-app chat feature:** rather than building a chat endpoint
into the app (a Claude tool-use loop with a read-only SQL tool, a chat UI, session state), the
local SQLite file is just queried directly by asking Claude (e.g. in a Claude Code session with
shell access to the machine) — the same read-only-safe querying an in-app feature would provide,
with no additional code to maintain and no separate billing relationship. An in-app version of
this was briefly built and then removed for exactly this reason; see Alternatives below for what
it would have looked like and why it didn't stay.

## Alternatives considered

| Option | Why not |
|---|---|
| DuckDB | Faster for pure analytical scans, but SQLite is already comfortably fast at this row count with composite indexes, and stdlib `sqlite3` avoids an extra dependency. |
| Postgres (local) | Requires running a server process for a single-user local app — unnecessary operational weight. |
| DOM parsing (`ElementTree.parse`) | Loads the full 1.5GB tree into memory at once; unnecessary given `iterparse` handles this natively. |
| Upsert on re-ingest | Solves a problem that doesn't occur — exports have no stable cross-export ID and are always full dumps. |
| In-app chat: `/api/chat` running a Claude tool-use loop against a read-only SQL tool (`mode=ro` connection + regex validation), with a React chat panel and in-memory sessions | Requires an `ANTHROPIC_API_KEY` billed separately via console.anthropic.com — not covered by a Claude Pro/Max subscription — to duplicate a capability an already-open Claude Code session provides for free via direct file access. Adds a bespoke tool-use loop, SQL-safety validation, and session state to maintain for a single-user local tool. |

## Consequences

Ingest is a single, restartable, all-or-nothing CLI command. Re-running it after a new export is
always safe. The tradeoff is that ingest is O(full file) every time — acceptable since this is an
occasional, one-shot operation, not a hot path. The dashboard has no built-in NL Q&A of its own;
asking questions about the data requires a Claude session (e.g. Claude Code) with access to the
machine it's running on, which is an acceptable constraint for a single-user, local-only tool.
Smaller dependency footprint (no `anthropic` SDK) and less code to maintain as a result.
