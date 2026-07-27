# Graphiti — investigation notes
**Repo:** https://github.com/getzep/graphiti · **Stars:** ~29.2k · **License:** Apache-2.0 · **Investigated:** 20260725 15:29
**Paper:** "Zep: A Temporal Knowledge Graph Architecture for Agent Memory" — arXiv:2501.13956

## What it is
Temporally-aware knowledge-graph memory for agents (the engine behind Zep). Ingests discrete
"episodes" (messages, text, JSON), extracts an entity/relationship graph with an LLM, and serves it
back through hybrid search. Backends: Neo4j 5.26+, FalkorDB 1.1.2+, Amazon Neptune; Kuzu (the only
embedded option) was **marked deprecated in v0.29.2** and dropped from the test matrix — the project
is server-database-first. Actively maintained: releases roughly monthly through mid-2026 (v0.28.x
Feb, v0.29.0–0.29.2 through June 2026; MCP server versioned separately, v1.0.2).

## How the graph is built
`graphiti_core/graphiti.py::Graphiti.add_episode(name, episode_body, source_description,
reference_time, source, group_id, entity_types, edge_types, edge_type_map, saga, ...)` runs a
pipeline (helpers in `graphiti_core/utils/maintenance/`):
1. `retrieve_episodes()` — pull the last-n prior episodes as extraction context.
2. `node_operations.extract_nodes()` — **LLM** entity extraction; `_collapse_exact_duplicate_extracted_nodes`
   merges exact normalized-name dupes within the pass.
3. `node_operations.resolve_extracted_nodes()` — dedup against the existing graph, cascading:
   `_collect_candidate_nodes` does a plain cosine search (`NODE_DEDUP_CANDIDATE_LIMIT = 15`,
   `NODE_DEDUP_COSINE_MIN_SCORE = 0.6`) → `_resolve_with_similarity` resolves deterministically when
   confident → only unresolved nodes escalate to `_resolve_with_llm`
   (`prompt_library.dedupe_nodes.nodes`, returns `duplicate_candidate_id`, negative = new entity).
4. `edge_operations.extract_edges()` — **LLM** relationship extraction, including `valid_at`/`invalid_at`
   guesses; `_extract_edge_timestamps` is a fallback **LLM** call for edges missing them.
5. `edge_operations.resolve_extracted_edges()` — per edge: `EntityEdge.get_between_nodes` fetches
   existing edges with the same endpoints, hybrid search finds duplicate + contradiction candidates,
   then `resolve_extracted_edge` calls the **LLM** `dedupe_edges.resolve_edge` prompt returning
   `duplicate_facts` and `contradicted_facts` indices.
6. `node_operations.extract_attributes_from_nodes()` — **LLM** typed-attribute extraction per node
   plus batched summary regeneration (`_extract_entity_summaries_batch`, flights of `MAX_NODES = 30`;
   short summaries get facts appended without an LLM call).
7. Embeddings for nodes/edges; `build_episodic_edges` adds MENTIONED_IN provenance edges
   episode→entity; optional `update_community()` (**LLM** community summaries).
So a single episode costs on the order of 4–6+ LLM calls even when nothing new is learned.
`add_episode_bulk` batches the same stages (`extract_nodes_and_edges_bulk`, `dedupe_nodes_bulk`,
`dedupe_edges_bulk`). `add_triplet` (also an MCP tool) bypasses extraction entirely.

## The bi-temporal model
Two independent timelines per entity edge (`EntityEdge` fields):
- **Ingest time:** `created_at` (when Graphiti learned the fact) and `expired_at` (when Graphiti
  learned it no longer holds).
- **Valid time:** `valid_at` / `invalid_at` — when the fact was true in the world, LLM-extracted
  from episode text relative to `reference_time`.

Contradictions never delete. `edge_operations.resolve_edge_contradictions` compares temporal bounds:
when a new edge supersedes an old one, the old edge gets `invalid_at = new_edge.valid_at` and
`expired_at = utc_now()`. History stays queryable ("point-in-time" questions); search filters
(`valid_at_after/before`, `invalid_at_after/before` on the MCP surface) slice it. Deletion exists
only as explicit tooling (`delete_entity_edge`, `delete_episode` with cascade of solely-derived
elements).

## How retrieval works
`graphiti_core/search/search.py::search()` fans out over four scopes in parallel
(`semaphore_gather`): `edge_search`, `node_search`, `episode_search`, `community_search`. Each scope
runs its configured channels in parallel, each fetching `2 * limit` candidates:
- **bm25** — `edge_fulltext_search` / `node_fulltext_search` (DB fulltext index),
- **cosine** — `edge_similarity_search` / `node_similarity_search`,
- **bfs** — `edge_bfs_search` / `node_bfs_search` graph expansion from `bfs_origin_node_uuids`; if
  BFS is enabled with no origins, origins are taken from the initial bm25/cosine results and BFS
  reruns — i.e. lexical/vector hits seed graph-neighborhood expansion.

Rerankers (`SearchConfig`): `rrf()`, `maximal_marginal_relevance()` (MMR over embeddings),
`cross_encoder.rank()`, `node_distance_reranker()` (graph distance from a `center_node_uuid`), and
episode-mentions (sort by `len(edge.episodes)` — frequency as salience).
`search_config_recipes.py` ships 16 named recipes, e.g. `EDGE_HYBRID_SEARCH_RRF` (the default for
`Graphiti.search()`), `EDGE_HYBRID_SEARCH_NODE_DISTANCE` (auto-selected when a `center_node_uuid` is
passed), `COMBINED_HYBRID_SEARCH_CROSS_ENCODER` (bm25 + cosine + bfs, cross-encoder rerank —
default for `search_()`). Simple API `search()` returns `list[EntityEdge]` (facts); advanced
`search_()` returns a `SearchResults` of nodes+edges+episodes+communities.

## The MCP server, tool by tool
`mcp_server/src/graphiti_mcp_server.py` (FastMCP; HTTP transport default at `/mcp/`, stdio
supported; `config.yaml` with `${ENV}` expansion). 13 tools; all errors come back as a uniform
`ErrorResponse {error: str}`, mutations as `SuccessResponse {message: str}`.

- **`add_memory`**`(name, episode_body, group_id?, source='text', source_description='', uuid?,
  reference_time?, excluded_entity_types?, custom_extraction_instructions?, previous_episode_uuids?,
  update_communities=False, saga?, saga_previous_episode_uuid?)` → SuccessResponse. Does **not**
  process inline: queues the episode per `group_id`, processed sequentially per group in the
  background to avoid race conditions. The caller gets "queued", never the resulting nodes/edges.
- **`search_nodes`**`(query, group_ids?, max_nodes=10, entity_types?, center_node_uuid?)` →
  `NodeSearchResponse {message, nodes: [{uuid, name, labels, created_at, summary, group_id,
  attributes}]}` — embeddings stripped (`to_node_result`).
- **`search_memory_facts`**`(query, group_ids?, max_facts=10, center_node_uuid?, edge_types?,
  valid_at_after?, valid_at_before?, invalid_at_after?, invalid_at_before?)` →
  `FactSearchResponse {message, facts: [...]}` where each fact is
  `edge.model_dump(exclude={'fact_embedding'})` — uuid, name (relation type), fact (NL sentence),
  source/target node uuids, group_id, created_at/expired_at, valid_at/invalid_at, episodes.
- **`get_entity_edge`**`(uuid)` → formatted edge dict. **`delete_entity_edge`**`(uuid)`,
  **`delete_episode`**`(uuid)` → SuccessResponse.
- **`get_episodes`**`(group_ids?, max_episodes=10)` → `{message, episodes: [{uuid, name, content,
  created_at, source, source_description, group_id}]}` (recency, not search).
- **`get_episode_entities`**`(episode_uuids)` → `{message, nodes, edges}` — provenance: everything
  an episode created.
- **`add_triplet`**`(source_node_name, edge_name, fact, target_node_name, group_id?,
  source_node_uuid?, target_node_uuid?)` → `{message, nodes, edges}` — direct write, no extraction.
- **`summarize_saga`**`(saga_name, group_id?)` → `{message, uuid, name, summary}`;
  **`build_communities`**`(group_ids?)` → `{message, community_count, edge_count, communities}`;
  **`clear_graph`**`(group_ids?)`; **`get_status`**`()` → `{status, message}`; plus a non-MCP
  `GET /health` route.

**Well-designed:** every tool speaks entity/relation vocabulary, not graph plumbing — no generic
"run traversal" tool; small flat argument lists with defaults; `center_node_uuid` as a one-parameter
"rerank near this node" knob; uuids in every result so calls chain (search → get_entity_edge →
get_episode_entities); embeddings always stripped from payloads; uniform error/success envelopes;
facts as NL sentences an agent can quote directly. **Awkward:** `add_memory`'s fire-and-forget queue
means the agent can't act on what an episode produced (no job id / completion signal beyond polling
`get_episodes`); no explicit neighbors/traversal tool — graph structure is reachable only implicitly
through rerankers, so an agent cannot ask "what links to X"; timestamps are stringly-typed ISO args;
`group_ids` accepting `str | list[str]` is a schema smell; 13 tools is a lot of surface for what an
LLM caller must hold in context.

## Cost profile
- **LLM required, per episode, at ingest:** entity extraction, node dedup (escalation path), edge
  extraction, edge dedup/contradiction, timestamp fallback, attribute/summary extraction —
  unavoidable; this is the product. Plus embedding calls for every node/edge. Communities and saga
  summaries are additional LLM calls.
- **Free at query time:** bm25, cosine, BFS, RRF, MMR, node-distance, episode-mentions rerank —
  pure math/DB. Cross-encoder rerank costs per query (OpenAI/Gemini rerankers) unless using the
  local `sentence_transformers` BGE cross-encoder client.
- **Local models:** supported via OpenAI-compatible endpoints (Ollama, vLLM, llama.cpp) for both
  LLM and embedder, but the pipeline leans hard on structured output; the README warns small local
  models routinely fail the extraction/dedup schemas. There is no non-LLM ingestion mode.

## What's interesting for Pinakes
- Independent confirmation of Pinakes' retrieval shape: bm25 + cosine fused (RRF default),
  cross-encoder as the premium reranker — Graphiti converged on the same stack.
- **BFS as a third retrieval channel seeded by the other two channels' hits** is exactly the
  "graph as an RRF channel" idea, and cheaper than Personalized PageRank: expand the link
  neighborhood of top lexical/vector hits and let RRF fuse it.
- `center_node_uuid` + `node_distance_reranker`: graph distance from a focal document as a rerank
  signal — a free, local-computable alternative or complement to PPR.
- Bi-temporal fields as *data model* (valid_at/invalid_at vs created_at) — the invalidation-not-
  deletion discipline matches Pinakes' "ULIDs are permanent" ethos.
- Named search recipes (`EDGE_HYBRID_SEARCH_RRF`, ...) as a way to expose tuned configurations
  without exposing 15 knobs.

## What to steal
- **MCP result envelopes:** uniform `{message, <plural>: [...]}` success + `{error}` shapes,
  embeddings always stripped, ids in every row for chaining. Apply directly to
  `pinakes_search`/`pinakes_links` returns.
- **`center_node_uuid` pattern for `pinakes_links`-adjacent search:** one optional arg on
  `pinakes_search` ("near this doc") backed by link-graph distance is agent-ergonomic and free.
- **BFS-from-initial-results:** implement in SQLite with a recursive CTE over the existing `links`
  table, feed as a third RRF channel — no LLM, no schema change, satisfies the golden-set gate.
- **Provenance tool shape** (`get_episode_entities`): a "what does this doc link to / what links
  here" is exactly `pinakes_links(doc_id, rel?, direction?, depth?)` — Graphiti's *lack* of such an
  explicit tool is its biggest MCP gap; Pinakes' planned tool is the better design. Keep it.
- **Episode-mentions reranker analogue:** in-degree over the `links` table (citation count) as a
  zero-cost salience signal — cheaper than PPR, worth evaluating first.

## What to avoid / doesn't fit
- **LLM-at-ingest pipeline** — 4–6+ LLM calls per episode violates the free path absolutely; this
  is Graphiti's core loop and precisely what Pinakes already decided never to do at sync time.
- **Server graph DB dependency** — Neo4j/FalkorDB required, the embedded backend (Kuzu) deprecated
  in v0.29.2. Confirms betting local-first on a graph DB engine is fragile; SQLite + links table is
  the right call.
- **Fire-and-forget ingest tool** — `add_memory`'s opaque queue is the wrong shape for a local CLI
  where `pnk sync` can just be synchronous and report what changed.
- **Extracted-entity graph as the unit of retrieval** — Graphiti returns facts/entities, Pinakes
  returns documents/chunks with human-authored typed links; grafting entity extraction on (even
  lazily) should stay behind the existing "budgeted, query-scoped, write-back" gate, not be copied
  from here.
- **13-tool MCP surface** — keep Pinakes at 4–5 tools; Graphiti shows the cost of surface sprawl.

## Key sources
- `graphiti_core/graphiti.py` — `add_episode`, `add_episode_bulk`, `search`, `search_`, `retrieve_episodes`
- `graphiti_core/utils/maintenance/node_operations.py` — `extract_nodes`, `resolve_extracted_nodes`,
  `_collect_candidate_nodes`, `_resolve_with_llm`, `extract_attributes_from_nodes`
- `graphiti_core/utils/maintenance/edge_operations.py` — `resolve_extracted_edges`,
  `resolve_extracted_edge`, `resolve_edge_contradictions`, `build_episodic_edges`
- `graphiti_core/search/search.py` — `search`, `edge_search`/`node_search`/`episode_search`/`community_search`
- `graphiti_core/search/search_config_recipes.py` — the 16 recipes
- `mcp_server/src/graphiti_mcp_server.py` — the 13 tools; `mcp_server/src/utils/formatting.py` —
  `format_fact_result`, `to_node_result`, `to_edge_result`
- README (backends, local-model caveats); releases page (v0.29.2, Kuzu deprecation, MCP v1.0.2);
  arXiv:2501.13956
