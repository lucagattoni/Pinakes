# Pinakes — project instructions

Architecture and rationale live in [`docs/DESIGN.md`](docs/DESIGN.md); [`docs/README.md`](docs/README.md)
indexes the rest (which file owns which fact). This file only carries rules that change how you work.

## 🛑 Land with `tools/land.py` — never `git merge` by hand

    python3 tools/land.py <branch>                  # merge, verify, push
    python3 tools/land.py <branch> --cleanup        # ... and remove the worktree and both branch copies
    python3 tools/land.py <branch> --cleanup-only   # remove a branch that landed earlier

**Running `git merge <branch>` from inside that branch's own worktree merges it into itself.** Git
reports *"Already up to date"*, the push reports *"Everything up-to-date"*, and a tag created there
points off-`main` — **three successful commands and nothing landed.** It has happened repeatedly
here, always the same way: one `&&` chain beginning `cd <worktree>` and later containing
`git merge`.

**Git cannot catch it.** A branch merged into itself creates no commit, so `pre-merge-commit` never
fires — the no-op is silent by design. So `tools/land.py` is the guard: it finds the primary
checkout itself whatever directory you ran it from, **refuses if `main`'s sha did not move**, and
re-reads `origin/main` after pushing, because a push reporting success is only a claim. `--cleanup`
removes the worktree *and* both copies of the branch, since deleting one leaves the other behind;
`--cleanup-only` does that for a branch you landed earlier, after verifying it is an ancestor of
`origin/main` — because "looks merged" is not "landed".

**This is the only rule here with an executable guard, because it is the only one that fails
silently.** Everything else fails loudly or is caught by `./check.sh`.

## This repository is PUBLIC

- **Never commit real knowledge-base content.** The repo is the engine. The only KBs here are the
  synthetic corpora under `tests/` (`demo-kb`, `partner-kb`) — written for the purpose, never
  harvested.
- **The paid extractor's key is `PINAKES_ANTHROPIC_API_KEY`, never `ANTHROPIC_API_KEY`**, enforced
  in code (`extract/claude.py: resolve_api_key`), not by machine hygiene: the SDK reads its own
  variable out of whatever environment it is handed, so on a machine where another tool exports one
  the paid path would find a live key nobody aimed at it (measured 20260804). It lives in `.env`
  (gitignored by pattern), passed per command: `uv run --env-file .env pnk …`. **Never teach
  Pinakes to load `.env` itself**, and never add an `ANTHROPIC_API_KEY` fallback — the same defect,
  one layer apart. What bounds spend is the §5 caps and the allowlist, not the invocation form
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
what is true **today** lands on `main` at once. A doc change describing **your unlanded work** lands
with your merge: main must not document a command that does not exist yet.

**Why:** documentation is the coordination surface, and a clean auto-merge is not a correct merge
(20260729). The cost is accepted: a correction waits for the planner.

## 🚫 Unbuilt work is named, never numbered

**A version number belongs to a release when it is cut — never before.** Refer to unbuilt work by
name:

| Name | What it is |
|---|---|
| **the deep release** | `pnk ask --deep` |
| **the template release** | Template ecosystem, `pnk upgrade`, the `sqlite-vec` tier |

**A release that cuts more than once keeps its name here until the *final* cut.** Dropping it at an
interim cut deletes a name the later increments still need.

**Never write `v0.4` for something unbuilt** — not in docs, `--help`, an error message or a code
comment. Increment IDs (`I7b`, `I8`) stay: they name work inside a plan, not a release. Decided
20260729 00:09, after `v0.3` meant two releases at once
([docs/STATUS.md](docs/STATUS.md#release-roadmap)). **Historical records keep the numbers they were
written with**, with a header note: `CHANGELOG.md`, `docs/RETROSPECTIVES.md`, `plans/`,
`docs/graph/`.

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

**[`docs/INVARIANTS.md`](docs/INVARIANTS.md)** — ULID permanence, the sidecar byte-identity bound and
its `ruamel`-only rule, `docs/` belonging to the user, `.pinakes/` disposability, the append-only
ledger and what a `void` record needs, the paid-path allowlist, `Decimal` money, `schema_version`.
**Read it before touching a sidecar, the ledger, the index schema, or anything that could import a
paid client.** Each one fails *silently* when broken, which is why it is a list and not a convention.

## Building an increment

**The procedure is [`docs/BUILDING.md`](docs/BUILDING.md)** — own worktree, tests in the same
increment, `./check.sh` green, mutate the assertions, adversarial review, fragments, then
`tools/land.py`. Never batch increments. Read the build order out of `plans/` — **never** "the newest
file" there ([`docs/README.md`](docs/README.md) tells them apart).

**What is live right now:**

- **[`plans/20260805_1721-metadata-as-retrieval-context.md`](plans/20260805_1721-metadata-as-retrieval-context.md) — CLOSED 20260807, answered.** Read its **§0** before proposing anything about titles, `heading_path` or injecting either into retrieval; the rest of the file is the record of how. **The screen returned no-go — 6 improved, 6 regressed, 84 unchanged** — so `schema_version` 4 was not taken and **PDF layout heuristics and paid title inference stay unapproved**. What it measured is *vector-only* injection on *one* corpus; the both-channel form was never tested, so it does not say metadata is worthless. **What would re-open it is a corpus, not an idea about the prefix**: this one's `lexical` and `simple-lookup` classes are saturated at 1.00, so all its power sat in `paraphrase`. Still live from it: the frozen golden set (`tools/rfc_corpus/questions.yaml`, 110 questions — **never reword or renumber one**, `id` pairs a before row with an after row), and `[chunking] metadata`, shipped default `off`.
- **[`plans/20260804_1016-template-release.md`](plans/20260804_1016-template-release.md)** — reviewed, its four decisions taken, unstarted; re-run its Baseline block first.
- **[`plans/20260731_1202-open-corrections.md`](plans/20260731_1202-open-corrections.md) has two live items as of 20260807**, both from building 2d and neither visible by reading the code that holds them: `graph_gate.check_identity` is blind to `chunking`, and `--rebuild` never re-chunks a protected paid document. **The list refills from *use*** — add to it when something bites.

## Landing work: always push, always release

**Nothing is done until it is on `origin/main` and, when it completes a unit of work, tagged.** Work
left local is invisible to every other agent, machine and scheduled run. **The procedure — the
number, the tag, the verification and the documents a release stales — is
[`docs/RELEASING.md`](docs/RELEASING.md).** These are the rules it assumes:

- **Push every landing** to `origin/main`, and fast-forward the primary checkout afterwards
  (`git pull --ff-only`). Never leave merged work sitting locally.
- **Before merging, run `python3 tools/shared_file_overlap.py --fetch --strict`** — then go and
  *read* the merged state of the files it names. **A clean auto-merge is not a correct merge:** git
  merges edits that do not overlap textually, never edits that *agree*, so two agents can leave one
  document contradicting itself with every command reporting success (20260729). For the two
  documents every change writes to, the cause is removed rather than reported:
  [`changelog.d/`](changelog.d/README.md), [`retro.d/`](retro.d/README.md).
- **Cut the release** as soon as the work passes the SemVer table (feature = MINOR, fix/docs/deps =
  PATCH, breaking = MAJOR). Complete work never lingers in `[Unreleased]`.
- **A tag publishes to PyPI** and PyPI never accepts a version twice: `make release-check` runs
  **before** the tag, never after. **A CHANGELOG entry and a `__version__` are only claims** —
  verify the release happened, never assume it.

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

**One fact, one home** — [`docs/README.md`](docs/README.md) is the routing table and the
per-increment landing checklist. `docs/DESIGN.md` is rationale only; it changes when the *reasoning*
changes, never for a new flag or field alone.

**Seven rules live in [`docs/README.md` § Conventions](docs/README.md#conventions), each with its
measurement — read them before any docs change**: audit the neighbourhood not the diff; name the
audience and goal before writing; rewrite to the current state, never layer corrections; compact
monthly; verify a doc by running the commands it shows; a link *out* of `docs/` is absolute; never
rename a heading to fix a site anchor. `docs/` is **published** to
[lucagattoni.github.io/pinakes](https://lucagattoni.github.io/pinakes/) on every push to `main`, so
run `make docs` (`mkdocs build --strict`, which a PR also gates) before landing a docs change.

- **README and DESIGN.md are deliberately version-free** — they describe what Pinakes *is*, never
  which release it's on. Never reintroduce a version number or "as of vX" claim into their prose.
- **Every date carries a time, in UTC** — `YYYYMMDD HH:MM` — in the CHANGELOG, `docs/STATUS.md`,
  `docs/RETROSPECTIVES.md` and any "verified on" claim. **Read the clock, never compose it**: run
  `date -u "+%Y%m%d %H:%M"` and paste it, or derive a past stamp from `git log`. **Timestamps written
  before 20260804 11:32 are local and stay local** — converting a recorded time invents precision
  nobody measured. Where the two could be confused, say which.
- **Every new file in `plans/`, `changelog.d/` and `retro.d/` is named `YYYYMMDD_HHMM-<rest>.md`**
  (UTC, underscore not colon — the branch-name format), so `ls` reads chronologically.
  `tools/fragments.py` strips the prefix before reading a fragment's category; a file without one is
  accepted, since the convention began 20260804 07:00.
