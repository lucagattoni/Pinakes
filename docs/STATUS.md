# Status — what ships today

**Installed version: 0.2.0** · last reviewed 20260728 16:40

> **This file is the only place in the repo that says what is built.** Every other doc describes
> *how* something works or *why* it was designed that way, and links here for whether you can use it
> yet. When an increment lands, flip its row below — no other doc should need a version edit.

---

## The surface you can use today

| Command | State | Notes |
|---|---|---|
| `pnk init` | shipped | one template (`notes`) |
| `pnk sync` | shipped | `--rebuild`, `--sidecars-only`, `--index-only`, `--extract`, `--force`, `--clear-cache` |
| `pnk search` | shipped | BM25 + vector + rerank, metadata filters, `--json` |
| `pnk doctor` | shipped | environment, coherence, orphans, links, hooks, cache |
| `pnk install-hooks` | shipped | the three-hook split |
| `pnk serve` | shipped | MCP: `pinakes_search`, `pinakes_get`, `pinakes_list_kbs` |
| `pnk budget` | **not built** | v0.2 · I6b |
| `pnk ask --deep` | **not built** | v0.4 |

| Capability | State | Notes |
|---|---|---|
| Markdown / text / code ingest | shipped | |
| **PDF ingest, free path** | shipped | `pypdfium2`, needs `pinakes[pdf]`. **Off by default — see the caveat below** |
| Extraction cache | shipped | `.pinakes/cache/extract/` |
| Page provenance (`page_start`/`page_end`) | shipped in the **index** | not yet surfaced in results — I8 |
| Extraction quality scoring | shipped | `make pdf-eval` against `tests/pdf-corpus/` |
| **PDF ingest, paid path** (scanned PDFs) | **not built** | v0.2 · I7b. `claude-vision` is a stub that names its increment |
| Budget ledger, reservations, caps | **not built** | v0.2 · I6a/I6b. `[budget]` is parsed and validated; nothing reads it |
| `path:page` citations | **not built** | v0.2 · I8 |
| Cross-KB links (`pnk link`, `pinakes_links`) | **not built** | v0.3 |
| `sqlite-vec` tier, template ecosystem | **not built** | v0.5 |

**Nothing in the shipped surface can spend money.** The only paid code path in the design is the
`claude-vision` extractor, and it is a stub. See [DESIGN §5](DESIGN.md#5-cost-control).

### Caveat: PDFs are off by default

`pnk init` stamps `include = ["**/*.md", "**/*.txt"]`. A PDF dropped into a fresh KB is **silently
skipped** — sync reports `0 indexed` and explains nothing. Add `"**/*.pdf"` to `[sources] include`
yourself ([GUIDE](GUIDE.md#indexing-pdfs)). The template gains a commented-out line in I9.

### Caveat: the `[light]` backend needs a manifest edit

`pnk init` always stamps `provider = "sentence-transformers"` — it cannot see which extra you
installed. On a `pinakes[light]` install, set `provider = "fastembed"` in **both** `[embedding]` and
`[rerank]` before the first sync ([GUIDE](GUIDE.md#choosing-a-backend)).

---

## v0.2 increment ledger

The build order is [`plans/v0.2.md`](../plans/v0.2.md). Each increment is a separate, bisectable
landing with its own tests.

| # | Increment | State |
|---|---|---|
| I1 | Extras, the extractor seam, core-only failure | shipped 0.2.0 |
| I2 | The synthetic hard-case PDF corpus and its generator | shipped 0.2.0 |
| I3a | Extraction core, pure — chars to ordered text | shipped 0.2.0 |
| I3b | The `pypdfium2` adapter, quality metrics, two fitted floors | shipped 0.2.0 |
| I4 | The extraction cache | shipped 0.2.0 |
| I5 | PDF chunking, page provenance, backend-aware sync (`schema_version` 2) | shipped 0.2.0 |
| I6a | Budget core, pure — estimator, reservation, `prices.toml` | **planned** |
| I6b | Budget I/O — ledger, prompt, `pnk budget`, hooks that cannot spend | **planned** |
| I7a | The paid-path allowlist gate and the invariant amendments | **planned** |
| I7b | The paid Claude-vision extractor — request shape, validation, retries | **planned** |
| I7c | The completeness audit, staging, all-or-nothing commit | **planned** |
| I8 | `pnk doctor` text yield, `path:page` citations on both surfaces | **planned** |
| I9 | Docs sweep, template, CI | **planned** |

**Open: I6–I9 have no version target.** `plans/v0.2.md` cuts 0.2.0 at the end of I9, but 0.2.0 was
released after I5 — correctly, since I1–I5 is complete, self-contained, user-visible work that the
project's own rule says must not sit in `[Unreleased]`. The remaining increments therefore need a
new target (0.3.0, or 0.2.x each). Decide before I6a lands, and record it here.

---

## Release roadmap

Rationale for the ordering is in [DESIGN §8](DESIGN.md#8-delivery-plan).

| Release | Adds |
|---|---|
| **0.2.0** ✅ | Free PDF ingest, extraction cache, page provenance in the index, extraction-quality scoring |
| v0.2 remainder | Budget machinery, the opt-in paid Claude-vision extractor, `path:page` citations |
| v0.3 | `pnk link`, `pinakes_links`, cross-KB traversal, link-coverage reporting, free structural edges — build order in [`graph/PINAKES_APPROACH.md`](graph/PINAKES_APPROACH.md) §10 |
| v0.3.x | PPR graph channel, the `[ner]` extra — each eval-gated, not scheduled |
| v0.4 | `pnk ask --deep` |
| v0.5 | Template ecosystem, `pnk upgrade` migrations, the `sqlite-vec` tier |

## Measured numbers

Re-measure and re-date these whenever retrieval or extraction changes; never carry one forward
unverified.

| Metric | Value | Measured |
|---|---|---|
| recall@5 | 0.879 | 20260725 18:55, demo KB, `[light]` models |
| MRR | 0.774 | 20260725 18:55 |
| rerank precision | 0.727 | 20260725 18:55 |
| false-abstain | 0.03 | 20260725 18:55 |
| **false-confidence** | **0.25** | 20260725 18:55 — one no-answer question in four still gets a confident answer |
| NumPy vector tier | 2.25 ms/query at 50k×384, 77 MB resident | 20260725 13:49 |

The false-confidence figure is fitted and scored on the same 41-question set (8 of them no-answer),
so treat it as a floor rather than an estimate. Publishing it is the point:
[DESIGN §4.2](DESIGN.md#42-escalation--free-path-first) commits to measuring the heuristic's cost
rather than assuming it away.

## Not published yet

The package is **not on PyPI** — trusted publishing is unconfigured, so the release workflow's
upload step is gated on the `PUBLISH_TO_PYPI` repository variable and skipped while it is unset.
Tagging is always safe: version/tag agreement, the build and an isolated wheel smoke test still run.
Install from git until then ([GUIDE](GUIDE.md#install)).
