# ADR-0006: Rename the project to Pomona

- **Status:** Accepted
- **Date:** 2026-09-24

## Context

This repo is being published (see [ADR-0005](0005-ingest-only-the-clinical-types-the-app-renders.md)
for the shape of that: a fresh public repository seeded from the finished tree, with this one
kept private as the archive). The name it carried until now was `apple-healthz` — Apple's
trademark, first word, in the name of a thing other people would install.

Two different uses of the word have to be told apart, because only one of them is a problem:

- **Describing what the app reads.** "A local dashboard for your Apple Health export",
  "single-lead Apple Watch ECG recordings", "Apple's own aggregations". This is nominative
  use: the accurate name of the thing being referred to, with no plausible way to say it
  otherwise. It is necessary, there is a lot of it in the code and docs, and it stays.
- **Naming the product.** `apple-healthz`, the command you type, the package you install, the
  title in the tab. Here the trademark is not describing someone else's product, it is
  standing in for this one — which is the use that suggests affiliation, and the one worth
  not having an argument about. Apple is also specifically known for pursuing it.

Nobody has complained; there is nothing to respond to. The point is that renaming costs one
afternoon now and gets more expensive with every install, every link and every screenshot
after publication.

A name also has to be *available*, and that is a check rather than an opinion. The first
choice here was Orchard, and it failed that check in a way worth recording: `orchard` is an
active project on PyPI (46 releases, `2026.6.2` published June 2026) whose wheel claims the
distribution name `orchard`, the top-level import package `orchard`, the console script
`orchard`, and an `orchard/cli/` submodule — every surface a rename touches. Its summary is
"Python client for Orchard, a compute platform for Apple Silicon", so the name chosen to stop
this project reading as Apple-adjacent was already owned by an Apple-silicon product. The
practical collision is narrow (this app installs by clone, so the two only clash inside one
environment) but the confusion is not, and it defeats the reason for renaming at all.

## Decision

**The project is called Pomona**, after the Roman goddess of fruit trees and orchards. It
keeps the orchard idea, reads as a name rather than a word, is not an apple cultivar, and is
unclaimed on PyPI and in this account's GitHub namespace — checked, not assumed. Concretely:

| Surface | Was | Is |
|---|---|---|
| Display name | `apple-healthz` | Pomona |
| Python package | `src/apple_healthz/` | `src/pomona/` |
| CLI command | `apple-healthz ingest` | `pomona ingest` |
| Distribution name | `apple-healthz` | `pomona` |
| Env prefix | `APPLE_HEALTHZ_*` | `POMONA_*` |
| Browser storage keys | `apple-healthz-theme`, … | `pomona-theme`, … |

`apple_health_export/` keeps its name: that is the directory Apple's own export unpacks to,
not this project's, and renaming it would make the docs describe something the reader doesn't
have. `rel="apple-touch-icon"` likewise stays — it is an attribute name from Apple's own
spec, not a choice.

The README says outright that the project is not affiliated with or endorsed by Apple, and
that Apple's marks appear only to name what the app reads. That statement is cheap, true, and
the thing a reader would otherwise have to guess at.

The old `APPLE_HEALTHZ_*` prefix is **not read**. Accepting it as a fallback would keep two
names for one setting alive indefinitely, which is the half-rename rejected below.

For the duration of the rename, `config.py` also warned on startup about variables still
carrying the old prefix, because `extra="ignore"` drops them silently and the setting then
falls back to its default — surfacing as a missing database, which the "no database yet" page
explains as a working-directory mistake, the one cause it isn't. That warning was removed
before publication: the rename precedes the first public commit, so nobody outside this repo
can have the old prefix set, and a migration aid with no one left to migrate is sixty lines of
code and nine tests describing a name the project no longer uses.

## Alternatives considered

| Option | Why not |
|---|---|
| Keep `apple-healthz` | The whole reason for the rename. A personal repo nobody installs is a different risk from a published one that strangers do, and the cost of changing it only ever grows. |
| Rename the display name only, keep the module and command | Half a rename is the worst of both: the trademark is still what you type to run it and what appears in an install log, and the project pays the confusion of two names anyway. |
| **Orchard** | The first choice, and abandoned on evidence rather than taste — see Context. `orchard` on PyPI is an active Apple-silicon compute platform claiming the same distribution name, import package and console script. Keeping it would have meant never publishing under it and sharing a name with a product in the exact domain this rename exists to get away from. |
| Honeycrisp | A good name, rejected for being an *apple* cultivar specifically — a name that still points at Apple is a smaller version of the problem, and it invites reading the resemblance as intentional. Pomona is the orchard, not a variety in it. |
| Hortus, Graftwork, Gleaning, Pomarium | All verified free, all fine. Pomona was preferred as the most pronounceable and most memorable; Pomarium was additionally weakened by *pomum* meaning apple. |
| Something health-flavoured (`vitals`, `healthz`) | Generic to the point of being unsearchable, and `healthz` on its own is a well-known Kubernetes-style endpoint convention, so it names a liveness probe to most readers. A health-sounding name also pulls against the README's own disclaimer that this is not a medical device. |
| Wait for a problem | There is no version of this where waiting is cheaper. |

A note for the next rename, since this one needed two passes: **check the name against the
registries before writing any of it down.** Single common English words are effectively all
claimed on PyPI — fifteen candidates were tried and every one was taken — so the realistic
field is proper nouns, compounds and coinages.

## Consequences

Anyone with an existing checkout runs `uv sync` to pick up the new command name, which also
uninstalls the old `apple-healthz` entry point. It has to be the explicit command: the
implicit sync behind `uv run` leaves the previous project's console script in `.venv/bin`,
where it stays on the PATH and fails with a `ModuleNotFoundError` rather than pointing
anywhere useful. Observed during this rename, not theorised. `.env` files need their variable prefix changed. Browser-stored UI preferences
— theme, expanded metric groups, the routes basemap — are keyed by name and so reset once;
they are remembered UI state, not data, and `lib/storage` treats a missing value as the
default by design.

Earlier `CHANGELOG.md` entries were updated to say `pomona ingest` where they said
`apple-healthz ingest`. That is a deliberate exception to leaving history alone: the old
command does not exist any more, so a reader following one of those entries would type
something that fails. The claims themselves are untouched.

No ADR before this one is invalidated. [ADR-0005](0005-ingest-only-the-clinical-types-the-app-renders.md)
is the only earlier one that cites a module path; it now reads `pomona/clinical.py`, which is
the same decision about a renamed file, updated in place rather than superseded.
