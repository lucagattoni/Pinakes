# CLI reference

Every command and flag on the `pnk` surface, as of 0.2.0 (20260728 16:40). Task-oriented walkthroughs
are in [GUIDE.md](GUIDE.md); whether something is built yet is in [STATUS.md](STATUS.md).

`pnk --help` and `pnk <command> --help` are authoritative — this file adds the *when* and *why*.

## Exit codes

A contract, not an accident:

| Code | Means |
|---|---|
| `0` | Success — including a no-op, and including a sync that found a live lock held by this host |
| `1` | Operational failure — one or more documents failed, a check refused, a lock could not be taken |
| `2` | Usage error — an unknown flag, an unknown backend name, a missing argument |

Every error carries a **remedy**, not just a message. If one doesn't, that's a bug worth filing.

## Common flags

| Flag | On | Means |
|---|---|---|
| `--kb PATH` | `sync`, `search`, `doctor`, `install-hooks`, `budget` | KB root. Defaults to the nearest `pinakes.toml`, searching upwards from the cwd — git-style |
| `--offline` | `sync`, `search`, `serve` | Never reach out for model weights. Fails fast instead of downloading |

---

## `pnk init`

```
pnk init [--name NAME] [--template TEMPLATE] [--ci] path
```

Stamps a new KB and mints its **permanent** KB ULID.

| Flag | Default | Notes |
|---|---|---|
| `path` | — | Directory to create the KB in |
| `--name NAME` | the directory name | Human-facing only; rename freely |
| `--template TEMPLATE` | `notes` | The blueprint. `notes` is the only one shipped |
| `--ci` | off | Also write `.github/workflows/pinakes.yml`, which syncs and caches `.pinakes/`. Refuses to overwrite an existing one |

Writes `pinakes.toml`, `docs/` and a `.gitignore` covering `.pinakes/`. It does **not** create an
index — the first `pnk sync` does that.

`--ci`'s workflow runs `pnk sync --extract=pypdfium2` and says so on the line itself: CI is
non-interactive and must never spend, exactly as the git hooks are. `init` prints that at write
time too.

Two things `init` cannot know, both needing a manual manifest edit afterwards
([GUIDE](GUIDE.md#choosing-a-backend)): it always stamps the `sentence-transformers` provider, and
it does not include `**/*.pdf` in `[sources]`.

## `pnk sync`

```
pnk sync [--kb PATH] [--rebuild] [--sidecars-only] [--index-only] [--stage]
         [--offline] [--force-unlock] [--extract BACKEND] [--force]
         [--clear-cache[=paid]] [--yes] [-q]
```

The freshness primitive. Walks the sources, compares content hashes, re-processes only what changed.
Free and deterministic, so running it on every commit costs nothing.

Each document is processed in its own transaction: one broken PDF cannot block a 1,000-document
corpus. Failures are recorded, the run continues, and sync exits non-zero listing them.

| Flag | Notes |
|---|---|
| `--rebuild` | Rebuild the index from scratch. Builds into `index.db.new`, checkpoints, closes, then renames atomically. **`ledger.jsonl` always survives** |
| `--sidecars-only` | Mint missing sidecars; never touch the index. The `pre-commit` half |
| `--index-only` | Update the index; never write into `docs/`. The `post-commit` half |
| `--stage` | With `--sidecars-only`: limit to staged files and `git add` them, so a document and its ID land in one commit |
| `--extract BACKEND` | Override `[extraction] backend` for this run only. Validated against the registry *without importing* it, so an unknown name is a usage error before any extra could matter |
| `--force` | Meaningful **only** with an explicit free `--extract`: overwrite a paid extraction, printing what it discards. `--force` alone changes nothing |
| `--clear-cache[=paid]` | Empty `cache/extract/` entirely — paid or free, active or orphaned — after printing the entry count and bytes and requiring a `y`. Never touches `ledger.jsonl`. `=paid` is the explicit authorisation to destroy entries a paid backend wrote |
| `--yes` | Answer this run's confirmation prompts, for cron. **Raises no cap**, and does not authorise clearing paid cache entries — that needs `--clear-cache=paid` as well |
| `--force-unlock` | Take a lock held by another machine. Liveness cannot be checked across hosts, so this is deliberately a human decision |
| `-q`, `--quiet` | Print only problems |

**A paid extraction is never silently downgraded.** A free run, a `--rebuild`, a rename and an
explicit free `--extract` all leave paid-extracted text alone, and the run says once which paths it
protected. The single override is `--force` *plus* a free `--extract`. Full decision table:
[DESIGN §6.4](DESIGN.md#64-sync-semantics-the-part-that-silently-corrupts-a-kb-if-left-vague).

**A file no `include` pattern matches is named, not silently skipped** (0.2.2), grouped by extension
with the glob that would pick it up. Only files pinakes could actually index are listed — the test
is whether the bytes are UTF-8, the same one indexing itself applies, plus `.pdf` — so images and
archives beside your notes never appear, and the suggested glob never leads to a failed document.
`exclude` them to silence the line for good.

**`--yes` has exactly one job: answering a prompt.** It does not raise a cap — a run that would
breach one is refused before any confirmation is considered — and it does not authorise destroying
paid cache entries. Unattended, `pnk sync --yes --clear-cache` on a cache holding paid work exits
non-zero naming `--clear-cache=paid`, which no hook and no generated workflow ever writes.

**Locking.** `.pinakes/sync.lock` records pid, hostname and start time. A live holder on this host
means a quiet exit 0 — hook-driven contention is normal, not an error. A dead pid is reclaimed with
a warning. Another host refuses, pointing at `--force-unlock`.

## `pnk search`

```
pnk search [--kb PATH] [--tag TAG] [--path-prefix PREFIX] [--source-type TYPE]
           [--modified-after YYYYMMDD] [--modified-before YYYYMMDD]
           [-k K] [--json] [--offline] query
```

The free retrieval pipeline: metadata filter → BM25 + dense vectors in parallel → reciprocal rank
fusion → local cross-encoder rerank → cited passages plus a confidence signal.

| Flag | Notes |
|---|---|
| `--tag TAG` | Only documents carrying this tag. **Repeatable.** Tags come from the sidecar |
| `--path-prefix PREFIX` | Only documents whose path starts with this |
| `--source-type TYPE` | `markdown`, `text`, `code` or `pdf` |
| `--modified-after YYYYMMDD` | By the document's **mtime** — every document has one, unlike a sidecar's optional `created` |
| `--modified-before YYYYMMDD` | Same |
| `-k K` | How many passages to return. Defaults to `[retrieval] final_k` |
| `--json` | Machine-readable output |

Filters compose and are applied in SQL *before* retrieval, not as a post-filter.

Queries **refuse to run** against an index built by a different embedding model, or one whose free
PDF extractor's fingerprint has drifted — returning garbage silently would be worse. `pnk sync
--rebuild` clears both, for free.

`confidence` is `unknown` unless the manifest carries fitted `[retrieval.confidence]` thresholds
**and** `fitted_for` names the reranker actually in use. That is the honest default, not a defect
([GUIDE](GUIDE.md#about-that-confidence-unknown)).

## `pnk doctor`

```
pnk doctor [--kb PATH] [--prune]
```

Health check. Reports environment (SQLite version, FTS5, loadable extensions), backend and cached
weights, template drift, index/model coherence, extraction coherence, calibration validity,
orphaned sidecars, duplicate IDs, dangling links and link coverage, recorded failures, extraction
cache stats, the 50k-chunk NumPy threshold, held sync locks, hook status, the price table's age,
unknown-outcome ledger records, and whether a paid backend is configured on a KB whose hooks force
the free one.

| Flag | Notes |
|---|---|
| `--prune` | Delete orphaned sidecars — **the only thing `doctor` can change**. Prints every path first |

Every non-OK check carries a remedy. Exits non-zero when any check fails.

## `pnk install-hooks`

```
pnk install-hooks [--kb PATH]
```

Writes three git hooks, split by what each may touch: `pre-commit` (mints and stages sidecars — the
only one that writes into `docs/`), `post-commit` and `post-merge` (index only). See
[GUIDE](GUIDE.md#keeping-the-index-fresh).

All three run `pnk sync --extract=pypdfium2`, forcing the free extractor, and `install-hooks`
prints one line saying so. A hook is non-interactive: without the flag it would either abort on
every commit (no terminal to confirm an estimate from) or spend afresh on every commit. Paid
extraction stays a `pnk sync` you run.

An existing hook that is not ours is left untouched and printed with the line to add.

## `pnk budget`

```
pnk budget [--kb PATH] [--resolve CALL_ID --actual EUR]
```

Reads `.pinakes/ledger.jsonl` and reports today's and this month's spend against their caps, the
per-operation cap, the outcome of every call (`reconciled`, `voided`, `unknown outcome`), and the
five most recent operations. It only ever reads — it cannot spend, and it works on a KB that has
never spent, printing zeros.

| Flag | Notes |
|---|---|
| `--resolve CALL_ID` | Close an `unknown outcome` by **appending** a reconciliation. Never an edit: the ledger is append-only |
| `--actual EUR` | Required with `--resolve`. What the call actually cost, read from the vendor's usage dashboard. Priced at the reservation's own rate, so the pair stays internally consistent |

**Each window names the rate and price date behind its total**, and says so when a window spans more
than one — a euro figure derived from two USD/EUR rates is correct but not reproducible from a
single number.

**A timeout is neither reconciled nor voided.** It may or may not have billed, so it counts at its
reserved amount until resolved; three of them consume a €1.00 day. `pnk budget` lists them with the
exact `--resolve` line, and `pnk doctor` warns once their total passes a quarter of a window.

**`monthly_eur` is per KB.** Ten paid KBs have ten monthly allowances. v0.2 adds no global cap and
says so rather than leaving a reader to assume one.

## `pnk serve`

```
pnk serve [--offline] [KB ...]
```

Runs the MCP server over stdio, exposing `pinakes_search`, `pinakes_get` and `pinakes_list_kbs`.

`KB` is one or more KB directories; with none, the nearest one. **The server answers only about the
KBs named here** — no tool argument accepts a filesystem path, and `pinakes_get` resolves a document
ULID through the index.

Indexes are opened **read-only**, and re-opened when a `stat()` shows the file was swapped by a
rebuild — so a sync during a session is safe.

---

## Planned — not built yet

Listed so the shape is known in advance; each names the increment that lands it
([STATUS](STATUS.md#v02-increment-ledger)).

| Surface | Increment | Adds |
|---|---|---|
| `pnk sync --estimate-only` | I7b | Builds the real request and counts tokens. **A network call**, not an offline estimate |
| `path:page` citations | I8 | `docs/paper.pdf:7` / `:7-8` on both the CLI and MCP surfaces; page spans are already in the index |
| `stale_extraction` on MCP results | I8 | The marker a paid-fingerprint mismatch sets, reaching the agent surface and not only the CLI |
| `pnk ask --deep` | v0.4 | Bounded, budgeted synthesis for CLI and cron use, where no agent is present |
| `pnk link`, `pinakes_links` | v0.3 | Authoring and traversing cross-KB links |
| `pnk upgrade` | v0.5 | Diffs a KB's template version against the installed one and *prints* a migration — never applies one |
