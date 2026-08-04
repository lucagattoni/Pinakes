# Pinakes — project instructions

Architecture and rationale live in [`docs/DESIGN.md`](docs/DESIGN.md); [`docs/README.md`](docs/README.md)
indexes the rest (which file owns which fact). This file only carries rules that change how you work.

## 🛑 Land with `tools/land.py` — never `git merge` by hand

    python3 tools/land.py <branch>              # merge, verify, push
    python3 tools/land.py <branch> --cleanup    # also remove the worktree and both branch copies

**Running `git merge <branch>` from inside that branch's own worktree merges it into itself.** Git
reports *"Already up to date"*, the push reports *"Everything up-to-date"*, and a tag created there
points off-`main` — **three successful commands and nothing landed.** It has happened repeatedly
here, always the same way: one `&&` chain beginning `cd <worktree>` and later containing
`git merge`.

**Git cannot catch it.** A branch merged into itself creates no commit, so `pre-merge-commit` never
fires — the no-op is silent by design. So `tools/land.py` is the guard: it finds the primary
checkout itself whatever directory you ran it from, **refuses if `main`'s sha did not move**, and
re-reads `origin/main` after pushing, because a push reporting success is only a claim. `--cleanup`
removes the worktree *and* both copies of the branch, since deleting one leaves the other behind.

**This is the only rule here with an executable guard, because it is the only one that fails
silently.** Everything else fails loudly or is caught by `./check.sh`.

## This repository is PUBLIC

- **Never commit real knowledge-base content.** The repo is the engine. The only KBs here are the
  synthetic corpora under `tests/` (`demo-kb`, `partner-kb`) — written for the purpose, never
  harvested.
- **The paid extractor's key is `PINAKES_ANTHROPIC_API_KEY`, never `ANTHROPIC_API_KEY`** — and
  that is enforced in code (`extract/claude.py: resolve_api_key`), not by machine hygiene. The SDK
  reads its own variable out of whatever environment it is handed, so on a machine where some
  other tool exports one the paid path would find a live key nobody aimed at it — measured true
  here on 20260804. Supplying the key must be an act aimed at *this* tool. It lives in `.env`,
  gitignored by pattern (`.env`, `.env.*`), passed per command: `uv run --env-file .env pnk …`.
  **Never teach Pinakes to load `.env` itself**, and never add an `ANTHROPIC_API_KEY` fallback —
  both are the same defect, one layer apart. Note what actually bounds spend once a key is
  present: the §5 caps and the enumerated allowlist, not the invocation form
  ([docs/MEASUREMENT-RUN.md](docs/MEASUREMENT-RUN.md)).
- Vet every file for PII, credentials, private URLs, and anything copied from memory before staging.
- Never commit model weights or `.pinakes/` state (both are gitignored — keep it that way).

## Documentation has one owner

**The planner agent owns every document in this repo. No other agent edits one — it proposes.**
Decided by the user 20260801 01:24.

| | |
|---|---|
| **Planner-only** | `docs/**`, `plans/**`, `README.md`, `CLAUDE.md`, `CHANGELOG.md` |
| **Yours to write** | `changelog.d/` and `retro.d/` fragments; docstrings and comments in `src/`, `tests/`, `tools/`. Fragments exist so an implementer records what it changed *without* touching a shared document — that is the mechanism, not an exception to it |
| **One narrow exception** | `docs/VERIFICATION.md`: add **only** the row a test you wrote requires. `tests/test_verification.py` hard-fails on an unresolvable name, so a renamed or new test with no row makes *your own* branch red and you could not self-certify. Nothing else in that file |

**How to propose:** `git diff <sha> -- <file>` against a **named commit**, in your branch's commit
message or a note the planner reads. Never an edit, never "it is one line".

**What the planner does with it:** incorporates it — judging *when*, not whether. A correction to
what is true **today** lands on `main` at once, independently of your branch. A doc change that
describes **your unlanded work** lands with your merge, because main must not describe a command
that does not exist yet.

**Why:** documentation is the coordination surface, and a clean auto-merge is not a correct merge
(20260729). A document edited by whoever happened to be in the code drifts until no reader can tell
which sentence is current. The cost is real and accepted: a correction waits for the planner.

## 🚫 Unbuilt work is named, never numbered

**A version number belongs to a release when it is cut — never before.** Refer to unbuilt work by
name:

| Name | What it is |
|---|---|
| **the graph release** | Structural edges, the expansion channel — each eval-gated |
| **the deep release** | `pnk ask --deep` |
| **the template release** | Template ecosystem, `pnk upgrade`, the `sqlite-vec` tier |

**A release that cuts more than once keeps its name in this table until the *final* cut**, and its
roadmap row carries both tags. Dropping the name at an interim cut deletes one the later increments
still need — the churn the two-cut decision was taken to avoid.

**Never write `v0.4` for something unbuilt** — not in docs, not in `--help`, not in an error
message, not in a code comment. Increment IDs (`I7b`, `I8`) stay: they name work inside a plan, not
a release. Decided 20260729 00:09, after `v0.3` meant two releases at once and either reading would
have renumbered ~60 references ([docs/STATUS.md](docs/STATUS.md#release-roadmap)). **Historical
records keep the numbers they were written with** and carry a header note: `CHANGELOG.md`,
`docs/RETROSPECTIVES.md`, `plans/`, `docs/graph/`.

## Naming (fixed — changing any of these is a breaking change)

| Thing | Value |
|---|---|
| **Project name, in prose** | **`Pinakes`** — capital P. "Pinakes is a portable KB", "a newer Pinakes" |
| Package / command | `pinakes` / `pnk` |
| Repository / docs site | `github.com/lucagattoni/pinakes` · `lucagattoni.github.io/pinakes` |
| Manifest / sidecar | `pinakes.toml` / `<file>.pnk.yaml` |
| Generated state | `.pinakes/` |
| MCP tools | `pinakes_*` — never bare `kb_*`, which collides across servers |
| Cross-KB URI | `pnk://<kb-ulid>/<doc-ulid>` — ULIDs only, never aliases |

**Capital `P` names the project; lowercase `p` names something you can type.** `pinakes.toml`,
`.pinakes/`, `pinakes[st]`, `pinakes_search`, `import pinakes`, `requires_pinakes`, `src/pinakes/`
and every URL stay lowercase inside a sentence that otherwise says Pinakes. Runtime output names
the *command*, so it stays lowercase too — a git hook's `echo "pinakes: …"` is not prose. Applied
across the repo 20260804 11:55, history included.

## Invariants that must not be broken

- **Document and KB ULIDs are permanent.** Never renumber, never regenerate. Every inbound link
  depends on them, and there is no migration machinery by design.
- **An unknown key in a sidecar round-trips byte-identically.** Stronger and more testable than
  "untouched", which was true of the dict and false of the file: under YAML 1.1 `country: NO` was
  read as `False` and written back as `false`. Sidecars are read and written through
  **`ruamel.yaml` in round-trip mode at YAML 1.2** — never `pyyaml`, which is dev-only and gated by
  an AST scan over `src/` plus a runtime check on the free path. `write()` reconciles known keys
  *into* the loaded document; it never renders a fresh one. Values must be JSON-encodable and every
  key a string, because the index stores metadata as JSON. The invariant is **bounded** — by what
  Pinakes normalises, what ruamel normalises, and what YAML does not carry — and **each exclusion is
  pinned by a test**, which is the authoritative list because a bound stated only in prose cannot
  notice the library's behaviour moving under it: `docs/VERIFICATION.md` § *The sidecar round-trip*,
  and `docs/MANIFEST.md`'s bounds table.
- **`docs/` belongs to the user.** Never modify source documents; never delete a sidecar without an
  explicit `--prune`-style flag plus a printed list. Two exceptions, both narrow: a paid PDF
  extraction (or `--force` discarding one) additively rewrites that document's own sidecar with
  `provenance.extraction` (DESIGN §2.2) — no other key, never on a free extraction; and a
  user-invoked authoring command writes `links[]` to the source document's own sidecar.
- **`.pinakes/` is disposable except `ledger.jsonl` and any cache entry a paid backend wrote.** A
  rebuild must preserve spend history, and the ledger is **append-only** — correct a record by
  appending another (`pnk budget --resolve`), never by editing. A paid cache entry is derived state
  that cost real money to derive: the automatic sweep spares it, and destroying one takes an
  explicit `--clear-cache=paid`.
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
  float via `Decimal(str(value))`, never `Decimal(value)`, which reproduces float's binary
  imprecision instead of the decimal a human wrote: `Decimal(0.05) != Decimal("0.05")`.
- Index schema changes bump `schema_version` and require a rebuild. Never write a migration.

## Building a release — one increment at a time

The build order is [`plans/20260729_0256-links-and-graph.md`](plans/20260729_0256-links-and-graph.md) — **not** "the newest
file in `plans/`", which also holds shipped plans, an iteration log, standalone increments and
decision records ([`docs/README.md`](docs/README.md) tells them apart). **That plan is open at G3**
— the links release is complete, and the graph release restarted on 20260804 when the RFC corpus
cleared G2's precondition
([decision](plans/20260804_1442-decision-g3-go.md)). **G3 is the live increment**, then G5, then G6.
Beside it: whatever [`plans/20260731_1202-open-corrections.md`](plans/20260731_1202-open-corrections.md)
lists as live — its structural-chunking item is required by that decision, because it is what
contaminated three of the six edge kinds in the measurement. Never batch increments; each
is a separate, bisectable landing:

1. Own worktree, branch `YYYYMMDD_HHMM-i<N>-<slug>`.
2. Implement the increment **with its tests** — tests ship in the increment that introduces the
   behaviour, never deferred.
3. Green before review: run `./check.sh` (or `make check`) — every gate under `set -e`, so a
   failure is a non-zero exit rather than a line in a log that a pipe then swallows. It formats
   Python **inside Markdown fences** too: a docs-only commit can still fail the gate.
   **Then break the code on purpose.** For the 3–5 most safety-critical assertions, mutate the
   source (delete the guard, flip the comparison, neuter the conversion), confirm the *right* test
   fails, and restore. Green proves the tests ran, never that they can detect the defect, and
   **"mutation-verified" is a per-assertion claim, never a per-commit one** — a test that fails
   proves the mutant is caught, never that it is caught for the *stated* reason. Tests written by
   the reasoning that wrote the code inherit its assumptions; the worked cases are in
   `docs/RETROSPECTIVES.md` § *Start here* → "claim a test is mutation-verified".
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

**Nothing is done until it is on `origin/main` and, when it completes a unit of work, tagged.** Work
left local is invisible to every other agent, machine and scheduled run.
**The procedure is [`docs/RELEASING.md`](docs/RELEASING.md)** — these are the rules it assumes.

- **Push every landing** to `origin/main`. Never leave merged work sitting locally.
- **Before merging, run `python3 tools/shared_file_overlap.py --fetch --strict`** — then go and
  *read* the merged state of the files it names. A clean auto-merge is **not** a correct merge: git
  merges edits that do not overlap textually, never edits that *agree*, so two agents can leave one
  document contradicting itself with every command reporting success (20260729 — three branches, one
  hour; `CHANGELOG.md` conflicted loudly and two documents merged silently). For the two documents
  every change writes to, the cause is removed rather than reported:
  [`changelog.d/`](changelog.d/README.md), [`retro.d/`](retro.d/README.md).
- **Before assigning a release number, check what has already landed on `main`** — another agent may
  have cut one since this branch started (20260728).
- **Cut the release** as soon as the work passes the SemVer table in the global rules (feature =
  MINOR, fix/docs/deps = PATCH, breaking = MAJOR). Complete work never lingers in `[Unreleased]`.
- **Land with `python3 tools/land.py <branch>`, never `git merge` by hand** ([above](#-land-with-toolslandpy--never-git-merge-by-hand)).
- **A tag publishes to PyPI** (`PUBLISH_TO_PYPI` true since 20260728 17:15) and PyPI does not allow
  re-uploading a version. Run `make release-check` **before** pushing the tag, never after.
- **Verify, never assume, that a release happened**, and sweep the three documents it stales — both
  in [`docs/RELEASING.md`](docs/RELEASING.md). A CHANGELOG entry and a `__version__` are only claims.
- After anything lands on `main`, fast-forward the primary checkout (`git pull --ff-only`).

## Tooling

- **uv only** — `uv add`, `uv run`, `uv build`. Never pip, poetry, or a hand-managed venv.
- Python 3.13+. `ruff`, `pyright` (strict), `pytest` must pass before any commit.
- `uv run ty check` is a fast pre-check, **never** the gate — at 0.0.63 it caught a fraction of
  what `pyright` strict does (RETROSPECTIVES, I1). Re-measure when it leaves beta.
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

**`docs/` is published** to [lucagattoni.github.io/pinakes](https://lucagattoni.github.io/pinakes/)
on every push to `main`, so a docs edit now has a second renderer that a PR gates with
`mkdocs build --strict`. Two rules follow, both in `docs/README.md` § Conventions: a link *out* of
`docs/` is absolute (`plans/`, `CLAUDE.md`, `changelog.d/` have no page there), and a heading is
never renamed to fix a site anchor — `mkdocs_hooks.py` makes the site match GitHub, not the
reverse. Run `make docs` before landing a docs change.

- **README and DESIGN.md are deliberately version-free** — they describe what Pinakes *is*, never
  which release it's on. Never reintroduce a version number or "as of vX" claim into their prose
  (CHANGELOG.md `[0.2.1]` — a 20260728 restructure existed specifically to stop that drift).
- **Verify docs by running the commands they show**, install line included — prose drifts toward
  the design, because the design is what you are thinking about while writing it (20260727: four
  README claims contradicted the code while `cli.py` and the CHANGELOG were right).
- **Audit the neighbourhood, not the diff.** Any change *or decision* re-reads what depended on it
  for consistency, logic, superseded decisions and outdated facts — including every table,
  increment, release structure and invariant that assumed the decision it replaces, not only prose.
  Full rule and measurements: [`docs/README.md` § Conventions](docs/README.md#conventions).
- **Name the audience (human / agent / both) and the goal (reference / executor) before writing.**
  An executor doc — `CLAUDE.md`, a `plans/` increment — is imperative and self-sufficient, naming
  exact files, symbols and predicates. A reference doc argues and measures. Rationale in an executor
  doc is noise; an instruction in a reference doc is a defect.
- **Rewrite to the current state; never layer corrections**, and **compact monthly** — cut recaps,
  superseded reasoning, and anything re-arguing what another file owns; keep decisions, measured
  numbers and instructions. A section far larger than its siblings is the signal.
- **Every date carries a time, in UTC** — `YYYYMMDD HH:MM`, `date -u` — in the CHANGELOG, `docs/STATUS.md`,
  `docs/RETROSPECTIVES.md`, and any "verified on" claim.
- **Every new file in `plans/`, `changelog.d/` and `retro.d/` is named `YYYYMMDD_HHMM-<rest>.md`**
  (UTC, underscore not colon — the branch-name format). `ls` then reads chronologically and a
  file is dated without opening it. `tools/fragments.py` strips the prefix before reading a
  fragment's category, so it never becomes part of the slug; a file without one is accepted, since
  the convention began 20260804 07:00 and refusing older files buys nothing.
- **UTC everywhere, from 20260804 11:32.** `date -u`. **Timestamps written before that are local and
  stay local** — converting a recorded time invents precision nobody measured. Where the two could
  be confused, say which.
- **Read the clock; never compose a timestamp.** Run `date -u "+%Y%m%d %H:%M"` and paste it — session
  context carries a date, never a time, and an invented `HH:MM` lands in the future about half the
  time. Derive a past timestamp from `git log`, never from memory.
