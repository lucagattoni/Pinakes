# fast-graphrag — investigation notes

**Repo:** https://github.com/circlemind-ai/fast-graphrag · **Stars:** ~3,800 · **License:** MIT · **Investigated:** 20260725 15:30

## What it is

Circlemind's open-source GraphRAG variant (~30 Python files, `fast_graphrag/`): LLM-extracted
entity/relation graph at insert time, **Personalized PageRank (PPR) exploration at query time**
instead of Microsoft GraphRAG's community detection + community-report summarization. Configured by
three strings — `domain`, `example_queries`, `entity_types` — templated into every extraction
prompt. Python 3.10–3.12, package version 0.0.5. Last commit **2025-11-01**; effectively dormant
since (Circlemind, a 3-person YC company, moved to a hosted product; the OSS repo is not archived
but has ~38 open issues and no activity through mid-2026). Benchmarks (`benchmarks/README.md`,
2wikimultihopqa 101q): evidence-recall 93% vs GraphRAG 73%, LightRAG 45%, VectorDB 42%; insertion
~1.5 min vs GraphRAG ~40 min for ~800 chunks.

## How the graph is built

- **Chunking** (`_services/_chunk_extraction.py`): regex split on separators, char-based windows
  (`chunk_token_size=800`, `chunk_token_overlap=100`, × `TOKEN_TO_CHAR_RATIO`). Chunk ID =
  `xxhash.xxh3_64_intdigest(chunk)` — content hash.
- **Incremental dedup** (`_graphrag.py: async_insert` → `state_manager.filter_new_chunks()`):
  chunks whose hash already exists in the KV store are skipped, so re-inserting a document costs
  zero LLM calls for unchanged chunks. That is the whole incremental story — no diffing, no
  re-linking pass.
- **Extraction** (`_services/_information_extraction.py: extract`): per new chunk, one
  `entity_relationship_extraction` call returning a structured `TGraph` (entities typed against
  `entity_types`; non-matching types coerced to `UNKNOWN`), then a gleaning loop
  (`entity_relationship_continue_extraction` + `entity_relationship_gleaning_done_extraction`) up
  to `max_gleaning_steps`. So 2 to 1+2·n LLM calls per chunk.
- **Merge** (`_policies/_graph_upsert.py`): `NodeUpsertPolicy_SummarizeDescription` merges nodes
  **by exact name**; when accumulated descriptions exceed `max_node_description_size=512` an LLM
  `summarize_entity_descriptions` call compresses them. `EdgeUpsertPolicy_UpsertValidAndMergeSimilarByLLM`
  only calls the LLM (`edges_group_similar`) when >`edge_merge_threshold=5` parallel edges exist
  between a node pair. Additionally `_state_manager.py: upsert` embeds each entity, does
  `get_knn(top_k=3)` and inserts an `"is"` identity **edge** between entities whose embedding
  similarity ≥ `insert_similarity_score_threshold=0.9` — alias resolution as graph edges, not
  destructive merging.
- **Storage** (`_storage/`): igraph graph pickled to `igraph_data.pklz` (`_gdb_igraph.py`,
  `write_picklez`/`Read_Picklez`), hnswlib vector index (`_vdb_hnswlib.py`), pickle KV stores
  (`_ikv_pickle.py`). No SQL, no server. Deps: igraph, hnswlib, scipy, scikit-learn, xxhash,
  pydantic, instructor, openai, google-genai, vertexai, voyageai, tiktoken — no torch, but the
  three vendor SDKs are hard deps; "local models" means any OpenAI-compatible endpoint, there is
  no bundled local inference.

## How retrieval works (PageRank exploration)

All in `_services/_state_manager.py: get_context` + `_graphrag.py: async_query`:

1. **Query entity extraction** — one LLM call (`extract_entities_from_query`, prompt
   `entity_extraction_query`) splits the query into **named** entities ("Alice") and **generic**
   ones ("teachers"). This is the only query-time LLM call before answer generation.
2. **Map to nodes by embedding** (`_score_entities_by_vectordb`): each named entity → nearest node
   with `top_k=1, threshold=0.7`; each generic entity → `top_k=20, threshold=0.5`; scores
   normalized per query-entity (`/= sum + 1e-8`) then max-aggregated into one sparse vector over
   nodes.
3. **PPR** (`_score_entities_by_graph` → `_gdb_igraph.py: score_nodes` →
   `igraph.personalized_pagerank(damping=0.85, directed=False, reset=that vector)`). Random-walk
   mass spreads from seed nodes to multi-hop neighbours — this replaces both community reports and
   any query-time LLM graph traversal.
4. **Cascade by sparse matmul**: entity scores × entity-to-relation incidence matrix
   (`_score_relationships_by_entities`, `entity_scores.dot(e2r)`) → relation scores × chunk
   matrix (`_score_chunks_by_relations`, `.dot(c2r)`) → chunk scores. Each stage filtered by a
   `_policies/_ranking.py` policy: `RankingPolicy_WithThreshold(threshold=0.05, max_entities=128)`,
   `RankingPolicy_TopK(top_k=10)`, or `RankingPolicy_Elbow` (max-gap cutoff on sorted scores).
5. Top entities/relations/chunks are truncated to token budgets (`entities_max_tokens` etc.) and
   sent to one answer-generation LLM call (`generate_response_query_with_references`).

## Where the 6× saving comes from

Measured $0.08 vs $0.48 on *The Wizard of Oz* (README). Mechanically: (a) **no community
detection/summarization** — Microsoft GraphRAG's Leiden clustering + per-community LLM report
generation (and re-generation on update) is the dominant cost, replaced here by PPR which is pure
igraph math; (b) **conditional LLM merging** — description summarization only past 512 chars,
edge grouping only past 5 parallel edges, vs unconditional summarize-everything; (c) **content-hash
chunk skipping** makes updates pay only for genuinely new chunks; (d) query time is 2 LLM calls
(entity extraction + answer), never map-reduce over communities. The extraction pass itself is
*not* cheaper than GraphRAG's — the saving is everything around it.

## Cost profile

Still fundamentally **pay-per-ingest**: every new chunk costs 2+ extraction LLM calls at sync
time, plus occasional merge/summarize calls, plus embedding of every entity and chunk. Query time
is cheap (2 LLM calls + PPR in milliseconds). A rebuild from scratch re-pays the full extraction
bill unless the pickle survives.

## What's interesting for Pinakes

- **PPR as a retrieval channel is LLM-free at query time.** Steps 2–4 above need only: seed
  nodes, an edge list, and sparse matmuls. Pinakes already has real nodes (documents) and real
  typed edges (`links` table + planned structural edges) — human-authored, so *better* seeds than
  LLM-extracted soup. The planned "PPR as third RRF channel" is exactly fast-graphrag's step 3–4
  with documents in place of entities, and it validates that the cascade (graph score → chunk
  score via incidence matmul) works and wins on multi-hop questions (93% vs 42% for pure vectors).
- **Named vs generic query-entity split** maps cleanly onto Pinakes: named → exact/FTS5 title
  match with a tight threshold, generic → embedding search with a loose one — and the split can be
  done heuristically (capitalization, quoting, title-index hit) without any LLM call.
- **Elbow ranking policy** (`RankingPolicy_Elbow`) is a nice free-path trick for deciding how many
  graph results deserve fusion, instead of a fixed k.
- The domain/example_queries/entity_types idea transfers to the *deep* path: a `pnk ask --deep`
  agent could carry KB-level "domain + typical queries + link types" from `pinakes.toml` to steer
  query-scoped extraction, with results written back to sidecars — consistent with the
  "lazy, budgeted, written to committed files" decision.

## What to steal

- **Personalized PageRank over the existing `links` graph as the third RRF channel** — seed from
  BM25+embedding top hits, damping 0.85, undirected, sparse scipy implementation (no igraph
  needed at Pinakes' scale; a few hundred lines with scipy already in the light stack). Free path
  stays free: zero LLM, zero network.
- Score cascade via incidence matrices (node scores → chunk scores by one sparse `.dot`) — the
  clean way to convert graph relevance into chunk-level RRF input.
- Elbow cutoff for variable-k selection of graph-channel results.
- Content-hash chunk identity for incremental sync cost-skipping (Pinakes should already hash;
  fast-graphrag confirms xxhash3 is sufficient and fast).
- Alias handling as explicit `is` edges rather than destructive merges — fits Pinakes' "ULIDs are
  permanent, never renumber" invariant.

## What to avoid / doesn't fit

- **LLM extraction at sync time** — the entire insert pipeline (2+ calls per chunk, gleaning,
  summarize-on-merge) violates the free path and the "never LLM extraction at sync time" decision
  outright. Also makes rebuilds expensive, violating ".pinakes/ is disposable."
- **Pickle-everything storage** (`igraph_data.pklz`, pickled KV) — opaque, version-fragile,
  contradicts Pinakes' single-SQLite + committed-files model. Graph edges belong in the `links`
  table; PPR can load them into scipy at query time.
- igraph/hnswlib dependencies — redundant with SQLite FTS5 + existing embedding index; hard vendor
  SDK deps (vertexai, voyageai) are exactly the weight Pinakes' core avoids.
- Exact-name node merging (`NodeUpsertPolicy_SummarizeDescription`) — brittle; Pinakes' ULID +
  sidecar identity is strictly stronger.
- Treat maintenance as **abandoned**: no commits since 2025-11-01, version 0.0.5, unimplemented
  stubs (`RankingPolicy_WithConfidence` raises `NotImplementedError`). Steal ideas, never depend
  on the package.

## Key sources

- `fast_graphrag/_services/_state_manager.py` — `get_context`, `_score_entities_by_vectordb`,
  `_score_entities_by_graph`, `_score_relationships_by_entities`, `_score_chunks_by_relations`,
  `upsert` (thresholds 0.7/0.5/0.9)
- `fast_graphrag/_storage/_gdb_igraph.py` — `IGraphStorage.score_nodes`,
  `personalized_pagerank(damping=0.85, directed=False)`, `igraph_data.pklz`
- `fast_graphrag/_policies/_ranking.py` — `RankingPolicy_WithThreshold(0.05, 128)`,
  `RankingPolicy_TopK(10)`, `RankingPolicy_Elbow`
- `fast_graphrag/_policies/_graph_upsert.py` — `NodeUpsertPolicy_SummarizeDescription(512)`,
  `EdgeUpsertPolicy_UpsertValidAndMergeSimilarByLLM(edge_merge_threshold=5)`
- `fast_graphrag/_services/_information_extraction.py` — `extract`,
  `extract_entities_from_query` (named/generic), gleaning loop
- `fast_graphrag/_services/_chunk_extraction.py` — xxhash3 chunk IDs, 800/100 char-ratio chunks
- `fast_graphrag/_graphrag.py`, `fast_graphrag/_prompt.py` — insert/query orchestration,
  domain/example_queries/entity_types templating
- `benchmarks/README.md` — 2wikimultihopqa/HotpotQA recall numbers; `README.md` — $0.08 vs $0.48
- GitHub API 20260725: 3,828 stars, MIT, pushed_at 2025-11-01, 38 open issues, not archived
