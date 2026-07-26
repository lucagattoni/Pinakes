# LinearRAG — investigation notes

**Repo:** https://github.com/DEEP-PolyU/LinearRAG · **Stars:** ~526 · **License:** GPL-3.0 · **Investigated:** 20260725 15:34
**Paper:** [arXiv:2510.10114](https://arxiv.org/abs/2510.10114) — "LinearRAG: Linear Graph Retrieval Augmented Generation on Large-scale Corpora", ICLR 2026 (PolyU DEEP lab)

## What it is

The closest published embodiment of Pinakes' R3 position: GraphRAG with **zero LLM calls at index
time and zero at retrieval time**. Its core argument (paper §2.2–2.3) is that LLM relation
extraction is both the cost and the noise source in GraphRAG — relation triples are locally
inaccurate and globally inconsistent — and that **aligned entities, not relations, are the anchors
that connect passages**; relational semantics stay in the original text for the reader-LLM to
interpret. So it builds a relation-free "Tri-Graph" from spaCy NER + embeddings only, and beats
HippoRAG2/GFM-RAG/LightRAG on HotpotQA/2Wiki/MuSiQue/Medical while indexing 4–20x faster with
0 tokens. Codebase is small research code: one 1000-line class (`src/LinearRAG.py`), ~6 files.

## How the graph is built (and what it costs)

`LinearRAG.index()` in `src/LinearRAG.py` (paper §3.1):

1. **Chunk → passage nodes**; passage embeddings stored in parquet (`src/embedding_store.py`).
2. **NER** over passages with spaCy (`src/ner.py::SpacyNER.batch_ner`) — default
   `en_core_web_trf` (RoBERTa-based, ~440 MB), `en_core_sci_scibert` for medical. Drops only
   ORDINAL/CARDINAL entities; **no canonicalization** — entity nodes are raw surface forms
   ("Einstein" and "Albert Einstein" are distinct nodes, bridged only by co-mention + embeddings.)
3. **Sentence split** (spaCy sents) → sentence set; entities/sentences/passages are the three
   node types.
4. **Edges — binary co-occurrence only, no similarity thresholds anywhere at build time:**
   - *mention matrix* M (sentence×entity): sentence mentions entity → 1.0
   - *contain matrix* C: passage→entity edges weighted `count(entity)/total_entity_count_in_passage`
     (`add_entity_to_passage_edges`)
   - **adjacent-passage edges**, weight 1.0, consecutive chunks (`add_adjacent_passage_edges`) —
     exactly Pinakes' planned sibling edge.
5. Embed all entities and **all sentences** (all-mpnet-base-v2 by default). This is the real
   index cost: ~2–3x the embedding work of a passages-only index. "Semantic linking" in the
   marketing is *not* an edge type — no entity–entity or similarity-threshold edges exist; the
   semantics enter only at query time through sentence/entity embeddings.
6. igraph graph (`augment_graph`) holds **only entity + passage nodes**; sentences live solely in
   the sparse M matrix used for activation. Graph persisted as GraphML; NER results cached as
   JSON with **incremental update** — `load_existing_data` diffs passage hashes so new passages
   only trigger NER/embedding for themselves (paper claims O(|P|·T) construction, Appendix D).

Verified: no LLM anywhere in `index()`; the only LLM use in the repo is answer generation
(`qa()`) and GPT-based eval. Retrieval itself is fully local.

## How retrieval works

`retrieve()` → `graph_search_with_seed_entities()`, two stages (paper §3.2):

1. **Seeds** (`get_seed_entities`): spaCy NER on the *question*; each question entity matched to
   its nearest corpus entity by embedding argmax, seed score = that similarity. **If the question
   has no NER entities, it silently falls back to pure dense retrieval** — the graph is bypassed.
2. **Entity activation via "semantic bridging"** (`calculate_entity_scores`, or the
   torch-sparse `_vectorized` variant): spreading activation, *not* PPR. Per iteration (≤3,
   `max_iterations`): each active entity looks at its unused sentences, keeps the
   `top_k_sentence` (1–3) most similar **to the question**, and every entity in those sentences
   gets `score = entity_score × sim(question, sentence)`. Pruned below `iteration_threshold`
   (0.4–0.5); sentences are consumed once (dedup). So multi-hop paths are followed only through
   sentences that themselves resemble the query — the query embedding gates every hop.
   Paper Eq. 5: `a_t = MAX(Mᵀ(σ_q ⊙ M a_{t-1}), a_{t-1})`.
3. **Passage scoring + PPR** (`calculate_passage_scores` → `run_ppr`): hybrid reset vector —
   entity nodes get activation scores; passage nodes get
   `λ·DPR_sim + ln(1 + Σ activated-entity score·log(1+occurrences)/hop_tier)` (entity occurrences
   counted by **plain substring match** in passage text), scaled by `passage_node_weight` 0.05.
   Then igraph `personalized_pagerank` (prpack) over the entity–passage graph, damping 0.5 in
   `src/config.py` (paper says "typically 0.85"), rank passages by PPR score, top-k=5.
4. One benchmark-shaped wart: `enable_hybrid_attribute_fallback` boosts passages sharing
   hardcoded keywords ("born", "capital", "founded"…) with the question — a community patch
   (PR #21) for attribute queries about hub entities, off by default.

Ablations (paper Fig. 4): removing either stage costs only ~2–3 points; the two stages overlap.

## Entity topology vs Pinakes' structural edges

- **What entity edges capture that heading/sibling/tag edges don't:** cross-document topical
  bridges with no structural relationship — two notes in different directories, different tag
  sets, no authored link, that both mention "SQLite WAL mode" become 2 hops apart. This is
  precisely the edge class Pinakes' planned set cannot produce (structural edges never leave the
  file/directory/tag neighborhood; authored links only exist where the user wrote them). It's
  the multi-hop connector on 2Wiki/MuSiQue-style questions.
- **What Pinakes' edges capture that LinearRAG's don't:** intent. Heading hierarchy, sibling
  order (LinearRAG has this one edge type too) and *typed authored links* (`cites`, `refutes`…)
  are human-asserted structure with ~zero noise. LinearRAG has no document hierarchy at all —
  passages are a flat list — and its entity edges inherit NER noise plus surface-form
  fragmentation (no alias merging).
- Convergence check: LinearRAG independently lands on the same final ranker as Pinakes' plan —
  **PPR over a chunk+X graph with fused seed scores** — but its bipartite entity–passage graph is
  the topology, whereas Pinakes planned PPR over structural edges. The two edge families are
  complementary, not competing: entity co-occurrence edges could be a *fourth* free edge type in
  the same `links`-style table (`rel: mentions`), feeding the same PPR.

## Cost profile

- **Index:** 0 LLM tokens (verified in code). Compute: transformer NER + sentence-level embedding
  pass. Paper Table 2 (2Wiki): 250 s vs HippoRAG 936 s / LightRAG 4933 s; Table 6: 10M-token
  corpus in 3084 s vs RAPTOR 46431 s — on an RTX 4090. CPU-only (Pinakes' floor) multiply
  accordingly; `en_core_web_sm` would cut NER cost at some recall loss (untested in paper).
- **Query:** ~0.1 s avg (Table 2), all local: 1 question embedding + a few sparse matmuls + PPR.
  E2GraphRAG/RAPTOR retrieve faster (0.05–0.06 s) but score ~20 points lower.
- **Storage:** embeddings for passages+sentences+entities (linear, but sentences dominate), two
  sparse matrices, one GraphML.
- **Where it loses** (paper Table 4, Appendix E.1): *relevance* on complex-reasoning (81.6 vs
  vanilla RAG 84.1) and contextual-summarization (87.9 vs 89.9) tasks; fact-retrieval recall
  slightly behind GFM-RAG. And structurally: entity-free queries get plain dense retrieval;
  vague/conceptual queries with no named entities gain nothing from the graph.

## What's interesting for Pinakes

1. Independent, peer-reviewed validation of R3: zero-LLM graph construction *beats* the
   LLM-extraction GraphRAGs (HippoRAG2, LightRAG) it was designed to undercut, with a real
   noise-based argument for *why* relation extraction hurts.
2. Entity–passage bipartite edges are the missing cross-silo edge type in Pinakes' planned set,
   and they're free: NER + counting, incremental per new document.
3. Query-gated spreading activation (hop only through sentences similar to the query) is a
   cheap, principled alternative to blind graph expansion — it kills topic drift, LightRAG's
   documented failure mode.
4. Hybrid PPR reset (dense-retrieval score on passage nodes + activation on entity nodes)
   matches Pinakes' "seeds = fused top-k" plan and shows λ should be small (0.05: entity signal
   primary, DPR auxiliary — Obs. 11).

## What to steal

- **Entity co-mention as a free edge type:** spaCy NER at sync → `mentions` edges
  chunk→entity in the existing `links` table; weight by normalized occurrence count like
  `add_entity_to_passage_edges`. Feeds the already-planned PPR channel unchanged.
- **Hybrid reset vector:** put RRF-fused scores on chunk nodes *and* activation mass on
  entity/tag nodes rather than seeding chunks only.
- **Per-hop query gating with threshold + dedup** (`iteration_threshold`, used-sentence set,
  `top_k_sentence`) if Pinakes ever does multi-hop expansion before PPR.
- **Incremental NER cache diffing by content hash** (`load_existing_data`) — matches Pinakes'
  hash-based resync design.
- The eval framing: report *relevance* alongside recall; graph channels tend to buy recall by
  spending relevance (Table 4 is the cautionary dataset).

## What to avoid / doesn't fit

- **GPL-3.0**: ideas are fine, code must not be copied/vendored into Pinakes.
- Sentence-level embedding of the whole corpus (~2–3x index cost) — Pinakes chunks are already
  small; entity–chunk edges alone likely capture most of the value. Treat sentence granularity
  as an eval-gated option, not a default.
- `en_core_web_trf` as default: a 440 MB transformer dependency fights Pinakes' light-core rule;
  it would have to live in an extra (`[st]`-style), with `en_core_web_sm` as the light path.
- No entity canonicalization: surface-form nodes fragment aliases; Pinakes' personal-KB corpora
  (people, projects, own jargon) will hit this harder than Wikipedia text. Cheap mitigation:
  casefold + embedding-nearest merge above a high threshold; anything fancier is out of scope.
- Hardcoded attribute-keyword fallback (PR #21) — benchmark patchwork; Pinakes has BM25 for
  exactly that job.
- Research-code hygiene: damping 0.5 in code vs 0.85 in paper, `δ = 4` typo, `CUDA_VISIBLE_DEVICES`
  hardcoded in `run.py`. Take the algorithm, re-derive the hyperparameters on the golden set.

## Key sources

- Code: [`src/LinearRAG.py`](https://github.com/DEEP-PolyU/LinearRAG/blob/main/src/LinearRAG.py)
  — `index`, `add_entity_to_passage_edges`, `add_adjacent_passage_edges`, `get_seed_entities`,
  `calculate_entity_scores`, `calculate_passage_scores`, `run_ppr`;
  [`src/ner.py`](https://github.com/DEEP-PolyU/LinearRAG/blob/main/src/ner.py) (`SpacyNER`);
  [`src/config.py`](https://github.com/DEEP-PolyU/LinearRAG/blob/main/src/config.py) (defaults).
- Paper: [arXiv:2510.10114v4](https://arxiv.org/abs/2510.10114) — §3.1 (Tri-Graph, Eq. 1–2),
  §3.2 (Eq. 3–7), Table 1–2 (accuracy/efficiency), Appendix D (linearity), Appendix E
  (Table 4 relevance losses, Table 5 embedding backbones, Table 6 10M-token scaling).
- Maintenance: last code change 20260304 (PR #21, external contributor); README-only commits
  through 20260705. Active-ish research code, not a maintained product. ~526 stars, 61 forks.
