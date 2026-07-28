# Changelog

All notable changes to this project are documented here.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project
adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- **Budget I/O: the ledger, `pnk budget`, and hooks that cannot spend (I6b)** —
  `.pinakes/ledger.jsonl` is append-only, one atomic sub-4KB `O_APPEND` write per record, fsynced.
  Three record kinds keyed by `call_id`: a **reservation** written *before* the call, then exactly
  one **reconciliation** or **void**. A void closes a reservation at zero and is written **only
  when no response was received** — never from a bare `finally`, which cannot tell "the call never
  happened" from "the call returned and then something else raised", and in the second case would
  record €0 for money that left the account, permanently, in a file nothing can edit. A reservation
  with neither successor is reported as `unknown outcome`, never dropped and never counted as zero.

  Every line carries `cost_usd`, the `usd_per_eur` rate and the price table's `as_of`; EUR is
  computed at read time. Two identifiers, `operation_id` and `call_id`, because one word for both
  made `per_operation_eur` ambiguous by a factor of forty. **No query text and no document
  content** — asserted by running a sentinel through the call protocol and grepping the whole file.

  `pnk budget` shows day and month spend against their caps with the rate behind each total (and
  says so when a window spans two), the reconciled/voided/unknown counts, and the exact
  `pnk budget --resolve <call_id> --actual <eur>` line that closes a timeout — an **append**, never
  an edit. `pnk doctor` gains a price-table age check and an unknown-outcome check that warns past
  a quarter of a window. `make budget` wraps the command.

  I6a's pure arithmetic is now wired to a real ledger by `budget/accountant.py`, and the wiring is
  tested rather than assumed: a KB holding €4.99 of a €5.00 month refuses the next call with an
  untouched per-operation cap. **Nothing calls any of it yet** — the paid extractor is I7b.

- **`pnk init --ci`** — writes `.github/workflows/pinakes.yml`, designed in DESIGN §6.3 and never
  built in v0.1. It refuses to overwrite an existing workflow, the same trust rule `install-hooks`
  applies to a foreign git hook.

- **The paid-path allowlist gate (I7a)** — `.paid-path-allowlist` names every module under `src/`
  permitted to import a paid-API client, and `check.sh`, CI and `tests/test_paid_path.py` all read
  that one file, so three copies cannot drift. It ships **empty**: the gate lands before
  `src/pinakes/extract/claude.py` exists, because a gate arriving in the same increment as the thing
  it guards has never once refused that thing — v0.1 promised this check under a heading with no
  increment number, so nobody owned it and it never shipped.

  Four gates: every listed path exists and lives under `src/`; no paid-client import outside the
  list; `anthropic` never in `[project.dependencies]`; and the one that matters — a **full free-path
  run** (`init`, `sync`, `search`, `doctor`, an MCP handshake, over a free KB *and* a
  `claude-vision`-configured one) in a fresh subprocess, asserting no paid client reached
  `sys.modules`. Each gate has a test that makes it *fail*, including the path-exclusion trap an
  entry of `claude.py` implemented as a prefix match would open. The runtime gate skips with a
  printed reason where `pinakes[claude]` is absent — with the package missing, the assertion is true
  by construction and proves nothing — and runs for real on CI's `[light,pdf,claude]` leg.

  This replaces the unconditional `grep` that lived only in CI's `build` job. Unconditional admits
  no exceptions, so it would have turned `main` red on every commit from I7b onward.

### Changed

- **All four machine-driven callers force the free extractor.** The three git hooks and
  `pnk init --ci`'s workflow now write `pnk sync --extract=pypdfium2` explicitly, print one line
  saying so, and carry the same line as a comment in what they generate. All four are
  non-interactive: without the flag, a KB configured for a paid backend would abort on every commit
  for want of a terminal to confirm from; with a `--yes` in the hook it would spend afresh on every
  commit. The test **executes** each hook against a `claude-vision` KB and asserts the free backend
  extracted and no ledger was written, with a control that strips the flag and shows the same hook
  failing — asserting the string is *present* passes on a hook that never runs.

- **`--yes` no longer authorises destroying paid cache entries.** `pnk sync --yes --clear-cache` in
  a cron job could have thrown away paid extractions unattended, which is exactly what that
  guarantee claims to forbid. Clearing a cache holding paid entries non-interactively now requires
  `--clear-cache=paid` as well, which no hook and no generated workflow writes. `--yes`'s `--help`
  now states what it authorises: this run's prompts, no cap raised.

### Fixed

- **`pnk doctor` and `pnk sync` imported the paid API client on a KB configured for
  `claude-vision`.** Both reported a backend's availability by *loading* it —
  `doctor._extraction` on every run, and `sync._missing_pdf_extra` when building the "matched no
  `include` pattern" hint for a skipped `.pdf` — and the registry's factory imports the client. Two
  commands that cannot spend therefore pulled `anthropic` into a free-path process.

  Found by the new gate rather than by reading, and each confirmed by mutation: restoring either one
  alone puts `anthropic` back in `sys.modules`. Availability now resolves through
  `importlib.util.find_spec` against a `(module, extra)` pair declared on the registry entry, which
  for a top-level module adds nothing to `sys.modules`. No released version could spend from either
  path — `claude-vision` is a stub — so the effect was a needless import, never a charge.

### Changed

- **CLAUDE.md's paid-path invariant is now an enumerated allowlist**, rather than "no paid API call
  outside `pnk ask --deep`", matching DESIGN §1 and `.paid-path-allowlist`. DESIGN §1's prose covers
  paid LLM *work* (reasoning **and** PDF extraction), its decisions table no longer reads "Claude for
  reasoning only", §8's v0.2 row states both extraction paths, and §9 gains four risk rows:
  allowlist erosion, unbounded spend across invocations, price-table staleness, and the scanned-page
  audit blind spot.
- `pytest` runs with `-rs` in `check.sh` and CI, so a skipped gate prints its reason instead of
  reading as a pass.
- `pyright` now type-checks `tools/` alongside `src/` and `tests/`.
- Gate 4's runtime check matches paid modules on a dotted-prefix boundary against
  `google.generativeai` in full, not on the bare root `google` — which would have made
  `google.protobuf` (transitive via onnxruntime and grpc) a paid client and failed the flagship
  safety gate for an unrelated reason on some future CI leg.

## [0.2.2] — 20260728 18:49

### Fixed

- **A file that matched no `include` pattern was skipped in silence — including, in a KB made by
  `pnk init`, every PDF.** 0.2.0 shipped free PDF ingest as its headline feature while the `notes`
  template stamped `include = ["**/*.md", "**/*.txt"]`, so the actual first-run experience was:
  drop in a PDF, run `pnk sync`, read `0 indexed`, and get no hint that a missing glob was the
  reason. The mixed case was worse — Markdown indexed, PDFs dropped, the run reporting success —
  because nothing prompted anyone to look.

  `pnk sync` now names what it skipped, grouped by extension, with the exact glob that would pick
  the commonest up and a pointer to `exclude` for silencing it instead:

  ```text
  0 indexed, 0 renamed, 0 metadata-only, 0 unchanged, 0 removed
  1 file(s) matched no `include` pattern: .pdf (1) — add "**/*.pdf" to `[sources] include` to index them, or `exclude` them to silence this.
  ```

  **Only files pinakes could actually index are reported**, and the test is the one indexing itself
  applies: whether the first 8 KB decode as UTF-8 (`_index_document` reads every non-PDF source with
  `read_text(encoding="utf-8")`), plus `.pdf`, binary on purpose and indexable through
  `pinakes[pdf]`. An image or an archive beside your notes never appears — suggesting a glob for one
  would hand back a remedy that produces a `UnicodeDecodeError` failure row when followed, and a
  wrong hint is worse than none. Deciding by decodability rather than an extension allowlist also
  covers `.rst`, `.org`, `.tex` and every other text format without a list anyone has to maintain,
  since `chunk.source_type` already falls back to `"text"` for an unknown suffix. Silent too,
  deliberately: anything `exclude` already names, sidecars, and anything under a dotted path segment
  (`.git/`, `.DS_Store`).

- **The `notes` template now spells out the PDF glob and the extra it needs** (plan decision 6,
  pulled forward from I9 — the defect was live in a released version, and the plan had already
  reversed itself on the same reasoning for I7a's allowlist gate). PDFs stay **off** by default:
  `init` cannot see whether `pinakes[pdf]` is installed, and a glob stamped without it turns every
  PDF into a *failed* document rather than a skipped one. Off, but no longer undiscoverable.

  An independent adversarial review caught two defects that each handed the silence straight back,
  plus five smaller ones — all fixed here:

  - **The probe read a fixed 8 KB prefix and decoded it in one go**, so a multi-byte character
    straddling the boundary raised `UnicodeDecodeError` on a perfectly valid document — about two
    times in three for CJK, Cyrillic or Greek prose. A non-English corpus therefore got exactly the
    pre-fix behaviour: PDF beside the notes, `0 indexed`, no explanation. Now decoded incrementally,
    which holds a partial trailing character instead of failing on it.
  - **With more than one `[sources] root`, matched and unmatched were not disjoint.** The unmatched
    pass ran inside the per-root loop, testing each file against a matched-set the later roots had
    not contributed to yet — so a document indexed via root B was *also* reported as having no
    pattern, and swapping the two roots in the manifest made it disappear. Now a second pass, after
    every root's include walk.
  - `pnk sync --quiet` never printed the line, and the git hooks `docs/GUIDE.md` recommends run
    exactly that — leaving the project's own documented workflow as the one place the fix could not
    reach. `-q` prints only problems, and this is one; it now goes to stderr.
  - The suggested glob was lowercased, so `Report.PDF` was told to add `"**/*.pdf"` — which
    `pathlib` glob, case-sensitive on POSIX whatever the filesystem does, will not match. Suffixes
    are now grouped as they appear on disk.
  - An unmatched `.pdf` now names `pinakes[pdf]` when the extractor is genuinely not importable:
    adding the glob alone on a core-only install turns a skipped file into a *failed* one, the same
    trap the binary exclusion exists to avoid.
  - Probing is capped per root (`MAX_PROBED_PER_ROOT`), because a `node_modules/` under a root is
    thousands of `open()` calls per sync — a network round trip each on an SMB or NFS mount — to
    produce advice nobody wants. Truncation is stated (`500+ file(s)`), never silent.
  - A symlinked source root resolving outside the KB raised an uncaught `ValueError` out of the
    walk; ties in the extension ranking no longer let `(no extension)` take the hint slot from a
    real suffix; and "and N more" now says "extension(s)", since it counts extensions while the
    number beside it counts files.

  Tests: 22 cases across `tests/test_sync.py` and `tests/test_init.py`, each confirmed to fail
  against the code before its fix by mutating the source and watching the right one break. One of
  them — the PDF-extra hint — was first written as a self-consistency check that agreed with itself
  under every extras leg and survived deleting the feature; it now forces the extractor missing.

### Changed

- **The per-increment workflow now requires mutating the source to prove the tests can detect a
  defect**, not merely that they pass (`CLAUDE.md`). Two consecutive increments produced the same
  class of finding: I5 tested paid-extraction protection down one of the four code paths that reach
  the decision, and I6a's timezone conversion — the entire reason `window.py` exists — passed all 35
  tests with the conversion deleted, because every fixture was constructed in the zone being
  converted to. Tests written by the reasoning that wrote the code inherit its blind spots, so the
  cheap counter is to break the guard, watch the right test fail, and restore.

### Added

- **I6a of the v0.2 build order: budget core, pure (rule 11 — the pure half of the money
  machinery).** `src/pinakes/budget/` — no I/O, no `anthropic` import, asserted by an AST-based
  import-graph test over every file in the package. This is the accountant and the estimator;
  reading `ledger.jsonl`, `pnk budget`, and actually spending are I6b's job.

  **`prices.toml` ships as package data**, exactly like `extract/floors.toml` (verified: it is
  present inside a real built wheel, not only this source checkout). Every price is a TOML
  *string*, not a bare number — `prices.toml` is entirely project-controlled, never
  user-authored, so parsing via `Decimal(the_string)` directly removes the float intermediary
  altogether rather than reconstructing it from `str(float(...))` the way a user-authored manifest
  number has to. Seeded: `claude-opus-5` at $5.00 / $25.00 per MTok, `usd_per_eur = 1.08`, both
  carrying the same `as_of`. `prices.py` mirrors `floors.py`'s `load_floors()` shape precisely,
  including a new `PricesMissingError` for a missing/unreadable/malformed file and
  `UnknownModelPriceError` naming the models a document's own manifest could actually ask for.

  **`estimate.py` estimates over *requests*, never a whole document and never a single page**
  (decision 8): worst case per request = `(K * page_tokens + prompt_tokens) * input_price +
  max_tokens * output_price`, and a document is `ceil(pages / K)` requests. `K = 5` is a semantic
  constant (hashed into the paid extractor's own request-shape version in I7b, not a tuning knob).
  `page_tokens` is a conservative ceiling of 6,000 until I7b measures the real figure;
  `prompt_tokens = 300` and `max_tokens = 8,000` are measured module constants, not afterthoughts a
  real worst case could omit. No cache-write multiplier: the shared prefix is a few hundred tokens
  against the model's own cache minimum, so it very likely cannot be cached at all. A context-window
  precheck (1,000,000 tokens on `claude-opus-5`) runs before the estimate is even produced — cheap,
  and under the shipped constants (30,300 tokens per request) it never fires, but it names the exact
  limit rather than letting a real 400 response discover it. A stale `as_of` (older than
  `[budget] max_price_age_days`) refuses to estimate at all, naming the remedy. Verified directly
  against `plans/v0.2.md`'s own worked examples: 200 pages resolves to exactly 40 requests and
  $14.06 reserved; a single 5-page slice resolves to exactly $0.3515 — both to the last digit the
  plan states.

  **`reserve.py` is the pure accountant.** `reserve(reserved_eur, caps, spent) -> Decision` checks
  one call's cost against all three ceilings — `per_operation_eur`, the new `daily_eur`, and
  `monthly_eur` — in order, and refuses before any call is made if `spent.window + reserved` would
  exceed any of them; the refusal names which window and by how much. `reserve_document(estimate,
  caps, spent, confirm_above_eur=...) -> DocumentDecision` is the whole-document precheck run
  before the first call: unlike `reserve`, it names *every* blocked window at once, prints the
  computed estimate, the complete `[budget]` manifest edit that would admit this run (each blocked
  cap's minimum sufficient value, rounded up to the cent), and one line stating that raising a cap
  is a permanent, ongoing exposure — a one-run `--extract=<backend>` override is not.
  `confirm_above_eur` is evaluated once, against the whole-document estimate, never per slice: a
  20-page document whose *per-request* cost sits below the threshold but whose *document total*
  clears it is still flagged, exactly as the design says. All display amounts (never the internal
  comparisons, which stay full-precision `Decimal` throughout) are rounded to the cent for a human
  to actually read — an early version printed
  `€0.3254629629629629629629629630`, fixed before this was ever exercised by a test.

  **`window.py` aggregates ledger records into day/month totals**, in `[budget] timezone` — reading
  the ledger file itself is I6b's job, so this only ever takes an in-memory list. The
  reservation/reconciliation/void rule a draft of this design never stated, now pinned down and
  tested: a pair is one record, attributed to the *reservation's* own timestamp (never the
  outcome's); a reconciliation supersedes the reservation's amount in place, never adding to it; an
  unreconciled reservation counts at its reserved amount, so an in-flight or crashed call consumes
  headroom rather than vanishing; a void (I7b) closes a reservation at zero. Verified directly
  against a genuine midnight-straddling pair, a month-end-straddling pair, and a real DST
  spring-forward transition (`Europe/Berlin`, 2026-03-29) — all three attributed correctly. The
  `operation` window total is supplied by the caller (its own running tally for the current
  invocation), never aggregated from the historical ledger — a call from an *earlier* operation
  today must not bleed into a fresh one's own count.

  **`manifest.py`'s `[budget]` block moves from `float` to `Decimal` end to end** — a reservation
  compared against a float-derived cap is a representation error wearing a different hat, and the
  boundary tests this increment adds assert exact equality at the cent. `_toml.py` gains
  `Table.decimal()`, parsing a TOML number via `Decimal(str(the_parsed_float))`, never
  `Decimal(the_parsed_float)` directly — verified empirically that the latter reproduces the exact
  binary value a literal like `0.05` only approximates
  (`Decimal("0.05000000000000000277555756156289135105907917022705078125")`), not the clean decimal
  a human wrote. `[budget]` gains `daily_eur` (default 1.00 — a burst limiter between the
  per-operation and monthly caps) and `max_price_age_days` (default 30).

  **`check.sh` gains a `prices-toml-parses` gate**: `as_of` must exist and parse as
  `YYYYMMDD HH:MM`, failing the build if not. Deliberately *not* a staleness gate — a wall-clock
  check would fail a quiet weekend with no code change at all; staleness itself is a runtime
  refusal (`estimate_document`, above) and belongs to `pnk doctor` as a WARN, not to CI.

  **Tests, `tests/test_budget_core.py`** (35 cases): the exact boundary for each of the three
  windows (`spent + reserved == cap` proceeds, one cent more refuses, parametrised over all three);
  a case where the operation cap passes but the month's does not; `test_reservation_bounds_every_
  usage_table` (hand-written hypothetical usages, the worst-case reservation never below any of
  them); the midnight/month-end/DST attribution trio; reservation/reconciliation/void semantics;
  `test_the_refusal_names_all_three_windows`; `test_an_unaffordable_document_is_refused_before_
  the_first_call` (a spy asserting zero calls made); `test_confirmation_is_once_per_document_not_
  per_slice`; `test_confirm_threshold_and_hard_cap_are_independent_boundaries` (a request landing
  exactly at the hard cap is still allowed *and* still confirmable — design pass 3's finding);
  a stale `as_of`, a missing `prices.toml`, a malformed one, and one missing a required field, each
  a named startup error rather than a silent zero; `test_the_context_window_precheck_names_its_
  limit`; `test_prices_are_installed_package_data`; the import-graph test. `tests/test_manifest.py`
  gains exact-`Decimal` parsing coverage for `[budget]` (rejecting the float-comparison trap
  directly: `Decimal("0.05") == 0.05` is `False` in Python, so an existing test written the wrong
  way would have silently stopped proving anything). `tests/test_check_script.py` gains a check
  that the new gate's own snippet is genuinely present in `check.sh` — nothing else would notice if
  it were quietly deleted, since neither `ruff` nor `pyright` parse shell.

  **An independent adversarial review before this reached a commit found two real defects and
  three test-coverage gaps, all fixed here** (a `docs/RETROSPECTIVES.md` entry is owed once the
  parallel documentation pass reaches it — recorded here in full for now, per this round's scope):

  - `prices.py`'s malformed-file handling caught TOML *syntax* errors but not value-level ones:
    `Decimal(str(x))` raises `decimal.InvalidOperation`, not the `ValueError` `floors.py`'s
    `float(x)` raises for the same mistake, so a one-typo price (a European "5,00", an unfilled
    "TBD") or a wrong-shaped `models` table crashed uncaught instead of raising the documented
    `PricesMissingError`. Both exceptions are now caught.
  - `window.py`'s entire reason to exist — converting a differently-zoned input into `[budget]
    timezone` before comparing — was completely unexercised: every test constructed
    `reserved_at`/`now` already in the target zone, where `.astimezone()` is a no-op, so mutating
    the conversion away entirely still passed every test. A new test aggregates a UTC-stamped
    record against a Berlin-configured window (2026-03-15 23:30 UTC is the *next* calendar day,
    00:30, in Berlin) and catches exactly that regression.
  - `estimate_document` had no validation on `pages`/`pages_estimated`: `pages=0` divides by zero
    computing `per_request_eur`, and a negative `pages_estimated` produced a *negative*
    `total_eur` — the one direction a budget guard must never move, since it understates real
    spend rather than overstating it. Both now raise `ValueError` before any arithmetic runs.
  - `Table.decimal()`'s default path returned early, skipping its own `minimum` check — unlike
    `integer()`/`number()`, which validate their defaults for free by sharing one code path with
    the parsed value — so a below-`minimum` default would have silently passed. Restructured to
    check `minimum` on both paths.
  - `reserve_document`'s "every blocked window is named" claim and `reserve()`'s "first breach
    wins, in order" claim were each tested only where every window breached at once (or where
    only one *could*), so neither a partial breach nor a genuine two-window tie was ever
    exercised. `confirm_above_eur`'s exact boundary (`>`, not `>=`) had only an incidental test,
    never a dedicated one. Three new tests pin all of this down.
  - Two low-severity fixes: `ContextWindowExceededError`'s remedy suggested lowering a
    "`[chunking]`-equivalent slice size K" that does not exist as a configurable knob (`K` is a
    fixed constant); and a cap lowered mid-window below already-recorded spend printed a negative
    "headroom €-X.XX" in a refusal message, now rendered as "already €X.XX over cap" instead.

  Documentation for this increment landed separately, immediately after — see *Documentation* below.

### Documentation

- **[`docs/KB-UPDATES.md`](docs/KB-UPDATES.md) — what happens to a KB somebody already has when
  pinakes changes.** A design note, decided but **not built and not assigned to an increment**. The
  build plans had specified three drift axes and never asked about the fourth: an index schema, an
  embedding model and a PDF extractor each drift *detectably* and are remedied by rebuilding derived
  state, which is free — while a manifest and a template drift **silently**, and the remedy touches
  a file the user owns, so it cannot borrow the same shape.

  The gap is live rather than theoretical: I9's `**/*.pdf` template line will reach new KBs only, so
  every KB created before it stays PDF-blind permanently; and `doctor`'s sole drift signal compares
  declared version strings (`doctor.py:135`) while I9 as drafted changes template content without
  bumping `1.0` — a rule with no gate, lapsed before shipping.

  A compatibility asymmetry nobody designed on purpose is recorded with its evidence: **sidecars are
  forward-compatible** (unknown keys preserved under `extra`, `sidecar.py:35`) while **the manifest
  is not** (unknown keys are a hard error, `_toml.py:184`) — demonstrated against `main`, where a
  future `[budget]` key is refused with a remedy blaming a *typo* for what is version skew.

  Decisions recorded: downgrade is unsupported and refuses loudly; strictness is unchanged;
  `[kb]` gains `requires_pinakes` so the refusal can name the version, read in a **pre-pass** before
  validation or it is unreachable in the one case it exists for; `pnk upgrade --apply` may write to
  `pinakes.toml` via `tomlkit` (MIT, zero dependencies, 197 KB) with comments preserved, but never
  touches `docs/`, never renumbers a ULID and never re-chunks as a side effect; and a CI gate hashes
  the template directory minus an ignore-list, so a content change without a version bump fails at
  commit time rather than in a user's KB.
- **The docs now describe I6a, and the shipped-vs-merged distinction they lacked.** I6a's own
  implementation deliberately left `docs/` untouched while a parallel restructuring pass was in
  flight (that pass became `0.2.1`); this reconciles the two.

  `docs/DESIGN.md` §5 replaces its "⏳ pending amendment" placeholder with the real rationale: the
  first spender is the paid PDF extractor rather than `pnk ask --deep`, three independent windows
  instead of one cap, why a *request* (a fixed page slice) is the estimation unit rather than a
  document or a page, the reservation/reconciliation/void aggregation rule, why money is `Decimal`
  end to end, and why price staleness is a runtime refusal rather than a CI gate.
  `docs/MANIFEST.md` documents `daily_eur` and `max_price_age_days` with their real defaults (read
  from `manifest.py`, then verified against it), states that all three caps are checked and that a
  refusal names every blocked one at once, and notes the exact-`Decimal` parsing.

- **`docs/STATUS.md` said "Installed version: 0.2.0" while the package was already `0.2.1`** — the
  one file whose entire job is being right about what ships. Now `0.2.1`, and it gained the
  distinction it was missing: an increment merged to `main` but not released reads **"on `main`,
  unreleased"**, never "shipped", because installing from a tag and installing from `main` are
  different answers to "can I use this yet". `docs/README.md`'s landing checklist says so too.

- **The I6–I9 version target is decided** (`docs/STATUS.md`): they accumulate in `[Unreleased]` and
  cut as one MINOR release once paid extraction is usable (I7b) and safe (I7c) — never a `0.2.x`
  patch, since a KB that can spend money is new capability. I6a, I6b and I7a are each explicitly
  partial and none passes the SemVer table alone. **The number itself is left unassigned and the
  reason is recorded**: `v0.3` is already committed across the docs, `docs/graph/` included, as the
  cross-KB links release, so taking `0.3.0` for paid extraction cascades through the whole roadmap.
  That is a roadmap decision rather than a documentation one. Forward roadmap rows are relabelled as
  ordered scope rather than assigned numbers, since pre-assigning a version years ahead is what
  created the collision.

- `docs/README.md` gains the rule this round produced the hard way: **check what has landed on
  `main` before assigning a release number** — an I6a worktree nearly reasoned about "0.2.1 vs
  0.3.0" from a stale base while a parallel pass had already shipped `0.2.1`.

- `docs/RETROSPECTIVES.md` gains I6a's entry: the timezone conversion whose every test passed with
  the conversion deleted, an except-tuple inherited from a sibling module that parsed with `float`
  where this one parses with `Decimal`, missing validation at the one boundary where a wrong sign
  understates spend, and three true-but-untested assertions.

## [0.2.1] — 20260728 16:54

### Added

- **A documentation structure built for continuous development.** Each fact now has exactly one
  home, so landing an increment edits one file instead of four. New:
  [`docs/GUIDE.md`](docs/GUIDE.md) (how to use it, task by task — install, first KB, PDFs, search,
  calibration, git hooks, MCP setup, troubleshooting), [`docs/CLI.md`](docs/CLI.md) (every command,
  flag and exit code, plus a *Planned* table naming the increment behind each unbuilt surface),
  [`docs/MANIFEST.md`](docs/MANIFEST.md) (every manifest and sidecar field with its default, read
  from `manifest.py` rather than restated), [`docs/STATUS.md`](docs/STATUS.md) (**the only place in
  the repo that says what is built**, carrying the v0.2 increment ledger and the measured numbers),
  [`docs/README.md`](docs/README.md) (the index, a *where does a fact live* routing table, and a
  *landing a new increment* checklist) and [`docs/graph/README.md`](docs/graph/README.md) (an index
  for the fifteen research documents, with each project's licence and the three that may never be
  copied from).
- Every command in `docs/GUIDE.md` was **run against 0.2.0 before it was written up**, per the
  repo's own rule that docs are checked by running what they show. That is how the two caveats below
  were found.

### Fixed

- **`docs/DESIGN.md` §4.6 stated a span invariant that is false for PDFs.** `plans/v0.2.md`
  assigned the correction to I5, which shipped in 0.2.0 without it, so the released design claimed
  every citation "can be located exactly in the original file". It cannot for a PDF: the offsets
  address the *pinned extraction*, not the file, and what a PDF citation locates is a page. The
  invariant is now stated as `chunk.text == indexed_text[char_start:char_end]` with the two source
  types' consequences distinguished.
- **`pnk search --source-type` help hid a working filter.** It read "markdown, text or code" while
  `chunk.source_type` has returned `"pdf"` since I5 — the filter worked and was undiscoverable.
- The `notes` template's `[budget]` comment promised "nothing spends money before v0.4", which
  `plans/v0.2.md` decision 2 falsified by moving the first paid path into v0.2. It is now
  version-free and points at `docs/STATUS.md`.
- `docs/DESIGN.md`'s status line still read "v0.1.1 shipped", two releases stale. The document no
  longer carries a version at all — it is rationale, and `docs/STATUS.md` owns release state.
- The README described v0.1: no mention of PDF ingest, no `[pdf]`/`[claude]` install lines, a KB
  diagram with the one file type v0.1 could not read removed from it, and `make corpus` /
  `make pdf-eval` undocumented. It is now **deliberately version-free**, so it cannot drift again.

### Changed

- `docs/DESIGN.md` is specification and rationale only. Its manifest and sidecar field tables moved
  to `docs/MANIFEST.md`, its release table to `docs/STATUS.md` (the *why this order* reasoning
  stays), and its §10 iteration log to `docs/RETROSPECTIVES.md`, where all project history now
  lives. 879 → 783 lines with nothing lost.
- Three DESIGN sections whose amendments belong to unshipped increments (§5 budget, §4.7 agent
  surface, §9 scanned OCR) now carry dated **⏳ pending** notes naming the increment, rather than
  either describing unbuilt behaviour or silently contradicting the plan.

### Known issues surfaced (not fixed here)

- **A PDF dropped into a fresh KB is silently skipped.** `pnk init` stamps
  `include = ["**/*.md", "**/*.txt"]`, so v0.2's headline feature is off by default and sync reports
  `0 indexed` explaining nothing. Adding the commented-out `**/*.pdf` line is `plans/v0.2.md`
  decision 6, owned by I9; documented as a caveat in `docs/STATUS.md` and `docs/GUIDE.md` meanwhile.
- **I6–I9 have no version target.** The plan cuts 0.2.0 at the end of I9; it was released after I5.
  Recorded as an open question in `docs/STATUS.md`.

## [0.2.0] — 20260728 14:05

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
- **I2: the synthetic hard-case PDF corpus and its generator.** `tests/pdf-corpus/` holds 19
  committed fixtures across seven strata (two-column, tables, headers/footers, ligatures &
  hyphenation, scanned, pathological, baseline) totalling 59 pages and 266 KiB of PDF against a
  2 MiB budget (216 KiB of it the scanned stratum, against 1.5 MiB), each paired with a
  hand-authored `.expected.txt` written from the fixture's *spec* — never from an extractor's
  output, which would only prove an extractor agrees with itself. No real-world PDF is committed:
  a dependency-free PDF writer (`pdfwriter.py`) emits raw content streams using the base-14 fonts,
  so no layout engine hides the coordinates under its own decisions. The three scanned fixtures
  raster `baseline-12p`'s own pages via pypdfium2 + Pillow and reuse its ground truth verbatim,
  making free-vs-paid extraction directly comparable on identical content. `make corpus`
  regenerates in place; `check.sh` gains a `corpus-regenerates` gate where the sixteen text-layer
  fixtures must reproduce **byte-identically** and the three scanned ones within a stated pixel
  tolerance (>300 pixels differing by >32 levels is a failure — an absolute count, derived in the
  test's own docstring, because a whole-page mean would accept arbitrary reflow). Pillow joins the
  dev dependency group only, never core and never an extra, and `pdf_runnable()` grows the third
  half of its environment check to match.
- **I3a: the free extraction pipeline's pure, structural half.** `src/pinakes/extract/layout.py`
  turns pdfium's character-level text into ordered, de-furnished text with no PDF library and no
  filesystem access (asserted by an import-graph test): `blocks_from_chars` groups characters into
  line-level blocks from geometry alone — including splitting same-height text into separate
  blocks at a column-sized gap, not a single line spanning the page; `reading_order` clusters
  blocks into columns by `x0` gap and orders top-to-bottom within each; `strip_running_heads`
  suppresses a line recurring, digits normalised, on `>= T` of pages (never fewer than two, or a
  one-page document would see every line as "100% recurring" and suppress itself whole);
  `join_hyphenation` joins a trailing hyphen or U+00AD into a lowercase continuation, skipping
  transparently over suppressed running heads but never joining into a heading, and can join
  across a page boundary. `extract/textpolicy.py` carries the one string policy both extraction
  backends will run — ligature expansion, NFC, whitespace collapse — versioned separately
  (`TEXT_POLICY_VERSION`) from `LAYOUT_VERSION` so a change to either is never invisible to the
  other's fingerprint. `assemble()` runs the whole pipeline and emits the seam's `ExtractedText`,
  normalising each block *before* computing its offset — never after, since normalisation changes
  length. Forty-two table-driven tests check three properties per `assemble()` case, not two:
  join-identity and contiguous coverage are one property and its corollary, so a third,
  content-anchored assertion (a sentinel placed on one page, and no other, must fall inside that
  page's span, and every non-empty page must carry one) is what actually catches a wrong page
  number.
- **I3b: the pypdfium2 adapter, the extraction-quality metrics, and the two fitted floors.**
  `extract/pdfium.py` is a thin I/O reader: guards a file's size at 256 MB before ever opening it,
  translates pdfium's own refusals into a named `ExtractionError` (corrupt/malformed header,
  password-protected, no pages at all), turns pdfium's character-level text API into I3a's
  `CharSpan`s, and hands the whole document to `layout.assemble()`. `slice_pages(path, first,
  last)` is I7b's future request unit, clamping its own range since `import_pages` raises outright
  on an out-of-range index rather than tolerating one. `extract/quality.py` scores a free-path
  extraction against `tests/pdf-corpus/`'s ground truth on five metrics — `char_recall`,
  `order_fidelity`, `junk_rate`, `pair_adjacency`, `word_coverage` — each carrying its own
  numerator and denominator rather than a bare float, so a stratum with nothing to measure reports
  `null`, never an indistinguishable `0.0`. `make pdf-eval` (`check.sh`, and CI as its own job in
  this commit, not deferred to I9) extracts and scores every fixture, compares each stratum
  against a committed `tests/pdf-corpus/baseline.json` with a tolerance, and re-fits both floors to
  check neither has drifted. Two floors are fitted from the corpus, not guessed, and ship as
  package data (`extract/floors.toml`, beside I6a's future `prices.toml`) with `fitted_on`: the
  running-head threshold *T* (0.666667 — the midpoint of the lowest recurrence any genuine running
  head reaches across the headers-footers stratum and the highest recurrence anything else
  reaches, `tests/pdf-corpus/spec.py::KNOWN_RUNNING_HEAD_SIGNATURES` stating which is genuine per
  fixture) and the text-yield floor (65.75 non-whitespace characters per page — the midpoint of
  the scanned stratum's yield, 0, and the lowest real document's).

  Verifying the adapter against real PDFs — the first time in this project real pdfium output ever
  reached I3a's pure pipeline — surfaced six defects the hand-built fixtures in `test_extract_layout.py`
  never could: `_LINE_TOLERANCE` (2.0) was too tight for real descender depth, silently splitting
  g/y/q/j onto phantom one-character lines; the geometric word-gap heuristic inserted a space
  between nearly every letter pair, since real intra-word kerning gaps and inter-word gaps overlap
  (now removed — word breaks come from the source stream's own space characters); `reading_order`'s
  column clustering read a caption spanning two columns as that column's own last line rather than
  after both (fixed with a width-based spanning-block detection, `_SPANNING_WIDTH_FRACTION`); a
  `Tj` string authored with an embedded line break duplicated the newline `assemble()` already
  inserts between blocks; a soft hyphen sitting mid-block (not at a block boundary) was never
  removed by any existing code path (`textpolicy.normalise` now drops U+00AD unconditionally,
  wherever it falls); and I2's `pdfwriter.py` wrote a *partial* ToUnicode CMap that made pdfium
  misreport an unrelated, unmapped character as U+FFFE — fixed by filling in an identity mapping
  for every printable ASCII byte, not only the one needing an override. The `hyphenation-soft`
  fixture is restructured to a two-page layout (the same shape `hyphenation-page-break` already
  used safely) after finding that pdfium's own text-extraction reconstruction misreads an ordinary
  hyphen as U+FFFE whenever the text-showing operation ending in it is immediately followed by
  another one starting lowercase *on the same page* — and its own ground truth had a typo
  ("archive" + U+00AD + "al" spells "archiveal", not "archival"). All six are recorded in
  `docs/RETROSPECTIVES.md`.

  **A known, accepted limitation:** `reading_order`'s column detection is geometric, not
  structural, so the free path reads a table column by column, not row by row.
  `pair_adjacency` measures this directly for the tables stratum, though this corpus's own tables
  are small enough that even the wrong reading order keeps a label and its value within the
  metric's 80-character window — a disclosed limitation of this corpus's diagnostic power, not of
  the metric's design. There is no `word_coverage` floor yet (decision 12, `plans/v0.2.md`): the
  correct pair to fit it against is (native layer → Claude's output), and no Claude output exists
  before I7b.
- **I4: the extraction cache.** `extract/cache.py` — one JSON file per
  `.pinakes/cache/extract/<content_hash>-<fingerprint>.json`, storing the whole `ExtractedText`
  (text, page spans, per-page provenance) a call returns, so a cache hit and a cache miss are the
  same shape to every caller. `_index_document`'s PDF branch now calls the cache instead of the
  extractor directly; the extractor is only ever loaded — importing pypdfium2, say — on an actual
  miss, never on a hit. Invalidation is by key alone (a changed `content_hash` or a changed
  `fingerprint`, e.g. a fitted-threshold update); any entry that fails to parse — missing,
  truncated, an unrecognised schema — is a miss, never a crash. `operation_id`/`call_ids` are
  already part of the schema, always `null` today, as the future join key to `ledger.jsonl`
  (I6b/I7c) — so no cache migration is needed once a paid backend exists to populate them.

  After a fully successful sync (never after one with failures; for `--rebuild`, only once its
  atomic swap has landed), entries whose `content_hash` matches no active document are swept —
  except entries a paid backend wrote (`operation_id` is not `None`), which are only ever
  reported, never deleted automatically: a soft-deleted or un-sidecarred document is not an
  "active document," and sweeping away a paid extraction with no prompt and no printed cost is
  the one mistake this cache must not make. `pnk sync --clear-cache` empties `cache/extract/`
  entirely (paid or free, active or orphaned) after confirming — it prints the entry count and
  bytes and requires a `y`; `--yes` skips the prompt for cron use — and never touches
  `ledger.jsonl`, the same guarantee `--rebuild` already gives. `pnk doctor` gains an "extraction
  cache" check: entry count, bytes, `orphans/entries`, and paid orphans (`Status.WARN` when any
  paid orphan or unreadable entry exists) reported separately.

  **Tests, `tests/test_extract_cache.py` (no `pypdfium2` needed — a plain callable stands in for
  the extractor):** a hit never calls `extract` at all, not even lazily; a changed content hash, a
  changed fingerprint, a truncated file, a wrong schema version, and a missing required field each
  miss rather than crash; two KBs holding the same PDF get two cache files; a paid orphan survives
  the sweep and is reported while its free twin is removed; a corrupt entry is left alone, not
  swept, since a paid entry can't be ruled out for a file that can't be read. `tests/test_sync.py`
  adds the integration wiring: a plain second sync of an unchanged PDF never reaches the cache at
  all (pairing's own `Skip` returns first), so the reuse test uses `--rebuild`, which forces every
  document back through `_index_document` — proving a real cache hit (the entry's mtime is
  unchanged) rather than merely proving pairing's pre-existing skip; a fully successful sync
  evicts a deleted document's entry; `--clear-cache` preserves the ledger, aborts without `--yes`,
  and is a no-op (not a prompt) on an empty cache.
- **I5: PDF chunking, page provenance, and a backend-aware sync (`schema_version` 2 — a v0.1 or
  pre-I5 index refuses to open, naming `pnk sync --rebuild`).** `chunk_document(kind="pdf")` looks
  up each chunk's page span against the extractor's own per-page character spans and stores it as
  1-indexed `page_start`/`page_end` — no new block-splitting algorithm, since the existing
  blank-line block detection already produces a block spanning two pages whenever
  `join_hyphenation` (I3a) joined a word across one; `heading_path` stays `None` for every PDF
  chunk, since a PDF has pages, not headings. `documents` gains `extraction_backend` /
  `extraction_fingerprint`, populated only for PDFs; `ExtractorEntry` gains a `paid: bool` field
  (`claude-vision` alone is `True`) so a coherence or pairing decision can ask "is this backend
  paid" from the registry alone, never by importing the client.

  **Decision 9 — a paid extraction is never silently downgraded.** `pairing.py`'s decision table
  grows three backend-aware rows: a free-recorded, paid-effective document is always stale,
  regardless of hash; a paid-recorded, free-effective, **unchanged**-hash document is skipped —
  not by a hook, not by `--rebuild`, not by an explicit free `--extract` — and the run says once
  which paths were protected; the same document with a **changed** hash is neither a silent Skip
  nor a silent overwrite but a `failures` row naming the paid remedy (decision 14), since letting
  the hash win would overwrite paid text with a free extractor's empty output on an image-only PDF,
  and letting the backend win would describe a file that no longer exists, forever. `pnk sync`
  gains `--force`, meaningful only together with an explicit free `--extract`: the one combination
  that overwrites a paid extraction, printing what it discarded first (`--force` alone changes
  nothing). A paid extraction under `--index-only` is refused with a remedy naming a normal sync,
  since recording it requires writing into `docs/`, which `--index-only` must never do.

  **Provenance lives in the sidecar, because `--rebuild` reads its `before` from a brand-new,
  empty database** (`docs/DESIGN.md` §6.4) — a backend recorded only in `index.db` is invisible at
  exactly the moment a rebuild needs it. The sidecar's existing `provenance` block gains an
  additive `extraction: {backend, fingerprint, extracted, content_hash}`, written only when a
  genuinely fresh paid extraction happens (or `--force` clears a stale one), never for the routine
  free case. `index.db`'s two extraction columns are the sidecar's cache, reseeded from it.
  `content_hash` here is the file's own hash *at the time of that paid extraction* — narrower than
  the general change-detection hash `docs/DESIGN.md` §2.2 already refuses to store, and the one
  fact that lets a later sync answer "has this changed since" **directly**, without depending on
  whether `extract/cache.py`, or any prior local index, still happens to hold the answer.

  A rebuild does not depend on `extract/cache.py` to honour this: before the new database exists,
  sync reads the *old* `index.db` (still on disk until the atomic swap) for every paid-recorded
  document, keyed on `doc_id` alone — this table's own primary key, therefore unique by
  construction, and the one identifier a renamed sidecar still carries unchanged — and copies its
  row, chunks and embeddings straight across via SQLite's `ATTACH DATABASE`, at the file's *old*
  content_hash. If that still matches the current file, the document is simply protected; if it
  does not, the stale row is copied forward anyway alongside a `failures` entry, so a changed paid
  document survives a rebuild exactly as it survives a normal sync (decision 14) rather than
  vanishing from the index the instant one runs. A rename reaches this same guarantee a different
  way: `pair()`'s `Adopt`/`Rename` rows never touch the same-path comparison a normal sync uses, so
  a sync also checks whether *this same connection* already holds an active row for the document's
  own `doc_id` at its unchanged content_hash, before `extract/cache.py` is ever consulted at all.

  **Per-document extraction coherence** (`docs/DESIGN.md` §4.4, decision 13): every query
  re-derives each distinct recorded backend's current, client-free fingerprint and compares. A
  mismatch on a **free** backend refuses the query, naming the stale paths (the text can be
  silently wrong, and re-extracting is free). A mismatch on a **paid** backend never refuses —
  the text is still correct, merely older — but marks every affected `Passage.stale_extraction`
  and warns in `pnk doctor`. An unrecognised backend name is skipped, never a reason to refuse an
  otherwise-healthy KB. `pnk doctor` also gains three by-path gap reports: documents awaiting a
  paid extraction, paid extractions the manifest no longer asks for, and a paid document whose
  file has changed since.

  **Caught by an independent adversarial review before this ever reached a commit** (full detail:
  `docs/RETROSPECTIVES.md`): the original design protected a paid extraction only via `pair()`'s
  same-path comparison or `--rebuild`'s own copy-forward — any *other* pairing outcome (a rename,
  or a document adopted some other way) fell through to a cache lookup alone, which cannot tell
  "just renamed" or "just cloned" apart from "genuinely changed" — all three look identical as a
  cache miss. Fixed by moving the change-decision itself onto the sidecar's own recorded
  content_hash (above), with a same-connection lookup added for the rename case and the
  doc_id-keyed rebuild lookup extended to the changed-hash case — three fixes, described in the
  two paragraphs above rather than as a separate, later correction. A `sidecar_hash` staleness bug
  (a fresh paid-provenance write left the very next sync one `RefreshMetadata` cycle away from
  settling) was found and fixed the same pass.

  **Tests:** `tests/test_chunk_pdf.py` proves the span invariant, the never-drop guarantee, and
  page monotonicity over the corpus's 15 extractable fixtures, plus a dedicated two-page-chunk
  case against the `hyphenation-page-break` fixture. `tests/test_pairing.py` and
  `tests/test_sync.py::test_backend_drift` (six named cases, addressable as
  `test_backend_drift[changed_hash]` etc.) cover the decision table in isolation and end to end;
  `test_a_rebuild_preserves_paid_provenance` and `test_a_rebuild_after_clear_cache_still_
  preserves_it` cover the two rebuild cases specifically — the second constructed, and confirmed
  by deliberately reverting the `ATTACH DATABASE` mechanism first, to fail without it.
  `test_a_rebuild_never_lets_a_free_twin_inherit_the_paid_ones_backend`,
  `test_a_rename_after_clear_cache_does_not_falsely_claim_content_changed`,
  `test_a_fresh_clone_with_no_local_cache_or_index_fails_honestly_not_falsely`,
  `test_a_rebuild_keeps_a_changed_paid_document_searchable_but_flagged` and
  `test_three_consecutive_paid_syncs_settle_after_the_first` each cover one review finding above,
  every one confirmed to fail against the pre-fix code first. A working *paid* test backend stands
  in for `claude-vision`, whose own loader remains an honest I7b stub throughout.
  `tests/test_search.py` covers both coherence outcomes and asserts `"anthropic" not in
  sys.modules` after a query, in a subprocess, over a KB holding a paid document.
  `tests/test_doctor.py` covers the extraction-coherence WARN and all three by-path gap reports,
  including that "paid extraction not requested" stays green — it names the protection working,
  not a problem.

### Fixed

- **`main` had been CI-red since I2's first scanned-corpus run — through I3a and I3b — on a
  cross-platform rendering bug nobody had checked GitHub Actions for.** `test_scanned_regeneration_
  within_tolerance` failed deterministically on the `check (light pdf)` / `check (light pdf
  claude)` jobs with the identical signature every time: `scanned-clean: 8006 pixels differ by >32
  levels`. `pdfwriter.py` wrote every text fixture as `/BaseFont /Helvetica` with no embedded font
  program, relying on the PDF reader's own substitution — and pypdfium2's prebuilt binaries
  substitute a *different* font per platform (macOS has a real Helvetica; `ubuntu-latest` doesn't).
  Same word-wrap, same layout, different glyph outlines, so the scanned stratum (rasterized through
  pdfium at fixture-generation time) baked in whatever glyphs the generating machine's pdfium
  substituted. Confirmed directly, not just theorized: an `ubuntu:24.04` Docker container
  reproduced CI's exact number (8,006 px) on the first try, and a diff heatmap showed every changed
  pixel sitting exactly on a glyph edge — same text, same positions, different anti-aliasing.
  Measured cross-platform noise across all ten scanned pages ranged 507-8,262 px, which ruled out
  simply raising `MAX_CHANGED_PIXELS`: the test's own docstring establishes its detection target as
  a single moved word, plausibly smaller than that noise floor, so a threshold wide enough to
  absorb it would likely have gone blind to the exact defect class the test exists to catch. Fixed
  at the root: `pdfwriter.py` now embeds a subsetted, real TrueType font
  (`tests/pdf-corpus/fonts/LiberationSans-Subset.ttf`, SIL OFL 1.1 — the project's first and only
  third-party binary asset, chosen for Helvetica/Arial metric compatibility so none of
  `generate.py`'s hand-placed coordinates needed to change) instead of a bare base-14 name, so
  every platform rasterizes the same glyph outlines. Re-ran the same Docker reproduction after the
  fix: 0 pixels changed across every scanned page, not merely under tolerance. `Font` drops its now
  always-"Helvetica" `base_font` field; `_font_object` gained a real `/FontDescriptor`/`/FontFile2`/
  `/Widths` embed, derived from the subset's own hmtx/head/hhea/OS2 tables (documented, reproducible
  commands in `tests/pdf-corpus/fonts/README.md`) rather than assumed. All nineteen fixtures were
  regenerated; no `.expected.txt` changed, confirming the font swap altered no extracted character.

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

[Unreleased]: https://github.com/lucagattoni/Pinakes/compare/v0.2.2...HEAD
[0.2.2]: https://github.com/lucagattoni/Pinakes/releases/tag/v0.2.2
[0.2.1]: https://github.com/lucagattoni/Pinakes/releases/tag/v0.2.1
[0.2.0]: https://github.com/lucagattoni/Pinakes/releases/tag/v0.2.0
[0.1.4]: https://github.com/lucagattoni/Pinakes/releases/tag/v0.1.4
[0.1.3]: https://github.com/lucagattoni/Pinakes/releases/tag/v0.1.3
[0.1.2]: https://github.com/lucagattoni/Pinakes/releases/tag/v0.1.2
[0.1.1]: https://github.com/lucagattoni/Pinakes/releases/tag/v0.1.1
[0.1.0]: https://github.com/lucagattoni/Pinakes/releases/tag/v0.1.0
