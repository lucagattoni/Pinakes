# HippoRAG 2 — investigation notes

**Repo:** https://github.com/OSU-NLP-Group/HippoRAG · **Stars:** ~3.9k · **License:** MIT · **Investigated:** 20260725 15:32
**Papers:** HippoRAG (NeurIPS 2024) https://arxiv.org/abs/2405.14831 · HippoRAG 2 "From RAG to Memory" (ICML 2025) https://arxiv.org/abs/2502.14802

## What it is

Graph-augmented retrieval framed as hippocampal memory: an LLM ("neocortex") builds a schema-less
open KG at index time; at query time, Personalized PageRank (PPR) over that KG performs multi-hop
retrieval in a single step. HippoRAG 2's core claim: unlike GraphRAG/LightRAG (which *expand* the
corpus with LLM-generated summaries and regress on simple factual QA), it uses the graph only to
*re-rank existing passages*, so it beats a strong dense retriever (NV-Embed-v2 7B) on multi-hop
(+5.0 / +13.9 R@5 on MuSiQue / 2Wiki) without losing on simple QA. Actively maintained mid-2026
(last push 20260724), pip-installable, Python 3.10+.

## What gets indexed

Per passage (all in `src/hipporag/HippoRAG.py`, defaults in `src/hipporag/utils/config_utils.py::BaseConfig`):

1. **OpenIE triples via LLM** — 1-shot prompting, two steps: NER first, then triples seeded with those
   entities (`src/hipporag/information_extraction/`, `prompts/`). Schema-less. This is the expensive,
   LLM-required part. Ablation (v1 paper, Table 5): replacing the LLM with REBEL (a small end-to-end
   OpenIE model) drops avg R@5 72.9 → 58.4; Llama-3.1-8B is nearly on par with GPT-3.5 → local works.
2. **Phrase nodes** (`entity-` hash ids, `extract_entity_nodes()`) = triple subjects/objects.
   **Relation edges** between them, weight = co-occurrence count (`add_fact_edges()`).
3. **Passage nodes** (`chunk-` ids) with **context edges** ("contains", weight 1.0) to every phrase
   extracted from that passage (`add_passage_edges()`). New in v2.
4. **Synonym edges** — KNN over phrase-node embeddings; edge added when cosine ≥
   `synonymy_edge_sim_threshold = 0.8` (`synonymy_edge_topk = 2047`), weight = similarity score
   (`add_synonymy_edges()`). Embedding-only, no LLM.
5. Embeddings stored for phrases, **facts (triples)**, and passages (`embedding_store.py`; default
   encoder `nvidia/NV-Embed-v2`). Graph is **undirected** (`is_directed_graph = False`), held in igraph.

Scale (paper Table 10, MuSiQue 11.6k passages, Llama-3.3-70B): 85k phrase nodes, 141k relation
edges, 133k context edges, **1.13M synonym edges** — synonym edges dominate the edge set ~8:1.

LLM-required vs replaceable-for-free: triples + relation edges need an LLM; synonym edges need only
a local embedder; passage↔entity bipartite structure is mechanical once you have node sets. Pinakes'
structural edges (sibling, parent/child, co-located, shared-tag, authored links) can stand in for
relation edges; tags/headings play the phrase-node role; the passage↔entity bipartite shape maps to
chunk↔tag / chunk↔heading.

## The PPR mechanism, precisely

Query flow (`HippoRAG.retrieve()` → `graph_search_with_fact_entities()` → `run_ppr()`), all in
`src/hipporag/HippoRAG.py`; paper §3.5 + Appendix G.1:

1. **Query→triple**: embed the query, dot-product against all fact embeddings (`get_fact_scores()`).
   This replaces v1's query-NER. Normalized embeddings → scores are cosines.
2. **Recognition-memory filter**: top candidate facts go through an LLM filter
   (`rerank_facts()` → `DSPyFilter`, `src/hipporag/rerank.py`), keeping ≤ `linking_top_k = 5` triples.
3. **Phrase seed weights**: each phrase node in a surviving triple gets the *average* fact score of
   the filtered triples it appears in; additionally each fact score is divided by
   `len(self.ent_node_to_chunk_ids[phrase_key])` — a node-specificity/IDF-style damper so ubiquitous
   entities don't dominate (v1 called this node specificity, s_i = |P_i|^-1; ablating it cost ~2 pts
   avg R@5). Top-k filtered via `get_top_k_weights()`; ≤ 5 phrase seeds.
4. **Passage seed weights**: **every** passage node is a seed. `dense_passage_retrieval()` scores all
   passages against the query; each passage node's reset mass = its dense score ×
   `passage_node_weight = 0.05`. Broad activation of all passages (not just top-k) is deliberate —
   it's what lets probability flow along multi-hop chains. The 0.05 factor is the knob balancing
   phrase vs passage influence; sweep (paper Table 5) is mild: R@5 on MuSiQue 79.9/80.5/79.8/78.4/77.9
   at 0.01/0.05/0.1/0.3/0.5.
5. **Reset vector**: `node_weights = phrase_weights + passage_weights` (unnormalized; igraph
   normalizes internally).
6. **PPR call** (`run_ppr()`):
   ```python
   self.graph.personalized_pagerank(
       vertices=range(n), damping=0.5, directed=False,
       weights='weight', reset=reset_prob, implementation='prpack')
   ```
   python-igraph, prpack solver, **damping = 0.5** (`BaseConfig.damping`; tuned on 100 MuSiQue
   training examples in the v1 paper; same value in both versions). d=0.5 means half the walk mass
   teleports back to seeds each step — a very local, ~1–2-hop diffusion, not global PageRank d=0.85.
7. **Passage ranking**: final score = raw PPR probability at each passage node
   (`doc_scores = pagerank_scores[self.passage_node_idxs]`), sorted descending. **There is no
   post-hoc fusion with dense scores** — dense retrieval enters only through the reset vector
   (v1 ensembled graph and dense scores externally; v2 replaced that with passage-node seeding).
8. **Fallback**: if the filter returns zero triples (`len(top_k_facts) == 0`), return pure
   `dense_passage_retrieval()` ranking — no graph search. Error analysis: 18% of failing MuSiQue
   samples hit this path; the system degrades to standard dense RAG, never worse.

v1 differences in mechanics: seeds = KG nodes nearest (cosine) to query NER entities, uniform reset
prob × node specificity; no passage nodes; passage score = Σ over PPR node probabilities of phrases
occurring in the passage (|N|×|P| count matrix multiply).

## HippoRAG 1 → 2, what changed

| Change | Mechanism | Evidence (Table 4, R@5 avg over MuSiQue/2Wiki/HotpotQA) |
|---|---|---|
| Passage nodes in KG ("dense-sparse integration") | passages become nodes + "contains" edges; dense scores seed them | 87.1 → 81.0 without them; also what fixes v1's simple-QA collapse (NQ R@5 44.4 → 78.0) |
| Query-to-triple linking ("deeper contextualization") | embed whole query vs fact embeddings, instead of NER→node | NER-to-node 74.6, query-to-node 59.6, query-to-triple 87.1 |
| Recognition-memory filter | LLM filters candidate triples before seeding | without filter 86.4 vs 87.1 — small on average, but filter precision is the top error source (26% of failures) |

## Cost profile

Paper Appendix F, Table 12 (MuSiQue, 11,656 passages, Llama-3.3-70B on 4×H100 via vLLM):
indexing **9.2M input / 3.0M output tokens** (~800+260 per passage) — vs GraphRAG 115.5M/36.1M
(12.5×) and LightRAG 68.5M/18.3M; indexing 99.5 min (NV-Embed-v2 alone: 12.1); query 1.2 s
(dense: 0.3 s); 9.9 GB extra GPU memory at query time, mostly fact embeddings. Query-time LLM use =
one small filter call. Fully local is supported (vLLM `openie_mode='offline'`, local embedders), but
"local" here means a 70B-class LLM + 7B embedder — nothing like Pinakes' free path. Where it does
NOT win: PopQA (entity-centric simple QA) — HippoRAG 1 keeps the best R@5, and v2 roughly ties the
big embedders on NQ/PopQA rather than beating them; the graph pays off only on multi-hop/associative
queries. GraphRAG/LightRAG *lose* to plain dense retrieval on simple QA; HippoRAG 2's passage nodes
are precisely the guard against that regression.

## What's interesting for Pinakes

- Independent confirmation of R4's architecture-level bet: graph signal helps multi-hop, and the way
  to avoid regressing simple lookups is to keep the original chunks in the loop (their passage
  nodes ≈ our "fused top-k as seeds" + chunk nodes in the graph).
- PPR is the *entire* graph machinery at query time — no LLM needed for the walk itself; igraph
  prpack on a ~1.4M-edge graph runs in well under a second.
- The LLM-built KG is the only part Pinakes can't afford, and their own ablations show the graph
  *structure* (synonym + bipartite context edges) carries much of the weight: synonym edges are
  embedding-only, context edges are mechanical. Structural edges are a plausible free substitute for
  relation edges; nobody has published that exact ablation, so our golden-set eval must decide.
- Their fallback story is exactly ours: no seeds → pure baseline ranking, graph can only abstain.

## What to steal (incl. concrete PPR parameters for R4)

- **damping = 0.5**, undirected graph, weighted edges. Tuned twice by OSU on held-out data and kept
  across both versions. Start R4 there (sweep 0.3–0.7 in eval); do NOT default to textbook 0.85.
- **Two-part reset vector**: (a) a *small* set (≤5) of high-precision non-chunk seeds weighted by
  their retrieval scores, (b) **all chunk nodes** weighted by `fused_score × passage_node_weight`
  with **passage_node_weight = 0.05** (sweep 0.01–0.1; their curve is flat there, cliff above 0.3).
  Seeding every chunk — not only top-k — is their stated key to multi-hop flow.
- **Node-specificity damping**: divide a seed entity/tag node's weight by the number of chunks it
  links to (IDF-for-free, +~2 R@5 in v1). For Pinakes: damp shared-tag and co-located hub nodes.
- **Score averaging for seed nodes**: node weight = mean score of the query-matched items it appears
  in, not max/sum.
- **Rank = raw PPR probability at chunk nodes.** In HippoRAG 2 dense enters via the reset vector and
  PPR is the final ranker. R4 plans PPR-as-third-RRF-channel instead — keep that (safer for the
  abstention signal), but implement the reset vector their way so the channel is well-formed; an
  eval-time variant "PPR-as-final-ranker" is cheap to test since it's the same computation.
- **Fallback**: empty seed set (or graph untouched by query) → skip PPR channel entirely, RRF over
  BM25+vector as today. Their 18%-of-errors number says this path is common; make it silent and free.
- scipy implementation note: with reset vector r (normalized), solve x = (1−d)·(I − d·W^T)^{-1} r
  via power iteration on the row-normalized weighted adjacency W; d=0.5 converges in ~20–40
  iterations to 1e-8. No igraph dependency needed at Pinakes' scale.

## What to avoid / doesn't fit

- **LLM OpenIE at index time** — ~1,000 LLM tokens/passage; violates the free path and free rebuilds.
  Their REBEL ablation warns that *cheap* triple extraction is much worse than no clever graph, which
  supports R4's choice to skip triples entirely rather than approximate them badly.
- **Recognition-memory filter (DSPyFilter)** — query-time LLM call; its job (precision-filter the
  seeds) is done in Pinakes by the cross-encoder rerank scores. Worth noting it was their #1 error
  source even with an LLM.
- **Fact/triple embedding store** — their biggest memory cost (9.9 GB); irrelevant without triples.
- Don't expect graph gains on simple lookups: even with a 70B LLM index, v2 only ties strong dense
  baselines on NQ/PopQA. R4's default-off-until-eval stance matches the evidence.

## Key sources

- Code: `src/hipporag/HippoRAG.py` (`index`, `add_fact_edges`, `add_passage_edges`,
  `add_synonymy_edges`, `retrieve`, `get_fact_scores`, `rerank_facts`,
  `graph_search_with_fact_entities`, `dense_passage_retrieval`, `run_ppr`),
  `src/hipporag/utils/config_utils.py` (`BaseConfig`), `src/hipporag/rerank.py` (`DSPyFilter`),
  `src/hipporag/embedding_store.py` — read via GitHub raw, 20260725.
- HippoRAG 2 paper: §3.2–3.5 (method), §6.1–6.2 + Table 4/5 (ablations, reset-weight sweep),
  Appendix E (error analysis), F + Table 12 (cost), G.1 + Table 13 (PPR init, hyperparameters).
- HippoRAG 1 paper: §2.3 (PPR + node specificity), §3.4 (τ=0.8, damping 0.5), Table 5
  (REBEL/PPR/specificity/synonym ablations), Appendix A (worked pipeline example).
- Repo metadata: GitHub API, 20260725 (3,886 stars, MIT, pushed 20260724).
