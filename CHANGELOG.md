# Changelog

All notable changes to this project are documented here.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project
adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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

Nothing is released yet — no functionality exists, so this stays unreleased until the v0.1 vertical
slice (`init` / `sync` / `search` / MCP server / eval harness) is usable end to end.

[Unreleased]: https://github.com/lucagattoni/Pinakes/commits/main
