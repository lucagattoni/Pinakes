# Status — what ships today

**Latest release: 0.2.1** · `main` carries unreleased work — see the [increment
ledger](#v02-increment-ledger) · last reviewed 20260728 17:52

> **This file is the only place in the repo that says what is built.** Every other doc describes
> *how* something works or *why* it was designed that way, and links here for whether you can use it
> yet. When an increment lands, flip its row below — no other doc should need a version edit.
>
> "Shipped" below means **released**; an increment merged to `main` but not yet in a release says so
> explicitly. Installing from a tag and installing from `main` are different answers to "can I use
> this yet", and this file is where that difference has to be visible.

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
| Budget estimator, caps, window aggregation | **on `main`, unreleased** | I6a. The pure logic only — nothing calls it yet, so no behaviour changes |
| Budget ledger, `pnk budget`, spend enforcement | **not built** | v0.2 · I6b. Reading `ledger.jsonl` and wiring I6a's decisions to a real call |
| `path:page` citations | **not built** | v0.2 · I8 |
| Cross-KB links (`pnk link`, `pinakes_links`) | **not built** | v0.3 |
| `sqlite-vec` tier, template ecosystem | **not built** | v0.5 |

**Nothing in the shipped surface can spend money.** The only paid code path in the design is the
`claude-vision` extractor, and it is a stub. See [DESIGN §5](DESIGN.md#5-cost-control).

### Caveat: PDFs are off by default (but no longer silently)

`pnk init` stamps `include = ["**/*.md", "**/*.txt"]`, so PDFs need one manifest edit: add
`"**/*.pdf"` to `[sources] include` ([GUIDE](GUIDE.md#indexing-pdfs)). The generated manifest spells
out the glob and the extra it needs, and since 0.2.2 `pnk sync` names any file it skipped for want
of a pattern instead of reporting `0 indexed` and explaining nothing. It stays off by default
because `init` cannot see whether `pinakes[pdf]` is installed, and a glob stamped without it turns
every PDF into a failed document rather than a skipped one.

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
| I6a | Budget core, pure — estimator, reservation, `prices.toml` | **on `main`, unreleased** |
| I6b | Budget I/O — ledger, prompt, `pnk budget`, hooks that cannot spend | **planned** |
| I7a | The paid-path allowlist gate and the invariant amendments | **planned** |
| I7b | The paid Claude-vision extractor — request shape, validation, retries | **planned** |
| I7c | The completeness audit, staging, all-or-nothing commit | **planned** |
| I8 | `pnk doctor` text yield, `path:page` citations on both surfaces | **planned** |
| I9 | Docs sweep, template, CI | **planned** |

**Decided 20260728 17:52 — I6–I9 accumulate, and cut as one MINOR release.** `plans/v0.2.md`
assumed a single release at I9; 0.2.0 was instead released after I5, correctly, since I1–I5 was
complete, self-contained, user-visible work the project's rule forbids leaving in `[Unreleased]`.
The remaining increments are **not** the same shape: I6a, I6b and I7a are each explicitly partial —
the budget core is pure logic nothing calls, and I6b's own title is "hooks that *cannot* spend".
None adds a capability a user can reach, so none passes the SemVer table on its own. They therefore
stay in `[Unreleased]` until paid extraction is genuinely usable (I7b) and safe (I7c), and that
lands as **one MINOR bump — never a 0.2.x patch**, since a KB that can spend money is new
capability, not a fix. Patch releases in between remain available for work that stands alone (0.2.1,
the documentation restructure, was exactly that).

> ⚠️ **The number itself is unassigned, because `0.3` is already taken.** Every doc here — plus
> `docs/graph/` and [DESIGN §8](DESIGN.md#8-delivery-plan) — uses **v0.3** to mean the cross-KB
> links release. The next MINOR after 0.2.x is 0.3.0, so either paid extraction takes 0.3.0 and the
> graph work shifts to 0.4 (cascading through `ask --deep` and templates), or the graph line keeps
> its number and paid extraction takes something else. That is a roadmap decision, not a
> documentation one, and renumbering ~15 committed references — including research documents — is
> not something to do silently. **Resolve before cutting the release**, and per
> [CLAUDE.md](../CLAUDE.md)'s rule, re-check what has landed on `main` at that moment rather than
> trusting this note.

---

## Release roadmap

Rationale for the ordering is in [DESIGN §8](DESIGN.md#8-delivery-plan).

Rows below the released ones are **ordered scope, not assigned version numbers** — the `v0.x` labels
are how the docs have long referred to each body of work, and one of them now collides with the next
MINOR (see the warning above). A number belongs to a release when it is cut, not years ahead of it.

| Release | Adds |
|---|---|
| **0.2.0** ✅ | Free PDF ingest, extraction cache, page provenance in the index, extraction-quality scoring |
| **0.2.1** ✅ | Documentation restructure — one fact one home; three stale-claim fixes |
| *next MINOR* | Budget machinery, the opt-in paid Claude-vision extractor, `path:page` citations (I6–I9) |
| "v0.3" | `pnk link`, `pinakes_links`, cross-KB traversal, link-coverage reporting, free structural edges — build order in [`graph/PINAKES_APPROACH.md`](graph/PINAKES_APPROACH.md) §10 |
| "v0.3.x" | PPR graph channel, the `[ner]` extra — each eval-gated, not scheduled |
| "v0.4" | `pnk ask --deep` |
| "v0.5" | Template ecosystem, `pnk upgrade` migrations, the `sqlite-vec` tier |

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
