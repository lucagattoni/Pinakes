# Guide — using pinakes

How to build, feed, search and share a knowledge base. Every command here was run against 0.2.0
(20260728 16:40); the output shown is real.

For the flag-by-flag reference see [CLI.md](CLI.md); for every manifest and sidecar field see
[MANIFEST.md](MANIFEST.md); for whether a feature exists yet see [STATUS.md](STATUS.md).

- [Install](#install)
- [Your first KB](#your-first-kb)
- [Choosing a backend](#choosing-a-backend)
- [Indexing PDFs](#indexing-pdfs)
- [Searching](#searching)
- [Keeping the index fresh](#keeping-the-index-fresh)
- [Using it from an agent](#using-it-from-an-agent)
- [Health checks](#health-checks)
- [Moving, sharing and publishing a KB](#moving-sharing-and-publishing-a-kb)
- [Troubleshooting](#troubleshooting)

---

## Install

```bash
uv add "pinakes[st]"          # default backend
uv add "pinakes[light]"       # ONNX, no torch
uv add "pinakes[light,pdf]"   # + PDF ingest
```

Python 3.13+. To try it without installing anything:

```bash
uvx --from "pinakes[light]" pnk --version
```

**To install unreleased work from `main`** — a contributor, or anything in
[STATUS](STATUS.md#the-surface-you-can-use-today) marked "on `main`, unreleased":

```bash
uv add "pinakes[light] @ git+https://github.com/lucagattoni/Pinakes"
```

| Extra | Pulls | Gives you |
|---|---|---|
| *(none)* | — | Parsing, FTS5, storage, MCP, CLI. **Cannot embed** — a supported state, not a broken one |
| `[st]` | `sentence-transformers` (~2 GB, torch) | Default backend; widest model choice |
| `[light]` | `fastembed` (~100 MB, ONNX) | Same default models, no torch |
| `[pdf]` | `pypdfium2` | Free PDF text extraction |
| `[claude]` | Anthropic SDK — **requires `[pdf]`** | The opt-in paid extractor. Built, but [in no release yet](STATUS.md) — `main` only |

Extras compose: `pinakes[light,pdf]` is a normal install. A core-only install fails with the exact
extra to add, rather than a traceback:

```
error: the `sentence-transformers` backend is not installed.
Install it with `uv add "pinakes[st]"`. A core-only install can index and search nothing that
needs embeddings — that is expected, not a fault.
```

Model weights are a separate, one-time **download**, not part of the install: about 1.4 GB for the
default embedding + reranker pair, cached in the shared `HF_HOME` so every KB on the machine shares
one copy.

## Your first KB

```bash
pnk init my-kb --name "My notes"
```

```
created /path/to/my-kb from notes@1.0
  kb id: 01KYMJMH8ECH945D5056CJD72V  (permanent — never edit it)

Next:
  1. put Markdown files in /path/to/my-kb/docs
  2. `pnk sync` to index them, then commit the sidecars it writes
  3. `pnk search "…"` to search, for free, offline
```

You get:

```
my-kb/
├── pinakes.toml     # the manifest — sources, models, chunking, budget
├── docs/            # SOURCE OF TRUTH: your files, never modified
└── .gitignore       # ships covering .pinakes/
```

**That KB id is permanent.** Every cross-KB link ever written to this KB resolves through it, and
there is no migration machinery by design. Never edit or regenerate it.

Drop a file in and index it:

```bash
echo '# Retrieval notes

Hybrid retrieval fuses BM25 with dense vectors using reciprocal rank fusion.' > my-kb/docs/retrieval.md

pnk sync --kb my-kb
```

```
1 indexed, 0 renamed, 0 metadata-only, 0 unchanged, 0 removed
```

Sync also wrote `docs/retrieval.md.pnk.yaml` — the **sidecar**, holding that document's permanent
ULID, its title, tags and links. Commit it alongside the document; the ID is the thing every inbound
link depends on. ([MANIFEST §sidecar](MANIFEST.md#the-sidecar--filepnkyaml))

`pnk sync` is incremental and free. It compares content hashes and re-processes only what changed,
so running it on every commit costs nothing.

## Choosing a backend

`pnk init` always stamps `sentence-transformers`, because it cannot see which extra you installed.
**On a `[light]` install, edit `pinakes.toml` before your first sync** — set `provider` in *both*
blocks:

```toml
[embedding]
provider = "fastembed"                 # was "sentence-transformers"
model    = "BAAI/bge-small-en-v1.5"
dim      = 384

[rerank]
provider = "fastembed"                 # this one too
model    = "BAAI/bge-reranker-base"
```

The model **ids are identical on both backends**, so only `provider` changes. Skip this and the
first sync stops with the core-only error above — accurate, but an avoidable wall.

Changing the embedding model later invalidates the index: queries refuse to run rather than return
garbage, and `pnk doctor` names the mismatch. `pnk sync --rebuild` fixes it, and costs nothing.

## Indexing PDFs

Needs `pinakes[pdf]`. **PDFs are not indexed by default** — the shipped template does not include
them, because `init` cannot see which extras you installed. `pnk sync` says so rather than leaving
you to guess:

```
0 indexed, 0 renamed, 0 metadata-only, 0 unchanged, 0 removed
1 file(s) matched no `include` pattern: .pdf (1) — add "**/*.pdf" to `[sources] include` to index them, or `exclude` them to silence this.
```

That line lists any file pinakes could have indexed but had no pattern for, grouped by extension.
Files it could not read either way — images, archives, anything not valid UTF-8 — are never
mentioned, since adding a glob for them would only produce a failed document. It also names
`pinakes[pdf]` when a PDF is waiting and the extractor is not installed, because adding the glob
alone would turn a skipped file into a failed one. `pnk sync --quiet` still prints it, on stderr.

Add the glob to your manifest:

```toml
[sources]
roots   = ["docs/"]
include = ["**/*.md", "**/*.txt", "**/*.pdf"]   # ← add the PDF glob
```

Then `pnk sync` extracts, chunks and indexes it like any other document. Extracted text is cached
under `.pinakes/cache/extract/`, keyed on the file's content hash and the extractor's fingerprint —
so a `--rebuild` re-indexes without re-extracting.

What the free path does and does not do:

| | |
|---|---|
| ✅ | Text-layer PDFs: columns, running heads stripped, hyphenation joined across line and page breaks |
| ✅ | Page spans recorded per chunk in the index |
| ✅ | `path:page` citations in results, on the CLI and the MCP surface alike — `docs/paper.pdf:p7`, or `:p7-8` for a chunk straddling a page break |
| ✅ | `pnk doctor` names the pages with no text layer, by path *and* page, before you decide whether to pay for any of them |
| ⚠️ | **Tables are read column by column, not row by row.** Column detection is geometric, not structural — a disclosed limitation, measured by `pair_adjacency` in the quality harness |
| ❌ | **Scanned / image-only PDFs.** The free path yields nothing on them. The paid extractor reads them — shipped, opt-in, and it spends: `pnk sync --extract=claude-vision` |

Filter to PDFs with `--source-type pdf`.

## Searching

```bash
pnk search "how are dense and lexical results combined" --kb my-kb
```

```
[1] docs/retrieval.md — Retrieval notes
    # Retrieval notes

    Hybrid retrieval fuses BM25 with dense vectors using reciprocal rank fusion.
    (docs/retrieval.md:0-95 (Retrieval notes))

confidence: unknown — no calibrated thresholds in the manifest ([retrieval.confidence])
retrieval-only result. Paid synthesis (`pnk ask --deep`) is planned for the deep release; until then,
narrowing the query or adding a filter is the lever you have.
```

Free, offline, and unlimited. The pipeline is BM25 (FTS5) + dense vectors, fused with reciprocal
rank fusion, then reranked by a local cross-encoder — all on your CPU.

**Filters** narrow before retrieval, and compose:

```bash
pnk search "conservation" --tag policy --tag draft     # repeatable; documents carrying the tag
pnk search "conservation" --path-prefix docs/policies/ # by path
pnk search "conservation" --source-type pdf            # markdown, text, code or pdf
pnk search "conservation" --modified-after 20260101    # by document mtime
pnk search "conservation" -k 20 --json                 # more passages, machine-readable
```

Tags come from the sidecar, so tagging a document means editing its `.pnk.yaml` — sync picks the
change up without re-embedding anything.

### About that `confidence: unknown`

It is the honest default, not a bug. Cross-encoder scores are not comparable across queries, so an
absolute threshold is meaningless until it is **fitted against a golden set for your own corpus**.
Thresholds fitted on someone else's corpus are not a calibration, so the template ships
`[retrieval.confidence]` commented out.

To calibrate: write questions with known-correct sources in `eval/questions.yaml`, then run
`pinakes.calibrate`, which *prints* a `[retrieval.confidence]` block for you to paste — it never
writes one. Until you do, every result reports `unknown`.

The cost of the heuristic once calibrated is published rather than hidden: measured false-confidence
on the demo corpus is **0.25** ([STATUS](STATUS.md#measured-numbers)).

## Keeping the index fresh

A KB is normally a git repo, and freshness is git-triggered:

```bash
pnk install-hooks --kb my-kb
```

Three hooks, split by what each is allowed to touch:

| Hook | Runs | Why the split |
|---|---|---|
| `pre-commit` | `pnk sync --sidecars-only --stage --extract=pypdfium2` | Mints IDs for **staged** documents and `git add`s the sidecars, so a document and its permanent ID land in the *same commit*. The only hook that writes into `docs/`. It refuses to overwrite a sidecar that will not parse, and that refusal fails the hook — repair the file, or `git commit --no-verify` |
| `post-commit` | `pnk sync --index-only --extract=pypdfium2` | Index only |
| `post-merge` | `pnk sync --index-only --extract=pypdfium2` | Index only |

Sidecars are authored at pre-commit time precisely so `post-commit` never dirties the tree it just
committed. `git commit --no-verify` is the escape hatch.

**Every hook forces the free extractor**, and `install-hooks` says so when it writes them. A hook is
non-interactive: on a KB configured for a paid backend, a hook without that flag would either abort
on every commit (nothing to confirm an estimate from) or spend afresh on every commit. A scanned PDF
committed this way is indexed with its empty free extraction and left *stale*, so a later
`pnk sync --extract=<paid-backend>` you run yourself picks it up — never skipped forever. `pnk
doctor` reports the combination and how many documents are waiting.

`pnk init --ci` writes a GitHub Actions workflow that does the same thing, for the same reason.

An existing hook that is not ours is left untouched and printed with the line to add. A hook that
cannot find `pnk` warns and exits 0 — a hook that fails every commit only teaches `--no-verify`.

No hooks? `pnk sync` from cron or CI works identically. It is safe to run concurrently: a second
sync finding a live lock exits 0 quietly, and `pnk doctor` reports any held lock with its age.

## Watching what it costs

Nothing in the shipped surface spends money yet — but the accounting is already there, and
`pnk budget` reads it:

```bash
pnk budget --kb my-kb
```

It prints today's and this month's spend against their caps, how many calls were reconciled, voided
or left with an **unknown outcome**, and the last few operations. On a KB that has never spent it
prints zeros; it can only ever read.

Caps live in `[budget]` ([MANIFEST](MANIFEST.md#budget)) and there are three, all enforced before
every call: `per_operation_eur` bounds one `pnk sync`, while `daily_eur` and `monthly_eur` bound
*sequences* of them — a per-operation cap alone is no protection against a hook-driven KB syncing
thirty times a day. **They are per KB**: ten paid KBs have ten monthly allowances, and there is no
global cap in this release.

An `unknown outcome` is a call that timed out: it may or may not have billed, so it keeps consuming
its reserved amount until you check the vendor's dashboard and close it:

```bash
pnk budget --kb my-kb --resolve <call_id> --actual 0.043
```

That **appends** a reconciliation — `.pinakes/ledger.jsonl` is append-only, survives every
`--rebuild` and every `--clear-cache`, and is the one thing in `.pinakes/` that cannot be
recomputed. Never edit it by hand.

## Using it from an agent

`pnk serve` speaks MCP. Point it at one or more KBs:

```bash
pnk serve /path/to/my-kb /path/to/other-kb
```

For Claude Code, add it to `.mcp.json`:

```json
{
  "mcpServers": {
    "pinakes": {
      "command": "pnk",
      "args": ["serve", "/path/to/my-kb"]
    }
  }
}
```

Or without installing anything:

```json
{
  "mcpServers": {
    "pinakes": {
      "command": "uvx",
      "args": ["--from", "pinakes[st]", "pnk", "serve", "/path/to/my-kb"]
    }
  }
}
```

Four tools, namespaced so they cannot collide with another KB server the agent has loaded:

| Tool | Does |
|---|---|
| `pinakes_search` | Ranked, cited passages with a confidence signal. Each carries `page_start`/`page_end` (both `null` for a source with no pages) beside the rendered citation |
| `pinakes_get` | A document by ULID. `page_start`/`page_end` read one range of a PDF; page boundaries come back marked by a line reading `[page N]` |
| `pinakes_links` | What a document connects to, and what connects to it. `depth` is capped at 3 server-side; a neighbour in another KB is returned and never expanded |
| `pinakes_list_kbs` | The KBs this server was pointed at |

**`pinakes_links` reports `confidence: "unknown"` on every call** — with a `query` and without one.
The signal `pinakes_search` reports is fitted per KB on the reranker score of a retrieved passage; a
traversal neighbour is not one, and a neighbour list spanning two KBs has no single manifest whose
thresholds would apply. `unknown` is the honest answer, and it is the only one this tool gives.

A neighbour in a KB **this server was not pointed at** still comes back — with its `kb_id`, its
`doc_id` and `reachable: false` — because a link that exists is worth knowing about even when this
process cannot follow it. Point `pnk serve` at both KBs and it becomes reachable; nothing about the
KBs themselves changed. A reachable neighbour in a *different* KB needs its `kb_id` passed too —
`pinakes_get(doc_id, kb=kb_id)`, since an id resolves inside one KB — and the row carries a
`fetch_with` object holding exactly that pair.

Rows come back **in rank order**. `score` is comparable only among rows with the same
`scored_by_query`: with a `query`, a neighbour with no local chunks to embed falls back to its edge
weight, which is a different scale from a cosine — so re-sorting by `score` reorders the list
against itself.

**One citation vocabulary across both surfaces.** An agent can cite `docs/paper.pdf:p7` from a
`get` exactly as it can from a `search` — the numbers are the same numbers, and the trace tests
assert that by comparing them.

**Multi-hop falls out of composition.** `pinakes_search → pinakes_get → pinakes_search` *is* a
plan-retrieve-read-refine loop, and your agent already runs it in its own context — on reasoning you
are already paying for. There is no second agent framework here, and the KB never spends your money.

Two boundaries worth knowing: the server answers **only** about the KBs named on its command line —
no tool argument accepts a filesystem path — and retrieved text comes back inside a delimited
evidence field stating it is data to reason about, never instructions to follow. A KB whose
documents say "ignore previous instructions" is a KB, not an exploit.

## Health checks

```bash
pnk doctor --kb my-kb
```

Checks the environment (SQLite version, FTS5, loadable extensions), the backend and whether weights
are cached, template drift, index/model coherence, calibration validity, orphaned sidecars,
duplicate IDs, dangling links and link coverage, recorded failures, the extraction cache, the
50k-chunk NumPy-tier threshold, a held sync lock, and hook status.

Every non-OK check carries a remedy. `--prune` is the only thing that changes anything, and it
prints every path before removing it.

## Moving, sharing and publishing a KB

A KB is a directory. Move it, copy it, commit it, hand it to someone — `.pinakes/` is derived state
and rebuilds for free with `pnk sync --rebuild`.

**Commit `docs/`, `pinakes.toml` and every sidecar. Never commit `.pinakes/`** — the shipped
`.gitignore` already covers it, which is what keeps your index (and, once it exists, your spend
ledger) off any remote.

⚠️ **Publishing a KB repo publishes every sidecar**, not just your documents — titles, tags and
`provenance.source` URLs included. Those routinely carry more signal than people expect. The engine
cannot enforce anything here; check before you push.

Links between KBs use `pnk://<kb-ulid>/<doc-ulid>` — ULIDs, never aliases — so they survive renames,
moves, and being shared with someone whose local alias for your KB is different. Authoring and
traversing them lands in the links release; the *schema* ships today precisely because IDs cannot be retrofitted.

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `the sentence-transformers backend is not installed` | `[light]` install, default manifest | Set `provider = "fastembed"` in `[embedding]` **and** `[rerank]` |
| `N file(s) matched no include pattern` | Those files are in your roots but no glob picks them up | Add the glob it names ([above](#indexing-pdfs)), or `exclude` them |
| A PDF indexes with no text | Scanned / image-only — the free path has no OCR | Needs the paid extractor, [in no release yet](STATUS.md) |
| `no extractor for .pdf` | `[pdf]` extra missing | `uv add "pinakes[pdf]"` |
| Queries refuse to run, naming a model mismatch | Embedding model changed since the index was built | `pnk sync --rebuild` — free |
| Index refuses to open, naming `schema_version` | Index predates 0.2.0 | `pnk sync --rebuild`. There are no migrations, by design |
| `confidence: unknown` on every search | No fitted `[retrieval.confidence]` | Expected. Calibrate against your own golden set ([above](#about-that-confidence-unknown)) |
| Sync exits non-zero listing documents | Per-document failures, isolated by design | `pnk doctor` lists them with the error; the rest of the corpus indexed fine |
| A sync seems stuck behind a lock | A killed sync, or another machine | `pnk doctor` reports the holder and age; `pnk sync --force-unlock` if it is not this host |
| Searches slow past ~50k chunks | NumPy tier is exact, not sublinear | Expected; `pnk doctor` warns. The `sqlite-vec` tier is the template release — splitting the KB is the honest answer |

Nothing here spends money, and nothing can: see [STATUS](STATUS.md#the-surface-you-can-use-today).

## Following links between two KBs

Two KBs know about each other through `[[links.kb]]`, and a link is written in the *source*
document's sidecar:

```toml
# archive/pinakes.toml
[[links.kb]]
name = "museum"                        # a local alias; it means nothing on another machine
id   = "01KYP11WY2ZGX9B2Q5V7PJ8DW1"    # the KB's ULID — this is what travels
path = "../museum"                     # where it lives here
```

```yaml
# archive/docs/loans-outward.md.pnk.yaml
links:
  - to: pnk://01KYP11WY2ZGX9B2Q5V7PJ8DW1/01KYP8878AZWS2ZWEBD0KQYTXE
    rel: counterpart
```

`pnk sync` records that link, and also reads the *other* KB's committed sidecars to learn what
points back:

```console
$ pnk sync --scan-links
30 indexed, 0 renamed, 0 metadata-only, 0 unchanged, 0 removed
inbound links: museum 6
```

Then ask what a document connects to:

```console
$ pnk links docs/loans-outward.md
-> related: conservation assessment  [hop 1]
<- governs: 01KYP88789WHHN93TW49AX096C (other KB)  [hop 1]
-> counterpart: 01KYP8878AZWS2ZWEBD0KQYTXE (other KB)  [hop 1]
```

`->` is a link written by the document the row hangs off — the one you asked about at hop 1,
its parent beyond that; `<-` is one pointing back, learned by scanning the other KB when it
lives there; `<->` is the same relation written from both ends. A
neighbour in another KB shows its ULID rather than a title, because this KB holds the partner's
*links*, not its documents.

Going deeper follows same-KB links only:

```console
$ pnk links docs/loans-outward.md --depth 2
-> related: conservation assessment  [hop 1]
<- governs: 01KYP88789WHHN93TW49AX096C (other KB)  [hop 1]
-> counterpart: 01KYP8878AZWS2ZWEBD0KQYTXE (other KB)  [hop 1]
-> related: pest management  [hop 2]
-> related: storage environment  [hop 2]
```

The two cross-KB neighbours are still there and still at hop 1: **a neighbour in another KB is
terminal**. Not because there is nothing beyond it — this index does hold that KB's links pointing
back here — but because expanding it would show a partial slice of someone else's graph that you
could not tell apart from the whole. To go further, open that KB and ask it.

`--json` adds `frontier` (what was found and not expanded, and why), `unresolved` (links whose
target is missing) and `truncated` (which caps bit).
