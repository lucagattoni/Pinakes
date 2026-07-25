# pinakes — a portable, agent-first knowledge base

**Status:** reviewed — ready to implement · **Date:** 20260725
**Repo:** github.com/lucagattoni/Pinakes (PUBLIC) · **Licence:** Apache-2.0 · **Python:** 3.13+
**Package:** `pinakes` (PyPI) · **Command:** `pnk` · **Tooling:** uv

> *The* Pinakes *were Callimachus's catalogue of the Library of Alexandria — the first known index
> of a body of knowledge.*

---

## 1. What this is

A Python engine for building **self-contained knowledge bases**: one directory = one KB, holding
human-readable source documents, human-readable metadata, and a disposable machine index.

KBs are created from **templates** (the "blueprint"), rebuilt **reproducibly** from a manifest, and
**linked to each other** so an agent can follow a reference from one KB into another.

The design has one organising principle: **the free path does the work.** Local embeddings, local
lexical search, local reranking — the whole retrieval stack costs nothing to run, forever. Paid LLM
reasoning is an explicit, budgeted opt-in, and the default agent surface never triggers it.

### Decisions taken (from requirements gathering)

| Area | Decision |
|---|---|
| Consumer | Agent-first, but source of truth is human-readable files |
| Surfaces | MCP server + CLI (Python API is the internal substrate, not yet a public contract) |
| Deployment | Local-first, one portable directory per KB. No server, no daemon |
| Build posture | Own the format + orchestration; reuse proven components |
| Sources | Markdown / plain text / code, and PDF. **Not** Office, web, email, chat |
| Scale | Scale-agnostic: exact and simple when small, memory-bounded upward (§3) |
| Compute | Local embeddings (free, unlimited re-index) + Claude for reasoning only |
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

```toml
[kb]
name     = "research"                 # local, human-facing; may be renamed freely
id       = "01JQ8ZK3…"                # ULID. Permanent. The authority in pnk:// URIs
template = "research-papers@1.2"      # template's own version, not the package version
created  = "20260725 09:14"

[sources]
roots   = ["docs/"]                   # relative to KB root, always
include = ["**/*.md", "**/*.pdf", "**/*.py"]
exclude = ["**/drafts/**"]

[embedding]
provider = "sentence-transformers"
model    = "BAAI/bge-small-en-v1.5"
dim      = 384
revision = "…"                        # HF commit sha — index refuses to load on mismatch (§4.4)

[chunking]
strategy   = "structural"             # headings/paragraphs, not blind character windows
max_tokens = 510                      # ≤ model max_seq_length minus special tokens (§4.6)
overlap    = 64

[retrieval]
candidates_per_source = 50            # BM25 top-N and vector top-N, before fusion
fusion                = "rrf"         # k = 60 by default
fusion_top_k          = 20            # survivors handed to the reranker
final_k               = 8             # passages actually returned
rerank                = "local"       # "local" | "none"
vector_tier           = "auto"        # "auto" | "numpy" | "sqlite-vec"

[retrieval.confidence]
# Fitted against the template's golden set (§4.2/§7). Absent ⇒ report `unknown`, never guess.
fitted_for = "BAAI/bge-reranker-base@…"   # reranker model@revision — on mismatch, report `unknown`
low_below  = 0.31
high_above = 0.62

# Consumed only when [retrieval] rerank = "local". Mirrors [embedding]. The default model id is
# identical on both backends (verified in fastembed's registry, 20260725), so switching backend
# does not change this block.
[rerank]
provider = "sentence-transformers"
model    = "BAAI/bge-reranker-base"       # ~1.04 GB — see §4.5 for the weight/caching story
revision = "…"

[budget]
confirm_above_eur = 0.01              # prompt for confirmation (soft)
per_operation_eur = 0.05              # hard ceiling — never exceeded, never prompted past
monthly_eur       = 5.00
timezone          = "UTC"              # makes "daily"/"monthly" unambiguous
on_exceed         = "abort"           # "abort" | "partial"

# Connected KBs. `id` is canonical; `name` is a local alias; `path` is machine-local.
# Schema present from v0.1 so IDs are stable; actually consumed from v0.3 (§8).
[[links.kb]]
name = "research-archive"
id   = "01JQ8ZM7…"
path = "~/kb/archive"
```

### 2.2 The sidecar — `<file>.pnk.yaml`

Auto-created at first ingest for **every** document, not only linked ones. This is deliberate: the
document ID lives here, and an ID that only appears once a doc is linked is an ID that cannot be
relied upon.

```yaml
id: 01JQ8ZC4V7K2N…            # ULID, assigned once, never regenerated
title: "Attention Is All You Need"
tags: [transformers, architecture]
created: 20260725 09:14
links:
  - to: pnk://01JQ8ZM7…/01JQ8ZD9M…   # <kb-ulid>/<doc-ulid> — portable across machines
    rel: cites
  - to: pnk://self/01JQ8ZE1P…        # `self` accepted on input; expanded to this KB's ULID on write
    rel: supersedes
provenance:
  source: https://arxiv.org/abs/1706.03762
  ingested: 20260725 09:14
```

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
| `documents` | id, path (relative, POSIX separators), content_hash, sidecar_hash, mtime, source_type, title, metadata (JSON), state (`active` / `deleted`) — `sidecar_hash` is what lets §6.4 notice a sidecar-only edit |
| `chunks` | id, doc_id, ordinal, text, char span, token count, heading path |
| `chunks_fts` | FTS5 external-content table over `chunks.text`, kept in sync by triggers — BM25 |
| `embeddings` | chunk_id, vector (float32 BLOB) — the single representation; tier 1 loads it into one contiguous NumPy array at open |
| `links` | src_kb_id, src_doc_id, dst_kb_id, dst_doc_id, rel, origin (`sidecar` = authored here, `reverse-scan` = discovered in a connected KB's sidecars). `src_kb_id` is required: a reverse link's *source* lives in another KB, and without it inbound and outbound edges are indistinguishable |
| `kb_refs` | connected KB id → alias, last resolved path, last scan time |
| `failures` | doc path, stage, error, timestamp — see §6.4 |
| `meta` | schema_version, build_id, embedding model + revision, vector tier, build timestamps |

**Index schema migrations do not exist.** On `schema_version` mismatch the index refuses to open and
instructs `pnk sync --rebuild`. Because `.pinakes/` is disposable and rebuilds are free, migration
code would be pure liability — this is the payoff of the truth/derived split.

### 3.1 Vector search: what the tiers actually buy

| Chunks | Strategy | Reality |
|---|---|---|
| < 50k | NumPy exact cosine over one in-process float32 array | **2.25 ms/query** measured at 50k×384 on this laptop, 77 MB resident. Zero extra dependency, exact, nothing to tune or corrupt |
| 50k – ~2M | `sqlite-vec` `vec0` table in the same file | Scanned from disk with SIMD, with int8/binary quantization + rescoring. Keeps RAM bounded and the single-file property intact |
| > ~2M | Documented ceiling; `pnk doctor` says so plainly | Honest advice is "split the KB" — pretending otherwise is how tools lie |

**Correction on the record:** `sqlite-vec` is **not an ANN index**. Verified against upstream
(20260725): it performs exhaustive KNN over `vec0` tables and its README advertises "fast enough",
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
`enable_load_extension` available. uv-managed CPython 3.13 satisfies both (verified 20260725: SQLite
3.53.1, FTS5 present, extension loading permitted); some system Pythons are built without them, so
`pnk doctor` probes both and reports a precise remedy rather than failing at query time.

---

## 4. Retrieval

### 4.1 The free pipeline (every query, €0)

```
query
 └─ metadata filter        (SQL WHERE: tags, path, date, source_type)
 └─ parallel:
      ├─ BM25 via FTS5     → candidates_per_source (50)
      └─ vector search     → candidates_per_source (50)
 └─ Reciprocal Rank Fusion (k=60) → fusion_top_k (20)
 └─ local cross-encoder rerank (optional, on by default) → final_k (8)
 └─ cited passages + doc IDs + confidence signal
```

Each stage's width is a distinct manifest field (§2.1); a single `top_k` would be ambiguous across
three different cut-offs.

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

### 4.5 Embedding backends, install, and model weights

`sentence-transformers` is the default backend: widest model selection, best quality ceiling, most
documentation. It pulls torch (~2GB), so **the documented install line includes the extra**:

```
uv add "pinakes[st]"                     # standard install — default backend
uv add "pinakes[light]"                  # fastembed (ONNX, ~100MB, no torch)
uv add pinakes                           # core only: parsing, FTS5, storage, MCP, CLI
uvx --from "pinakes[st]" pnk serve       # zero-install MCP server
```

A core-only install cannot embed. That is a supported state, not a broken one: any command needing
embeddings fails immediately with the exact extra to install, and `pnk doctor` reports it. CI runs
`[light]` — a 2GB torch download per job is untenable.

Both extras also provide the default reranker (§2.1): `BAAI/bge-reranker-base` exists under the same
id in `sentence-transformers` and in fastembed's registry (~1.04 GB of weights). Weights are a
*model download*, not an install cost, so the extras stay light — but CI must **cache `HF_HOME`**
(keyed on the model ids + revisions in the demo KB's manifest) so the ~1.4 GB of embedding + reranker
weights download once per cache key, not once per job. Without that cache the reranker would recreate
the very per-job download problem the extras split exists to avoid.

Model weights go to the **shared Hugging Face cache** (`HF_HOME`), never `.pinakes/cache/`, so N KBs
on a machine share one copy. One backend needs help to honour that: fastembed left alone caches to
`$TMPDIR/fastembed_cache`, not the HF cache (verified upstream, 20260725) — so the fastembed backend
always passes an explicit cache directory under `HF_HOME`, making the shared-cache statement true by
construction on both backends rather than an assumption that silently fails on `[light]`. `.pinakes/cache/` holds only KB-derived artifacts. `pnk doctor` reports
whether the configured model is present locally, and `--offline` fails fast instead of reaching out.

### 4.6 Chunking and tokens

`max_tokens` is counted with **the embedding model's own tokenizer**, and validated at sync against
the model's `max_seq_length` minus special tokens (bge-small-en-v1.5: 512 → 510). A manifest asking
for more is a hard error, not a silent truncation — a truncated chunk is a chunk whose tail is
unsearchable, and nothing in the output would reveal it. Chunks that cannot be encoded whole are
split, never trimmed.

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

---

## 5. Cost control

Nothing in v0.1–v0.3 costs money — the paid path doesn't exist yet. The budget system ships in the
same release as the first thing that can spend (`--deep`), which is the honest ordering.

| Control | Mechanism |
|---|---|
| **Estimate before running** | Dry-run the plan, count input tokens locally, price from a versioned table, print `~€0.014`, and prompt above **`confirm_above_eur`** — a separate, lower field than the hard cap. Confirming at the same number that aborts would make the prompt unreachable |
| **Hard cap per operation** | **Pre-call reservation.** Actual cost is only known from the response, so before each call the accountant reserves worst case = (counted input tokens + the request's output-token bound) × price. If spent + reserved > cap, **the call is never made**. The cap is therefore a real ceiling, at the price of slight over-reservation; the response's true usage is reconciled into the ledger afterwards |
| **What "operation" means** | One user-facing invocation — a whole `pnk ask --deep`, not one API call. `--deep` is a loop, so the cap is a *running total* across every call it makes; the loop halts when the next reservation would breach it. A per-call cap would let an N-step loop spend N× the stated limit, which is the failure this control exists to prevent |
| **Rolling ledger** | `.pinakes/ledger.jsonl`, append-only. Windows computed in `[budget] timezone`. Each line is a single sub-4KB `O_APPEND` write, atomic on POSIX, so concurrent processes cannot interleave a record |
| **Visibility** | `pnk budget` shows spend by day/month/operation. Real per-KB cost data, not vibes |

**The ledger stores no query text and no document content** — timestamp, operation, model, token
counts, cost, KB id, nothing more. It is diagnostics, not a transcript, and must never become an
accidental log of what you asked.

Pricing lives in a data file with an explicit `as_of` date; `pnk doctor` warns when it is stale, and
`--deep` refuses to estimate against prices older than a configurable age. A cost estimator built on
silently outdated prices is a liability.

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

Three consequences the table implies but must be stated:

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

---

## 8. Delivery plan

**v0.1 — thin vertical slice, end to end**

`pnk init` (one template) · `pnk sync` + `--rebuild` with the full §6.4 semantics · Markdown/text/code
ingest · structural chunking · local embeddings · FTS5 + NumPy exact vector + RRF · **local
cross-encoder rerank** (the §4.2 confidence signal is fitted on its scores, so it cannot ship later
than the signal) · metadata filters · **`pnk search`** — the CLI query surface §4.2's escalation
message depends on; a "vertical slice" that can only be queried over MCP would not reach end to end ·
`pnk doctor` (environment/FTS5, backend, model coherence, orphans, duplicate IDs, hook status, held
sync lock) · `pnk install-hooks` (§6.3 three-hook split) · WAL/read-only/lock policy (§6.5) ·
`pnk serve` — MCP server (`pinakes_search`, `pinakes_get`, `pinakes_list_kbs`) · golden-set eval
harness · CI (uv, ruff, pyright, pytest, `HF_HOME` cache §4.5) · Apache-2.0 · PyPI release.

Features deferred past v0.1, but whose **schema and identifiers ship in v0.1 because they cannot be
retrofitted**: ULID document *and* KB IDs, sidecar generation for every document, the manifest schema
including model-coherence fields and `[[links.kb]]`, and the `pnk://<kb-ulid>/<doc-ulid>` URI form.
Adding stable IDs to a populated KB later means either renumbering (breaking every link) or a
migration this design deliberately has no machinery for.

| Release | Adds | Why this order |
|---|---|---|
| v0.2 | PDF ingest (pymupdf), extraction cache, extraction quality tests | Parsing is the biggest quality risk; isolate it from core-design feedback |
| v0.3 | `pnk link`, `pinakes_links`, cross-KB traversal, sidecar scanning, link-coverage reporting | Needs two populated KBs to be worth anything |
| v0.4 | `pnk ask --deep`, budget ledger, reservations, `pnk budget` | First paid path and its guardrails ship together |
| v0.5 | Template ecosystem, `pnk upgrade` migrations, `sqlite-vec` tier | Generalisation, once real usage has shaped one template well |

**MCP tools are namespaced `pinakes_*`, not `kb_*`.** An agent commonly has several servers loaded at
once, and a tool called `kb_search` is a collision waiting to happen. Every tool takes an explicit
`kb` argument (alias or ULID) defaulting to the server's configured KB.

---

## 9. Known risks

| Risk | Assessment |
|---|---|
| **PDF extraction quality** | The most likely source of silent quality loss (tables, multi-column, scans). Mitigation: extraction tests on known-hard documents; `pnk doctor` flags suspiciously low text yield; scanned-PDF OCR is explicitly out of scope in v1 |
| **Linear search at scale** | No tier is sublinear (§3.1). Mitigation: measured limits published, `pnk doctor` warns as the ceiling nears, splitting is the documented answer |
| **Link coverage ceiling** | See §6.2. Measured and reported rather than hidden |
| **Sidecar/document separation** | A user moving a file without its sidecar is the most likely real-world corruption. Mitigated by hash-based rename detection (§6.4) and `pnk doctor`; not eliminated |
| **Confidence heuristic** | Uncalibrated abstention would be worse than none. Mitigated by golden-set calibration, `unknown` as an honest default, and measured false-abstain rate |
| **`sqlite-vec` maturity** | Pre-v1, breaking changes expected. Contained: only reached above 50k chunks, deferred to v0.5, NumPy tier remains a supported override |
| **torch install weight** | ~2GB for the default backend, plus ~1.4GB of model weights (embedding + reranker). Contained by the extras split and the CI `HF_HOME` cache (§4.5); CI runs `[light]` |
| **Template versioning** | Migrations are shown, never auto-applied (§6.1); templates version independently of the package |
| **Scope creep via `--deep`** | The paid loop is where this design could grow a second, worse agent framework. Bounded by: same tools as MCP, hard caps, and no orchestration the free path doesn't have |
| **Environment assumptions** | FTS5 and (for v0.5) loadable extensions are not universal in system Pythons. Probed by `pnk doctor` with a named remedy; uv-managed CPython is the supported baseline (§3.1) |
| **Accidental publication** | Publishing a KB repo exposes `docs/` and every sidecar, provenance URLs included (§4.7). Mitigated by shipped `.gitignore`, an index/ledger that never leaves the machine, and explicit docs — not by anything the engine can enforce |

---

## 10. Iteration log

**Pass 1** — 6 HIGH, 15 MEDIUM, 5 LOW resolved.
*HIGH:* `sqlite-vec` wrongly described as an ANN index (verified false upstream — §3.1 rewritten and
the tiering rationale corrected to bounded memory); reverse cross-KB links specified against the
other KB's gitignored index, impossible after clone (now scans committed sidecars, §6.2);
`pnk://` URIs used local aliases, breaking on share (now KB ULIDs, §2.2); rename/orphan/duplicate-ID
sync semantics unspecified (§6.4 added); per-operation budget cap claimed a guarantee it could not
deliver post-hoc (now pre-call reservation, §5); v0.1 omitted `pnk sync`, `pnk doctor` and hooks
though every other section depended on them (§8).
*MEDIUM:* MCP tools renamed `kb_*` → `pinakes_*` for namespace safety; multi-hop scope stated as
single-KB in v0.1; "no network" qualified against first-use model download and weights moved to the
shared HF cache; embedding storage described two ways, unified on a float32 BLOB; confidence signal
recast as calibrated with term-coverage demoted to a tiebreak; token limits validated against the
model's own tokenizer; template versioning decoupled from package version; install line corrected to
`uvx --from "pinakes[st]" pnk` with core-only behaviour defined; sync partial-failure semantics and
`failures` table added; WAL/read-only/lock concurrency policy added (§6.5); orphaned-sidecar deletion
made opt-in; paths fixed as KB-root-relative; index migration policy stated as rebuild-only; ledger
privacy and append atomicity specified; `pnk build` unified into `pnk sync --rebuild`.
*LOW:* budget window timezone; FTS5 external-content triggers; RRF k=60; latency claim replaced with
a measured 2.25 ms at 50k×384; golden-set size and coverage targets.

**Pass 2** — 1 HIGH, 7 MEDIUM, 5 LOW resolved. Several were introduced *by* pass 1's fixes, which is
the argument for looping rather than reviewing once.
*HIGH:* the `--rebuild` swap added in pass 1 renamed a WAL-mode database without checkpointing,
leaving a stale `-wal` beside a new `index.db` — a corrupt read. Now checkpoint-truncate, clean
close, then rename (§6.5).
*MEDIUM:* "operation" undefined for the per-op cap, letting an N-step `--deep` loop spend N× the
limit (§5); §4.2 referenced calibration thresholds the manifest had no field for (§2.1); the `links`
schema could not represent a reverse link, whose source doc lives in another KB (`src_kb_id` +
`origin` enum added); §3.1 presented three tiers as if all shipped, with v0.1 behaviour above 50k
chunks undefined; duplicate-content files made hash-based rename detection ambiguous with no
tie-break (§6.4); MCP server boundary and prompt-injection posture unstated (§4.7); FTS5 /
`enable_load_extension` treated as universally available — verified present on uv-managed CPython
3.13, now probed by `pnk doctor`.
*LOW:* a single `top_k` covered three different cut-offs (split into `candidates_per_source` /
`fusion_top_k` / `final_k`); `max_tokens` sat under `[embedding]` though §4.6 treats it as chunking;
`[[links.kb]]` present from v0.1 but unused until v0.3, now labelled; what publishing a KB repo
exposes; reverse-link origin provenance.

**Pass 3** — 1 HIGH, 3 MEDIUM, 4 LOW resolved.
*HIGH:* §6.3 said `--rebuild` "discards `.pinakes/`", which would delete `ledger.jsonl` — the spend
history §5's rolling budget is computed from. A routine maintenance command would have silently reset
the budget. Rebuild now replaces `index.db` only; `cache/` clearing is opt-in.
*MEDIUM:* the server's staleness check read `meta.build_id` through its own open connection, which
after a rename still points at the old inode and would report the old id forever — replaced with a
per-request `stat()` on the path (§6.5); `per_operation_eur` served as both the confirm threshold and
the hard ceiling, making the confirmation prompt unreachable (split into `confirm_above_eur` +
`per_operation_eur`, §2.1/§5); §6.4 framed pairing as ordered per-file rules, but rename and
duplicate detection require the whole before/after set — restated as an explicit two-phase algorithm.
*LOW:* v0.1's `pnk doctor` list omitted the environment probe §3.1 depends on, and `pnk serve` was
referenced in §4.5 but absent from the release list; "aliases … never stored" contradicted the
manifest that stores them (clarified: never inside a URI); the reservation formula reused the name
`max_tokens`, which `[chunking]` already claims; "not in v0.1 but present from day one" reworded.

**Pass 4** — 2 MEDIUM resolved, both self-inflicted by pass 3.
The rebuild bullet still ended "readers detect the new `build_id` and reopen" — directly contradicting
the `stat()`-based detection added three lines above it in the same pass (§6.5, now reconciled;
`build_id` is retained for provenance only). And `pnk://self/…` was left unexpanded, so a sidecar
copied into another KB would silently retarget its link at the *new* KB — `self` is now expanded to
the owning KB's ULID on write, like every other alias (§2.2). A grep sweep confirmed no stale
`kb_*` tool names, `pnk build`, or bare `top_k` references survive outside the log.

**Pass 5** — 0 findings. Verified by re-reading §§1–10 in full and grepping for every identifier
renamed across passes 1–4. No section contradicts another; every external claim (`sqlite-vec` is
exhaustive not ANN, FTS5 + extension loading on uv-managed CPython 3.13, `pinakes` free on PyPI,
2.25 ms at 50k×384) was measured or fetched in-session rather than recalled; every locked constraint
is honoured; every capability in §1 maps to a release in §8. Review complete.

**Pass 6** (20260725, implementation-readiness review) — 2 HIGH, 2 MEDIUM, 1 LOW resolved; the two
product calls were decided by the user, not the review.
*HIGH:* the reranker was simultaneously a v0.1 default (`rerank = "local"` in §2.1, "on by default"
in §4.1, its scores the substrate of §4.2's confidence signal, "rerank precision" in §7's v0.1 CI)
and a v0.5 deliverable in §8 — a freshly-inited KB would have defaulted to a stage that didn't
exist, and v0.1 would have shipped with no defined confidence signal. Resolved: the reranker ships
in v0.1; default `BAAI/bge-reranker-base` (user decision — same id on both backends beats the
smaller ms-marco model's provider-specific ids), a `[rerank]` manifest block mirroring
`[embedding]`, `fitted_for` added to `[retrieval.confidence]`, and a CI `HF_HOME` cache so ~1.4GB
of weights download per cache key, not per job (§2.1, §4.5, §8). And §8's v0.1 had no CLI query
surface at all — `pnk search` existed in §4.2's escalation story, the CLI stub and the README, but
not in the release that claims "end to end". Added explicitly (§8).
*MEDIUM:* the `post-commit` hook wrote sidecars, dirtying the tree it had just committed — every
document commit would trail an untracked `.pnk.yaml` forever. Resolved with a three-hook split:
`pre-commit` mints and stages sidecars for staged documents only, `post-commit`/`post-merge` touch
the index only (§6.3). And a stale `sync.lock` from a killed sync silently disabled hook-driven
freshness forever ("a second sync exits immediately" had no liveness story). Resolved: the lock
records pid/host/start-time; dead-pid locks are reclaimed with a warning, cross-host locks refuse
with `--force-unlock` as the human path, `pnk doctor` reports held locks (§6.5).
*LOW:* the sidecar's `content_hash` duplicated `documents.content_hash`, was read by nothing, and
guaranteed a two-file diff on every document edit while going stale whenever sync hadn't run —
dropped from the sidecar (user decision); change detection is index-only, stated in §2.2.

**Pass 7** (20260725, surfaced while adversarially reviewing `plans/v0.1.md` — the implementation
plan's review loop reads the design fresh each pass, which is how these escaped passes 1–6).
*HIGH:* §4.5 claimed model weights go to the shared HF cache on both backends — false for fastembed,
which defaults to `$TMPDIR/fastembed_cache` (verified upstream): CI's `HF_HOME` cache would never
hit and `pnk doctor`'s weights check would probe the wrong directory. The fastembed backend now
passes an explicit cache dir under `HF_HOME`, making the claim true by construction.
*MEDIUM:* a sidecar-only edit (tags/title/links changed, document untouched) fell through §6.4's
"path and hash unchanged → Skip" and was never re-indexed — `documents.sidecar_hash` added (§3) and
the sidecar-only change class stated (§6.4); soft delete left chunks and embeddings searchable —
removal on soft delete stated, identity row retained (§6.4); rename+edit in one sync had both the
adoption and deletion rows firing for the same ID with no stated winner — sidecar adoption now wins,
no soft delete emitted, and the sidecar-didn't-travel case is reported at sync time (§6.4).
