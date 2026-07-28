# pinakes — project instructions

Architecture and rationale live in [`docs/DESIGN.md`](docs/DESIGN.md); [`docs/README.md`](docs/README.md)
indexes the rest (which file owns which fact). This file only carries rules that change how you work.

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
  an explicit `--prune`-style flag plus a printed list. The one exception: a paid PDF extraction (or
  `--force` discarding one) additively rewrites that document's own sidecar with
  `provenance.extraction` (docs/DESIGN.md §2.2) — never any other key, and never for a free
  extraction.
- **`.pinakes/` is disposable except `ledger.jsonl`** — a rebuild must preserve spend history.
- **The free path stays free — paid entry points are an enumerated allowlist.** Exactly these may
  spend: `pnk sync` with `[extraction] backend = "claude-vision"` or `--extract=claude-vision`;
  `pnk ask --deep` (v0.4). Each goes through the §5 accountant. Adding an entry point edits this
  list, `.paid-path-allowlist` and DESIGN §1 in the same commit. Four gates enforce it in
  `check.sh` and CI (`tools/paid_path_gate.py`, `tests/test_paid_path.py`); the one that matters
  runs the whole free path in a fresh subprocess and asserts no paid client reached `sys.modules`.
  **Never probe a backend's availability by loading it** — `is_backend_installed` answers through
  `find_spec`; `load_extractor` runs the factory, which imports the client.
- **Money is `Decimal` end to end, quantised only once — at ledger-write time.** Convert a TOML
  float via `Decimal(str(value))`, never `Decimal(value)` directly: the latter reproduces float's
  own binary imprecision instead of the clean decimal a human wrote — verified directly,
  `Decimal(0.05) != Decimal("0.05")`.
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
   **Then break the code on purpose.** For the 3–5 most safety-critical assertions, mutate the
   source (delete the guard, flip the comparison, neuter the conversion), confirm the *right* test
   fails, and restore. Green proves the tests ran, never that they can detect the defect: I5 tested
   paid-extraction protection down one of four code paths, and I6a's timezone conversion passed all
   35 tests with the conversion deleted, because every fixture was built in the target zone. Both
   were the same increment-shaped blind spot — tests written by the reasoning that wrote the code
   inherit its assumptions.
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
- **Before assigning the next release number, check what has already landed on `main`.** `git fetch`
  and diff `origin/main` against this work's own base first — another agent, session, or worktree
  may have cut a release since this branch started, so the number you were about to assign, or a
  plan's assumed version target, may already be taken. Only decide the number after that check.
  Caught 20260728: an I6a worktree almost reasoned about "0.2.1 vs 0.3.0" from a stale base, when a
  parallel docs pass had already shipped v0.2.1.
- **Cut the release** as soon as the work passes the SemVer table in the global rules (feature =
  MINOR, fix/docs/deps = PATCH, breaking = MAJOR). Complete work never lingers in `[Unreleased]`.
- Release procedure: bump `__version__`, move `[Unreleased]` into a dated `[x.y.z] — YYYYMMDD HH:MM`
  section (add its link definition at the foot and repoint `[Unreleased]`'s compare), commit,
  **merge to `main` from the primary checkout**, push, then `git tag -a vx.y.z` and push the tag.
  The tag must equal `__version__` or the workflow refuses it — `make release-check` prints both.
- **Verify, never assume, that a release happened**: `git tag -l`, `gh release list`, and
  `git merge-base --is-ancestor vx.y.z main` before writing release notes. A CHANGELOG entry and a
  `__version__` are only claims — v0.1.0 had both for two days with no tag, no release and nothing
  published (docs/RETROSPECTIVES.md, 20260727).
- **Never run `git merge` from inside the feature worktree.** Merging a branch into itself reports
  "Already up to date", the following push reports "Everything up-to-date", and a tag created there
  points off-`main` — three successful commands, nothing landed.
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
  embedding backends are extras (`[st]`, `[light]`), and so are the PDF extractors (`[pdf]`,
  `[claude]`). CI's `check` job is a three-leg matrix over `[light]`, `[light,pdf]` and
  `[light,pdf,claude]`.

## Changing retrieval

Any change to chunking, fusion weights, reranking or the confidence signal must be justified by the
golden-set eval (`recall@k`, MRR, false-abstain rate) — never by intuition alone. Report the before
and after numbers in the commit message.

## Docs

**One fact, one home** — [`docs/README.md`](docs/README.md) is the routing table (which file owns
which fact) and the per-increment landing checklist. `docs/DESIGN.md` is rationale only; it changes
only when the *reasoning* changes, never for a new flag or field alone.

- **README and DESIGN.md are deliberately version-free** — they describe what pinakes *is*, never
  which release it's on. Never reintroduce a version number or "as of vX" claim into their prose
  (CHANGELOG.md `[0.2.1]` — a 20260728 restructure existed specifically to stop that drift).
- **Verify docs by running the commands they show**, install line included — prose drifts toward
  the design, because the design is what you're thinking about while writing it. An audit at 0.1.2
  found four README claims contradicting the code while `cli.py` and the CHANGELOG were correct in
  the same places (docs/RETROSPECTIVES.md, 20260727).
- **Every date carries a time** — `YYYYMMDD HH:MM`, local 24h — in the CHANGELOG, `docs/STATUS.md`,
  `docs/RETROSPECTIVES.md`, and any "verified on" claim.
- **Read the clock; never compose a timestamp.** Run `date "+%Y%m%d %H:%M"` and paste the result —
  session context carries a date, never a time, and an invented `HH:MM` lands in the future about
  half the time (docs/RETROSPECTIVES.md, 20260727 17:00).
