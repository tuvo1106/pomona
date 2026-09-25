# Contributing

## Commit messages

[Conventional Commits](https://www.conventionalcommits.org/): `type(scope): subject`, imperative, ≤72 chars.

Types: `feat` `fix` `docs` `refactor` `perf` `test` `build` `ci` `chore` `revert`.

No `Co-Authored-By` trailer.

Enforced by a `commit-msg` hook — run `lefthook install` once after cloning.

## Before opening a PR

- Fill out the [PR template](.github/PULL_REQUEST_TEMPLATE.md).
- `CHANGELOG.md` updated under `[Unreleased]` for anything user-visible.
- A decision that's hard to reverse, non-obvious to the next reader, or reached by rejecting a
  plausible alternative gets an ADR in [docs/adr/](docs/adr/) — see ADR-0001.

## Where things live

- `README.md` — getting started, nothing else. Install, the demo dataset, the short path for
  your own data, and links out. If something belongs to one reader in ten, it goes in `docs/`.
- `docs/YOUR-DATA.md` — the full walkthrough for a reader bringing their own Apple Health
  export: getting it off the phone, what's in it, what's ignored, timings, troubleshooting.
- `AGENTS.md` — how to work in this repo: conventions, branch/PR policy, security posture.
- `DESIGN.md` / `ARCHITECTURE.md` — the specification and how it's wired, if the project has one.
- `docs/adr/` — decisions made during implementation that the above don't cover.
- `CHANGELOG.md` — what shipped and why, once it has.
