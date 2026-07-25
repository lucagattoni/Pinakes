# LightRAG — investigation notes
**Repo:** https://github.com/HKUDS/LightRAG · **Stars:** ~38k · **License:** MIT · **Investigated:** 20260725 15:29
**Paper:** https://arxiv.org/abs/2410.05779 (EMNLP 2025)

## What it is
Graph-based RAG framework from HKU: LLM-extracted entity/relation knowledge graph + vector
embeddings, pitched as the lightweight alternative to Microsoft GraphRAG (no community hierarchy /
community summaries; dual-level keyword retrieval instead). Ships a server, WebUI, REST API, MCP is
third-party. Core is one big `LightRAG` dataclass (`lightrag/lightrag.py`, ~5.9k lines) orchestrating
pluggable storages defined in `lightrag/base.py`:

- `BaseKVStorage` (docs, chunks, LLM cache), `BaseVectorStorage`, `BaseGraphStorage` (undirected),
  `DocStatusStorage` (pipeline states, content-hash dedup).
- Defaults are file-based: `JsonKVStorage`, `NanoVectorDBStorage`, `NetworkXStorage`,
  `JsonDocStatusStorage`; production bindings for Postgres, Neo4j, Memgraph, Milvus, Qdrant,
  MongoDB, OpenSearch.
- Named instances: `chunks_vdb`, `entities_vdb`, `relationships_vdb` (three separate vector
  indexes), `chunk_entity_relation_graph`, `llm_response_cache`, `doc_status`.

Maintenance mid-2026: very active (~9k commits; recent work on multimodal parsing via
MinerU/Docling, role-specific LLMs, rerank bindings, deletion with KG rebuild).

## How the graph is built
Eager, at index time, entirely by LLM:

1. `ainsert` → `apipeline_enqueue_documents` (dedup by content hash, doc-status queue) →
   `apipeline_process_enqueue_documents` → fixed-token chunking.
2. `extract_entities` (`lightrag/operate.py:3559`): **one LLM call per chunk** with the
   `entity_extraction` prompt (delimiter format `<|#|>` or JSON mode), then up to
   `entity_extract_max_gleaning` (default **1**, `DEFAULT_MAX_GLEANING`) "please continue" gleaning
   calls per chunk, guarded by `MAX_EXTRACT_INPUT_TOKENS` (20480). Per-chunk caps:
   `DEFAULT_MAX_EXTRACTION_RECORDS=100`, `DEFAULT_MAX_EXTRACTION_ENTITIES=40`.
3. `merge_nodes_and_edges` → `_merge_nodes_then_upsert` / `_merge_edges_then_upsert`
   (`operate.py:2227/2560`): dedup is **exact entity-name match only** — no embedding-based entity
   resolution. Descriptions from all chunks are concatenated (`_combine_descriptions_dedup`).
4. `_handle_entity_relation_summary` (`operate.py:341`): when an entity accumulates ≥
   `force_llm_summary_on_merge` (default **8**) description fragments or exceeds
   `summary_context_size` (12000 tokens), an **LLM summarization call** rewrites the description
   (recursive map-reduce). So merging itself costs LLM calls as the corpus grows.
5. Entities and relations are embedded into `entities_vdb` / `relationships_vdb`; each node/edge
   keeps `source_id` = list of chunk ids (provenance).

Incremental: document-level only (hash dedup, status queue, resumable). Deletion
(`adelete_by_doc_id`) triggers `rebuild_knowledge_from_chunks` (`operate.py:992`), which rebuilds
affected entities/relations **from cached extraction results** (`_get_cached_extraction_results`,
`enable_llm_cache_for_entity_extract=True`) instead of re-calling the LLM.

## How retrieval works
**The caller picks the mode.** `QueryParam.mode ∈ {"local","global","hybrid","naive","mix","bypass"}`,
default `"mix"` (`base.py`). There is **no automatic router** — the only routing logic is fallback:
if both keyword lists come back empty and the query is <50 chars, the raw query becomes the
low-level keyword; otherwise fail (`kg_query`, `operate.py:4027`).

1. `extract_keywords_only` (`operate.py:4389`): **one LLM call per query** returning JSON
   `{high_level_keywords, low_level_keywords}` (prompt at `lightrag/prompt.py:484`); result cached
   in `llm_response_cache` by args-hash.
2. `_build_query_context` (`operate.py:5273`), 4 stages. `_perform_kg_search` (`operate.py:4551`):
   - **local**: embed ll_keywords → `entities_vdb` top-k → one-hop graph expansion
     (`_get_node_data`).
   - **global**: embed hl_keywords → `relationships_vdb` top-k → endpoint entities
     (`_get_edge_data`).
   - **hybrid**: both. **mix**: both + raw-query vector search on `chunks_vdb`.
   - **naive**: chunk vector search only, no graph, no keyword LLM call (`naive_query`,
     `operate.py:5992`).
   Query/ll/hl embeddings computed in a single batched embedding call.
3. Chunks are recovered from entity/relation `source_id` lists, picked by `kg_chunk_pick_method`:
   `"VECTOR"` (default, cosine vs query) or `"WEIGHT"` (occurrence-count polling)
   (`_find_related_text_unit_from_entities`, `operate.py:5512`).
4. **Fusion is naive round-robin interleave** of the three chunk streams (vector, entity-derived,
   relation-derived) with first-seen dedup — no RRF, no score fusion (`_merge_all_chunks`,
   `operate.py:4978`).
5. Token truncation budgets: `max_entity_tokens=6000`, `max_relation_tokens=8000`,
   `max_total_tokens=30000`.
6. Rerank: `apply_rerank_if_enabled` (`lightrag/utils.py:4642`) inside `process_chunks_unified`;
   backends are **hosted APIs only** — `cohere_rerank`, `jina_rerank`, `ali_rerank`,
   `generic_rerank_api` (`lightrag/rerank.py`) — no local cross-encoder. `enable_rerank=True` by
   default but `DEFAULT_RERANK_BINDING="null"`, then `min_rerank_score` filter.
7. Final answer = one more LLM call; `only_need_context=True` skips it and returns context.

## Cost profile
- **Index time (the expensive side):** 1–2 LLM calls per chunk (extraction + gleaning) + periodic
  LLM merge-summaries + embedding calls for chunks, entities, and relations. A personal-KB-sized
  corpus of a few thousand chunks means thousands of LLM calls before the first query.
- **Query time:** 1 keyword-extraction LLM call (cached per query hash) + 1 answer LLM call +
  1 batched embedding call (+ optional rerank API). `naive` mode skips the keyword call.
- **Caching:** `llm_response_cache` KV covers extraction, keywords, and query responses
  (`enable_llm_cache=True`, `enable_llm_cache_for_entity_extract=True`). Cache is what makes
  re-index/delete-rebuild cheap — but it lives in internal storage, keyed by prompt hash, not in
  anything user-visible or committable.
- **Budget consciousness:** token *context* budgets exist everywhere, but there is no spend
  ledger, no cost cap, no "free path" concept. Role-specific LLMs (`role_llm_funcs`: extract /
  query / keyword / vlm) let you point extraction at a cheap model — that is the whole cost story.
- Genuinely incremental: content-hash doc dedup, resumable pipeline, cached-extraction graph
  rebuild after deletion. Genuinely lazy: nothing — the graph is always built eagerly at insert.

## What's interesting for Pinakes
- Validates the Pinakes decision *against* sync-time extraction: LightRAG's entire cost center is
  exactly the pipeline Pinakes ruled out, and its own mitigation (cache extraction results, rebuild
  graph from cache for free) is a KV-store approximation of Pinakes' "write extraction back into
  sidecars, free forever after" — except LightRAG's version is invisible, uncommittable state.
- Dual-level keywords is a real, cheap idea: *entity-ish* terms query one index, *concept-ish*
  terms query another. The split itself needs no LLM if the caller (Claude via MCP) supplies it.
- `QueryParam.hl_keywords` / `ll_keywords` shows the right API shape: the query-understanding LLM
  call is skippable when the caller passes keywords — the agent outside does the thinking.
- Relation/edge embedding (`relationships_vdb`) — searching *edges*, not just nodes — is the one
  retrieval-channel idea here Pinakes doesn't already have. Pinakes' `links` table rows
  (`src, rel, dst` + doc titles) could be rendered to text and indexed in FTS5/embeddings as a
  cheap, extraction-free analogue.
- Round-robin fusion with no scores is *weaker* than Pinakes' RRF — nothing to learn there;
  confirms RRF + local cross-encoder is already ahead of a 38k-star project's fusion story.

## What to steal
- **Expose keyword slots on the MCP search tool** (`pinakes_search(query, entities=[], concepts=[])`
  or similar): let the calling agent do LightRAG's keyword-extraction step for free, mapping
  entity-ish terms to FTS5/link-graph lookups and concept-ish terms to embedding search. Zero cost,
  agent-driven — fits the free path exactly.
- **Index the link graph as a retrieval channel**: verbalize `links` rows + structural edges into
  searchable text (LightRAG's `relationships_vdb` without the LLM). Free at build time.
- **`only_need_context` discipline**: every retrieval surface returns context, never generated
  answers — Pinakes already does this via MCP; keep it that way even for `--deep`.
- **If lazy extraction ever lands**: copy the *shape* of `rebuild_knowledge_from_chunks` — derive
  graph state purely from stored extraction artifacts so rebuild never re-calls an LLM — but store
  the artifacts in committed sidecars, not an opaque KV cache. Also steal the merge-dedup guard
  (`_combine_descriptions_dedup`): re-extraction must not accumulate duplicate facts.
- Doc-status pipeline with content-hash dedup (`DocStatusStorage.get_doc_by_content_hash`) is a
  clean pattern for `pnk sync` resumability.

## What to avoid / doesn't fit
- **Eager per-chunk LLM extraction + gleaning + LLM merge-summaries** — violates the free path and
  the no-sync-time-extraction decision; it is also LightRAG's scaling problem, not a feature.
- **Query-time mandatory LLM keyword call** in every graph mode — Pinakes' caller-supplied
  keywords make it unnecessary; never put an LLM between the user and retrieval.
- **Hosted-API-only rerank** (`rerank.py`) — Pinakes' local cross-encoder is strictly better for
  the free path.
- **Three separate vector indexes + pluggable storage zoo** — the `base.py` abstraction layer plus
  9 backend bindings is most of the repo's bulk; Pinakes' single SQLite file is the right call.
- **Exact-name entity dedup** — if extraction ever exists, name-match-only merging silently forks
  entities ("LightRAG" vs "LightRAG framework"); don't copy it.
- Modes as user-facing API: five query modes pushed onto the caller with no router is a UX papercut;
  Pinakes' single `search` + agent-composed tools avoids inventing modes at all.

## Key sources
- https://github.com/HKUDS/LightRAG (stars/license/activity)
- https://arxiv.org/abs/2410.05779
- `lightrag/lightrag.py` — `ainsert`, `apipeline_*`, `aquery_llm` (mode dispatch ~L3497), storage
  defaults, `rerank_model_func` wiring
- `lightrag/base.py` — storage ABCs, `QueryParam` (modes, defaults)
- `lightrag/operate.py` — `extract_entities` L3559, `_merge_nodes_then_upsert` L2227,
  `_handle_entity_relation_summary` L341, `rebuild_knowledge_from_chunks` L992, `kg_query` L4027,
  `extract_keywords_only` L4389, `_perform_kg_search` L4551, `_merge_all_chunks` L4978,
  `naive_query` L5992
- `lightrag/prompt.py` — `keywords_extraction` L484, `entity_extraction`
- `lightrag/constants.py` — all defaults quoted above
- `lightrag/utils.py` — `apply_rerank_if_enabled` L4642; `lightrag/rerank.py` — API-only backends
