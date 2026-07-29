# pinakes — project instructions

Architecture and rationale live in [`docs/DESIGN.md`](docs/DESIGN.md); [`docs/README.md`](docs/README.md)
indexes the rest (which file owns which fact). This file only carries rules that change how you work.

## This repository is PUBLIC

- **Never commit real knowledge-base content.** The repo is the engine. The only KB here is the
  synthetic demo corpus under `tests/` — written for the purpose, never harvested.
- **An API key lives in `.env`, which is gitignored by pattern (`.env`, `.env.*`).** The paid
  extractor needs a real key, so one on this machine is normal; one that is merely *untracked* is
  a `git add -A` away from a public repo. Pass it explicitly — `uv run --env-file .env pnk …` —
  and never teach pinakes to load `.env` itself: a tool that can spend must not pick up
  credentials from a file nobody pointed it at ([docs/MEASUREMENT-RUN.md](docs/MEASUREMENT-RUN.md)).
- Vet every file for PII, credentials, private URLs, and anything copied from memory before staging.
- Never commit model weights or `.pinakes/` state (both are gitignored — keep it that way).

## 🚫 Unbuilt work is named, never numbered

**A version number belongs to a release when it is cut — never before.** Refer to unbuilt work by
name:

| Name | What it is |
|---|---|
| **the paid-extraction release** | Budget machinery, the paid Claude-vision extractor, `path:page` citations (I6–I9) |
| **the links release** | `pnk link`, `pinakes_links`, reverse-scan, link-coverage reporting |
| **the graph release** | Structural edges, the expansion channel — each eval-gated |
| **the deep release** | `pnk ask --deep` |
| **the template release** | Template ecosystem, `pnk upgrade`, the `sqlite-vec` tier |

**Never write `v0.4` for something unbuilt** — not in docs, not in `--help`, not in an error message,
not in a code comment. Increment IDs (`I7b`, `I8`) stay: they name work inside a written plan, not a
release. Decided 20260729 00:09, after `v0.3` came to mean two different releases at once and either
reading would have renumbered ~60 committed references
([docs/STATUS.md](docs/STATUS.md#release-roadmap)). Historical records — `CHANGELOG.md`,
`docs/RETROSPECTIVES.md`, `plans/`, the dated research in `docs/graph/` — keep the numbers they were
written with and carry a header note.

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
- **`.pinakes/` is disposable except `ledger.jsonl` and any cache entry a paid backend wrote** —
  a rebuild must preserve spend history, and the ledger is append-only: correct a record by
  appending another (`pnk budget --resolve`), never by editing or rewriting it. A paid cache entry
  is derived state that cost real money to derive, which is not the same as disposable: the
  automatic sweep already spares it, and destroying one takes an explicit `--clear-cache=paid`.
- **A `void` ledger record needs proof the call never billed** — written only when a
  `response_received` flag is false, never from a bare `finally`, which would record €0 for money
  that already left the account. Under-counting is the one direction a budget may never be wrong in.
- **The free path stays free — paid entry points are an enumerated allowlist.** Exactly these may
  spend: `pnk sync` with `[extraction] backend = "claude-vision"` or `--extract=claude-vision`;
  `pnk ask --deep` (the deep release). Each goes through the §5 accountant. Adding an entry point
  edits this list, `.paid-path-allowlist` and DESIGN §1 in the same commit. Four gates enforce it in
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
   Findings worth keeping — a real defect, or a fact expensive to rediscover — get a fragment in
   [`retro.d/`](retro.d/README.md); a finding that becomes a durable rule is promoted into this
   file too. Trivia stays in the commit message.
5. **A `changelog.d/` fragment in the same commit as the code** — never an edit to `CHANGELOG.md`
   itself ([`changelog.d/README.md`](changelog.d/README.md)).
6. Merge to `main`, push, remove the worktree.

## Landing work: always push, always release

**Nothing is done until it is on `origin/main` and, when it completes a unit of work, tagged.**
Work left local is invisible to every other agent, machine and scheduled run.

- **Push every landing** to `origin/main` — never leave merged work sitting locally.
- **Before merging, run `python3 tools/shared_file_overlap.py --fetch --strict`.** Several agents
  work in this repo at once. It names the files this branch touches that `origin/main` has touched
  too since they diverged — then go and *read* those files' merged state. A clean auto-merge is not
  a correct merge: git merges edits that do not overlap textually, never edits that agree, so two
  agents can leave one document contradicting itself with every command reporting success. Caught
  20260729, when three branches edited `CHANGELOG.md`, `docs/STATUS.md` and `docs/DESIGN.md` inside
  one hour; `CHANGELOG.md` conflicted loudly and the other two merged silently. For the two
  documents every change writes to, the cause is removed rather than reported — see
  [`changelog.d/`](changelog.d/README.md) and [`retro.d/`](retro.d/README.md).
- **Before assigning the next release number, check what has already landed on `main`.** `git fetch`
  and diff `origin/main` against this work's own base first — another agent, session, or worktree
  may have cut a release since this branch started, so the number you were about to assign, or a
  plan's assumed version target, may already be taken. Only decide the number after that check.
  Caught 20260728: an I6a worktree almost reasoned about "0.2.1 vs 0.3.0" from a stale base, when a
  parallel docs pass had already shipped v0.2.1.
- **Cut the release** as soon as the work passes the SemVer table in the global rules (feature =
  MINOR, fix/docs/deps = PATCH, breaking = MAJOR). Complete work never lingers in `[Unreleased]`.
- Release procedure: `python3 tools/fragments.py --apply` (splices `changelog.d/` and `retro.d/`
  into their documents and deletes the fragments), bump `__version__`, move `[Unreleased]` into a
  dated `[x.y.z] — YYYYMMDD HH:MM`
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
- **A tag now publishes to PyPI.** `PUBLISH_TO_PYPI` has been `true` since 20260728 17:15, so
  pushing a tag uploads a release the world can install — and PyPI does not allow re-uploading a
  version. The build and wheel smoke test still run first, and the workflow still refuses a tag
  disagreeing with `__version__`, but the safety net that made a bad tag merely embarrassing is
  gone. Run `make release-check` **before** pushing the tag, never after.
- Create the GitHub release with notes drawn from that CHANGELOG section.
- **A release makes three documents stale the moment it publishes** — sweep them in the release
  commit, not later: `docs/STATUS.md`'s *Published on PyPI* table (the published-version list, which
  is a fact about the index, not about this repo), its *Release roadmap* (tick the row and drop the
  name from the unbuilt-names table above it), and `README.md`'s install lines if the release added
  an extra or a capability a new user would look for. Verify by querying the index
  (`curl -s https://pypi.org/pypi/pinakes/json`) and installing what the docs show — not by reading
  them. **That endpoint is CDN-cached**: a query moments after an upload can return the previous
  release list, so bust the cache and cross-check `https://pypi.org/simple/pinakes/` before
  concluding a publish failed (20260729 — a correct 0.4.0 upload read as missing). Caught 20260729: `STATUS.md` still said "Published version: 0.2.2 **only**" after 0.3.0 had
  been on PyPI for three hours, and the roadmap still listed the paid-extraction release as unbuilt.
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
- **Audit the neighbourhood, not the diff.** Any docs change re-reads the claims around it for
  **consistency, logic, superseded decisions and outdated facts** — the cause of the line you came
  to fix rarely stopped there. Full rule and the 20260729 measurement:
  [`docs/README.md` § Conventions](docs/README.md#conventions).
- **Every date carries a time** — `YYYYMMDD HH:MM`, local 24h — in the CHANGELOG, `docs/STATUS.md`,
  `docs/RETROSPECTIVES.md`, and any "verified on" claim.
- **Read the clock; never compose a timestamp.** Run `date "+%Y%m%d %H:%M"` and paste the result —
  session context carries a date, never a time, and an invented `HH:MM` lands in the future about
  half the time (docs/RETROSPECTIVES.md, 20260727 17:00).
