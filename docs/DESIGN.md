# pinakes — a portable, agent-first knowledge base

**Repo:** github.com/lucagattoni/Pinakes (PUBLIC) · **Licence:** Apache-2.0 · **Python:** 3.13+
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
| What is **going to be built**, in order | [`plans/`](../plans/) |

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
lives in `.paid-path-allowlist`; adding to it edits that file, this section and `CLAUDE.md`
together. Everything else is free *by construction*: no module outside the allowlist may so much as
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
| Retrieval | Hybrid (BM25 + vector) + rerank · metadata filters · multi-hop (single-KB in v0.1, cross-KB in v0.3) |
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
[retrieval]             # three separate widths, fusion, rerank, vector tier
[retrieval.confidence]  # fitted thresholds; absent ⇒ report `unknown`, never guess
[rerank]                # mirrors [embedding]
[budget]                # soft confirm threshold, hard per-operation cap, rolling windows
[[links.kb]]            # connected KBs: canonical ULID + machine-local alias and path
```

**What must be present, and why.** `[kb]` (`name`, `id`), `[sources]` (`roots`) and `[embedding]`
(`provider`, `model`, `dim`) are required: nothing can sensibly default a KB's identity, its sources,
or the model whose output the index *is*. Everything else takes a default, except
`[retrieval.confidence]` and `[[links.kb]]`, which stay absent until something produces them.

**Three validation postures, each deliberate.** Unknown keys are rejected rather than ignored. An
explicit empty string is an error rather than a request for the default — silently substituting one
hides a mistake until it fails somewhere far away. And `[extraction] backend` is validated against
the registered extractors (`extract/__init__.py`) **without importing either**, so an unknown name is
rejected before either extra could matter.

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
content_hash}`** (v0.2, decision 11) — the one case where sync rewrites an *existing* sidecar rather
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
ordinary free extraction. The cost is real and accepted: PyYAML drops comments and re-sorts unknown
keys on this one write, same as any other `write()` call would; a comment-preserving writer is `pnk
link`'s problem (v0.3), not pulled forward here.

Why sidecars rather than in-text links: a PDF cannot carry a wikilink without being rewritten, and
mutating source documents breaks the "originals are the truth" contract. One mechanism that works
for every source type beats two mechanisms that each work for half.

**The cost of this choice is friction** — nobody hand-writes YAML per document. Mitigations, all v1:
`pnk link A B --rel cites` authors the sidecar; sync generates the skeleton; `pnk doctor` reports
dangling links, orphaned sidecars and ID collisions.

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

**Index schema migrations do not exist.** On `schema_version` mismatch the index refuses to open and
instructs `pnk sync --rebuild`. Because `.pinakes/` is disposable and rebuilds are free, migration
code would be pure liability — this is the payoff of the truth/derived split. `schema_version` is
`2` as of v0.2 (I5's page and extraction-backend columns above); a v0.1 index raises `IndexSchemaError`
naming the same rebuild remedy, never a migration.

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
in an ANN index. `sqlite-vec` is also pre-v1 with breaking changes expected — contained by only
being reached above 50k chunks, with `vector_tier = "numpy"` supported as a config override.

**What v0.1 actually ships:** the NumPy tier only, at *any* corpus size — the `sqlite-vec` tier lands
in v0.5 (§8). NumPy does not fail above 50k, it just costs linear RAM (≈1.5 GB at 1M chunks × 384
dims); `pnk doctor` warns past the 50k threshold and names the tier that will fix it. Stating this
matters because a table of three tiers reads as three *available* tiers.

**Environment requirement:** SQLite ≥ 3.35 compiled with FTS5, and — for the `sqlite-vec` tier —
`enable_load_extension` available. uv-managed CPython 3.13 satisfies both (verified 20260725 13:49: SQLite
3.53.1, FTS5 present, extension loading permitted); some system Pythons are built without them, so
`pnk doctor` probes both and reports a precise remedy rather than failing at query time.

---

## 4. Retrieval

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
```

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

Scope, stated precisely: **v0.1 gives multi-hop within a single KB.** Cross-KB hops need
`pinakes_links`, which ships in v0.3 (§8).

`pnk ask --deep` exists for CLI and cron use, where no agent is present. It runs a bounded version of
the same loop with its own API key under the budget ledger (§5). Same tools, same evidence contract —
only the driver differs. That keeps the paid path thin enough not to rot.

### 4.4 Model/index coherence

Embeddings are meaningless across models. The manifest records provider, model and revision; if
`.pinakes/index.db` was built with anything else, queries **refuse to run** and instruct a rebuild. A
KB that silently returns garbage after a model upgrade is worse than one that stops.

**Per-document extraction coherence (v0.2, decision 13).** A PDF's *extractor* can drift the same
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
the manifest) are the v0.2 extractor backends (§2.1's `[extraction]`). **`[claude]` requires
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
it** — not consumed as pure structure. The lexical index only sees chunk text, so a word appearing
only in a heading would otherwise be unsearchable, and a passage quoted back to the user reads
better carrying the heading it belongs to. `heading_path` still records the hierarchy separately,
for filtering and citation.

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

**PDF chunks additionally carry `page_start`/`page_end`** (v0.2), a 1-indexed lookup against the
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
state the exposure plainly. The engine repo itself contains no real KB: only the synthetic demo (§7).

> ⏳ **Pending amendment (noted 20260728 16:40).** The agent surface does not yet carry two things
> the rest of this document assumes: `page_start`/`page_end` on `pinakes_search` results (with
> `pinakes_get` accepting a page range), and the `stale_extraction` marker §4.4 sets on a
> paid-fingerprint mismatch — which today reaches the CLI's `Passage` but stops there. Both are
> increment **I8** ([STATUS.md](STATUS.md#v02-increment-ledger)). Page spans are already stored per
> chunk; only the surfacing is missing.

---

## 5. Cost control

**Nothing shipped today costs money.** The budget system ships in the same release as the first
thing that can spend, which is the honest ordering — and the first spender is no longer
`pnk ask --deep`. `plans/v0.2.md` decision 2 moved that role to the **opt-in Claude-vision PDF
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
| **Visibility** | `pnk budget` shows spend by day/month/operation. Real per-KB cost data, not vibes |

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

**Money is `Decimal` end to end, quantised exactly once**, when a record is written to the ledger. A
cap compared against a float is not a cap: `0.05` has no exact binary representation, so the ceiling
enforced would differ from the one configured by an amount nobody can predict or explain.

**The ledger stores no query text and no document content** — timestamp, operation, model, token
counts, cost, KB id, nothing more. It is diagnostics, not a transcript, and must never become an
accidental log of what you asked.

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
proposed migration. It never applies changes automatically — a template bump that silently re-chunks
someone's corpus is a data-loss event in slow motion.

**This is one of four drift axes, and the only one with no mechanism.** An index, an embedding model
and a PDF extractor each drift detectably and are remedied by rebuilding derived state, which is
free. A manifest and a template drift *silently*, and the remedy touches a file the user owns — so
it cannot borrow the same shape. [KB-UPDATES.md](KB-UPDATES.md) works the problem through and
records what has been decided; none of it is built.

### 6.2 Cross-KB links

Addressing is `pnk://<kb-ulid>/<doc-ulid>` (§2.2). Aliases in `[[links.kb]]` map a KB ULID to a local
path; resolution is machine-local, the link itself is not.

Forward traversal reads this KB's own `links` table. **Reverse links are computed by scanning the
other KB's committed sidecars** (`docs/**/*.pnk.yaml`) at sync time — *not* its index, which is
gitignored and simply absent in a fresh clone. Results are cached in `kb_refs` + `links`.

Failure modes are explicit rather than silent: an unresolvable KB id, an unreachable path, or a
`pnk://` target whose doc no longer exists are all reported by `pnk doctor` as dangling, and
traversal returns them as `unresolved` with the reason attached instead of dropping them.

**The honest limitation:** without fan-out query, a question must *start* in one KB and travel via
links. If no link exists, the connection is invisible. Link coverage is the ceiling on cross-KB
answers, so `pnk doctor` reports it (linked docs / total docs) — the ceiling is visible rather than
mysterious. If it bites, federated query is the v2 answer.

### 6.3 Freshness

`pnk sync` is the primitive: walk sources, compare content hashes, re-process only what changed.
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
the prompt for cron use. `ledger.jsonl` is never touched, the same guarantee `--rebuild` already
gives. Selective removal of paid orphans alone lands with the ledger reader that can price them
(I7c) — building it sooner would mean pricing entries against a ledger that does not exist yet.

`pnk install-hooks` writes **three** hooks, split by what each may touch:

- **`pre-commit`** runs `pnk sync --sidecars-only --stage`: for every *staged* new document it mints
  the ULID, writes the sidecar, and `git add`s it — so a document and its ID land in the **same
  commit**, never one behind. Only sidecars of staged documents are touched, which keeps partial
  staging (`git add -p`) honest, and `git commit --no-verify` is the documented escape hatch. This is
  the one hook allowed to write into `docs/`; it writes nothing else.
- **`post-commit` + `post-merge`** run `pnk sync --quiet`: index work only. Because sidecars were
  authored at pre-commit time, this stage never dirties the tree it just committed — a post-commit
  hook that created sidecars would leave every document commit trailing an untracked `.pnk.yaml`,
  demanding a second commit forever.

`pnk sync` gains `--extract=BACKEND`, overriding `[extraction] backend` for that one run; the name is
validated against the registered extractors the same way the manifest is — no importing either.

`pnk init --ci` drops a GitHub Actions workflow that syncs and caches `.pinakes/`. No daemon.

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
- **`--rebuild`'s empty `before` cannot see a recorded backend, so it is not asked to (v0.2).**
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
  human running `pnk sync --force-unlock`. `pnk doctor` reports any held lock with its age and
  holder. Residual risk — pid reuse can misjudge liveness — is accepted: start time in the lock
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

A golden set of questions, each with known-correct source chunks, lives with the demo KB and with
each template. CI scores **recall@k, MRR, rerank precision, and the false-abstain / false-confidence
rates of the §4.2 signal**, and fails the build on regression beyond a small tolerance.

This is what makes fusion weights, chunk sizes and reranker choices *decidable* instead of
superstitious. It is also unglamorous work that must not be deferred: retrieval tuning without a
scoreboard is guessing, and guessing at the foundation is expensive later.

**The demo KB is synthetic** — ~30 Markdown documents written for the purpose, with ≥40 golden
questions deliberately spanning: lexical-only hits, paraphrase-only hits, filter interactions,
multi-hop chains, and **questions with no answer in the corpus** (where the correct behaviour is to
abstain). Zero licensing risk, and better test signal than found text.

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
  (decision 12, `plans/v0.2.md`): the correct pair to fit it against is (native layer → Claude's
  output), and no Claude output exists before I7b.

**A known, accepted limitation:** `reading_order`'s column detection is geometric (x-gap
clustering), not structural — it has no notion of a table's rows and columns, so the free path reads
a table column by column, not row by row. `pair_adjacency` measures this directly for the tables
stratum, though this corpus's own tables are small enough that even the wrong reading order keeps a
label and its value within the metric's 80-character window — a disclosed limitation of this
specific corpus's diagnostic power, not of the metric's own design.

---

## 8. Delivery plan

> **What has actually shipped is [STATUS.md](STATUS.md); the ordered build order is
> [`plans/`](../plans/).** This section carries only *why* the order is what it is.

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
| v0.2 — PDF extraction | Parsing is the single biggest quality risk (§9), so it is isolated from core-design feedback rather than mixed into it. Scope covers **both** paths: the free `pypdfium2` default, and the opt-in paid Claude-vision extractor that is the only answer to a scanned page (§9) — which is what drags the budget machinery into this release, per the governing rule below |
| v0.3 — cross-KB links | Needs two populated KBs to be worth anything. Build order: [`graph/PINAKES_APPROACH.md`](graph/PINAKES_APPROACH.md) §10 |
| v0.3.x — graph channels | Each is **eval-gated rather than scheduled** — it ships only if the golden set justifies it (`graph/PINAKES_APPROACH.md` §9) |
| v0.4 — `pnk ask --deep` | A paid loop and its guardrails ship together, never apart |
| v0.5 — templates, `sqlite-vec` | Generalisation, once real usage has shaped one template well |

The governing rule across all of them: **the budget machinery ships in the same release as the first
thing that can spend** (§5). That is what moved it out of v0.4 when the paid extractor was pulled
into v0.2 — the design's own rule applied to a product decision, not scope creep.

**MCP tools are namespaced `pinakes_*`, not `kb_*`.** An agent commonly has several servers loaded at
once, and a tool called `kb_search` is a collision waiting to happen. Every tool takes an explicit
`kb` argument (alias or ULID) defaulting to the server's configured KB.

---

## 9. Known risks

| Risk | Assessment |
|---|---|
| **PDF extraction quality** | The most likely source of silent quality loss (tables, multi-column, scans). Mitigated by a scored corpus of known-hard documents with its own committed baseline and gate (§7.1), and two floors fitted from that corpus rather than guessed. **Two limits stand today:** the free path's column detection is geometric, so tables read column-by-column; and scanned/image-only PDFs yield nothing at all, since the free path has no OCR. `plans/v0.2.md` decision 3 puts scanned PDFs in scope **via the paid path only** — ⏳ that extractor is increment **I7b** and is not built ([STATUS.md](STATUS.md)) |
| **Linear search at scale** | No tier is sublinear (§3.1). Mitigation: measured limits published, `pnk doctor` warns as the ceiling nears, splitting is the documented answer |
| **Link coverage ceiling** | See §6.2. Measured and reported rather than hidden |
| **Sidecar/document separation** | A user moving a file without its sidecar is the most likely real-world corruption. Mitigated by hash-based rename detection (§6.4) and `pnk doctor`; not eliminated |
| **Confidence heuristic** | Uncalibrated abstention would be worse than none. Mitigated by golden-set calibration, `unknown` as an honest default, and a measured false-abstain rate. **Measured on the demo KB (20260725 18:55, bge-small + bge-reranker-base): false-abstain 0.03, false-confidence 0.25.** One no-answer question in four still gets a confident answer — the score distributions genuinely overlap. The number is small (8 no-answer questions) and the thresholds are fitted on the same set they are scored against, so treat it as a floor. This is the cost §4.2 said would be measured rather than assumed |
| **`sqlite-vec` maturity** | Pre-v1, breaking changes expected. Contained: only reached above 50k chunks, deferred to v0.5, NumPy tier remains a supported override |
| **torch install weight** | ~2GB for the default backend, plus ~1.4GB of model weights (embedding + reranker). Contained by the extras split and the CI `HF_HOME` cache (§4.5); CI's `check` job is a three-leg matrix over `[light]`, `[light,pdf]` and `[light,pdf,claude]`, never `[st]` |
| **Template versioning** | Migrations are shown, never auto-applied (§6.1); templates version independently of the package |
| **Scope creep via `--deep`** | The paid loop is where this design could grow a second, worse agent framework. Bounded by: same tools as MCP, hard caps, and no orchestration the free path doesn't have |
| **Environment assumptions** | FTS5 and (for v0.5) loadable extensions are not universal in system Pythons. Probed by `pnk doctor` with a named remedy; uv-managed CPython is the supported baseline (§3.1) |
| **Accidental publication** | Publishing a KB repo exposes `docs/` and every sidecar, provenance URLs included (§4.7). Mitigated by shipped `.gitignore`, an index/ledger that never leaves the machine, and explicit docs — not by anything the engine can enforce |
| **The paid-path allowlist erodes, or its decisive gate is inert** | A one-line import in a new module quietly makes the free path paid; and a behavioural gate that asserts a package is *absent* is vacuously true wherever that package is not installed — the `false_abstain: 0.0` failure reappearing in the flagship safety check. Mitigated by one `.paid-path-allowlist` that `check.sh`, CI and the tests all read, so three copies cannot drift; the gate landed **before** the code it guards, and its first job was to fail on a planted violation. The check that decides runs the whole free path in a fresh subprocess and asserts no paid client reached `sys.modules` — it skips loudly where `[claude]` is absent, runs for real on CI's `[light,pdf,claude]` leg, and has a negative test that plants an import and asserts it fails. It caught two real leaks on the day it landed: `pnk doctor` and `pnk sync` both reported a backend's availability by *loading* it, which imports the client |
| **Unbounded spend across invocations** | One `pnk sync` is capped; nothing caps the tenth. Freshness is hook-driven (§6.3), which makes `pnk sync` machine-driven, so a per-invocation cap is really an allowance renewed on every commit — the per-invocation framing hides that the invocations are the loop. Mitigated by making the cap arithmetic over a *running* total: `per_operation_eur`, `daily_eur` **and** `monthly_eur` are all checked before every call, aggregated in `[budget] timezone`. `monthly_eur` is **per KB**, so ten paid KBs are ten allowances; v0.2 adds no global cap and says so rather than letting a reader assume one. ⏳ the reservation arithmetic shipped inert (I6a); reading the ledger, forcing hooks and `pnk init --ci` onto the free backend, and the no-TTY abort are **I6b** and are not built ([STATUS.md](STATUS.md)) |
| **Price-table staleness, and the USD→EUR rate inside it** | The manifest prices in EUR and the vendor bills in USD, so the rate is a second number that goes stale with nothing saying so — and a ledger recording only a EUR figure cannot be re-derived once it moves. Mitigated by giving `usd_per_eur` the same `as_of` as the model prices (both shipped in `prices.toml`), recording `cost_usd`, the rate and its `as_of` on every ledger line with EUR computed at read time, and refusing to estimate against prices older than `max_price_age_days` rather than guessing. Deliberately **not** a CI gate: a wall-clock gate fails a quiet weekend with no code change, so staleness is a `pnk doctor` WARN and a runtime refusal, while CI only checks the file is well-formed. ⏳ the ledger fields and the doctor WARN are **I6b** and are not built ([STATUS.md](STATUS.md)) |
| **Scanned-PDF quality cannot be measured by the audit that measures everything else** | The completeness audit's witness is the page's native text layer, and a scanned page has none — so the gate is blind on precisely the stratum the paid feature exists for. Mitigated by reporting `exempt K of M` rather than scoring exempt pages as passing (a pass rate that counts unmeasurable pages as passes is the vacuous-metric failure §7 exists to avoid), and by hand-authoring the scanned stratum's ground truth from the generator's spec rather than from any extractor's output. ⏳ the audit is **I7c** and is not built; its measured numbers land in this section with date, model and euros actually spent, labelled as measured on synthetic rasters ([STATUS.md](STATUS.md)) |
| **A paid extraction's text has no durable, cross-machine home (v0.2)** | The sidecar's `provenance.extraction` proves a file is *unchanged* since a paid extraction anywhere (§6.4) — but the extracted *text* itself lives only in one machine's `extract/cache.py` or `index.db`, both gitignored. A fresh clone's first sync over a KB whose paid PDFs were extracted elsewhere gets an honest `PaidExtractionUnavailableError`, never a false "content changed" claim, but also cannot avoid paying again without one of those two local stores. Accepted for v0.2, not solved: a shared or committed store for paid extraction results is a real design question (would it live in git, defeating "originals are the truth"? A remote cache?) deliberately deferred rather than answered under this increment's own scope |

---

## 10. Review history

This document was reviewed across **seven adversarial passes before implementation began** — 58
findings resolved (11 HIGH, 32 MEDIUM, 15 LOW), including four externally verified claims, two of
which the review found to be **false**.

That record has moved to
[RETROSPECTIVES.md § Design review passes 1–7](RETROSPECTIVES.md#design-review-passes-17-pre-implementation),
so all project history — design review and per-increment build retrospectives alike — lives in one
file, and this document is specification only.
