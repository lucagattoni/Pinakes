# pinakes — project instructions

Architecture lives in [`docs/DESIGN.md`](docs/DESIGN.md). It is the source of truth; this file only
carries rules that change how you work.

## This repository is PUBLIC

- **Never commit real knowledge-base content.** The repo is the engine. The only KB here is the
  synthetic demo corpus under `tests/` — written for the purpose, never harvested.
- Vet every file for PII, credentials, private URLs, and anything copied from memory before staging.
- Never commit model weights or `.pinakes/` state (both are gitignored — keep it that way).

## Naming (fixed — changing any of these is a breaking change)

| Thing | Value |
|---|---|
| Package / command | `pinakes` / `pnk` |
| Manifest / sidecar | `pinakes.toml` / `<file>.pnk.yaml` |
| Generated state | `.pinakes/` |
| MCP tools | `pinakes_*` — never bare `kb_*`, which collides across servers |
| Cross-KB URI | `pnk://<kb-ulid>/<doc-ulid>` — ULIDs only, never aliases |

## Invariants that must not be broken

- **Document and KB ULIDs are permanent.** Never renumber, never regenerate. Every inbound link
  depends on them, and there is no migration machinery by design.
- **`docs/` belongs to the user.** Never modify source documents, and never delete a sidecar without
  an explicit `--prune`-style flag plus a printed list.
- **`.pinakes/` is disposable except `ledger.jsonl`** — a rebuild must preserve spend history.
- **The free path stays free.** No code path may make a paid API call outside `pnk ask --deep`.
- Index schema changes bump `schema_version` and require a rebuild. Never write a migration.

## Building a release — one increment at a time

Each version has a reviewed plan under [`plans/`](plans/) that is the build order (v0.1 shipped as
I1–I15; the current plan is the newest file there). Never batch increments; each one is a separate,
bisectable landing:

1. Own worktree, branch `YYYYMMDD_HHMM-i<N>-<slug>`.
2. Implement the increment **with its tests** — tests ship in the increment that introduces the
   behaviour, never deferred.
3. Green before review: run `./check.sh` (or `make check`) — every gate under `set -e`, so a
   failure is a non-zero exit rather than a line in a log that a pipe then swallows. It formats
   Python **inside Markdown fences** too: a docs-only commit can still fail the gate.
4. **Retrospective review** — a fresh adversarial pass over that increment's own diff, hunting for
   what is wrong, missed, or asserted without evidence. Fix findings, re-run the checks, repeat
   until a pass is clean. Findings and fixes are their own commit, separate from the implementation.
   Findings worth keeping — a real defect, or a fact expensive to rediscover — get a line in
   [`docs/RETROSPECTIVES.md`](docs/RETROSPECTIVES.md); a finding that becomes a durable rule is
   promoted into this file too. Trivia stays in the commit message.
5. **CHANGELOG `[Unreleased]` entry in the same commit as the code** — one line per increment.
6. Merge to `main`, push, remove the worktree.

## Landing work: always push, always release

**Nothing is done until it is on `origin/main` and, when it completes a unit of work, tagged.**
Work left local is invisible to every other agent, machine and scheduled run.

- **Push every landing** to `origin/main` — never leave merged work sitting locally.
- **Cut the release** as soon as the work passes the SemVer table in the global rules (feature =
  MINOR, fix/docs/deps = PATCH, breaking = MAJOR). Complete work never lingers in `[Unreleased]`.
- Release procedure: bump `__version__`, move `[Unreleased]` into a dated `[x.y.z] — YYYYMMDD HH:MM`
  section, commit, then `git tag -a vx.y.z` and push the tag. The tag must equal `__version__` or
  the workflow refuses it. `make release-check` prints both before you tag.
- The tag builds and smoke-tests the wheel every time; the **PyPI upload is gated** on the repo
  variable `PUBLISH_TO_PYPI` so tagging is always safe. Turn it on once trusted publishing exists
  (`gh variable set PUBLISH_TO_PYPI --body true`).
- Create the GitHub release with notes drawn from that CHANGELOG section.
- After anything lands on `main`, fast-forward the primary checkout (`git pull --ff-only`).

## Tooling

- **uv only** — `uv add`, `uv run`, `uv build`. Never pip, poetry, or a hand-managed venv.
- Python 3.13+. `ruff`, `pyright` (strict), `pytest` must pass before any commit.
- `uv run ty check` is a fast pre-check, never the gate: measured at 0.0.63 it catches a
  fraction of what `pyright` strict does (docs/RETROSPECTIVES.md, I1). Re-measure when it
  leaves beta.
- **Core dependencies stay light.** Nothing pulling torch enters `[project.dependencies]` —
  embedding backends are extras (`[st]`, `[light]`). CI runs `[light]`.

## Changing retrieval

Any change to chunking, fusion weights, reranking or the confidence signal must be justified by the
golden-set eval (`recall@k`, MRR, false-abstain rate) — never by intuition alone. Report the before
and after numbers in the commit message.

## Docs

A change to any user-facing surface (CLI flag, manifest key, MCP tool, default, behaviour) updates
`docs/DESIGN.md`, the README and `--help` text **in the same commit**.

**Every date carries a time** — `YYYYMMDD HH:MM`, local 24h — in the CHANGELOG, `docs/DESIGN.md`'s
iteration log and status line, `docs/RETROSPECTIVES.md`, and any "verified on" claim. Several
entries land per day; a bare date loses their order and hides how fresh a verified claim is.
