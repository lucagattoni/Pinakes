# CLI reference

Every command and flag on the `pnk` surface — including what is merged to `main` but not yet
released. Task-oriented walkthroughs are in [GUIDE.md](GUIDE.md); **whether a given surface is in a
release yet is [STATUS.md](STATUS.md)**, which is why no version is quoted here.

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
| `--kb PATH` | `sync`, `search`, `doctor`, `install-hooks`, `budget`, `link`, `links` | KB root. Defaults to the nearest `pinakes.toml`, searching upwards from the cwd — git-style |
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
pnk sync [--kb PATH] [--rebuild] [--sidecars-only] [--index-only] [--stage] [--offline] [--scan-links]
         [--offline] [--force-unlock] [--extract BACKEND] [--force]
         [--estimate-only] [--clear-cache[=paid]] [--yes] [-q]
```

The freshness primitive. Walks the sources, compares content hashes, re-processes only what changed.
Free and deterministic, so running it on every commit costs nothing.

Each document is processed in its own transaction: one broken PDF cannot block a 1,000-document
corpus. Failures are recorded, the run continues, and sync exits non-zero listing them.

| Flag | Notes |
|---|---|
| `--rebuild` | Rebuild the index from scratch. Builds into `index.db.new`, checkpoints, closes, then renames atomically. **`ledger.jsonl` always survives** |
| `--sidecars-only` | Mint missing sidecars; never touch the index. The `pre-commit` half. Refuses to mint over a sidecar that exists but will not parse — it still holds that document's permanent ULID — and records it as a failure, so **a `pre-commit` hook blocks the commit** until the file is repaired. Only a commit staging that *document* is affected; editing the sidecar alone is not |
| `--index-only` | Update the index; never write into `docs/`. The `post-commit` half |
| `--stage` | With `--sidecars-only`: limit to staged files and `git add` them, so a document and its ID land in one commit |
| `--scan-links` | Re-read every `[[links.kb]]`'s committed sidecars now, ignoring the freshness window. Ordinary syncs skip a partner read within the last hour, because this runs on `post-commit` and `post-merge`. Refused together with `--sidecars-only`, which never opens the index at all |
| `--extract BACKEND` | Override `[extraction] backend` for this run only. Validated against the registry *without importing* it, so an unknown name is a usage error before any extra could matter |
| `--estimate-only` | Price what a paid run would cost and exit, extracting nothing. **A network call** — it measures the real first-slice request with the vendor's own token counter, so it needs a key. It generates nothing and bills no output. Refuses on a free backend |
| `--force` | Overrules **exactly two** refusals: paying to extract a PDF whose free text layer is already healthy, and — **only together with an explicit free `--extract`** — overwriting a paid extraction, printing what it discards. It never widens `per_operation_eur`, `daily_eur`, `monthly_eur`, the stale-price refusal, the missing-floor refusal, or the no-terminal abort |
| `--clear-cache[=paid]` | Empty `cache/extract/` entirely — paid or free, active or orphaned — after printing the entry count, the bytes, **and what the paid entries cost in euros**, and requiring a `y`. Never touches `ledger.jsonl`. `=paid` is the explicit authorisation to destroy entries a paid backend wrote. The bare form is `=all` spelled out — both clear the whole cache, so the value names what you are authorising, not what is removed |
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

**Paid extraction never starts before the free checks finish.** Page count, encryption, the
per-request size limit, the model's context window, and — the one that saves the most money — the
free extractor's own text yield against the fitted floor: a PDF whose text layer is already healthy
is **refused**, because paying to re-read text you already have is the likeliest way to lose money
by accident. `--force` overrides it. Then the whole document is priced and checked against all
three caps *before the first call*, and every individual call is reserved before it is made.

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

**Citations name a page when the source has pages.** A PDF passage cites `docs/paper.pdf:p7`, or
`docs/paper.pdf:p7-8` when the chunk straddles a page break — which happens legitimately, since a
word hyphenated across the break is joined into one block. Every other source keeps the character
offsets it always rendered: `docs/notes.md:12-480`. **The `p` is not decoration** — without it,
`:12-480` would mean character offsets and `:12-13` would mean pages, in the same syntax, told
apart only by knowing the file.

`--json` carries `page_start` / `page_end` as separate integer fields (both `null` for a source
with no pages) alongside the rendered `citation`, so nothing has to parse a citation back apart. It
also carries `stale_extraction`: the recorded fingerprint when a document's *paid* extraction
backend has since moved on. Such a passage is **marked, never withheld** — the text is correct,
merely older — and the human-readable output prints the same marker under the citation.

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
cache stats, PDF text yield, the completeness audit's below-median pages, the 50k-chunk NumPy
threshold, held sync locks, hook status, the price table's age,
unknown-outcome ledger records, and whether a paid backend is configured on a KB whose hooks force
the free one.

**`text yield` reports per page, never per document.** It prints the median non-whitespace
characters per page over the PDFs it could measure, then the pages falling below the fitted floor —
by path *and* page (`docs/scan.pdf p4-9`). A document-level median would stay silent on a 200-page
report with eight scanned inserts, which is precisely the document worth knowing about. Pages
below the floor have no text layer, so nothing on them is searchable; the remedy names the paid
extractor and says that it spends.

It measures the **extraction cache**, never by re-extracting: the cache entry is the text the index
was built from. A document whose entry has been swept is counted as unmeasured and said to be —
`.pinakes/cache` is disposable, and `pnk sync` repopulates it. A document already extracted by a
paid backend is left out and named, since the question this check asks — *does the free path
suffice?* — is settled for it. With no fitted floor installed, the distribution is reported and
nothing is judged.

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

Runs the MCP server over stdio, exposing four tools:

| Tool | Arguments | Returns |
|---|---|---|
| `pinakes_search` | `query`, `kb?`, `tags?`, `path_prefix?`, `source_type?`, `k?` | Cited passages, a confidence signal, a suggested next step |
| `pinakes_get` | `doc_id`, `kb?`, `page_start?`, `page_end?` | One document, optionally one page range |
| `pinakes_links` | `doc_id`, `kb?`, `rel?`, `direction?` (`out`/`in`/`both`), `depth?`, `query?` | Neighbours, `frontier`, `unresolved`, `truncated` — and `confidence` always `unknown` |
| `pinakes_list_kbs` | — | The KBs this server was pointed at |

**Every tool that answers about a KB takes an explicit `kb`**, defaulting to the first one served
(`pinakes_list_kbs` takes no arguments — it *is* the list). `pinakes_links` caps `depth` at 3
server-side and has no query language, ever.

A neighbour's `score` is comparable only among rows carrying the same `scored_by_query`: with a
`query`, a neighbour with no local chunks to embed falls back to its edge weight, which is not on
the same scale as a cosine. The list comes back in rank order, so re-sorting it by `score` is a
mistake rather than a refinement. A neighbour in a *different* served KB carries `fetch_with` —
the `doc_id` and `kb` that `pinakes_get` needs together, because an id resolves inside one KB.

Its `confidence` is `unknown` on **every** return, with or without a `query`. The thresholds
`pinakes_search` reports against are fitted per KB on the reranker score of the top retrieved
passage; a traversal neighbour is not a retrieved passage, and a neighbour list spanning two KBs has
no single manifest whose thresholds would apply. Reporting anything else would be an invented
signal.

A neighbour whose KB **this server was not pointed at** comes back with `reachable: false`, its
`kb_id`, its `doc_id` and a reason — identified rather than omitted, so an agent can act on the fact
that the link exists and this process cannot follow it. Reachability is a property of the server
invocation, not of any manifest.

`KB` is one or more KB directories; with none, the nearest one. **The server answers only about the
KBs named here** — no tool argument accepts a filesystem path, and `pinakes_get` resolves a document
ULID through the index.

Indexes are opened **read-only**, and re-opened when a `stat()` shows the file was swapped by a
rebuild — so a sync during a session is safe.

---

## `pnk link`

```text
pnk link <source> <target> --rel REL [--kb PATH]
```

Write one link, into **`<source>`'s own sidecar and nothing else**. The other end learns about it
when it next runs `pnk sync --scan-links`; a link is never written into someone else's file.

`<source>` is a path relative to the KB root. A document with no sidecar is **refused** — run `pnk
sync` first, which mints the permanent ULID the link needs. `pnk link` never mints one: a fresh
ULID written over a file that already holds a permanent one breaks every inbound link to it, and
there is no migration machinery by design.

`<target>` has three grammars, tried **in this order**, because they overlap:

| Form | Example | Resolved by |
|---|---|---|
| a `pnk://` URI | `pnk://01J…KB/01J…DOC`, or `pnk://self/01J…DOC` | Parsing alone. `self` expands to this KB before anything is written |
| `<alias>:<path>` | `partner:docs/loan-agreements.md` | The alias must be a declared `[[links.kb]]`; that KB's own `[kb] id` and the document's sidecar supply the two ULIDs |
| a path in this KB | `docs/loans-outward.md` | Reading that document's sidecar for its ULID |

The `pnk://` prefix is tried first because `pnk://…` would otherwise split as the alias `pnk`, and
the alias form bites **only** on a declared name — a POSIX path may legitimately contain a colon.

**Aliases never reach disk.** `partner:` is machine-local; what is written is
`pnk://<kb-ulid>/<doc-ulid>`, which is why a link survives the KB being shared. The same is true of
`self`.

**What is refused, and what is not.** A well-formed `pnk://` URI whose target is not on this
machine **is written**: both ULIDs are already in it, and refusing would make authoring depend on
which KBs happen to be checked out. Nothing checks that target afterwards, either — `pnk doctor`'s
cross-KB check is not built yet, and `pnk links` reports only *local* targets under `unresolved`,
because a cross-KB one cannot be verified from here without the other KB. An **alias** that cannot
be turned into a ULID pair is refused, because
resolving one means reading that KB. So is an alias whose partner declares a different `[kb] id`
than `[[links.kb]]` does — one of the two names the wrong KB, and what would be written is
permanent.

Running the same `pnk link` twice writes nothing the second time and says so. Two *different*
relations to one target are two entries: a pair of documents can relate more than one way.

The sidecar is rewritten through the round-trip parser, so comments, quoting, blank lines, your own
key order and any key pinakes does not know all survive — including a key of your own inside a
`links[]` entry. Two documented exceptions, both from the YAML writer rather than from this
command: appending to an **indented** `links:` block re-indents that block, and appending `links:`
for the first time to a file whose last line is a comment leaves that comment reading as the
block's introduction. [MANIFEST](MANIFEST.md#the-sidecar--filepnkyaml) lists the full set.

**It takes no lock.** `pnk sync` holds one; this does not, so a sync writing the same sidecar at the
same moment can lose one side's change — whichever writes last wins. Rename-atomicity prevents a
*torn* file, not a lost update.

Only one thing can actually collide with it: a **paid** extraction you started yourself, which is
the one sync that rewrites an existing sidecar. The git hooks cannot — `post-commit` and
`post-merge` run `--index-only` and never write into `docs/` at all, `pre-commit` only *mints*
sidecars for documents that have none, and all three force the free extractor. So the window is a
`pnk link` typed while your own `pnk sync` is paying to extract that same document; if it happens,
re-run whichever change went missing.

---

## `pnk links`

```text
pnk links <document> [--kb PATH] [--rel R] [--direction out|in|both] [--depth N] [--query Q]
          [--offline] [--json]
```

What a document connects to, and what connects to it. `<document>` is a ULID or the path `pnk
search` prints.

| Flag | Notes |
|---|---|
| `--rel` | Only links carrying this relation |
| `--direction` | `out` (links written here), `in` (links pointing here), `both` (default) |
| `--depth` | Hops to follow. Default 1, **server-capped at 3** |
| `--query` | Rank neighbours by similarity to this instead of by edge. Loads the embedding model; without it, no model is loaded at all |
| `--json` | `{document, neighbours, frontier, unresolved, truncated}` |

Without `--json` each neighbour is one line, and the arrow says who wrote the link:

| Glyph | Means |
|---|---|
| `->` | written **by the document it hangs off** — the one you asked about at hop 1, its parent beyond that |
| `<-` | written at the other end, pointing back; from the other KB's sidecars when it lives in one |
| `<->` | the **same relation written from both ends** — two people, one pair |
| `?` | no direction was established. Unreachable through the shipped provider; it exists so an unestablished direction cannot render as `<->` |

A row also reports `direction` under `--json`, carrying `out`, `in` or `both` — and `unknown` for
the `?` case. Beyond hop 1 the direction is relative to the **parent** that reached the row, not to
the document you asked about, because a row does not carry which parent that was. Rows come back in
rank order; `score` is comparable only among rows sharing a `scored_by_query`, because a neighbour
with no local chunks to embed falls back to its edge weight, which is not a cosine.

**Every neighbour is a document**, and `kb_id` is always the KB's ULID — never `[kb] name`, which
is free to rename, and never a `[[links.kb]]` alias, which means nothing on another machine.

A neighbour in **another KB is terminal**: it is returned, and never expanded, at any depth. Not
because there is nothing there — this index holds that KB's links *pointing back here* — but
because expanding it would show a systematically partial slice of someone else's graph that you
could not tell apart from the whole. `title` is present for a local neighbour and absent for a
cross-KB one, for the same reason: this index has the partner's links, not its documents.

Neighbours found but **not** expanded come back on `frontier` with one of five reasons —
`terminal`, `depth`, `fanout`, `rows`, `tokens`. Links whose target this KB does not have come back
under `unresolved` rather than being dropped, and never appear as neighbours: there is no document
there to be one. When a walk returns nothing the human output says **why**, in the same precedence
`pinakes_links` uses: your `--rel`, `--direction` or `--depth` excluded everything, or the links
resolve to nothing, or there genuinely are none. The narrowing is reported first because a live neighbour may
sit one dropped argument away — and stdout must never print `no links` for a document whose links
stderr is listing.

---

## Planned — not built yet

Listed so the shape is known in advance; each names the increment that lands it
([STATUS](STATUS.md#v02-increment-ledger)).

| Surface | Increment | Adds |
|---|---|---|
| `pnk ask --deep` | the deep release | Bounded, budgeted synthesis for CLI and cron use, where no agent is present |
| `pnk upgrade` | the template release | Diffs a KB's template version against the installed one and *prints* a migration — never applies one |
