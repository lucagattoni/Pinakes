# Graph, RAG and agents — what the research says, and what pinakes should do

> ℹ️ **Version numbers below reflect the convention in use when this was written.** Unbuilt
> work is now **named, not numbered** ([STATUS.md](../STATUS.md)). This record is left as it was.

**Status:** research summary + recommendations · **Date:** 20260725 15:12 (file mtime — the doc
predates its commit)
**Scope:** whether pinakes should acquire a graph layer, and if so, which one
**Relates to:** [`../DESIGN.md`](../DESIGN.md) §4 (retrieval), §6.2 (links), §8 (roadmap)
**Superseded as the decision layer by** [`PINAKES_APPROACH.md`](PINAKES_APPROACH.md), which turns
R1–R7 below into a gated build order after twelve further investigations. This file records what
the research found; that one records what Pinakes decided to do about it.

---

## 1. The question

Relational structure is what lets a retrieval system answer *"which contracts were signed by someone
who also approved the amendment"* — a question flat vector similarity cannot reach, because the
answer exists only in the relationships between chunks, never inside any one of them.

The obvious way to get that structure is to extract it up front: run an LLM over the whole corpus,
pull out entities and relations, build a knowledge graph, then query it. That is Microsoft GraphRAG,
and it works. It is also the single most expensive thing you can do to a corpus.

**The question for pinakes is not "is structure valuable" — it plainly is — but "how much of it can
be had for €0."** The free-path principle (DESIGN §1) is not a nice-to-have here; it decides the
answer.

---

## 2. What the research actually found

### 2.1 Prebuilt graphs are priced out of the design

Full GraphRAG's cost is concentrated entirely in indexing, and it scales with the corpus, not with
usage. Published figures: a moderately sized document set runs $5–20 in API calls to index; one
reported enterprise case hit ~$47,000 to index 100k internal documents — before answering a single
question.

For pinakes this is disqualifying twice over. It breaks the free path, and it breaks something
subtler and more important: **DESIGN §4.1 relies on re-indexing being free.** That is what removes
cost pressure from improving chunking or swapping embedding models. An LLM-extraction step in `pnk
sync` would make `--rebuild` an expense, and the truth/derived split (§2) would quietly stop being
the good deal it currently is.

### 2.2 The field has already moved away from prebuilding

This is the useful finding, and it is recent:

| Work | Claim |
|---|---|
| **LazyGraphRAG** (MSR, late 2024 → Azure prod June 2025) | Defer all LLM summarisation to query time; index cost drops to ~0.1% of GraphRAG — i.e. the same as plain vector RAG — with ~700× lower global query cost |
| **"You Don't Need Pre-built Graphs for RAG"** (AAAI 2026) | Build only the local reasoning structure a given query needs, per query. Prebuilt global graphs are unnecessary |
| **EcphoryRAG** (2025) | Index *entities only*, infer relations at query time. ~94% token reduction at index time, SOTA on 2WikiMultiHop / HotpotQA / MuSiQue |
| **HippoRAG 2** (ICML 2025) | Store a light entity graph; do the work at query time with Personalized PageRank. ~10× more efficient than GraphRAG, better on multi-hop |
| **SubQRAG** (2025) | Decompose the question, retrieve per sub-question, and extract new triples *only where the existing graph came up short* |
| **Graph-R1** (ICML 2026) | Train the agent to traverse: a `think → query → retrieve subgraph → rethink` loop, RL-optimised end to end |

The through-line: **the graph stopped being an artifact you build and became a structure an agent
grows while reasoning.** Pinakes is on the right side of that shift already, for unrelated reasons.

### 2.3 Graph retrieval is not a free win — it is a routing decision

The counter-evidence matters as much as the case for. GraphRAG-Bench (ICLR 2026) and related analyses
report GraphRAG *underperforming* vanilla RAG on ordinary factual lookup — one study measured ~13%
lower accuracy on Natural Questions, worse still on time-sensitive queries. Practitioner benchmarks
show the same split from the other side: graph retrieval reaching ~91% on multi-hop relational
queries where vector RAG manages ~34%, while losing badly to structure-aware chunk retrieval (~97%
vs ~72%) when the answer is one date or clause in one known document.

**Reading:** a graph layer must be *additive and routed*, never a replacement for the hybrid pipeline.
Most queries against a pinakes KB will be local lookups, and those are exactly the ones a graph makes
worse.

---

## 3. Where pinakes already stands

Worth stating plainly, because it changes what is left to build:

- **The sidecars are already a knowledge graph.** `links: [{to: pnk://…, rel: cites}]` is a typed,
  directed edge, authored by a human, committed to git, portable across machines, and free. It is
  higher-precision than anything an LLM extractor produces, and it never needs recomputing.
- **The `links` table is already the storage layer**, with `src_kb_id`, `rel` and `origin` — enough
  to distinguish inbound from outbound and authored from discovered.
- **RRF over BM25 + vector (§4.1) is the fusion pattern the 2025/26 systems converged on.** Adding a
  graph channel means adding a third ranked list to a fusion that already exists — not a new pipeline.
- **DESIGN §4.3 already made the agentic call**: multi-hop via composable tools driven by the
  caller's agent, not an agent framework inside pinakes. That is the Graph-R1 loop, executed on
  someone else's token budget. It is the correct architecture and it should not be revisited.

**So the recommendation is not "adopt GraphRAG."** It is: recognise that the cheap 80% of a graph is
already in the design, and spend the remaining effort on traversal and ranking rather than on
extraction.

---

## 4. Recommendations

### R1 — Do not add LLM entity/relation extraction to `pnk sync`. Ever, at any version.

The strongest, most load-bearing recommendation here. It breaks the free path, makes `--rebuild`
expensive, and the 2025/26 literature says it buys less than it costs. If entity extraction is ever
wanted, see R5 — but the default answer is no.

### R2 — Prioritise v0.3 (`pnk link`, `pinakes_links`, cross-KB traversal).

Currently scheduled fourth. On this analysis it is the highest-value graph work in the whole roadmap,
because it is the only graph capability that costs nothing to build and delivers what vector search
structurally cannot. The prerequisite stated in §8 — "needs two populated KBs to be worth anything" —
is real, so this is an argument for getting two KBs populated sooner, not for reordering blindly.

### R3 — Add a free structural graph channel at sync time.

Everything below is already in the index or derivable from it at zero LLM cost:

| Edge type | Source | Cost |
|---|---|---|
| `sibling` | adjacent `chunks.ordinal` within a doc | free |
| `parent`/`child` | `chunks.heading_path` hierarchy | free |
| `co-located` | shared directory in `documents.path` | free |
| `shared-tag` | sidecar `tags` overlap | free |
| `cites`/`supersedes`/… | sidecar `links` (authored) | free |

This is the LinearRAG / structural-GraphRAG position: relation-free graph construction, where topology
comes from document structure rather than from semantic extraction. It costs one pass over data sync
already touches.

### R4 — Rank with Personalized PageRank over that graph, as a third RRF channel.

This is HippoRAG 2's core mechanism and the highest value-per-line item on the list. Concretely:

1. Run the existing pipeline; take the fused top-*k* chunks as seed nodes.
2. Run PPR over the edge set from R3, seeded on those nodes.
3. Feed the PPR-ranked list into the *existing* RRF as a third input, alongside BM25 and vector.
4. Rerank as today.

Properties that make it fit: it is pure NumPy/scipy over an adjacency matrix the index already holds,
adds no dependency, no network, no LLM, and no new storage — and it degrades to today's behaviour
when the graph is sparse. It also inherits the §4.4 coherence story unchanged, because nothing about
it is model-specific.

Gate it behind `[retrieval] graph_channel = "off" | "ppr"`, default `off` until the golden set says
otherwise (R7).

### R5 — If entity extraction is ever added, make it lazy, agent-driven, and write-back to sidecars.

The SubQRAG pattern, adapted to pinakes' truth/derived split:

- Never at sync. Only on an explicit, budgeted `--deep` path (v0.4 machinery, already specified).
- Only for the specific gap the current query hit — not the corpus, not the document set.
- **Write discovered triples into the sidecar, not into `.pinakes/`.** They then become committed,
  diffable, human-reviewable, and free forever after — which is exactly the property the design's
  "anything another KB needs to see must live in committed files" rule already demands.

That last point turns a recurring inference cost into a one-time, human-auditable one. It is the only
form of LLM extraction consistent with this design.

### R6 — Expose the graph to the caller's agent; do not traverse on its behalf.

`pinakes_links(doc_id, rel?, direction?, depth?)` returning neighbours plus the same confidence
signal as `pinakes_search`. The calling agent runs think → traverse → rethink in its own context, on
its own subscription — §4.3's existing bet, extended to edges. Resist adding a traversal *policy*
inside pinakes; that is the "second, worse agent framework" already flagged in §9.

### R7 — Measure before shipping any of it.

Add a multi-hop and a relational-lookup section to the template golden set *before* R3/R4 land, and
report per-class scores. Given §2.3, the specific risk to watch is regression on simple factual
lookup: if the graph channel costs precision there, it must stay `off` by default or route by query
class. The eval harness already reports false-abstain and false-confidence; this is the same
discipline applied to a new channel.

---

## 5. Prior art worth tracking

| Project | Stars (mid-2026) | Relevance to pinakes |
|---|---|---|
| [LightRAG](https://github.com/HKUDS/LightRAG) | ~28k | Dual-level entity/relation indexing; most actively developed in the space. Read for its retrieval-mode routing |
| [microsoft/graphrag](https://github.com/microsoft/graphrag) | ~31k | Reference implementation. Read as the *cost* case study; LazyGraphRAG is not yet in the OSS library |
| [Graphiti](https://github.com/getzep/graphiti) | ~20k | Incremental, bi-temporal graph built for agent memory; no batch summarisation. Closest philosophical match; its MCP server is worth studying for `pinakes_links` shape |
| [HippoRAG 2](https://github.com/OSU-NLP-Group/HippoRAG) | ~2k | The PPR mechanism behind R4. Read the paper before implementing |
| [fast-graphrag](https://github.com/circlemind-ai/fast-graphrag) | ~800 | PageRank exploration + incremental updates, ~6× cheaper than GraphRAG. Small enough to read end to end |
| [Graph-R1](https://github.com/LHRLAB/Graph-R1) | ~400 | ICML 2026. RL-trained traversal. Not actionable now; the direction the field is heading |

**Papers:** LazyGraphRAG (MSR blog, Nov 2024) · *You Don't Need Pre-built Graphs for RAG* (arXiv
2508.06105, AAAI 2026) · *When to use Graphs in RAG* / GraphRAG-Bench (arXiv 2506.05690, ICLR 2026) ·
SubQRAG (arXiv 2510.07718) · EcphoryRAG (arXiv 2510.08958) · Graph-R1 (arXiv 2507.21892) ·
[Awesome-GraphRAG](https://github.com/DEEP-PolyU/Awesome-GraphRAG) for the running bibliography.

---

## 6. Summary

| # | Recommendation | Version | Cost |
|---|---|---|---|
| R1 | No LLM extraction in `pnk sync` | all | — |
| R2 | Prioritise authored links (`pnk link`, `pinakes_links`) | v0.3 | €0 |
| R3 | Structural edges from existing index data | v0.3 | €0 |
| R4 | PPR as a third RRF channel, default `off` | v0.3–v0.4 | €0 |
| R5 | Lazy extraction → sidecar write-back, only if ever needed | v0.4+ | budgeted |
| R6 | Expose traversal as a tool; no traversal policy inside pinakes | v0.3 | €0 |
| R7 | Multi-hop golden-set coverage before R3/R4 ship | v0.3 | €0 |

The short version: **pinakes does not need GraphRAG, because it already has the part of GraphRAG that
was worth having.** Typed, human-authored, committed links are a better graph than an LLM extractor
produces, and they cost nothing. The work that remains is traversal and ranking over that graph — and
the research consensus of 2025/26 is that this is where the value was all along.
