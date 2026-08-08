# Pinakes — a portable, agent-first knowledge base

**Repo:** github.com/lucagattoni/pinakes (PUBLIC) · **Licence:** Apache-2.0 · **Python:** 3.13+
**Package:** `pinakes` · **Command:** `pnk` · **Tooling:** uv
**Design date:** 20260725 09:52 (review pass 7) · **Last reviewed against the code:** 20260728 16:40

> *The* Pinakes *were Callimachus's catalogue of the Library of Alexandria — the first known index
> of a body of knowledge.*

---

**This document is the architecture and its rationale — *why* the system is shaped this way.** It
deliberately does not track releases:

| For | Read |
|---|---|
| Whether something is **built yet** | [STATUS.md](STATUS.md) — the only place that says so |
| **How to use** it | [GUIDE.md](GUIDE.md) |
| A **flag** or a **manifest field** | [CLI.md](CLI.md) · [MANIFEST.md](MANIFEST.md) |
| What is **going to be built**, in order | [`plans/`](https://github.com/lucagattoni/pinakes/tree/main/plans/) |

Sections whose amendment is assigned to an unshipped increment carry a dated **⏳ pending** note
saying so, rather than describing behaviour that does not exist.

---

## 1. What this is

A Python engine for building **self-contained knowledge bases**: one directory = one KB, holding
human-readable source documents, human-readable metadata, and a disposable machine index.

KBs are created from **templates** (the "blueprint"), rebuilt **reproducibly** from a manifest, and
**linked to each other** so an agent can follow a reference from one KB into another.

The design has one organising principle: **the free path does the work.** Local embeddings, local
lexical search, local reranking — the whole retrieval stack costs nothing to run, forever. Paid LLM
work — reasoning *and* PDF extraction — is an explicit, budgeted opt-in.

"The default agent surface never triggers it" is stated as an **enumerated allowlist of paid entry
points** rather than as a convention, because a convention has nothing to check it against. Exactly
two things may spend: `pnk sync` on a KB whose `[extraction] backend` is `claude-vision` (or a run
passing `--extract=claude-vision`), and `pnk ask --deep`. Both go through §5's accountant. The list
lives in `.paid-path-allowlist`; adding to it edits that file, this section and
[INVARIANTS.md](INVARIANTS.md) together. Everything else is free *by construction*: no module outside the allowlist may so much as
import a paid client. What proves it is not a grep — a grep only ever knows the spellings someone
thought of — but a run of the whole free path in a fresh process, asserting on what actually landed
in `sys.modules`.

### Decisions taken (from requirements gathering)

| Area | Decision |
|---|---|
| Consumer | Agent-first, but source of truth is human-readable files |
| Surfaces | MCP server + CLI (Python API is the internal substrate, not yet a public contract) |
| Deployment | Local-first, one portable directory per KB. No server, no daemon |
| Build posture | Own the format + orchestration; reuse proven components |
| Sources | Markdown / plain text / code, and PDF. **Not** Office, web, email, chat |
| Scale | Scale-agnostic: exact and simple when small, memory-bounded upward (§3) |
| Compute | Local embeddings (free, unlimited re-index) + Claude for reasoning **and opt-in PDF extraction** — the two entries on §1's paid allowlist |
| Embeddings | `sentence-transformers` default, installed via the `[st]` extra (§4.5) |
| Budget | Pre-call reservation · hard cap per operation · rolling ledger (§5) |
| Blueprint | Instantiable template **and** reproducible recipe |
| Federation | Cross-KB links you can follow (no fan-out query in v1) |
| Retrieval | Hybrid (BM25 + vector) + rerank · metadata filters · multi-hop within a KB, and one terminal hop across a link |
| Cost policy | Free path first; escalate only when it's insufficient |
| Content vs repo | Engine public; real KBs live elsewhere; one synthetic demo KB in-repo |
| Linking | Sidecar metadata files (originals never mutated) |
| Freshness | Git-hook / CI triggered, calling the explicit `pnk sync` primitive |
| Quality | Golden question set + scored regression tests in CI |
| Eng bar | uv · ruff · pyright · pytest · CI · semver · Apache-2.0 |

---

## 2. Anatomy of a KB

```
my-research-kb/                    ← this whole directory IS the KB. Normally a git repo.
├── pinakes.toml                   ← manifest: identity, template, models, sources, budget
├── docs/                          ← SOURCE OF TRUTH. Human-readable, human-editable, git-tracked.
│   ├── attention-is-all-you-need.pdf
│   ├── attention-is-all-you-need.pdf.pnk.yaml    ← sidecar: id, tags, links, provenance
│   ├── notes/transformers.md
│   └── notes/transformers.md.pnk.yaml
├── .pinakes/                      ← GENERATED. Disposable. gitignored.
│   ├── index.db                   ← SQLite (WAL): documents, chunks, FTS5, vectors, links
│   ├── ledger.jsonl               ← append-only spend log
│   ├── sync.lock                  ← advisory lock, one writer at a time
│   └── cache/                     ← KB-derived artifacts only (extracted PDF text)
└── .gitignore                     ← ships with `.pinakes/`
```

**The split is the whole trick.** `docs/` + `pinakes.toml` are portable, diffable, and meaningful to
a human with no tooling — and **both are committed, including every sidecar**. `.pinakes/` is derived
state, always regenerable with `pnk sync --rebuild`. That is what makes a KB simultaneously a
*reproducible recipe* and a directory you can hand to someone.

A direct consequence, used repeatedly below: **anything another KB needs to see must live in
committed files, never in `.pinakes/`** — a freshly cloned KB has no index at all.

### 2.1 The manifest — `pinakes.toml`

> **Every field, its default and its validation rule: [MANIFEST.md](MANIFEST.md).** This section
> carries only the reasoning behind the shape.

```toml
[kb]                    # identity — REQUIRED. `id` is a permanent ULID
[sources]               # roots / include / exclude, always KB-root-relative
[embedding]             # provider, model, dim — REQUIRED: the index *is* this model's output
[extraction]            # PDF backend: free or paid
[chunking]              # structural, max_tokens, overlap
[retrieval]             # three separate widths, fusion, rerank, vector tier, adjacent_k
[retrieval.confidence]  # fitted thresholds; absent ⇒ report `unknown`, never guess
[rerank]                # mirrors [embedding]
[budget]                # soft confirm threshold, hard per-operation cap, rolling windows
[[links.kb]]            # connected KBs: canonical ULID + machine-local alias and path
```

**What must be present, and why.** `[kb]` (`name`, `id`), `[sources]` (`roots`) and `[embedding]`
(`provider`, `model`, `dim`) are required: nothing can sensibly default a KB's identity, its sources,
or the model whose output the index *is*. Everything else takes a default, except
`[retrieval.confidence]` and `[[links.kb]]`, which stay absent until something produces them.

**Pinakes writes the manifest in exactly one place, and stating the count is the rule.** The file
is the user's, like `docs/`, and for most of this project's life nothing rewrote it after `pnk
init`. The exception is `pnk upgrade --apply`: a **user-invoked** command that writes the KB's own
`pinakes.toml`, **after printing the change**, and only the hunks that apply cleanly — refusing the
whole run rather than merging if any conflicts. It backs the file up first and restores it if the
result does not load. The narrowness is the whole justification, and it is the same shape as the
two sidecar exceptions: an exception with a boundary anyone can check by counting write sites is
cheaper to hold than a general permission.

**One consequence is money, and it was decided rather than overlooked.** A cleanly-applying hunk
inside `[budget]` moves a spending cap like any other hunk — there is no exclusion and no second
flag. What makes that acceptable is the consent path: the cap's old and new values are printed
under their own labelled heading, by the report *and* by `--apply`, before anything is written; the
heading appears exactly when a cap would move; and a raised cap is still only permission — spending
requires a paid entry point invoked deliberately (§5).

**Three validation postures, each deliberate.** Unknown keys are rejected rather than ignored. An
explicit empty string is an error rather than a request for the default — silently substituting one
hides a mistake until it fails somewhere far away. And `[extraction] backend` is validated against
the registered extractors (`extract/__init__.py`) **without importing either**, so an unknown name is
rejected before either extra could matter.

**Rejecting unknown keys makes the manifest forward-incompatible, and one field pays that debt.**
Strictness is worth its cost against typos, but it means a manifest from a *newer* Pinakes fails on
the first key this build has not heard of — and the refusal, though correct, diagnoses a spelling
mistake when the real problem is an out-of-date Pinakes. `[kb] requires_pinakes` states the oldest
version that can read the KB, and is read in a **pre-pass over the raw TOML, before any of the above
runs**. The ordering is not an implementation detail: read afterwards, the parse has already died on
the unknown key and the field is unreachable in the only situation it exists for. It is a floor
only — a KB may be opened by the Pinakes that wrote it or a newer one, never an older one — so there
is no specifier grammar to support and no parsing dependency to take on. Its absence means no floor
declared, never a refusal, because every KB written before it existed lacks it. What it cannot do is
explain a key retroactively: a build without the pre-pass fails on `requires_pinakes` itself, so the
field only ever helps for keys added after it shipped ([KB-UPDATES.md](KB-UPDATES.md)).

Cross-key invariants are checked at *read* time, not at use time, because a manifest that parses but
cannot work is a failure deferred to the least convenient moment: widths must narrow
(`final_k <= fusion_top_k <= candidates_per_source`), `confirm_above_eur <= per_operation_eur` or the
confirmation prompt is unreachable, `overlap < max_tokens`, thresholds must be ordered, and
`fitted_for` is required whenever thresholds are present.

### 2.2 The sidecar — `<file>.pnk.yaml`

Auto-created at first ingest for **every** document, not only linked ones. This is deliberate: the
document ID lives here, and an ID that only appears once a doc is linked is an ID that cannot be
relied upon.

> **Every field and a worked example: [MANIFEST.md](MANIFEST.md#the-sidecar--filepnkyaml).**

**URIs address ULIDs, not names.** A `pnk://research-archive/…` link would break the moment the KB
is used on a machine where that alias doesn't exist, or is renamed — so aliases are accepted as CLI
input and resolved to ULIDs before the sidecar is written. Aliases live only in the manifest's
`[[links.kb]]` (machine-local resolution); they never appear inside a `pnk://` URI. This is the
single decision that makes links survive being shared.

**The sidecar carries no content hash.** Change detection belongs to the index
(`documents.content_hash`, §3), which sync compares against the file on disk. A hash in the sidecar
would dirty two files on every document edit, and would be stale — silently wrong — whenever the
document changed without a sync in between. Nothing in the pairing algorithm (§6.4) reads it:
sidecars pair by adjacency, documents pair by the index's hashes.

**A paid PDF extraction adds `provenance.extraction: {backend, fingerprint, extracted,
content_hash}`** (decision 11) — the one case where sync rewrites an *existing* sidecar rather
than only minting or moving one. `content_hash` here is deliberately narrower than the general
change-detection hash this section already refuses to store: it records the file's hash *at the
moment this specific paid extraction ran*, changes only when a fresh paid extraction does, and exists
solely so a later sync can answer "has this changed since" directly — without depending on whether
`extract/cache.py`'s entry, or any prior local index row, still happens to exist (§6.4's own
retrospective finding: a cache miss on its own proves nothing about whether the content changed — a
`--clear-cache`, a rename, or a first sync after a fresh clone all miss identically, without the file
having changed at all). It must live here rather than only in `index.db` because `pnk sync --rebuild`
discards and rebuilds the index from an empty database (§6.4); a backend recorded only there would be
invisible at the exact moment a rebuild needs it, and a paid extraction would either be silently
re-billed or silently overwritten by whatever free backend the manifest names. The write is additive
(existing `provenance` keys survive) and happens only when a *paid* extraction actually ran, or was
explicitly discarded by `--force` (§6.4) — never for the common, no-money-involved case of an
ordinary free extraction. This write costs the file nothing: the sidecar
is read and written through a **round-trip YAML parser**, so `write()` reconciles the keys Pinakes
owns *into the document that was read* rather than rendering a fresh one — comments, quoting, block
scalars, blank lines and the author's own key order all survive.

**Why a round-trip parser rather than the obvious one.** The choice looks like a dependency
question and is really a data-integrity one. `extra` promises above that unknown keys are preserved,
and under YAML 1.1 that promise was false in a way nobody would notice: `country: NO` was read as
`False` and written back as `false`, `shelf: 0755` as `493`, `duration: 1:30` as `90`. The values
changed, the file still parsed, and nothing failed. YAML 1.2 reads three of them as the strings they visibly
are; `0755` becomes int **755** — not the string, and not PyYAML's octal 493 — and survives on
disk because ruamel preserves the source form. Corruption reduced, not eliminated.
[KB-UPDATES.md](KB-UPDATES.md) §5 — a file a person edits needs a parser that can put it back.

The promise is now **byte-identical**, which is testable in a way "untouched" was not, and it is
bounded by what Pinakes normalises by design (`pnk://self/…` expansion; canonical key ordering on a
*minted* sidecar only), by what the parser normalises (block-sequence and nested-mapping
indentation, which follows the dumper rather than the source), and by what YAML does not carry
(CRLF, a BOM, `---`/`...` markers). One limitation is pinned rather than fixed: a comment is stored
against the construct *preceding* it, so deleting a key or a list entry leaves that comment
attached to whatever takes its place and loses the last one in the block.

**Values must also be JSON-encodable**, because the index stores document metadata as JSON (§3).
That bound is not a new refusal — it is what keeps behaviour the same across the parser change,
which accepts tags the previous one rejected outright.

Why sidecars rather than in-text links: a PDF cannot carry a wikilink without being rewritten, and
mutating source documents breaks the "originals are the truth" contract. One mechanism that works
for every source type beats two mechanisms that each work for half.

**The cost of this choice is friction** — nobody hand-writes YAML per document. Mitigations, all v1:
`pnk link A B --rel cites` authors the sidecar; sync generates the skeleton; `pnk doctor` reports
dangling links, orphaned sidecars and ID collisions.

That authoring command is the **second** exception to "originals are the truth", and it is a
narrower one than the paid extraction above rather than a widening of it. Sync's write is
unattended — it happens on a git hook, so what it may touch is one key of one block. `pnk link`'s is
the opposite: a person naming the file they mean, in the command they typed. Both write only a
sidecar, only the one belonging to the document named. What neither may do is write into the *other*
end of a link: a link is authored forward, and the KB it points at learns of it by reading committed
sidecars (§6.2) — never by having its files edited by a machine it does not run.

Both writes are rename-atomic, which is a claim about *this* write and not about two of them:
`pnk link` takes no lock, so a concurrent write to the same sidecar can lose one side's change.
Atomicity prevents a torn file holding a permanent ULID; it does not order two writers.

The exposure is narrow by construction rather than by luck. A sync rewrites an *existing* sidecar in
exactly two cases — a paid extraction, and the `--force`-plus-free-`--extract` override that clears
the paid claim (§6.4) — and neither is ever automatic: the hooks force the free backend, none passes
`--force`, and the two that run unattended are `--index-only`. So the collision needs one person
running both halves at once, and the answer is to re-run the change that went missing. Taking the
sync lock here would trade that for an interactive command blocked for as long as someone else's
extraction takes to bill.

---

## 3. Storage

One SQLite file, `.pinakes/index.db`, in **WAL mode**. No server, no separate vector store, no daemon.

| Table | Purpose |
|---|---|
| `documents` | id, path (relative, POSIX separators), content_hash, sidecar_hash, mtime, source_type, title, metadata (JSON), state (`active` / `deleted`), extraction_backend, extraction_fingerprint — `sidecar_hash` is what lets §6.4 notice a sidecar-only edit; the two extraction columns are `NULL` for a non-extracted source and otherwise the index's own cache of the sidecar's `provenance.extraction` (§2.2), reseeded from there on a rebuild |
| `chunks` | id, doc_id, ordinal, text, char span, token count, heading path, page_start, page_end — the last two are `NULL` for a non-paged source (markdown/text/code) and 1-indexed otherwise; a chunk may legitimately span two pages (§4.6) |
| `chunks_fts` | FTS5 external-content table over `chunks.text`, kept in sync by triggers — BM25 |
| `embeddings` | chunk_id, vector (float32 BLOB) — the single representation; tier 1 loads it into one contiguous NumPy array at open |
| `links` | src_kb_id, src_doc_id, dst_kb_id, dst_doc_id, rel, origin (`sidecar` = authored here, `reverse-scan` = discovered in a connected KB's sidecars). `src_kb_id` is required: a reverse link's *source* lives in another KB, and without it inbound and outbound edges are indistinguishable |
| `kb_refs` | connected KB id → alias, last resolved path, last scan time |
| `failures` | doc path, stage, error, timestamp — see §6.4 |
| `meta` | schema_version, build_id, embedding model + revision, vector tier, build timestamps |
| `nodes` | id (surrogate), kind (`doc` / `chunk` / `tag` / `heading` / `dir`), key — `UNIQUE (kind, key)`. The five kinds span incompatible id spaces, so identity is `(kind, key)`: a document's ULID, `<doc-ulid>:<ordinal>` for a chunk (**never** `chunks.id`, which has no identity across a rebuild), the tag string, `<doc-ulid>:<heading_path>` for a heading — scoped per document, so no global "Introduction" hub can exist — and the KB-root-relative directory |
| `edges` | src, dst, kind — the derived structural graph (§3.2), indexed on `(src, kind)` and `(dst, kind)` |

**Index schema migrations do not exist.** On `schema_version` mismatch the index refuses to open and
instructs `pnk sync --rebuild`. Because `.pinakes/` is disposable and rebuilds are free, migration
code would be pure liability — this is the payoff of the truth/derived split. `schema_version` is
`3` (the `nodes` and `edges` tables above; `2` was the page and extraction-backend columns); an
index written under any earlier version raises `IndexSchemaError` naming the same rebuild remedy,
never a migration.

### 3.2 The structural graph

Derived at sync, read only by the expansion channel. `pnk links` and `pinakes_links` serve document
neighbours out of `links` and never touch it, which is what makes the graph addable without changing
a released surface (§6.2).

**Why a hub node rather than pairwise edges.** Every shared-value relation — `doc ↔ tag`,
`doc ↔ directory`, `chunk ↔ heading` — goes *through* a node standing for the value. A tag on 30
documents is 30 spokes, not 435 edges: linear rather than O(members²) per value, and one node for
the channel's visited-edge dedup to expand once globally instead of once per encounter. It is also
what makes damping expressible at all, since the divisor is a property of the hub. A hub with fewer
than two members is not minted: expanding it returns only the node that reached it.

| Edge | Connects | Stored as | Weight at read |
|---|---|---|---|
| `membership` | chunk ↔ doc | doc → chunk | 1.0 — transit plumbing, not signal |
| `sibling` | chunk ↔ chunk, adjacent ordinal | lower → higher | 1.0 |
| `parent-child` | chunk ↔ chunk, `heading_path` prefix | parent → child | 1.0 |
| `in-section` | chunk ↔ heading hub | hub → chunk | 1/section-size |
| `co-located` | doc ↔ directory hub | hub → doc | 1/dir-size |
| `shared-tag` | doc ↔ tag hub | hub → doc | 1/tag-degree |
| `authored` | doc ↔ doc | **not stored** — read from `links` | 2.0 |

**Orientation is part of the table, not the reader's choice.** Every edge is one row. A hub spoke
always carries the hub as `src`, which is precisely what makes the damping divisor
`count(*) WHERE src = ? AND kind = ?` well defined — there is no stored `degree`, because that would
be derived state inside derived state. The symmetric kinds are stored once under the rule above and
must be read with `src = ? OR dst = ?`; a `src`-only read silently drops half of every one of them.
A hub kind's two directions are *different questions* — `src = ?` asks who is in this hub, `dst = ?`
asks what this member is in — and are never unioned. Flow between two members of a hub is the
**product of both spokes**, so a big hub damps superlinearly.

**Hierarchy is the one relation that is not hubbed** (APPROACH §3), so it materialises pairwise: an
ancestor heading holding *a* chunks and a descendant holding *d* gives *a·d* rows. On document shapes
with a long lead section that measured 5.8x to 53.5x the chunk count. The alternative — routing it
through the heading hub `in-section` already provides — would change what the relation *means*, so
it is a retrieval question rather than a storage one and belongs to the channel's gate.

**`authored` keeps one home.** It stays in `links` and is resolved to `doc` nodes at read time. A
`doc` node is keyed on the document ULID alone, so only a *local* document has one: a row with a
foreign `src_kb_id` (every reverse-scanned row) or a foreign `dst_kb_id` (an outbound cross-KB link)
resolves to nothing and never enters the channel, in either direction. The kb-id filter is not
redundant with that lookup — two KBs share document ULIDs the moment one is forked.

**Derivation is full, never incremental**, and only over `state = 'active'` documents. Every hub
degree is a property of the whole corpus, so a per-document deriver would have to reproduce the
removals as well as the additions — the same class of bug as a migration, in state a rebuild
regenerates for free. It is also how a soft-deleted document's edges disappear. `--sidecars-only`,
the pre-commit hook, never opens the index and so never derives; `post-commit` and `post-merge` do,
and pay for it whether or not the corpus moved.

**Measured 20260804.** `tests/demo-kb` 192 edges, `tests/partner-kb` 171, each under 2 ms; the
300-document / 106 806-chunk RFC realism corpus 214 608 edges in 1.3 s, adding 31 MB to a 265 MB
index. `pnk sync` prints the per-kind census and its wall clock — every kind, including the ones at
zero, because a kind missing from a report is indistinguishable from a kind that derived nothing.

### 3.1 Vector search: what the tiers actually buy

| Chunks | Strategy | Reality |
|---|---|---|
| < 50k | NumPy exact cosine over one in-process float32 array | **2.25 ms/query** measured at 50k×384 on this laptop, 77 MB resident. Zero extra dependency, exact, nothing to tune or corrupt |
| 50k – ~2M | `sqlite-vec` `vec0` table in the same file | Scanned from disk with SIMD, with int8/binary quantization + rescoring. Keeps RAM bounded and the single-file property intact |
| > ~2M | Documented ceiling; `pnk doctor` says so plainly | Honest advice is "split the KB" — pretending otherwise is how tools lie |

**Correction on the record:** `sqlite-vec` is **not an ANN index**. Verified against upstream
(20260725 13:49): it performs exhaustive KNN over `vec0` tables and its README advertises "fast enough",
not approximate. The tiers therefore buy **bounded memory and disk-resident vectors, not sublinear
search** — latency still grows linearly with corpus size in every tier.

True ANN (faiss / hnswlib / usearch) is deliberately excluded: each means a native dependency and a
second index file outside SQLite, which breaks the single-portable-directory constraint. If linear
scan becomes the binding limit before 2M chunks, the honest fix is splitting the KB, not smuggling
in an ANN index. `sqlite-vec` is also pre-v1 with breaking changes expected — contained today by
the tier being unbuilt and unnameable (below), and once built, by only being reached above 50k
chunks with `vector_tier = "numpy"` supported as a config override.

**What is built:** the NumPy tier only, at *any* corpus size — the `sqlite-vec` tier lands in the
template release (§8). NumPy does not fail above 50k, it just costs linear RAM (≈1.5 GB at 1M chunks × 384
dims); `pnk doctor` warns past the 50k threshold and names the tier that will fix it. Stating this
matters because a table of three tiers reads as three *available* tiers.

**And saying so is not enough, which is the part that had to be fixed.** `[retrieval] vector_tier`
accepted `"sqlite-vec"` for as long as the value existed, and gave the KB the NumPy tier anyway —
`sync` stamped `numpy` into the index's `meta` whatever the manifest said, and `search` never read
the field, so the setting was silent on every surface a user could check. A manifest naming the
tier is now **refused at load time**, naming the tiers that are built; the value returns when the
tier does. This is the same rule `[retrieval] graph_channel` applies to `"ppr"` (§4A) — a setting
the code does not implement is not a setting, and disclosing that in a table does not make it one.

**Environment requirement:** SQLite ≥ 3.35 compiled with FTS5, and — for the `sqlite-vec` tier —
`enable_load_extension` available. uv-managed CPython 3.13 satisfies both (verified 20260725 13:49: SQLite
3.53.1, FTS5 present, extension loading permitted); some system Pythons are built without them, so
`pnk doctor` probes both and reports a precise remedy rather than failing at query time.

---

## 4. Retrieval

**Traversal is bounded four ways, and the bounds are not interchangeable.** Depth counts **logical
hops**, not physical edges — composition through a hub is one hop, because counting physically would
strand the highest-trust authored edges beyond any usable depth. `[retrieval] adjacent_k` caps
fan-out per expansion and is applied **after** ranking, so a cap never selects by whatever order a
provider happened to return. The response carries its own two caps — a row count and a token
budget — reported **independently**, because "too many neighbours" and "too much text" have
different remedies and a single flag would leave a caller guessing. Every bound is clamped
server-side; a caller asking for more gets less and is told so, and a gate drives the shipped core
at absurd values on every commit to keep that true.

A neighbour that was found and **not** expanded comes back on a `frontier` with one of five
reasons — `terminal`, `depth`, `fanout`, `rows`, `tokens` — in that precedence. Five rather than one
because they mean different things to whoever asked: `depth` and `fanout` invite a retry with
different arguments, `rows` and `tokens` invite a narrower request, and `terminal` invites none at
all. A caller told `fanout` about a terminal neighbour retries a hop that can never succeed.

### 4.1 The free pipeline (every query, €0)

```
query
 └─ metadata filter        (SQL WHERE: tags, path prefix, mtime range, source_type)
 └─ parallel:
      ├─ BM25 via FTS5     → candidates_per_source (50)
      └─ vector search     → candidates_per_source (50)
 └─ Reciprocal Rank Fusion (k=60) → fusion_top_k (20)
 └─ local cross-encoder rerank (optional, on by default) → final_k (8)
 └─ cited passages + doc IDs + confidence signal
      citation: path:char_start-char_end, or path:pN / path:pN-M for a paged source
      plus the stale_extraction marker a paid-fingerprint mismatch sets (§4.4)
```

**A paged citation carries an explicit `p`, and that is load-bearing.** `report.pdf:12-480` already
means character offsets, so a bare `report.pdf:12-13` would be a page range and a character range in
one syntax, told apart only by knowing the file — a citation that can be misread is worse than one
that is ugly. Non-paged sources are unchanged.

Each stage's width is a distinct manifest field (§2.1); a single `top_k` would be ambiguous across
three different cut-offs. The date filter is the document's **mtime**: every document has one,
whereas a sidecar's `created` is optional, and a filter that silently skipped documents lacking an
optional field would be worse than no filter. Vector candidates with a non-positive cosine are
dropped rather than padded into fusion — no shared direction is not weak evidence, it is none.

No network at query time **once model weights are cached locally**; first use downloads them (§4.5).
Embedding a corpus is free, so re-indexing is free, so **there is no cost pressure against improving
chunking or swapping models** — a property worth protecting, and the main reason local embeddings
were the right call.

### 4.2 Escalation — "free path first"

Below a confidence threshold the system does **not** silently spend money:

- **on MCP**: returns the passages *plus* `confidence` and a suggested next search. The calling agent
  decides — its reasoning is already paid for.
- **on CLI**: returns retrieval-only and prints how to escalate (`pnk ask --deep`).

**The signal is a calibrated heuristic and is labelled as one.** Cross-encoder scores are not
comparable across queries, so an absolute threshold is meaningless; thresholds are fitted per
template against the golden set and stored in the manifest as `[retrieval.confidence]` (§2.1). Where
that block is absent the system reports `confidence: unknown` rather than inventing a number — and
because the block is model-specific, changing the embedding or reranker invalidates it, which
`pnk doctor` reports alongside the §4.4 coherence check.

Query-term coverage is used only as a **tiebreak, never a veto** — as a gate it would penalise
exactly the paraphrase queries vector search exists to serve. The eval harness reports
**false-abstain** and **false-confidence** rates so the heuristic's cost is measured rather than
assumed.

### 4.3 Multi-hop, without paying for it

Multi-hop is delivered by **making the tools composable rather than by building an agent**.
`pinakes_search` → `pinakes_get` → `pinakes_search` is a plan-retrieve-read-refine loop, and Claude
Code already runs it in its own context on the caller's existing subscription.

Scope, stated precisely: `pinakes_search` → `pinakes_get` walks **within one KB**. Crossing into
another takes `pinakes_links`, because a link is the only thing that knows where the other KB is —
and a cross-KB neighbour is terminal, since this KB cannot vouch for what lies beyond it (§6.2).

`pnk ask --deep` exists for CLI and cron use, where no agent is present. It runs a bounded version of
the same loop with its own API key under the budget ledger (§5). Same tools, same evidence contract —
only the driver differs. That keeps the paid path thin enough not to rot.

### 4.4 Model/index coherence

Embeddings are meaningless across models. The manifest records provider, model and revision; if
`.pinakes/index.db` was built with anything else, queries **refuse to run** and instruct a rebuild. A
KB that silently returns garbage after a model upgrade is worse than one that stops.

**Per-document extraction coherence (decision 13).** A PDF's *extractor* can drift the same
way an embedding model can: `pypdfium2` upgrades its running-head threshold, `claude-vision`'s prompt
or schema changes. Every query re-derives each distinct recorded `(extraction_backend,
extraction_fingerprint)` pair's *current* fingerprint and compares — from a dict of version strings
and constants declared beside each registry entry, never by importing the backend itself, so this
check costs nothing to run on every query, including ones touching no paid document at all. The two
outcomes are asymmetric, on purpose:

- A mismatch on a **free** backend refuses the whole query, naming the stale paths — the text can be
  silently wrong (a running-head threshold fix can change what counts as body text) and re-extracting
  costs nothing, so there is no reason to serve it.
- A mismatch on a **paid** backend never refuses. The already-paid text is still correct, merely
  older; every affected `Passage` is marked `stale_extraction` (the backend name) instead, and `pnk
  doctor` reports it as a WARN. Refusing a query over documents someone already paid to extract,
  because a prompt version ticked over, would make the paid path actively hostile to use.

An **unrecognised** backend name (a future version's KB, or an extra that is not installed) is
skipped entirely: it can be neither computed nor compared, and an otherwise-healthy KB must not
refuse a query over that alone.

### 4.5 Embedding backends, install, and model weights

`sentence-transformers` is the default backend: widest model selection, best quality ceiling, most
documentation. It pulls torch (~2GB), so **the documented install line includes the extra**:

```
uv add "pinakes[st]"                     # standard install — default backend
uv add "pinakes[light]"                  # fastembed (ONNX, ~100MB, no torch)
uv add "pinakes[pdf]"                    # free PDF extraction (pypdfium2)
uv add "pinakes[claude]"                 # + the opt-in paid Claude-vision extractor
uv add pinakes                           # core only: parsing, FTS5, storage, MCP, CLI
uvx --from "pinakes[st]" pnk serve       # zero-install MCP server
```

A core-only install cannot embed. That is a supported state, not a broken one: any command needing
embeddings fails immediately with the exact extra to install, and `pnk doctor` reports it. CI's
`check` job is a three-leg matrix over `[light]`, `[light,pdf]` and `[light,pdf,claude]` — each is a
supported install state and each must pass on its own; a 2GB torch download per job stays untenable
regardless, which is why `[st]` is never one of the three.

`[pdf]` (pypdfium2, BSD-3-Clause/Apache-2.0) and `[claude]` (the Anthropic SDK — named for the
vendor, because an extra whose name hid which client it installs would hide that from whoever reads
the manifest) are the extractor backends (§2.1's `[extraction]`). **`[claude]` requires
`[pdf]`**: the paid path slices PDFs, pre-checks the free text yield and audits its output against
the native layer, all through pypdfium2 — installing it without `[pdf]` would be a backend that
cannot run its own pre-checks.

Both extras also provide the default reranker (§2.1): `BAAI/bge-reranker-base` exists under the same
id in `sentence-transformers` and in fastembed's registry (~1.04 GB of weights). Weights are a
*model download*, not an install cost, so the extras stay light — but CI must **cache `HF_HOME`**
(keyed on the model ids + revisions in the demo KB's manifest) so the ~1.4 GB of embedding + reranker
weights download once per cache key, not once per job. Without that cache the reranker would recreate
the very per-job download problem the extras split exists to avoid.

Model weights go to the **shared Hugging Face cache** (`HF_HOME`), never `.pinakes/cache/`, so N KBs
on a machine share one copy. One backend needs help to honour that: fastembed left alone caches to
`$TMPDIR/fastembed_cache`, not the HF cache (verified upstream, 20260725 13:49) — so the fastembed backend
always passes an explicit cache directory under `HF_HOME`, making the shared-cache statement true by
construction on both backends rather than an assumption that silently fails on `[light]`. `.pinakes/cache/` holds only KB-derived artifacts. `pnk doctor` reports
whether the configured model is present locally, and `--offline` fails fast instead of reaching out.

### 4.6 Chunking and tokens

Chunks are paragraphs under a heading, and **the heading line is part of the first chunk beneath
it** — not consumed as pure structure. **The document's source type is what dispatches, and
`[chunking] strategy` still does not control it** — that key is validated at parse time and never
read again.

`markdown` gets ATX headings. `text` gets a **numbered outline grammar, opt-in behind
`[chunking] headings = "numbered"`** and off by default; `code` and `pdf` take the plain-text path
and record no `heading_path` at all. For three releases every type but `markdown` did, so a `.txt`
corpus was chunked without structure however rigidly it was sectioned — and **nothing failed to
match, because nothing was tried**. `pnk doctor`'s heading-coverage check exists because that was
silent until a 106 806-chunk corpus indexed with zero heading paths and no warning.

**The numbered grammar's design principle is that it refuses rather than guesses.** `1.` at line
start is also an ordered list, so acceptance is decided over the *whole document*: the numbers must
form a valid outline walk, and **if the walk fails anywhere the document yields no headings at
all**, falling back to exactly the pre-grammar behaviour. A misread document therefore loses nothing
it had, where a partial labelling would have invented structure that was never there. This is the
same judgement the title decision reached — a visibly absent value beats a plausible wrong one,
because a wrong one is harder to notice. The lexical index only sees chunk text, so a word appearing
only in a heading would otherwise be unsearchable, and a passage quoted back to the user reads
better carrying the heading it belongs to. `heading_path` records the hierarchy separately, and it is
worth being exact about what consumes it, because it is not retrieval: **citations**
(`path:locator (heading > path)`), the **`in-section`, `parent` and `child` edges** derived from it,
and the passage payload returned over the CLI and MCP surfaces. **Nothing filters or ranks on it** —
FTS5 indexes `chunks.text` and embeddings are computed over `chunks.text`, so a chunk's recall is
unaffected by whether it carries one. That is the point of putting the heading line *into* the
chunk: the words stay searchable either way, and `heading_path` buys attribution and structure
rather than reach.

**The span invariant, stated over the *indexed* text** (amended 20260728 16:40 — I5 shipped the
behaviour without this edit). Every chunk satisfies:

```
chunk.text == indexed_text[char_start:char_end]
```

where `indexed_text` is **the decoded file** for a text source, and **the pinned extraction** for a
PDF — pinned by `documents.extraction_fingerprint` (§4.4), because a PDF's characters exist only
once an extractor has produced them, and a different extractor produces different offsets.

The consequence differs by source type, and the difference is the point:

- **Text sources:** a citation locates the passage *exactly in the original file*, byte for byte.
- **PDFs:** it does **not**, and cannot. The offsets address the extraction, not the file. What a PDF
  citation locates is a **page** (`page_start`/`page_end`, below). An earlier draft of this section
  claimed exact location in the original file for every source; that claim is false for PDFs and is
  replaced here.

`max_tokens` is counted with **the embedding model's own tokenizer**, and validated at sync against
the model's `max_seq_length` minus special tokens (bge-small-en-v1.5: 512 → 510). A manifest asking
for more is a hard error, not a silent truncation — a truncated chunk is a chunk whose tail is
unsearchable, and nothing in the output would reveal it. Chunks that cannot be encoded whole are
split, never trimmed.

**PDF chunks additionally carry `page_start`/`page_end`**, a 1-indexed lookup against the
extractor's own per-page character spans — no separate page-aware splitting algorithm, since the
existing paragraph/blank-line block detection already produces a block that straddles a page
boundary whenever the free path's own hyphenation-joining joined a word across one with no
separator; a chunk spanning two pages records both rather than picking one. `heading_path` is always
`None` for a PDF chunk — a PDF has pages, not headings, and stuffing "p. 7" into a free-text filter
column is the opposite of what a structured `page_start` is for.

### 4.7 Server boundary and what publishing a KB exposes

The MCP server serves **only the KBs named in its own configuration**. Tool arguments select among
those by alias or ULID; there is no argument that accepts a filesystem path, and `pinakes_get` takes
a document ULID resolved through the index, never a path. An agent talking to the server therefore
cannot reach outside the KBs it was pointed at — worth stating explicitly, because the caller is an
LLM acting on untrusted document content.

Retrieved document text is untrusted input, not instruction: passages are returned to the caller
inside a clearly delimited evidence field, and `--deep` synthesis prompts treat them as data. A KB
whose documents contain "ignore previous instructions" is a KB, not an exploit.

Publishing a KB repo publishes `docs/` **and every sidecar** — including `provenance.source` URLs,
tags and titles, which routinely carry more signal than people expect. `pnk init` ships a
`.gitignore` covering `.pinakes/` (so the ledger and index never leave the machine), and the docs
state the exposure plainly. The engine repo itself contains no real KB: only the two synthetic
corpora (§7).

**Publishing a KB also publishes the ULIDs and relations of every KB it links to.** A sidecar's
`links[]` carries the partner's KB ULID and the relation, and `[[links.kb]]` carries its ULID and
alias — so a public KB names its private partners, in a form that is stable and correlatable across
repositories. The ULID is the whole point (§2.2) and cannot be elided, so the exposure is stated
rather than mitigated: link *out of* a public KB deliberately. `path` is the one part that is
machine-local rather than published-by-design, which is why an absolute one is a `pnk doctor` warning
(MANIFEST).

**Page provenance and the stale-extraction marker reach both surfaces, or neither counts.**
`pinakes_search` results carry `page_start`/`page_end` beside the rendered citation, `pinakes_get`
accepts a page range and marks boundaries with a `[page N]` line, and both carry the
`stale_extraction` marker §4.4 sets on a paid-fingerprint mismatch. Shipping any of this on the CLI
alone would recreate the divergence v0.1 pass 2 removed for filters — on the surface §1 calls
primary, in the release whose subject is page-citable PDFs. The marker in particular reached
*neither* surface before this: it was computed in `search.py` and dropped by both renderers, so
"and not only the CLI" understated the gap by half.

A `get` cannot serve a PDF's bytes, so it serves the **extraction cache** entry the index was built
from — never a fresh extraction. A free re-extraction would return text the index does not contain;
a paid one would spend money inside a read-only tool call. A swept entry is an error naming
`pnk sync`, which is the honest answer rather than either.

---

## 5. Cost control

**The budget system ships in the same release as the first thing that can spend**, which is the
honest ordering — and the first spender is no longer `pnk ask --deep`. `plans/20260727_1543-v0.2.md` decision 2 moved that role to the **opt-in Claude-vision PDF
extractor**, dragging the whole budget machinery earlier with it. Field definitions and defaults are
in [MANIFEST](MANIFEST.md#budget); whether any of it is wired up yet is in
[STATUS](STATUS.md#the-surface-you-can-use-today).

| Control | Mechanism |
|---|---|
| **Estimate before running** | Price a *worst case* locally from a versioned table, print it, and prompt above **`confirm_above_eur`** — a separate, lower field than the hard caps. Confirming at the same number that aborts would make the prompt unreachable, so the two thresholds are evaluated independently: a request sitting exactly at a cap is still allowed, and still asked about |
| **Hard caps, checked before the call** | **Pre-call reservation.** Actual cost is only known from the response, so the accountant reserves worst case first. If `spent + reserved` exceeds any cap, **the call is never made** — a real ceiling, at the price of slight over-reservation, reconciled to true usage afterwards |
| **Three windows, not one** | `per_operation_eur` bounds one invocation; `daily_eur` and `monthly_eur` bound *sequences* of them. A per-operation cap alone is no protection against a hook-driven KB syncing thirty times a day, which is the shape this project actually has |
| **What "operation" means** | One user-facing invocation — a whole `pnk sync` or `pnk ask --deep`, not one API call. Both are loops, so the cap is a *running total* across every call made; the loop halts when the next reservation would breach it. A per-call cap would let an N-step loop spend N× the stated limit |
| **The whole document is checked first** | Per-call reservation alone bounds each call and nothing else — a document that will certainly breach a window by call 15 is refused at call 0, with every blocked window named at once and the exact manifest edit that would admit the run. Discovering the real ceiling by raising one cap at a time is the failure this prevents |
| **Rolling ledger** | `.pinakes/ledger.jsonl`, append-only. Windows computed in `[budget] timezone`. Each line is a single sub-4KB `O_APPEND` write, atomic on POSIX, so concurrent processes cannot interleave a record |
| **Visibility** | `pnk budget` shows spend by day/month/operation, each window with the rate and price date behind its total. `pnk budget --resolve <call_id> --actual <eur>` closes a call whose outcome is unknown — by *appending* a reconciliation, never editing. Real per-KB cost data, not vibes |

**A request is the unit of estimation** — for the paid extractor, a fixed-size page slice, never a
whole document and never a single page. The unit matters: a whole-document request makes input
quadratic and stops fitting the context window past a few hundred pages, while a per-page request
throws away the neighbouring context a table or a sentence spanning a page break needs. Because the
slice size is part of what produced a given extraction's text, it is a semantic constant hashed into
the extractor's request-shape version, not a tuning knob.

**How a reservation and its outcome aggregate.** A reservation/reconciliation pair is *one* record,
attributed to the **reservation's** timestamp — a call reserved at 23:59:58 and reconciled at
00:00:03 belongs entirely to the first day, and attribution never moves afterwards. The
reconciliation *supersedes* the reserved amount rather than adding to it; an unreconciled
reservation counts at its reserved amount, so an in-flight or crashed call consumes headroom instead
of vanishing; and a *void* record closes a reservation at zero, the one escape hatch for a call that
never billed. Without that last one, a handful of transient failures would permanently consume
budget with no way to release it.

**The completeness audit reports; it never re-extracts.** After a paid extraction, each page's
`word_coverage` against the native text layer is computed and recorded, and pages scoring below
their own document's median are named by `path:page` — in the sync report, where the user has just
paid, and in `pnk doctor`, which reads them back from the cache entry rather than re-running
anything. Pages with no usable native layer, and pages whose text holds no significant words at
all, are **exempt and reported as exempt with their denominator**: there is nothing to measure, and
that is not the same as measuring zero — nor, in the other direction, the same as a pass.

**`on_exceed` is a corpus-level rule, never a page-level one.** `abort` (the default) makes a run
stopped by a cap a failure: the user asked for the corpus and the corpus is not indexed. `partial`
makes it a success: they asked for whatever fit inside the cap, and got it — every document that
completed keeps its entry, because each is its own transaction. Either way the run **stops at the
first breach** rather than trying every remaining document, since a cap does not un-breach itself
and continuing produces N copies of one fact.

What `partial` never means is part of a *document*. A half-extracted document writes no cache entry
and lands in `failures` whatever `on_exceed` says — permission to index fewer documents is not
permission to index part of one, which would be the silent truncation §4.6 exists to prevent.

**Money is `Decimal` end to end, quantised exactly once**, when a record is written to the ledger. A
cap compared against a float is not a cap: `0.05` has no exact binary representation, so the ceiling
enforced would differ from the one configured by an amount nobody can predict or explain.

**The ledger stores no query text and no document content** — timestamp, `operation_id`, `call_id`,
record kind, operation kind, model, token counts, `cost_usd`, the `usd_per_eur` rate it was priced
at, the price table's `as_of`, KB id, nothing more. It is diagnostics, not a transcript, and must
never become an accidental log of what you asked.

**Cost is recorded in USD with its conversion provenance, never as a bare number**; EUR is computed
at read time. A line saying only `cost: 0.043` is unreadable a month later — neither the currency
nor the rate that produced it is recoverable — and the rate is exactly the input that drifts.

**Two identifiers, because one word covered two things.** `operation_id` is one invocation, the unit
`per_operation_eur` bounds; `call_id` is one API call, the unit a reservation/outcome pair keys on
and what a cache entry joins against. Collapsing them made `per_operation_eur` ambiguous between
"one sync" and "one call", a difference of a factor of forty.

**A reservation with neither a reconciliation nor a void is `unknown outcome`** — a timeout may or
may not have billed. It counts at its reserved amount rather than being dropped or zeroed, which is
why `pnk budget` surfaces those records prominently and `pnk doctor` warns once their total passes a
quarter of a window: without a documented way back, a handful of them makes a KB unusable.

Pricing lives in a data file with an explicit `as_of` date, shipped as package data so an installed
wheel and a source checkout price identically. `pnk doctor` warns when it is stale, and estimation
*refuses* past `max_price_age_days` rather than quietly using numbers that may no longer be true.
Staleness is deliberately **not** a CI gate: a wall-clock check would fail a quiet weekend with no
code change at all.

---

## 6. Blueprints, connections and freshness

### 6.1 Templates

```
templates/research-papers/
├── template.toml       # declares the template's OWN version — independent of the package version
├── pinakes.toml.j2     # manifest defaults: chunking, filters, retrieval tuning, calibration
├── prompts/            # synthesis prompts for --deep
├── eval/questions.yaml # golden questions shipped with the template
└── README.md
```

`pnk init research --template research-papers` stamps out a new KB; the manifest records
`research-papers@1.2`. Templates version independently of `pinakes` itself, so a package upgrade does
not implicitly change a KB's blueprint.

`pnk upgrade` **diffs** the KB's recorded template version against the installed one and prints a
**template diff** — never a *migration*, a word this design reserves for index schema and
deliberately does not reuse here, because the two obey opposite rules and every reader who has to be
told they are different has already paid the cost. **Nothing is ever applied automatically**, and
that is the load-bearing word rather than *applied*: `--apply` exists, and it is a separate,
explicit invocation that prints the whole change first and refuses outright if any part of it does
not fit. A template bump that silently re-chunks someone's corpus is a data-loss event in slow
motion; one the user read and asked for is an upgrade.

**That comparison needs the old version's *content*, and a manifest records only a reference.** A
wheel ships one copy of each template — the current one — so for most of this project's life the
sentence above described something unimplementable: at runtime, the content the recorded reference
named did not exist. The only diff available without it is *the KB's own manifest against a fresh
render*, and that cannot tell a template change from a user's deliberate tuning; reporting the
second as the first is the failure this design refuses everywhere else. **The fix is an archive, not
a cleverer diff.** A template's released versions are frozen inside the wheel, so both sides of the
comparison are generated and neither is the user's file — a value they tuned that the template
renders cancels, and a literal they edited never enters either side. A version whose content was
never archived is reported as *cannot compare*, rather than diffed from a reconstructed base: the
reconstruction is what would make the report wrong in the one direction nobody can check.

**This is one of four drift axes, and the last to get a mechanism.** An index, an embedding model
and a PDF extractor each drift detectably and are remedied by rebuilding derived state, which is
free. A manifest and a template drift *silently*, and the remedy touches a file the user owns — so
it cannot borrow the same shape. What is built therefore reports first and writes only on request,
and the write is bounded by the report: nothing reaches the file that was not printed.
[KB-UPDATES.md](KB-UPDATES.md) works the problem through and records what has been decided.

### 6.2 Cross-KB links

Addressing is `pnk://<kb-ulid>/<doc-ulid>` (§2.2). Aliases in `[[links.kb]]` map a KB ULID to a local
path; resolution is machine-local, the link itself is not.

Forward traversal reads this KB's own `links` table. **Reverse links are computed by scanning the
other KB's committed sidecars** at sync time — *not* its index, which is gitignored and simply
absent in a fresh clone, and which could not be read without holding a second KB's lock. Results
are cached in `kb_refs` + `links` with `origin = 'reverse-scan'`.

**The partner's `pinakes.toml` is read too, and must be.** A sidecar does not carry the KB it
belongs to, so sidecars alone cannot supply `links.src_kb_id`, cannot key `kb_refs.kb_id`, and
cannot even locate the sidecars — which live under the partner's own `[sources] roots` and need not
be `docs/`. Three rules follow. `src_kb_id` comes from the partner's **own `[kb] id`**, never from
the `[[links.kb]] id` this manifest declared: when they disagree nothing is scanned, because
trusting the declaration would file one KB's links under another's alias and trusting the partner
would silently redirect a link the local author wrote deliberately. Sidecars are enumerated from the
partner's `[sources]`. And they are read with **the partner's id as owner**, so a partner's
`pnk://self/<doc>` resolves to the partner — reusing the local one would mint inbound edges the
partner never wrote, which is the retargeting defect §2.2's `self` expansion exists to prevent.

**Only links targeting this KB are kept.** A partner's link to a third KB is read and discarded: a
partial view of someone else's graph is the silently-incomplete answer this section refuses.

**Replacing a partner's rows is all-or-nothing, and only after a complete walk.** The delete is
scoped to that `src_kb_id` *and* to `origin = 'reverse-scan'` — both, because a manifest may list
itself, and then an origin-blind delete would remove the authored rows the insert's
`ON CONFLICT DO NOTHING` exists to protect. If any sidecar failed to parse mid-walk, nothing is
written at all: the previously known rows are still true, and a half-read partner would otherwise
lose edges that never went away. A failed walk does not stamp `last_scan` either, or the retry would
be suppressed for a full window on the strength of the failure.

**A KB dropped from `[[links.kb]]` has its inbound rows and `kb_refs` entry removed.** Nothing else
would ever remove them — the per-partner delete only fires for a KB being scanned, and a delisted
one never is.

Failure modes are explicit rather than silent — an unresolvable KB id, an unreachable path, a
sidecar that will not parse, or a `pnk://` target whose document is absent here. Each is reported
with a remedy, each lets the scan continue to the next KB, and **none of them fails the sync**:
`pnk sync` runs on three git hooks, and a partner that is merely not on this machine must not block
every commit. A missing target is still recorded as an edge — dropping it would hide a real claim
the other KB is making — and traversal returns it as `unresolved` with the reason attached.

**The honest limitation:** without fan-out query, a question must *start* in one KB and travel via
links. If no link exists, the connection is invisible. Link coverage is the ceiling on cross-KB
answers, so `pnk doctor` reports it (linked docs / total docs) — the ceiling is visible rather than
mysterious. If it bites, federated query is the v2 answer.

### 6.3 Freshness

`pnk sync` is the primitive: walk sources, compare content hashes, re-process only what changed.

**The cross-KB scan is bounded by a freshness window**, because `pnk sync` runs on `post-commit` and
`post-merge`: a partner with a thousand sidecars costs a thousand reads, and paying that on every
commit to learn an inbound link an hour sooner is the wrong trade. `kb_refs.last_scan` records when
each partner was last read; `--scan-links` ignores the window entirely. The window is a code
constant rather than a manifest key — "how stale may a cross-KB link be" is a question about this
engine's cost model, not about a KB. Uncertainty always resolves to *stale*: no stamp, an
unparseable stamp, or a stamp **in the future** all force a re-read, the last because a clock that
moved backwards would otherwise suppress every scan until real time caught up, with no symptom.

`--sidecars-only` does not scan — reverse rows are index rows and that mode never opens the index —
and `--sidecars-only --scan-links` together is refused rather than silently resolved, since
honouring both would mean one of the two flags doing nothing with no way to tell which.

`pnk sync --rebuild` rebuilds **`index.db` only** — `ledger.jsonl` survives, always. Free,
deterministic, cron-safe. A rebuild that wiped `.pinakes/` wholesale would destroy the spend history
that §5's rolling budget is computed from, turning a routine maintenance command into a silent
budget reset. Only `cache/` is optionally cleared, behind `--clear-cache`.

**The extraction cache** (I4) sits between `pnk sync` and every `Extractor`: one JSON file per
`<content_hash>-<fingerprint>.json` under `.pinakes/cache/extract/`, storing the whole
`ExtractedText` a call returns — text, page spans, per-page provenance — plus `operation_id`/
`call_ids`, the future join key to `ledger.jsonl` (`null` until a paid backend exists to populate
them, I6b/I7c). A hit skips the extractor entirely — `--rebuild` benefits the most, since it
re-processes every document but never re-pays for one whose content and backend fingerprint are
unchanged. Invalidation is by key alone: an edited document gets a new `content_hash`; a backend
version bump or a re-fitted threshold changes its `fingerprint` (`extract.fingerprint()`, §7.1).
Any entry that cannot be read — missing, truncated, an unrecognised schema — is a miss, never a
crash: a cache that could fail a correctly-configured sync would be worse than no cache at all.

After a **fully successful** sync (no failures, and — for `--rebuild` — only once the atomic swap
has landed), entries whose `content_hash` matches no active document are swept, except entries a
paid backend wrote, which are only ever reported, never deleted automatically: a soft-deleted or
un-sidecarred document is not an "active document," and silently sweeping away an extraction that
was paid for is the one mistake this cache must not make. `pnk doctor` reports entry count, bytes,
`orphans/entries`, and paid orphans as their own line.

`pnk sync --clear-cache` empties `cache/extract/` entirely — paid or free, active or orphaned —
after confirming: it prints the entry count and bytes about to go and requires a `y`; `--yes` skips
that prompt for cron use. **`--yes` does not authorise destroying entries a paid backend wrote** —
that needs the explicit `--clear-cache=paid`, which no hook and no generated workflow writes.
Otherwise a cron line carrying `--yes` for freshness would also throw away paid extractions
unattended, which is precisely what this guarantee claims to forbid. `ledger.jsonl` is never
touched, the same guarantee `--rebuild` already gives. **The prompt prices what it is about to
destroy**, in euros, joined from the ledger on each entry's own `call_ids` — not on its
`operation_id`, which prices a whole *run* and would attribute every document's spend to each of
them. A count answers "how many"; only the euros answer "is this worth re-paying for", which is the
question someone about to type `y` actually has.

**`--force` overrules exactly two refusals**, both of them refusals to spend or discard that a user
may legitimately overrule: paying to extract a PDF whose free text layer is already healthy, and —
**only together with an explicit free `--extract`** — letting a free run overwrite a paid
extraction (§6.4). That qualifier is part of the scope rather than a detail of the rule it names:
without it, a bare `pnk sync --force` on a KB whose manifest names the free backend destroys every
paid extraction it has. `--force` never widens `per_operation_eur`, `daily_eur`, `monthly_eur`, the
stale-price refusal, the missing-floor refusal, or the no-terminal abort — a flag that can widen a
hard cap is not a hard cap. Selective removal of paid orphans alone lands with the ledger reader that can price them
(I7c) — building it sooner would mean pricing entries against a ledger that does not exist yet.

`pnk install-hooks` writes **three** hooks, split by what each may touch:

- **`pre-commit`** runs `pnk sync --sidecars-only --stage`: for every *staged* new document it mints
  the ULID, writes the sidecar, and `git add`s it — so a document and its ID land in the **same
  commit**, never one behind. Only sidecars of staged documents are touched, which keeps partial
  staging (`git add -p`) honest, and `git commit --no-verify` is the documented escape hatch. This is
  the one hook allowed to write into `docs/`; it writes nothing else.
- **`post-commit` + `post-merge`** run `pnk sync --index-only --quiet`: index work only. Because sidecars were
  authored at pre-commit time, this stage never dirties the tree it just committed — a post-commit
  hook that created sidecars would leave every document commit trailing an untracked `.pnk.yaml`,
  demanding a second commit forever.

`pnk sync` gains `--extract=BACKEND`, overriding `[extraction] backend` for that one run; the name is
validated against the registered extractors the same way the manifest is — no importing either.

`pnk sync --estimate-only` builds the **real** first-slice request and measures it with the
vendor's own token counter, then extrapolates and exits without generating anything. It is
therefore **a network call, not an offline estimate** — it needs a key, and both `--help` and the
CLI reference say so, because "estimate" reads as free. It tightens the reservation constant at a
fraction of a real run's cost, which is what makes it the documented first step before paying for
one. It refuses on a free backend rather than reporting €0.00: "nothing to estimate" and "this run
would cost nothing" are different answers.

`pnk init --ci` drops a GitHub Actions workflow that syncs and caches `.pinakes/`. No daemon.

**All four machine-driven callers — the three hooks and that workflow — write
`pnk sync --extract=pypdfium2` explicitly, forcing the free backend regardless of the manifest**,
print one line saying so at write time, and carry the same line as a comment in what they generate.
All four are non-interactive, so on a KB configured for a paid backend the alternatives are both
wrong: without the flag there is no terminal to answer a `confirm_above_eur` prompt from and every
commit aborts; with a `--yes` in the hook, every commit spends afresh under a fresh per-operation
allowance. Forcing the free backend indexes a scanned PDF's (empty) free extraction honestly **and
recoverably** — §6.4's backend-drift rule leaves that document stale until a paid run picks it up,
rather than skipped forever behind a content hash that never changes again. Paid extraction stays a
deliberate human invocation, and `pnk doctor` reports the combination so the split is visible rather
than surprising.

Because freshness is git-triggered, **a KB is normally a git repo** — an assumption of the design,
not an accident. A loose folder still works via manual or cron `pnk sync`, and `pnk doctor` reports
that it is not hook-managed.

### 6.4 Sync semantics (the part that silently corrupts a KB if left vague)

Pairing is a **two-phase, set-wise** operation, not a per-file decision: phase 1 walks every source
file and every sidecar to build the full before/after picture; phase 2 resolves pairings against that
whole picture. Rename and duplicate detection are impossible file-by-file — you cannot know a path
was *renamed* rather than deleted until you have seen every other file.

Phase-2 rules, applied in order:

| Case | Action |
|---|---|
| Path and hash unchanged | Skip |
| Path unchanged, hash changed | Re-chunk and re-embed; **keep the ID** |
| Path gone, exactly one new path has the same hash | Treat as a **rename**: keep the ID, re-pair the sidecar, report it |
| Path gone, *several* new paths share that hash (duplicate content) | Ambiguous — do not guess. Prefer a candidate whose adjacent sidecar already carries the old ID; failing that, mint fresh IDs for all of them and report the ambiguity. Silently attaching an ID to the wrong duplicate would silently redirect every inbound link |
| New path with an adjacent sidecar | Adopt its ID after a uniqueness check |
| New path, no sidecar | Mint a ULID, write the sidecar |
| New path, a sidecar that **will not parse** | **Never mint over it.** The walk drops an unreadable sidecar so one bad file cannot stop the others — which makes the document *look* like the row above, while the file still holds its permanent ULID. A `failures` row; the file is left byte-identical and the document is not indexed. The walk had to swallow the parse error to keep walking, so the mint path **re-reads that one file to name it** — "already exists" alone reads like a Pinakes bug and says nothing about the character the user mistyped. Distinguishing these two rows is the whole point: writing a freshly minted id over a sidecar replaces a permanent ULID with a different one, and every inbound link points at the old one with no migration by design |
| An **indexed** document's sidecar stops parsing, content unchanged | The same `failures` row, and the run continues. Pairing yields `RefreshMetadata` here rather than `Mint`, and that branch re-reads the sidecar too — so the three ways one broken file can be met (`Mint`, `Reembed`, `RefreshMetadata`) report it identically instead of three different ways |
| Path gone, no hash match | Mark `state = deleted` (soft). **Leave the sidecar on disk** and report it as orphaned |
| Same ID in two sidecars | Hard error naming both paths. Never silently renumber — that would break every inbound link |
| Recorded extraction is **free**, this run's effective backend is **paid** | Stale regardless of hash — re-extract and re-embed |
| Recorded extraction is **paid**, effective backend is **free**, hash **unchanged** | Never re-extracted — not by a hook, not by `--rebuild`, not by a rename, not by an explicit free `--extract`. Say once which paths were protected. Whether the text itself is reused from this same sync's connection, the old index a rebuild is replacing, or `extract/cache.py`, "unchanged" is decided once, from the sidecar's own recorded content_hash — never from any of those three happening to still hold an answer |
| Recorded extraction is **paid**, effective backend is **free**, hash **changed** | Neither a silent Skip nor a silent overwrite: a `failures` row naming the path, remedy pointing at the paid `--extract` (decision 14). Under `--rebuild` specifically, the *old* (now stale) text is carried forward rather than the document vanishing from the rebuilt index — matching what a normal sync already leaves searchable in the identical situation |
| Recorded extraction is **paid**, hash **unchanged**, but the extracted text is not available anywhere on this machine | An honest, distinct failure (`PaidExtractionUnavailableError`) — never conflated with "content changed" above. The common case is the first sync after cloning a KB whose paid PDFs were extracted elsewhere: no cache, no prior local index, but the file itself did not change (a known, accepted limitation — see §9) |
| `--force` **with** an explicit free `--extract`, against a paid-recorded document | The one override: re-extracts, discards the paid text, and names what it discarded. `--force` alone changes nothing |

Four consequences the table implies but must be stated:

- **Soft delete removes the searchable trace, keeps the identity.** Executing a soft delete deletes
  the document's chunks and embeddings (FTS rows follow via triggers) so a deleted document can
  never surface in results; the `documents` row itself stays, `state = deleted`, because it is the
  identity the next sync's pairing needs.
- **Sidecar-only edits are their own change class.** The table above governs *document identity*;
  a user editing tags, title or links with the document untouched must not fall through to "Skip"
  and freeze. Sync also hashes sidecar content (`documents.sidecar_hash`, §3); on change it
  refreshes `documents.metadata` and `links` without re-chunking or re-embedding.
- **Rename + edit in the same sync:** the hash tie is gone, so rows alone would soft-delete the old
  path and mint at the new one — breaking inbound links. If the sidecar travelled with the file,
  the adoption row wins over the deletion row: the ID continues at the new path, content is
  re-embedded, and **no soft delete is emitted for that ID**. If the sidecar did not travel,
  soft-delete + mint is the honest outcome, and sync reports it as a likely moved-without-sidecar
  case (§9's most-likely-corruption risk, surfaced at the moment it happens).
- **`--rebuild`'s empty `before` cannot see a recorded backend, so it is not asked to.**
  `pair()`'s comparison-based rows above only ever run against the same, populated `before` a normal
  sync sees; `--rebuild` builds into a brand-new `.pinakes/index.db.new` (§6.5) and reads `before`
  from that empty file, so every document looks new to it regardless — including a document that was
  *renamed* just before the rebuild, since there is no `before` for pairing to compare the rename
  against either. The paid-protection rows are still honoured during a rebuild, but by a separate
  mechanism: before the new database is even created, sync reads the *old* `index.db` (still on disk
  until the atomic swap at the very end) for every actively-indexed, paid-extracted document, keyed
  on **`doc_id` alone** — this table's own primary key, therefore unique by construction, and the one
  identifier a renamed sidecar still carries unchanged (a content_hash-only key would additionally let
  a *different*, later-minted document sharing that same content_hash incorrectly inherit the paid
  one's chunks, embeddings and backend label). When this run's effective backend is free, that
  document's row, chunks and embeddings are copied straight across via SQLite's `ATTACH DATABASE`,
  never re-extracted — at the file's *old* content_hash, not necessarily its current one:
  - If the current file's hash still matches, this is the ordinary "protected" case above.
  - If it does not (the file changed since the paid extraction), the old row is copied forward
    exactly the same way, but the run also records a `failures` entry, matching decision 14's normal
    outcome rather than letting the document silently vanish from the rebuilt index.

  This is deliberately independent of `extract/cache.py`: a `--clear-cache` immediately before
  `--rebuild` empties the cache but never touches `index.db`, so a mechanism keyed on the cache would
  wrongly conclude the content had changed, or silently re-extract for free, the moment both ran back
  to back. Reading the old index directly is what makes the two commands compose safely in either
  order — and the identical reasoning is why a **rename** (not a rebuild) also cannot rely on the
  cache: it reaches `pair()`'s `Adopt`/`Rename` rows, never the same-path comparison, so a sync
  additionally checks whether *this same connection* already holds an active row for the document's
  own `doc_id` at its unchanged content_hash before ever consulting `extract/cache.py` at all. Only
  when neither this connection, the old index during a rebuild, nor the cache has an answer does
  decision 9 fall back to the sidecar's own recorded content_hash alone — which can prove the file is
  unchanged even when nothing local can produce its text (see §9's "no local copy anywhere" case).

Deletion is soft and sidecars are never removed automatically: `pnk doctor --prune` does that, only
on explicit request, after printing the list. Deleting a user's file because a hash didn't match is
not a recoverable mistake.

**Partial failure:** each document is processed in its own transaction. A document that fails to
parse or embed is recorded in `failures` with its error, the run continues, and `pnk sync` exits
non-zero listing them. The index never half-describes a document, and one broken PDF cannot block a
1,000-document corpus.

### 6.5 Concurrency

A git hook can fire while an MCP server is answering. The policy:

- SQLite in **WAL mode**: readers are never blocked by the writer.
- The MCP server opens the index **read-only** (`file:…?mode=ro`) with a `busy_timeout`.
- `pnk sync` takes an advisory `.pinakes/sync.lock` recording **pid, hostname and start time**.
  A second sync finding the lock does not just exit: if the holder is alive on this host, exit 0
  quietly — hook-driven contention is normal, not an error. If the recorded pid is dead on this
  host, **reclaim the lock with a warning** — a sync killed mid-run must not disable hook-driven
  freshness forever, which is exactly what a bare "exit if lock exists" rule would do, silently,
  with `--quiet` hiding the symptom. If the hostname is not this machine (shared/NFS checkout),
  refuse and name the lock: liveness cannot be checked across hosts, so the conservative path is a
  human running `pnk sync --force-unlock`. `pnk doctor` reports any held lock with its holder and
  the time it was taken — `pid N on <host>, since <stamp>`, never a computed age, because an age
  would have to be differenced against a clock the reader cannot see.
  Residual risk — pid reuse can misjudge liveness — is accepted: start time in the lock
  makes the misjudgement window narrow, and the failure mode is one skipped sync, not corruption.
- The server detects a swapped index by **`stat()`ing `.pinakes/index.db` (inode + mtime) per
  request**, not by reading `meta.build_id` through its own connection — an open handle keeps the
  *old* inode alive after a rename, so it would report the old `build_id` forever and never notice
  the rebuild. On change it reopens; the stale-read window is one request rather than a session.
- `pnk sync --rebuild` builds into `.pinakes/index.db.new`, then **checkpoints
  (`PRAGMA wal_checkpoint(TRUNCATE)`) and closes cleanly before the swap**, so no `-wal`/`-shm`
  companion survives, then renames the single file into place. Renaming a WAL-mode database while its
  companions exist is not an atomic operation on a *set* of files — a stale `-wal` paired with a new
  `index.db` is a corrupt read waiting to happen. Readers notice via the `stat()` check above —
  `meta.build_id` remains in the schema for provenance in logs and eval runs, not for swap detection.

---

## 7. Quality

A golden set of questions, each with known-correct source chunks, lives with the demo KB. CI
scores **recall@k, MRR, rerank precision, and the false-abstain / false-confidence rates of the
§4.2 signal**, and fails the build on regression beyond a small tolerance.

**A template ships no golden set**, and `make eval` **skips** with a printed reason rather than
failing when it finds none. A template scaffolds an empty `docs/`, so any question it shipped would
name a document that does not exist — an earlier version of this section said a golden set lives
"with each template" while every committed template shipped `questions: []` against a harness that
rejected it, which made a freshly scaffolded KB fail its own evaluation by construction. What keeps
the skip from blessing an *emptied* golden set is that the committed one is asserted non-empty and
a file whose `questions` key is merely misspelled is still an error.

**Per class, not only in aggregate** — and the question count is itself a gated number. An aggregate
hides a trade: a change that lifts one kind of question and pays for it out of another moves the
headline rates by almost nothing, which is precisely the shape a graph channel has. A golden set
that *shrank* is caught the same way, because losing its hard questions improves every rate.

**And per question, not only per class.** Every run can emit `eval/outcomes.json` beside the
baseline — one row per question (`id`, `kind`, `hit`, `hit_rank`, `confidence`) under a header
naming the models and retrieval settings that produced it, because two artifacts from two
configurations are otherwise indistinguishable on inspection. Six aggregates cannot say *which*
questions moved, which is what a paired before/after comparison needs. The whole scoreboard is a
function of those five fields, so a committed artifact is re-scorable offline with no weights and
no network. Questions therefore carry a stable `id`: it is the only thing that pairs a before row
with an after row, and a repeated one silently drops a question from every comparison.

**A question's `kind` is validated, never defaulted.** An absent or unrecognised kind is an error
naming the six that exist. Defaulting it is a claim about how the question was authored, and a
wrong one puts it into a class whose score then measures two different things.

**A scripted multi-hop question is scored on every hop**: it counts as found only when each hop's
own query retrieves the document that hop names, so its `expect` is exactly the union of those
documents. Scoring only the last search would make the class a single-shot lookup wearing a label.

This is what makes fusion weights, chunk sizes and reranker choices *decidable* instead of
superstitious. It is also unglamorous work that must not be deferred: retrieval tuning without a
scoreboard is guessing, and guessing at the foundation is expensive later.

**The demo KB is synthetic** — ~30 Markdown documents written for the purpose, with ≥70 golden
questions deliberately spanning: lexical-only hits, **simple factual lookup**, paraphrase-only
hits, filter interactions, multi-hop chains, and **questions with no answer in the corpus** (where
the correct behaviour is to abstain). Zero licensing risk, and better test signal than found text.

**`simple-lookup` is the control class.** One study in the GraphRAG-Bench line measured a graph
channel *costing* ~13% accuracy on plain factual lookup while helping multi-hop, so the set carries
a body of ordinary questions — not authored to be hard, and not authored to share words with their
document the way `lexical` is — whose only job is to make that trade visible as a per-class drop
instead of a rounding error.

**Stated limit, measured rather than suspected:** at this corpus size the multi-hop class is nearly
saturated. Thirty short, topically disjoint documents make "retrieve 5 of 30" an undemanding task,
and a set authored from corpus structure scores 17 of 18. A class with no failures in it can only
ever show damage, so no channel should be tuned against this corpus until it is larger and its
documents are less separable.

**A second synthetic corpus exists to be linked to**, not to be scored: a partner museum that
transacts with the archive — loans both ways, courier and condition reporting, a shared emergency
plan, a joint digitisation programme. It ships no golden set, because cross-KB behaviour is verified
by traversing it directly rather than by scoring it: the eval harness is single-KB in its bones, and
a cross-KB question scored through it is 0.00 by construction (the hop cannot be followed) or 1.00
by construction (it confirms a link the corpus author wrote). Neither decides anything.

**Authored links across both corpora are deliberately sparse, and a gate keeps them so.** One author
writes the corpus, its links, and the questions that traverse them, so an over-linked fixture would
make cross-KB traversal look easy and make any later graph evaluation look better than a real corpus
will. The gate caps the *share* of documents carrying links and, separately, any one document's
*degree* — density alone permits a single hub wired to everything, which is a different corpus with
the same headline number. It also requires at least one same-KB link per corpus: a cross-KB link's
source lives in another KB and resolves to no local node, so a corpus linked only outward would
contribute no derived structure at all while appearing well connected.

Stated cost: synthetic prose is unrealistically clean, and small-corpus results do not automatically
hold at 50k documents. The harness is therefore built to be pointed at a user's own KB, and the docs
say so.

### 7.1 PDF extraction quality

`pinakes.extract.quality` scores a free-path extraction against `tests/pdf-corpus/`'s own ground
truth on five metrics, each shipping its own denominator rather than a bare float — a rate whose
denominator is legitimately zero (no native text layer, no `(label, value)` pairs to assert in this
stratum) is declared `null`, never a silent, indistinguishable `0.0` (this section's own
`false_abstain: 0.0` mistake, corrected here rather than repeated):

| Metric | Numerator | Denominator |
|---|---|---|
| `char_recall` | expected non-space characters found, in order (LCS) | expected non-space characters |
| `order_fidelity` | LCS length over word sequences | expected word count |
| `junk_rate` | extracted words absent from the ground truth | extracted word count |
| `pair_adjacency` | asserted `(label, value)` pairs within 80 characters of each other | asserted pairs |
| `word_coverage` | significant native-layer words present in the extraction | significant native-layer words |

`make pdf-eval` (`check.sh`, CI) extracts and scores every corpus fixture, compares each stratum
against `tests/pdf-corpus/baseline.json` with a tolerance, and re-fits both floors below to check
neither has drifted from `extract/floors.toml`. It skips, printing why, when `pinakes[pdf]` is
absent — never silently, and never failing a `[light]`-only checkout.

**Two floors are fitted from the corpus, not guessed**, and ship as package data
(`extract/floors.toml`, beside §5's `prices.toml`) with `fitted_on`:

- **The running-head threshold *T*** (`layout.strip_running_heads`) — the midpoint between the
  lowest recurrence any genuine running head or footer reaches and the highest recurrence anything
  else in the headers-footers stratum reaches (`tests/pdf-corpus/spec.py::KNOWN_RUNNING_HEAD_SIGNATURES`
  states which signature is genuine, per fixture). Costs nothing to apply, so its absence at runtime
  is a startup error, not a refusal to spend.
- **The text-yield floor** (non-whitespace characters per page) — the midpoint between the highest
  yield the scanned stratum reaches (0, no native text layer) and the lowest yield any real document
  reaches. It separates *empty* from *non-empty* and nothing finer — a stated blind spot, not a
  discovered one: the pathological stratum's invisible-render-mode fixture yields real characters
  while being useless text, and still needs the paid path. There is no `word_coverage` floor yet
  (decision 12, `plans/20260727_1543-v0.2.md`): the correct pair to fit it against is (native layer → Claude's
  output), and that pair now exists for one corpus — the human-gated run of 20260729 03:17
  (`docs/MEASUREMENT-RUN.md`). One synthetic corpus at one point in time is not yet enough to fit a
  floor a real document would be judged against.

**A known, accepted limitation:** `reading_order`'s column detection is geometric (x-gap
clustering), not structural — it has no notion of a table's rows and columns, so the free path reads
a table column by column, not row by row. `pair_adjacency` measures this directly for the tables
stratum, though this corpus's own tables are small enough that even the wrong reading order keeps a
label and its value within the metric's 80-character window — a disclosed limitation of this
specific corpus's diagnostic power, not of the metric's own design.

---

### 7.2 What bypassing `layout.py` on the paid path actually costs

Decision 10 has the paid backend skip reading-order and running-head handling, on the grounds that
a response of per-page strings has no geometry for them to operate on. **Measured 20260729 03:17**,
claude-opus-5, over the text-layer twins — documents with a perfectly good native layer, extracted
under `--force` precisely so the two paths can be compared on the same input:

| Fixture | char recall | order fidelity | junk rate | word coverage |
|---|---|---|---|---|
| `two-column-a` | — | — | — | — |
| `ligatures-a` | — | — | — | — |
| `baseline-12p` | — | — | — | — |
| **`tables-bordered`** | **+0.072** | **+0.119** | **+0.287 worse** | — |

Three of the four are **identical to the free path on every metric**: the bypass costs nothing
where `layout.py` had nothing to add. The fourth is the finding. On a bordered table the paid path
reads the cells in *better* order than the geometric column detector — and pays for it with 29%
junk, which is the table's own structure arriving as text. Neither path is simply better: the free
one loses order, the paid one adds noise, and a caller who cares about tables should know that
rather than infer it.

`headers-repeating` supplies no row: **the model refused it**, twice, and the refusal was recorded
as a document failure while the other four extracted normally. A refusal on an ordinary synthetic
document is worth stating plainly — the branch exists, it fires in practice, and it is not rare
enough to treat as theoretical.

---

## 8. Delivery plan

> **What has actually shipped is [STATUS.md](STATUS.md); the ordered build order is
> [`plans/`](https://github.com/lucagattoni/pinakes/tree/main/plans/).** This section carries only *why* the order is what it is.

**The first release had to be a thin vertical slice, end to end** — `init → sync → search`, plus
`doctor`, `install-hooks` and `serve`. Two orderings inside it were forced rather than chosen: the
local cross-encoder reranker could not ship later than the confidence signal, because the signal is
fitted on the reranker's own scores; and `pnk search` could not be deferred to a later release,
because a "vertical slice" queryable only over MCP does not reach end to end.

**Schema that cannot be retrofitted ships first, whatever release consumes it.** ULID document *and*
KB IDs, a sidecar for every document, the model-coherence fields, `[[links.kb]]`, and the
`pnk://<kb-ulid>/<doc-ulid>` URI form all shipped in v0.1 though most are consumed much later.
Adding stable IDs to a populated KB later means either renumbering — breaking every inbound link —
or a migration this design deliberately has no machinery for. The same reasoning put `[budget]`'s
schema in v0.1 and `page_start`/`page_end` in the index before anything displayed them.

**Why the releases come in this order.** The labels below are the names this project has long used
for each body of work, not committed version numbers — actual numbers are assigned when a release is
cut, and [STATUS](STATUS.md#release-roadmap) is where the mapping lives.

| Release | Why here |
|---|---|
| PDF extraction, completed by the paid-extraction release | Parsing is the single biggest quality risk (§9), so it is isolated from core-design feedback rather than mixed into it. Scope covers **both** paths: the free `pypdfium2` default, and the opt-in paid Claude-vision extractor that is the only answer to a scanned page (§9) — which is what drags the budget machinery into this release, per the governing rule below |
| the links release — cross-KB links | Needs two populated KBs to be worth anything. Build order: [`plans/20260729_0256-links-and-graph.md`](https://github.com/lucagattoni/pinakes/blob/main/plans/20260729_0256-links-and-graph.md) |
| the graph release — structural edges and the expansion channel | Edges are only worth deriving once there is a link graph to derive them beside, and the channel is gated on the golden set. **Measured 20260801: a golden set is not sufficient — the gate is only as strong as the corpus underneath it.** A corpus small enough that retrieval already returns every document, or flat enough that its derived edges connect everything to everything at one weight, cannot distinguish a channel that helps from one that does nothing. That is a precondition on the *corpus*, and it was discovered by running the measurement before the schema change rather than after. **Built: `schema_version` 3's node and edge set, and the expansion channel behind `[retrieval] graph_channel`.** Its gate ran on the RFC realism corpus (20260804) and did not pass, so `expand` ships `off` — an eval-gated feature that is built, measured and stays off by construction, exactly as the governing rule below predicts ([STATUS](STATUS.md#did-the-expansion-channel-earn-its-default--no-measured-20260804-2252)) |
| the graph release (staged) — further graph channels | PPR and the `[ner]` extra, **not built**. Each is **eval-gated rather than scheduled** — either ships only if the golden set justifies it (`graph/PINAKES_APPROACH.md` §9), independently of whether the expansion channel above did |
| the deep release — `pnk ask --deep` | A paid loop and its guardrails ship together, never apart — and the guardrails are already here: the §5 accountant, the ledger and all three enforced windows ship with the paid extractor, so the deep release adds the loop, not the machinery |
| the template release — templates, `sqlite-vec` | Generalisation, once real usage has shaped one template well |

The governing rule across all of them: **the budget machinery ships in the same release as the first
thing that can spend** (§5). That is what pulled the budget machinery forward when the paid extractor was
scheduled ahead of `--deep` — the design's own rule applied to a product decision, not scope creep.

**MCP tools are namespaced `pinakes_*`, not `kb_*`.** An agent commonly has several servers loaded at
once, and a tool called `kb_search` is a collision waiting to happen. Every tool takes an explicit
`kb` argument (alias or ULID) defaulting to the server's configured KB — every tool that
answers *about* a KB, that is; `pinakes_list_kbs` takes none, being the list itself.

`pinakes_links` traverses the authored link graph and returns a `frontier` and a `score` on every
call. Its `confidence` is **always `unknown`**: the signal §4.2 defines is calibrated per KB on the
reranker score of a retrieved *passage*, and a traversal neighbour is not one — a list spanning two
KBs has no single manifest whose thresholds even apply. Reachability there is a property of *this
server invocation* rather than of a manifest: a neighbour in a KB the server was not pointed at is
returned, identified, and marked unreachable, because omitting it would hide a link that exists.

---

## 9. Known risks

| Risk | Assessment |
|---|---|
| **PDF extraction quality** | The most likely source of silent quality loss (tables, multi-column, scans). Mitigated by a scored corpus of known-hard documents with its own committed baseline and gate (§7.1), and two floors fitted from that corpus rather than guessed. **Two limits stand today:** the free path's column detection is geometric, so tables read column-by-column; and scanned/image-only PDFs yield nothing at all, since the free path has no OCR. `plans/20260727_1543-v0.2.md` decision 3 puts scanned PDFs in scope **via the paid path only**, and that path is now measured: on the synthetic scanned stratum (3 fixtures, 10 pages) the paid extractor scores **1.000 char recall, 1.000 order fidelity, 0.000 junk, 1.000 word coverage** where the free path scores **0.000 on all four** — measured 20260729 03:17, claude-opus-5, €0.11 spent (docs/MEASUREMENT-RUN.md). **Measured on synthetic rasters**, which is the caveat that matters: they are generated at modest resolution and are not a substitute for a real 300-DPI scan of a degraded page |
| **Linear search at scale** | No tier is sublinear (§3.1). Mitigation: measured limits published, `pnk doctor` warns as the ceiling nears, splitting is the documented answer |
| **Link coverage ceiling** | See §6.2. Measured and reported rather than hidden |
| **Sidecar/document separation** | A user moving a file without its sidecar is the most likely real-world corruption. Mitigated by hash-based rename detection (§6.4) and `pnk doctor`; not eliminated |
| **Confidence heuristic** | Uncalibrated abstention would be worse than none. Mitigated by golden-set calibration, `unknown` as an honest default, and a measured false-abstain rate. **Measured on the demo KB (20260801 12:14, the `[light]` models, 74 questions): false-abstain 0.015, false-confidence 0.25** ([STATUS § Measured numbers](STATUS.md#measured-numbers), which is where the current figures live). One no-answer question in four still gets a confident answer — the score distributions genuinely overlap. The number is small (8 no-answer questions) and the thresholds are fitted on the same set they are scored against, so treat it as a floor. This is the cost §4.2 said would be measured rather than assumed |
| **`sqlite-vec` maturity** | Pre-v1, breaking changes expected. Contained: only reached above 50k chunks, deferred to the template release, NumPy tier remains a supported override |
| **torch install weight** | ~2GB for the default backend, plus ~1.4GB of model weights (embedding + reranker). Contained by the extras split and the CI `HF_HOME` cache (§4.5); CI's `check` job is a three-leg matrix over `[light]`, `[light,pdf]` and `[light,pdf,claude]`, never `[st]` |
| **Template versioning** | Template diffs are shown, never auto-applied (§6.1); templates version independently of the package |
| **Scope creep via `--deep`** | The paid loop is where this design could grow a second, worse agent framework. Bounded by: same tools as MCP, hard caps, and no orchestration the free path doesn't have |
| **Environment assumptions** | FTS5 and (for the template release) loadable extensions are not universal in system Pythons. Probed by `pnk doctor` with a named remedy; uv-managed CPython is the supported baseline (§3.1) |
| **Accidental publication** | Publishing a KB repo exposes `docs/` and every sidecar, provenance URLs included (§4.7). Mitigated by shipped `.gitignore`, an index/ledger that never leaves the machine, and explicit docs — not by anything the engine can enforce |
| **The paid-path allowlist erodes, or its decisive gate is inert** | A one-line import in a new module quietly makes the free path paid; and a behavioural gate that asserts a package is *absent* is vacuously true wherever that package is not installed — the `false_abstain: 0.0` failure reappearing in the flagship safety check. Mitigated by one `.paid-path-allowlist` that `check.sh`, CI and the tests all read, so three copies cannot drift; the gate landed **before** the code it guards, and its first job was to fail on a planted violation. The check that decides runs the whole free path in a fresh subprocess and asserts no paid client reached `sys.modules` — it skips loudly where `[claude]` is absent, runs for real on CI's `[light,pdf,claude]` leg, and has a negative test that plants an import and asserts it fails. It caught two real leaks on the day it landed: `pnk doctor` and `pnk sync` both reported a backend's availability by *loading* it, which imports the client |
| **Unbounded spend across invocations** | One `pnk sync` is capped; nothing caps the tenth. Freshness is hook-driven (§6.3), which makes `pnk sync` machine-driven, so a per-invocation cap is really an allowance renewed on every commit — the per-invocation framing hides that the invocations are the loop. Mitigated by making the cap arithmetic over a *running* total: `per_operation_eur`, `daily_eur` **and** `monthly_eur` are all checked before every call, aggregated in `[budget] timezone`. `monthly_eur` is **per KB**, so ten paid KBs are ten allowances; there is no global cap, and this says so rather than letting a reader assume one. All of it is built: the reservation arithmetic (I6a), reading the ledger, hooks and `pnk init --ci` forced onto the free backend, and the no-TTY abort (I6b) |
| **Price-table staleness, and the USD→EUR rate inside it** | The manifest prices in EUR and the vendor bills in USD, so the rate is a second number that goes stale with nothing saying so — and a ledger recording only a EUR figure cannot be re-derived once it moves. Mitigated by giving `usd_per_eur` the same `as_of` as the model prices (both shipped in `prices.toml`), recording `cost_usd`, the rate and its `as_of` on every ledger line with EUR computed at read time, and refusing to estimate against prices older than `max_price_age_days` rather than guessing. Deliberately **not** a CI gate: a wall-clock gate fails a quiet weekend with no code change, so staleness is a `pnk doctor` WARN and a runtime refusal, while CI only checks the file is well-formed. Built: every ledger line carries `cost_usd`, the rate and its `as_of`, and `pnk doctor` reports the table's age against `max_price_age_days` |
| **Scanned-PDF quality cannot be measured by the audit that measures everything else** | The completeness audit's witness is the page's native text layer, and a scanned page has none — so the gate is blind on precisely the stratum the paid feature exists for. Mitigated by reporting `exempt K of M` rather than scoring exempt pages as passing (a pass rate that counts unmeasurable pages as passes is the vacuous-metric failure §7 exists to avoid), and by hand-authoring the scanned stratum's ground truth from the generator's spec rather than from any extractor's output. the audit is built and **reports only** — it re-extracts nothing and spends nothing, because the loop it would drive needs a floor and the pair that floor must be fitted against is (native layer → Claude output), which did not exist until the first real runs produced it. **Those numbers are now in the PDF-extraction-quality row above** — measured 20260729 03:17, claude-opus-5, €0.11 — and they are measured on synthetic rasters, which is the caveat that matters |
| **A paid extraction's text has no durable, cross-machine home** | The sidecar's `provenance.extraction` proves a file is *unchanged* since a paid extraction anywhere (§6.4) — but the extracted *text* itself lives only in one machine's `extract/cache.py` or `index.db`, both gitignored. A fresh clone's first sync over a KB whose paid PDFs were extracted elsewhere gets an honest `PaidExtractionUnavailableError`, never a false "content changed" claim, but also cannot avoid paying again without one of those two local stores. Accepted, not solved: a shared or committed store for paid extraction results is a real design question (would it live in git, defeating "originals are the truth"? A remote cache?) deliberately deferred rather than answered under this increment's own scope |

---

## 10. Review history

This document was reviewed across **seven adversarial passes before implementation began** — 58
findings resolved (11 HIGH, 32 MEDIUM, 15 LOW), including four externally verified claims, two of
which the review found to be **false**.

That record has moved to
[RETROSPECTIVES.md § Design review passes 1–7](RETROSPECTIVES.md#design-review-passes-17-pre-implementation),
so all project history — design review and per-increment build retrospectives alike — lives in one
file, and this document is specification only.
