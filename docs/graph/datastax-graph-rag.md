# datastax/graph-rag (graph-retriever) — investigation notes

**Repo:** https://github.com/datastax/graph-rag · **Stars:** ~89 · **License:** Apache-2.0 · **Investigated:** 20260726 08:52

## What it is

A small Python library (`graph-retriever` core + `langchain-graph-retriever` bindings) that overlays a
traversable graph on an **existing** vector store using nothing but document metadata — no re-ingestion,
no LLM extraction, no separate graph database. Retrieval = vector search for seeds, then iterative
edge expansion where "follow an edge" is compiled into a metadata-filtered similarity search against
the same store. Core package is ~10 files / ~2k lines including docstrings. Last commit 20250505.

## The metadata edge model

Defined in `packages/graph-retriever/src/graph_retriever/edges/metadata.py` and `edges/_base.py`.

- **Declaration:** `EdgeSpec = tuple[str | "$id", str | "$id"]` — a `(source_field, target_field)`
  pair. Source is read from the *outgoing* doc's metadata, target names the field matched on the
  *incoming* doc. The magic string `"$id"` substitutes the document ID. Examples from
  `docs/guide/edges.md`: `("cites", "$id")` follows citations out; `("$id", "cites")` finds citers
  (reverse direction is just the flipped tuple); `("keywords", "keywords")` is a shared-value
  (undirected) edge; `("authors", "primary_author")` is an asymmetric shared-value edge.
- **Runtime form** (`edges/_base.py`): each doc yields `Edges(incoming: set[Edge], outgoing: set[Edge])`.
  Outgoing edges are expressed as the *incoming* edge they match: `MetadataEdge(incoming_field, value)`
  (matches docs where `metadata[field] == value` or `CONTAINS value` for list fields) or `IdEdge(id)`.
  Traversal is therefore value-equality join, computed lazily — there is no edge table anywhere.
- **Metadata shapes:** scalars or iterables of scalars (`BASIC_TYPES`); anything else warns and is
  skipped. Nested keys supported via dot-paths (`_nested_get`, `MetadataEdgeFunction._edges_from_dict`).
- **Escape hatch:** `edges` can be an arbitrary `EdgeFunction: Content -> Edges` when metadata isn't
  in joinable shape. Edges may differ per query — they're an argument to `traverse()`, not the index.
- **Pinakes mapping:** sidecar `links` ≈ `("links.cites", "$id")` (IdEdge), shared-tag ≈
  `("tags", "tags")`, co-located ≈ `("dir", "dir")`, sibling/parent-child ≈ id edges. Every planned
  Pinakes edge type fits this two-field vocabulary; `rel` becomes which EdgeSpec you enable.

## The traversal strategies

Core loop in `packages/graph-retriever/src/graph_retriever/traversal.py` (`_Traversal.traverse`):

1. Seed: `store.search_with_embedding(query, k=start_k)` plus optional `initial_root_ids` via `get()` — depth 0.
2. `strategy.iteration(nodes, tracker)` — the strategy decides, via the tracker, what to keep/expand.
3. Stop when `select_k` reached or nothing queued (`NodeTracker._should_stop_traversal`).
4. `select_next_edges()` collects outgoing edges of queued nodes **minus already-visited edges**
   (`_visited_edges` — a hub value like a popular tag is expanded exactly once, globally) and tracks
   per-edge minimum depth (`_edge_depths`; new node depth = min over its matched incoming edges).
5. `_fetch_adjacent()` → `Adapter.adjacent()`: per `MetadataEdge` a filtered similarity search with
   `k=adjacent_k`, per batch of `IdEdge`s a `get(ids)`; results merged and cut to **top adjacent_k by
   cosine similarity to the query** (`utils/top_k.py`). Neighbor expansion is query-ranked, never raw.

`NodeTracker` (`strategies/base.py`) is the whole strategy API: `select(nodes)` (add to results),
`traverse(nodes)` (queue for expansion; enforces visited-set and `max_depth`), `select_and_traverse`,
`num_remaining` (select_k budget left). Selection and expansion are decoupled — a strategy may expand
without keeping, or keep without expanding.

Knobs on `Strategy`: `select_k` (total results, default 5), `start_k` (seeds, 4), `adjacent_k`
(per-edge fetch, 10), `max_depth`. Note: `max_traverse` is declared and documented but **never read
by the traversal loop** — a dead knob (grep `traversal.py`).

- **Eager** (`strategies/eager.py`, 3 lines of logic): `tracker.select_and_traverse(everything)` — plain
  BFS until select_k or frontier exhaustion.
- **Mmr** (`strategies/mmr.py`): best-first, not BFS. Keeps a candidate pool with embeddings; score =
  `lambda_mult * sim(query) − (1−lambda) * max sim(already-selected)`. Each iteration pops the single
  best candidate, selects it, and expands *only its* edges (`select_and_traverse([next])` then break) —
  the traversal frontier itself is MMR-guided. `min_mmr_score` gives early termination. All local math.
- **Scored** (`strategies/scored.py`): user callable `scorer(Node) -> float`, max-heap (inverted
  `__lt__`), pops top `per_iteration_limit` per round, `finalize_nodes` re-sorts by score. This is the
  hook for edge-type/recency/PageRank-weighted traversal without touching the engine.

## The LazyGraphRAG example, mechanically

`docs/examples/lazy-graph-rag.ipynb` (rendered on the docs site). Index time is LLM-free: 2wikimultihop
articles get `metadata["mentions"]` (link structure from the dataset) and `metadata["entities"]` via a
local spaCy NER transformer. The notebook estimates an LLM-built knowledge graph over the same corpus
at ~$70k, vs "basically free" for the metadata graph. At query time:

1. Traversing retrieval: `GraphRetriever(edges=[("mentions","$id"), ("entities","entities")], k=100,
   start_k=30, adjacent_k=20, max_depth=3)` → ~100 docs.
2. Build an in-memory networkx `DiGraph` **over just the retrieved docs** using the same edge function
   (`langchain_graph_retriever/document_graph.py:create_graph` — two-pass: index docs by incoming edge,
   then materialise outgoing matches).
3. Communities via iterated Girvan–Newman, keeping the partition until modularity stops improving
   (`document_graph.py:_best_communities`, `group_by_community`).
4. One gpt-4o structured-output call **per community** extracting query-relevant claims (`claim`,
   `source_id`).
5. One gpt-4o call **per claim** for RankRAG-style relevance: prompt forces a True/False next token,
   rank = probability of "True" from logprobs (`compute_rank`).
6. Select top-ranked claims up to a token budget; one final answer call over the claim list.

So "lazy" = all graph analysis (community structure, claim extraction) happens post-retrieval, on a
~100-node subgraph, with the question already in hand.

## Cost profile

- **Index:** embeddings only, plus local NER. No LLM. This is the load-bearing economic claim and it
  matches Pinakes' sync-time position exactly.
- **Traversal:** free apart from ANN queries — roughly `1 + Σ_depth |new_edges|` filtered searches per
  query. No LLM in `graph-retriever` itself, ever.
- **LazyGraphRAG chain:** per query ≈ 1 embedding + N_communities extraction calls (each carrying full
  community text) + N_claims ranking calls + 1 answer call — easily dozens of gpt-4o calls. Cheap
  relative to eager graph construction; expensive relative to Pinakes' free path. Strictly a
  `--deep`-shaped workload.

## What's interesting for Pinakes

- Structural twin: metadata-defined edges over an existing store is exactly the sidecar position.
  Their conclusion after building it — the graph can live entirely in per-doc metadata, joined at
  query time — validates the `links` table + tag columns design with no graph DB.
- The `(source_field, target_field)` vocabulary cleanly expresses every planned Pinakes edge type,
  including direction (flip the tuple) and shared-value edges (same field twice).
- **Query-ranked expansion** is the standout mechanic: neighbors are fetched per edge but kept only
  top-`adjacent_k` by similarity to the query. This is what keeps hub edges (popular tags) from
  flooding the traversal — bounded fan-out with relevance-ordered truncation, not blind adjacency.
- Visited-**edge** (not just visited-node) dedup: a shared value expands once globally.
- Their LazyGraphRAG pipeline is a ready-made blueprint for `pnk ask --deep`: traverse free, then
  budgeted claim-extraction + logprob ranking over communities of the retrieved subgraph only.

## What to steal

1. The knob set for `pinakes_links` depth>1 / traversal MCP tool: `select_k`, `start_k`, `adjacent_k`,
   `max_depth`, plus per-edge min-depth tracking (`select_next_edges`) — proven, minimal, sufficient.
2. `NodeTracker`'s two-verb API (`select` vs `traverse`) — decoupling "return this" from "expand this"
   is the right abstraction if traversal strategies ever become pluggable.
3. Per-edge fan-out capping ranked by query similarity (`Adapter.adjacent` + `top_k`) — apply verbatim
   to shared-tag and co-located edges, which are Pinakes' hub risks.
4. Visited-edge set semantics: dedupe on `(edge_type, value)`, not only on doc ID.
5. Best-first MMR traversal (`Mmr._next`) as a free-path option — pure numpy, no model calls, and it
   yields diversity-aware multi-hop expansion.
6. For `--deep`: Girvan–Newman-until-modularity-peaks on the retrieved subgraph (~100 nodes, cheap)
   as the unit of claim extraction, and logprob-of-"True" as a one-token relevance scorer.

## What to avoid / doesn't fit

- **Query-time filter-join adjacency.** Their store has no edge table so every hop is an ANN query
  with a metadata filter. Pinakes has SQLite: precomputed `links` rows + SQL joins are cheaper, exact,
  and support PPR. Steal the ranking/truncation, not the join mechanism.
- The LangChain layering (`GraphRetriever`, transformers) — pure integration glue.
- Per-claim LLM ranking calls: cost scales linearly with claims; Pinakes' local cross-encoder does the
  same job for free on the free path. Reserve logprob ranking for `--deep` only, if at all.
- No BM25/hybrid anywhere — seeds are vector-only. Pinakes' RRF seeding is strictly stronger.
- Don't copy `max_traverse` (dead code) or the deprecated `Id`/`k` shims — API churn artifacts.
- Dormancy caveat: not archived, but silent since 20250505 — right after IBM's acquisition of
  DataStax (announced 20250225) — and at 89 stars there is no community carrying it. Quarry only;
  never a dependency.

## Key sources

- `packages/graph-retriever/src/graph_retriever/edges/metadata.py` — `EdgeSpec`, `MetadataEdgeFunction`
- `packages/graph-retriever/src/graph_retriever/edges/_base.py` — `MetadataEdge`, `IdEdge`, `Edges`
- `packages/graph-retriever/src/graph_retriever/traversal.py` — `_Traversal`, `select_next_edges`
- `packages/graph-retriever/src/graph_retriever/strategies/{base,eager,mmr,scored}.py` — `NodeTracker`, strategies
- `packages/graph-retriever/src/graph_retriever/adapters/base.py` — `Adapter.adjacent`, `_metadata_filter`
- `packages/langchain-graph-retriever/src/langchain_graph_retriever/document_graph.py` — `create_graph`, `_best_communities`
- `docs/guide/{edges,strategies,traversal}.md`, `docs/examples/lazy-graph-rag.ipynb`
