# Changelog

All notable changes to this project are documented here.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project
adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- **I1 of the v0.2 build order: extras, the extractor seam, and an honest core-only failure.**
  `pyproject.toml` gains `[pdf]` (pypdfium2) and `[claude]` (the Anthropic SDK, requiring `[pdf]`)
  as opt-in extras — core stays torch-free and now extractor-free too. `src/pinakes/extract/`
  is a new package: an `Extractor` protocol, the `ExtractedText`/`ExtractionContext` types that
  will cross the seam for every backend to come, and an open, lazily-importing registry (mirroring
  `embed.py`'s) holding `pypdfium2` and `claude-vision` as honest stubs that name the increment
  that implements them (I3b, I7b) — plus a working `fake` backend for later increments to test
  against without either extra installed. `chunk.source_type` maps `.pdf` → `"pdf"`, and
  `pnk sync` routes a PDF through the registry instead of crashing on `read_text`: extraction
  failures record a `failures` row at stage `extract`, isolated from every other document, with
  the remedy printed once rather than once per file. The manifest gains `[extraction]`
  (`backend`, `model`), validated against the registry without importing anything, and
  `pnk sync --extract=BACKEND` overrides it for one run. `pnk doctor` gains a `pdf extractor`
  check. CI's `check` job is now a three-leg matrix (`[light]`, `[light,pdf]`,
  `[light,pdf,claude]`), and `check.sh` gains an `extras-not-core` gate.

## [0.1.4] — 20260727 21:19

### Added

- **`plans/v0.2.md`**, the reviewed build order for the PDF-extraction release (I1–I9): a free
  `pypdfium2` extractor, an opt-in paid Claude-vision extractor, and the budget machinery that
  ships with the first thing that can spend. Reviewed over four adversarial passes (7 HIGH/19
  MEDIUM/8 LOW, 5/18/8, 12/31/17, then three narrow methods — code-reality, arithmetic,
  promise-ledger — at 19/39/23) before implementation began.
- **A CLAUDE.md rule: read the clock, never compose a timestamp.** Run `date "+%Y%m%d %H:%M"` and
  paste the result — session context carries a date but never a time, so an invented `HH:MM` lands
  in the future about half the time, as four stamps in an early plan draft did.

## [0.1.3] — 20260727 15:40

### Added

- **A post-v0.1 housekeeping retrospective** in [`docs/RETROSPECTIVES.md`](docs/RETROSPECTIVES.md),
  covering the release-that-never-happened, the docs-only merge that turned `main` red, the merge
  run from inside a worktree that silently landed nothing while leaving a tag off-`main`, the four
  README claims that contradicted the code, and the promised CI gate that no increment owned.
- Three rules promoted into `CLAUDE.md` from those findings: verify a release the way a stranger
  would (`git tag -l`, `gh release list`, `merge-base --is-ancestor`) rather than believing the
  CHANGELOG; never `git merge` from inside the feature worktree, where three successive commands
  report success while nothing lands; and the README describes what ships, checked by running the
  commands it shows.

## [0.1.2] — 20260727 15:25

### Fixed

- **README accuracy.** An audit against the shipped CLI found the README to be the only surface
  overclaiming — `cli.py` and the CHANGELOG both say "planned for v0.4" where the README said
  "exists". Corrected: `pnk ask --deep` is now stated as planned rather than shipped; the budget
  ledger is future tense (`[budget]` is parsed and validated today, consumed by nothing); the
  install lines no longer point at a PyPI package that returns 404, and give a working
  install-from-source instead; the headline KB diagram no longer shows a `.pdf`, which is the one
  file type v0.1 cannot ingest (that lands in v0.2); and the design-review line now says four
  externally *verified* claims, two of which proved false, rather than "four factual errors".
- **A `[light]` install no longer walks into a wall.** `pnk init` always stamps the
  sentence-transformers backend, so the documented `[light]` path failed at the first `pnk sync`.
  The README now says to set `provider = "fastembed"` first. (The underlying asymmetry — `init`
  cannot see which extra is installed — is left for a `--backend` flag rather than papered over.)
- `docs/DESIGN.md`'s status line said "ready to implement" two releases after shipping, and §8
  listed the PyPI release as delivered when nothing has been published.
- The `[0.1.1]` CHANGELOG heading had no matching link definition, so it rendered as literal text,
  and `[Unreleased]` still compared against `v0.1.0`.

### Added

- README **Development** section (`make install` / `check` / `demo` / `eval`) — the Makefile shipped
  in 0.1.1 without its README counterpart, which the repo's own docs rule requires.
- README and `docs/DESIGN.md` §8 now point at [`docs/graph/`](docs/graph/); ~3,000 lines of research
  shaping v0.3 were reachable only from the CHANGELOG. §8 also gains the `v0.3.x` row for the
  eval-gated PPR channel and `[ner]` extra.

## [0.1.1] — 20260727 14:52

Documentation, tooling and release plumbing. No change to installed behaviour: the wheel's code is
identical to 0.1.0.

### Added

- **Graph-integration research** under [`docs/graph/`](docs/graph/) — fourteen investigation docs
  (LightRAG, microsoft/graphrag, Graphiti, HippoRAG 2, fast-graphrag, Graph-R1, LinearRAG,
  datastax/graph-rag, code-graph-rag, MiniRAG, Youtu-GraphRAG, LogicRAG, and ClaudeKB as the
  in-house precedent) plus `GRAPH_RAG.md`, the research record, and `PINAKES_APPROACH.md`, which
  turns them into a gated build order: free structural edges at sync, a staged expansion→PPR graph
  channel behind `graph_channel` (default off), a typed and capped `pinakes_links` returning score
  plus frontier, and a budgeted `--deep` loop whose discoveries are written back to sidecars. The
  synthesis passed six adversarial review passes (27→7→8→5→1→0 findings).
- **`Makefile`** — every target wraps the command CI actually runs, so a green `make check` locally
  means what it means on the runner. `make help` lists them.
- **A close-out on [`plans/v0.1.md`](plans/v0.1.md)** — "What the build taught", written against the
  15 shipped increments and the 52 retrospective findings: where the plan proved right, where it was
  wrong and whether planning could have caught it, what happened to each named risk, twelve rules
  for the next plan, and the list of what in it is now stale. The headline: no finding invalidated
  any plan-level decision, and every expensive miss was *machinery* — gate mechanism, test fidelity,
  warning policy, metric denominators, write durability — in a plan that specified algorithms
  closely and machinery barely at all.
- **CI gate: the free path stays free.** `plans/v0.1.md` promised a check that no paid-API client is
  imported in `src/` and it never shipped, because the item sat in a section with no increment
  number and so no increment owned it. Now enforced, and verified in both directions — it passes on
  the current source and catches a planted `import openai`.

### Changed

- The PyPI upload in the release workflow is **gated on the `PUBLISH_TO_PYPI` repository variable**
  and skipped rather than attempted while it is unset. Version/tag agreement, build and the
  isolated wheel smoke test still run on every tag, so tagging is always safe and never produces a
  red run for a reason the maintainer already knows about.
- `CLAUDE.md`: the increment workflow is no longer v0.1-specific, and a new *Landing work* section
  records the standing rule — always push to `origin/main`, always cut the release once the work
  passes the SemVer table, never let complete work sit in `[Unreleased]`.
- `test_version_is_set` asserts the version's *shape* (SemVer, never the `0.0.0` placeholder)
  instead of a hard-coded literal, which made every release edit a test for no functional reason.

### Fixed

- Red `main`: `ruff format --check` covers Python fenced blocks **inside Markdown**, so a docs-only
  merge failed the Format gate. The snippet is reformatted, and `CLAUDE.md` now says plainly that a
  docs-only commit is still subject to the full gate.

## [0.1.0] — 20260725 15:27

### Added

- **I1** — package skeleton: `errors.py` (`PinakesError` carries a message *and* a remedy, so no
  failure path strands the user), and `cli.py` rebuilt as argparse subparsers declaring the whole
  v0.1 command surface up front. Unimplemented commands name the increment that will land them.
  Exit codes are a contract: 0 success, 1 operational failure, 2 usage error.
- `ty` added as a dev dependency and fast type pre-check; `pyright` strict remains the gate
  (measured comparison in `docs/RETROSPECTIVES.md`).
- **I2** — identity: `ids.py` (ULID minting and strict parsing behind `KbId`/`DocId` NewTypes) and
  `uri.py` (`pnk://<kb-ulid>/<doc-ulid>`). Aliases are rejected inside a URI with an error naming
  where they do belong; `pnk://self/…` parses to an unresolved `ParsedUri` that *cannot* be
  formatted, so expanding it against the owning KB is enforced by the type system rather than by
  discipline. Lowercase IDs are rejected rather than normalised.
- ruff `BLE` ruleset enabled (blind `except Exception`), after I2's retrospective found two.
- **I3** — manifest: `manifest.py` parses and validates `pinakes.toml` (DESIGN §2.1) into frozen
  dataclasses, plus `find_kb_root` git-style walk-up. Unknown keys are a hard error, not a silent
  default — as is the retired `top_k`, which is rejected by name. Cross-key invariants are checked
  at read time: widths must narrow (`final_k <= fusion_top_k <= candidates_per_source`),
  `confirm_above_eur <= per_operation_eur` (or the confirmation prompt is unreachable),
  `overlap < max_tokens`, ordered confidence thresholds, and `fitted_for` required whenever
  thresholds are present. `[budget]` is validated from v0.1 though nothing consumes it until v0.4.
- **I4** — storage: `store.py` creates and opens `.pinakes/index.db` (DESIGN §3) — documents,
  chunks, FTS5 external-content index with its triggers, float32 vector BLOBs, links, kb_refs,
  failures and meta. `connect_rw` (WAL, foreign keys on) and `connect_ro` (`mode=ro`, so the MCP
  server cannot write even by mistake); a `schema_version` mismatch refuses to open and instructs a
  rebuild rather than migrating. `load_vectors` returns one contiguous float32 array with chunk ids
  in row order, and rejects any stored vector whose width disagrees with the manifest.
- Error pickling now preserves the exact subclass (I1 rebuilt through the base class, so an
  `except StoreError` across a process boundary would have missed it).
- **I5** — sidecars: `sidecar.py` reads, validates and writes `<file>.pnk.yaml` (DESIGN §2.2).
  Unknown keys round-trip untouched — the file belongs to the user, and normalising away their
  fields is data loss; `self` and alias links are resolved to ULIDs on read, so what reaches disk
  survives being shared; a hand-broken `id` errors with "restore the original", never a renumber.
  `find_duplicate_ids` reports every path claiming a shared id, for §6.4's hard error.
- Sidecar writes are atomic (write beside, then rename): a truncated sidecar would lose the
  document's permanent ULID and every inbound link with it.
- **I6** — chunking: `chunk.py` splits Markdown on headings and paragraphs (fenced code kept
  whole) and plain text on blank lines, counting tokens through a `TokenCounter` protocol so the
  logic is testable without model weights. Oversize text is split — sentences, then words, then
  characters for an unbroken run — **never trimmed**, and `assert_chunkable` refuses a `max_tokens`
  the model would have to truncate. Heading lines are included in their first chunk so heading-only
  words stay searchable, and every chunk satisfies `text == source[char_start:char_end]`.
- **I7** — backends: `embed.py` defines `EmbeddingBackend` and `Reranker` protocols behind open
  registries with lazy imports, so a core-only install never pulls torch and a missing backend fails
  naming the exact extra. sentence-transformers and fastembed implementations; fastembed is forced
  onto the shared `HF_HOME` cache rather than its `$TMPDIR` default, and `max_seq_length` is derived
  from the loaded tokenizer. `dim` disagreeing with the manifest is a hard error. Model-marked tests
  exercise real weights and skip when they are not cached.
- **I8a** — sync pairing: `pairing.py` implements DESIGN §6.4's two-phase algorithm as a pure
  function over two snapshots — no filesystem, no SQLite, no clock — returning actions for the sync
  driver to execute. Covers every row of the table plus the compound cases: adoption beats deletion
  so a rename+edit keeps its id and emits no delete; duplicate content is reported rather than
  guessed unless a sidecar breaks the tie; a sidecar disagreeing with the index wins, because
  `docs/` is the truth and the index is derived; one id in two sidecars raises rather than
  renumbering. Orphaned sidecars and moved-without-sidecar cases are reported, never acted on.
- **I8b** — `pnk sync` is real: walks the sources (never ingesting a sidecar as a document), runs
  §6.4 pairing, and applies each document in its own transaction so one unreadable file is recorded
  in `failures` and the run continues, exiting non-zero. `--rebuild` builds beside the index,
  checkpoints, closes, renames, and removes the old `-wal`/`-shm` — `ledger.jsonl` is never touched.
  `--sidecars-only [--stage]` is the pre-commit half (mints ids for staged files and `git add`s
  them); `--index-only` is the post-commit half and never writes into `docs/`. `sync.lock` records
  pid/host/start-time: a live holder means a quiet exit 0, a dead one is reclaimed with a warning,
  another host is refused with `--force-unlock`.
- **I9** — retrieval: `search.py` runs the §4.1 pipeline — metadata filters (tags from the sidecar
  metadata, path prefix, source type, mtime range), FTS5 BM25 with user text escaped so it can never
  be FTS syntax, NumPy cosine, RRF (k=60), optional local rerank, then the §4.2 confidence signal.
  Queries refuse to run against an index built by a different model. Confidence is `unknown` unless
  thresholds exist **and** `fitted_for` names the reranker actually in use; query-term coverage is a
  tiebreak, never a gate.
- **I10** — `pnk init` and `pnk search` are real. `init` stamps a KB from the packaged `notes`
  template (jinja2, `StrictUndefined`, so a template typo fails at render rather than becoming an
  empty manifest key), mints its permanent ULID, and writes the `.gitignore` that keeps the index
  and ledger off any remote. The template ships `[retrieval.confidence]` **commented out**:
  thresholds fitted on someone else's corpus are not a calibration. `search` runs the free pipeline
  with the full filter set, human or `--json` output, and an escalation note that names `pnk ask
  --deep` as *planned for v0.4* rather than implying it exists.
- pytest now treats warnings as errors, which immediately surfaced a deprecated
  `importlib.abc.Traversable` import and several leaked SQLite handles in the tests.
- **I11** — `pnk doctor`: environment (SQLite version, FTS5, loadable extensions), backend and
  weights, template drift, index coherence, calibration validity, orphaned sidecars, duplicate ids,
  dangling links and link coverage, recorded failures, the 50k-chunk NumPy-tier threshold, a held
  sync lock, and hook status. Every non-OK check carries a remedy. `--prune` is the only thing that
  changes anything, and it prints every path before removing it.
- **I12** — `pnk install-hooks` writes the §6.3 three-hook split: `pre-commit` mints ids for staged
  documents and stages the sidecars (so a document and its permanent id land in one commit),
  `post-commit`/`post-merge` update the index only and never dirty the tree. An existing hook that
  is not ours is left untouched and printed with the line to add; a hook that cannot find `pnk`
  warns and exits 0, because a hook that fails every commit only teaches `--no-verify`.
- **I13** — `pnk serve`: an MCP server exposing `pinakes_search`, `pinakes_get` and
  `pinakes_list_kbs`, namespaced so they cannot collide with another KB server an agent has loaded.
  It answers only about the KBs named on its command line; no tool argument accepts a filesystem
  path, and `pinakes_get` resolves a document ULID through the index. Passages come back inside a
  delimited evidence field stating they are text to reason about, never instructions to follow.
  Indexes are opened read-only and re-opened when a `stat()` shows the file was swapped.
- **I15** — CI (ruff, ty, pyright strict, pytest with warnings as errors, model-backed tests, a
  golden-set evaluation gated against the committed baseline, and a wheel smoke test that runs
  `pnk init` from the built artifact to prove templates are packaged), a release workflow that runs
  only on a `v*` tag and refuses one that disagrees with `__version__`, and the version moved to a
  single source of truth.
- **I14** — the scoreboard: a 30-document synthetic demo KB (invented institute, invented
  policies — nothing harvested), a 41-question golden set spanning lexical, paraphrase, filter,
  scripted multi-hop and no-answer cases, `pinakes.eval` (recall@k, MRR, rerank precision,
  false-abstain, false-confidence, confidence coverage, baseline comparison) and
  `pinakes.calibrate`, which prints a `[retrieval.confidence]` block and never writes one.
  Measured with the real `[light]` models: recall@5 0.879, MRR 0.774, rerank precision 0.727,
  **false-confidence 0.25** — the heuristic's real cost, now visible instead of assumed.
- Repository bootstrap: Apache-2.0 licence, `pyproject.toml` (uv, Python 3.13+, ruff, pyright
  strict, pytest), README, project conventions in `CLAUDE.md`, and a CLI stub that exits non-zero
  on every unimplemented command rather than implying it worked.
- `docs/DESIGN.md` — full architecture specification, reviewed across seven adversarial passes
  (58 findings resolved: 11 high, 32 medium, 15 low). Covers the KB directory format, SQLite schema,
  two-phase sync semantics, WAL concurrency policy, budget accounting by pre-call reservation,
  cross-KB linking via ULID-addressed sidecars, and the v0.1–v0.5 delivery plan.

- `plans/v0.1.md` (20260725 10:04) — implementation plan for the v0.1 vertical slice: 15 ordered
  increments (I1–I15) with per-increment tests and exit criteria, decisions table (argparse,
  jinja2-rendered manifests, `notes` template, open backend registry), and whole-slice acceptance
  checks. Adversarially reviewed across 5 passes, 28 findings resolved (3 high, 10 medium, 15 low).

### Changed

- Timestamp convention (20260725 13:49): every date in the CHANGELOG, design iteration log,
  retrospectives and "verified on" claims now carries `HH:MM` (local, 24h). Existing date-only
  stamps backfilled, and the four external claims in `docs/DESIGN.md` (sqlite-vec exhaustive KNN,
  fastembed's reranker registry, fastembed's `$TMPDIR` cache default, SQLite 3.53.1 + FTS5 +
  loadable extensions on uv-managed CPython 3.13) were **re-verified** at that time rather than
  having a time invented for them.

- Design pass 6 (implementation-readiness, 20260725 09:28): the local reranker moves from v0.5 into
  v0.1 with `BAAI/bge-reranker-base` as the default and a `[rerank]` manifest block; `pnk search`
  added explicitly to the v0.1 scope; git hooks split so `pre-commit` mints and stages sidecars
  while `post-commit`/`post-merge` touch only the index; `sync.lock` gains pid/host liveness with
  dead-lock reclaim and `--force-unlock`; the sidecar's redundant `content_hash` field is dropped.
- Design pass 7 (surfaced by the v0.1 plan review, 20260725 09:52): fastembed backend forced onto
  the shared `HF_HOME` cache (upstream defaults to `$TMPDIR`); `documents.sidecar_hash` added so
  sidecar-only edits re-index; soft delete now removes chunks/embeddings; rename+edit resolution
  stated (sidecar adoption wins over deletion).

**The v0.1 vertical slice is usable end to end**: `pnk init` → `pnk sync` → `pnk search`, plus
`pnk doctor`, `pnk install-hooks` and `pnk serve`, with a golden-set scoreboard and CI.

Measured on the demo KB with the `[light]` models: recall@5 0.879, MRR 0.774, rerank precision
0.727, false-abstain 0.03, **false-confidence 0.25**. That last number is the honest cost of the
confidence heuristic on a corpus of 30 documents and 8 no-answer questions — reported rather than
hidden, which is what §4.2 committed to.

Not in this release, by design: PDF ingest (v0.2), cross-KB links (v0.3), `pnk ask --deep` and the
budget ledger (v0.4), the `sqlite-vec` tier and template ecosystem (v0.5). Their schema ships now
where it could not be retrofitted — ULIDs, sidecars for every document, `[[links.kb]]`, `[budget]`.

[Unreleased]: https://github.com/lucagattoni/Pinakes/compare/v0.1.4...HEAD
[0.1.4]: https://github.com/lucagattoni/Pinakes/releases/tag/v0.1.4
[0.1.3]: https://github.com/lucagattoni/Pinakes/releases/tag/v0.1.3
[0.1.2]: https://github.com/lucagattoni/Pinakes/releases/tag/v0.1.2
[0.1.1]: https://github.com/lucagattoni/Pinakes/releases/tag/v0.1.1
[0.1.0]: https://github.com/lucagattoni/Pinakes/releases/tag/v0.1.0
