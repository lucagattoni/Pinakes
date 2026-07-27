# Microsoft GraphRAG (+ LazyGraphRAG) — investigation notes

**Repo:** https://github.com/microsoft/graphrag · **Stars:** ~34.8k · **License:** MIT · **Investigated:** 20260725 15:33
**Papers:** [From Local to Global (arXiv 2404.16130)](https://arxiv.org/abs/2404.16130) · [LazyGraphRAG MSR blog, 2024-11-25](https://www.microsoft.com/en-us/research/blog/lazygraphrag-setting-a-new-standard-for-quality-and-cost/) (blog only — no paper)

## What it is

LLM-built knowledge-graph RAG: at index time an LLM extracts an entity/relationship graph from
every chunk, Leiden clusters it into a community hierarchy, and an LLM pre-summarises every
community; queries then run over reports + graph + chunks. Python monorepo since v3.0
(2026-01): `packages/graphrag` plus `graphrag-llm/-storage/-vectors/-cache/-chunking/-common/-input`.
Actively maintained mid-2026: v3.1.1 released 20260718, pushed 20260725, ~60 open issues.
All paths below are under `packages/graphrag/graphrag/`.

## How the graph is built

Standard pipeline (`index/workflows/factory.py`, `IndexingMethod.Standard`), in order:

1. **Chunking** — `index/workflows/create_base_text_units.py`. Free.
2. **Graph extraction** — `index/operations/extract_graph/graph_extractor.py`,
   `GraphExtractor._process_document`: **one LLM call per chunk**, then a *gleanings* loop
   (default `max_gleanings: 1` in `config/defaults.py`) — each round adds a `CONTINUE_PROMPT`
   call plus a Y/N `LOOP_PROMPT` call. So 2–3 LLM calls per chunk at defaults. Optional claim
   extraction (`extract_covariates/claim_extractor.py`) adds another per-chunk pass.
3. **Entity resolution** — there barely is any: entities merge on *uppercased exact title match*
   (`clean_str(record_attributes[1].upper())` in `graph_extractor.py`). Merged duplicate
   descriptions then get **one LLM call per entity and per relationship** in
   `index/operations/summarize_descriptions/summarize_descriptions.py`.
4. **Community detection** — `index/operations/cluster_graph.py`,
   `_compute_leiden_communities`: hierarchical Leiden (`max_cluster_size: 10`), optional
   largest-connected-component filter. Free, pure graph code.
5. **Community summarisation** — `summarize_communities/community_reports_extractor.py`,
   `CommunityReportsExtractor`: **one LLM call per community per hierarchy level**, producing a
   structured report (title/summary/findings/rating). Reports are then embedded.

**Fast pipeline** (`IndexingMethod.Fast` → `index/workflows/extract_graph_nlp.py`): replaces
stage 2–3 with `build_noun_graph/build_noun_graph.py` — spaCy/regex noun-phrase extraction,
co-occurrence edges per text unit, PMI weighting (`calculate_pmi_edge_weights`). No LLM for the
graph, but community reports (built from text units, `create_community_reports_text.py`) still
call the LLM per community.

**Where the cost concentrates:** extraction is O(chunks × (1 + 2·gleanings)) LLM calls;
description summarisation is O(entities + relationships); reports are O(communities × levels).
On any real corpus the per-chunk extraction dominates, with reports second. The README itself
warns "GraphRAG indexing can be an expensive operation". This is the cost case study: every
stage Pinakes refused to build is a paid, per-document, re-paid-on-rebuild LLM pass.

## How retrieval works

- **Local search** (`query/structured_search/local_search/mixed_context.py`,
  `LocalSearchMixedContext.build_context`): embed query → `map_query_to_entities` (similarity
  over entity-description embeddings, `top_k_mapped_entities: 10`, 2× oversample) → fill an
  8 000-token context: 50 % text units, 25 % community reports, remainder
  entities/relationships/covariates → **one** answer LLM call. Cheapest graph mode.
- **Global search** (`global_search/search.py`, `GlobalSearch.search`): map-reduce over
  community reports — parallel `_map_response_single_batch` LLM calls score points per report
  batch, one `_reduce_response` call composes the answer. Cost O(all reports at chosen level)
  per query. Optional **dynamic community selection**
  (`query/context_builder/dynamic_community_selection.py`, `DynamicCommunitySelection.select`):
  BFS from root communities, `rate_relevancy` (0–10 rating, JSON, majority vote over
  `num_repeats`) on each report, descend into children only when rating ≥ threshold.
- **DRIFT search** (`drift_search/primer.py`, `search.py`): HyDE-style
  `PrimerQueryProcessor.expand_query` (hypothetical answer → embedding) → top community
  reports → `DRIFTPrimer.search` decomposes into intermediate answer + ≥5 follow-up queries
  (LLM call per report batch) → loop `n_depth` epochs running each of `drift_k_followups`
  follow-ups as a full LocalSearch, each spawning more follow-ups → final reduce call. An
  agentic multi-hop loop *inside* the library; the most expensive query mode.
- **Basic search** (`basic_search/`): plain vector RAG over chunks, one LLM call.

## LazyGraphRAG: what is actually known

**Status, verified 20260725:** *not* in the OSS library. The v3.1.1 tree contains no
lazy-named module (checked the full git tree). In discussion
[#1490](https://github.com/microsoft/graphrag/discussions/1490) maintainer AlonsoGuevara said
(2024-12-09) it was "the next top priority item to release"; there has been **no maintainer
update since**, with users still asking as of July 2026. Officially it ships only inside
**Microsoft Discovery** and **Azure Local** (public preview June 2025). Third-party claims of a
"Q1–Q2 2026 OSS integration" are not corroborated by the repo or its maintainers.

**Published mechanism** (MSR blog, 2024-11-25 — quotes are the blog's):
- Index: "NLP noun phrase extraction to extract concepts and their co-occurrences" + "graph
  statistics to optimize the concept graph and extract hierarchical community structure". No
  LLM at index time; "data indexing costs are identical to vector RAG and 0.1% of the costs of
  full GraphRAG". This index is essentially what the OSS `extract_graph_nlp` path builds.
- Query: **best-first** — rank chunks by embedding similarity, then rank communities via
  chunk-community membership; **breadth-first** — "an LLM-based sentence-level relevance
  assessor" rates top-k untested chunks; iterative deepening "recurses into relevant
  sub-communities after z successive communities yield zero relevant text chunks"; an LLM then
  extracts subquery-relevant claims from community-grouped chunks and map-reduces them.
- One knob: the **relevance test budget** (tested at 100 / 500 / 1 500). At 500 tests
  (~4 % of global-search query cost) it "significantly outperforms all conditions"; global
  answer quality comparable to global search at ">700 times lower query cost".

**Published vs inferred:** the pipeline sketch, budget levels and cost ratios are published;
exact prompts, budget allocation across subqueries, and the claim-extraction format are not.
The OSS repo already contains the *ingredients* (noun graph, `rate_relevancy`, dynamic
selection) but not the deferred-summarisation query engine itself.

## Cost profile

- Index: dominated by per-chunk LLM extraction (+gleanings), then per-entity/edge description
  summarisation, then per-community reports. Only Leiden and embeddings are cheap.
- Rebuild: full re-spend unless the LLM cache (`graphrag-cache`, hash-keyed prompt cache) is
  retained — cost mitigation via caching, not via a free path.
- OSS cost knobs: `IndexingMethod.Fast` (LLM-free graph); `max_gleanings`; `graphrag
  prompt-tune` (auto-generates domain-adapted extraction prompts); **incremental indexing**
  (`graphrag update` → `update_*` workflows in `index/workflows/factory.py`, merging new docs
  and re-summarising only affected communities); `prune_graph`; dynamic community selection
  (`dynamic_search_*` defaults) to cut global-search query cost.
- No hard budget ceiling anywhere: nothing enforces a spend cap; token/call counts are
  reported (`llm_info` in `dynamic_community_selection.py`) but never limited by cost.

## What's interesting for Pinakes

GraphRAG is the strongest available evidence *for* Pinakes' standing decisions. Microsoft's own
trajectory — Standard → Fast (LLM-free noun graph) → LazyGraphRAG (no index-time LLM at all,
query-time budgeted assessment) — converges on exactly the Pinakes rules: never LLM extraction
at sync time; free structural edges; lazy, query-scoped, budgeted extraction if ever. And
Pinakes starts ahead of the noun graph: human-authored typed `links:` sidecars are
higher-precision edges than noun-phrase co-occurrence, at zero build cost.

## What to steal

- **The relevance-test budget as the single cost knob.** LazyGraphRAG's one-parameter
  cost/quality dial is exactly the abstraction `pnk ask --deep` needs: a budget counted in
  cheap LLM relevance tests, spent best-first, hard-stopped. `rate_relevancy`
  (`query/context_builder/rate_relevancy.py`) is a complete reference: 0–10 JSON rating,
  majority vote, per-call `llm_calls/prompt_tokens/output_tokens` accounting returned upward.
- **Iterative deepening over a cheap hierarchy** (`DynamicCommunitySelection.select`): rate
  coarse things first, descend only on relevance, fall through a level when nothing matches.
  Pinakes analog: rate documents (titles/abstracts) before chunks inside `--deep`.
- **Best-first seeding + breadth-first testing**: seed from the existing RRF ranking, then test
  link-graph neighbours breadth-first under the budget — a concrete recipe for the caller's
  agent composing `pinakes_search` + `pinakes_links`, no framework needed.
- **PMI edge weighting** (`graphrag.graphs.edge_weights.calculate_pmi_edge_weights`) if Pinakes
  ever derives free co-occurrence edges to feed the Personalized PageRank channel.
- **Golden-set discipline**: their published win-rate-vs-budget curves are the model for how a
  `--deep` change should be justified (matches the existing eval rule).

## What to avoid / doesn't fit

- **The entire Standard indexing pipeline** — per-chunk LLM extraction, gleanings,
  per-entity summarisation, per-community reports. Violates the free path, and since
  `.pinakes/` is disposable a rebuild would re-pay it; their mitigation is a prompt cache,
  Pinakes' is never paying.
- **Precomputed community reports as index artifacts** — paid summaries that go stale and make
  rebuilds paid. Any summarisation must stay query-time and budgeted (write-back to sidecars).
- **Map-reduce global search** — O(corpus) LLM calls per question.
- **DRIFT's in-library agent loop** — Pinakes deliberately leaves multi-hop composition to the
  caller's agent; embedding an epochs/follow-ups loop would duplicate the MCP client's job.
- **Their entity resolution** (uppercase exact-match) — even Microsoft punts on real ER; ULID
  links make the problem structurally absent in Pinakes. Don't reintroduce it via extraction.
- **Waiting for LazyGraphRAG code** — 19 months of "next priority" with no OSS landing; treat
  the blog as the spec and the OSS ingredients as reference code.

## Key sources

- Repo: https://github.com/microsoft/graphrag (v3.1.1, 20260718; metadata via GitHub API 20260725)
- Pipeline factory: `packages/graphrag/graphrag/index/workflows/factory.py`
- Extraction: `.../index/operations/extract_graph/graph_extractor.py`; NLP path
  `.../index/workflows/extract_graph_nlp.py`, `.../build_noun_graph/build_noun_graph.py`
- Communities: `.../index/operations/cluster_graph.py`,
  `.../summarize_communities/community_reports_extractor.py`
- Query: `.../query/structured_search/{local_search/mixed_context.py,
  global_search/search.py, drift_search/{primer.py,search.py}}`;
  `.../query/context_builder/{dynamic_community_selection.py,rate_relevancy.py}`
- LazyGraphRAG: MSR blog 2024-11-25 (above); status thread
  https://github.com/microsoft/graphrag/discussions/1490; Project GraphRAG page
  https://www.microsoft.com/en-us/research/project/graphrag/
- Docs: https://microsoft.github.io/graphrag/ (architecture, prompt tuning, incremental indexing)
