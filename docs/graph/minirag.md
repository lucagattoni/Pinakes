# MiniRAG — investigation notes
**Repo:** https://github.com/HKUDS/MiniRAG · **Stars:** ~2.0k · **License:** MIT · **Investigated:** 20260726 08:52
**Paper:** arXiv 2501.06713 (ACL 2026, "MiniRAG: Towards Extremely Simple Retrieval-Augmented Generation")

## What it is
HKU (same lab as LightRAG) RAG framework designed so that **small language models (1.5–4B)** can
both build and query a graph index without collapsing. Two ideas (paper §2): (1) a *semantic-aware
heterogeneous graph* mixing text-chunk nodes and named-entity nodes, so raw chunks stay retrievable
and the SLM never has to summarize well; (2) *topology-enhanced retrieval* — entity matching plus
k-hop path/edge voting replaces the precise semantic matching an SLM can't do. Codebase is a
LightRAG fork in miniature: `MiniRAG` dataclass (`minirag/minirag.py`) over pluggable storages
(`minirag/base.py`), defaults `JsonKVStorage` + `NanoVectorDBStorage` + `NetworkXStorage`; bindings
for Neo4j/Postgres/TiDB/Milvus etc. under `minirag/kg/`. Default `llm_model_name` in the dataclass
is literally `meta-llama/Llama-3.2-1B-Instruct`.

Maintenance mid-2026: **quiet**. Created 2025-01-11, last push **2025-10-16** (GitHub API,
checked 20260726 08:52); ~2.0k stars, 255 forks, 36 open issues. Research artifact, not a product.

## The heterogeneous graph, precisely
Paper §2.1, Eq. 1: `G = ({V_c, V_e}, {E_α, (e_β, d_eβ) ∈ E_β})`.

- **Nodes:** text chunks `V_c` (1200-token, 100 overlap) and named entities `V_e`
  (name + type + LLM description; types default `["organization","person","location","event"]`,
  `PROMPTS["DEFAULT_ENTITY_TYPES"]` in `minirag/prompt.py`).
- **Edges:** entity–entity `E_α` (with LLM description + keywords + numeric strength) and
  entity–chunk `E_β` carrying a text description `d_eβ` of the entity-in-context.
- **In code**, entity–chunk edges are not explicit graph edges: provenance `source_id` fields
  (chunk-hash lists joined by `<SEP>`) on every node and edge play that role
  (`_merge_nodes_then_upsert` / `_merge_edges_then_upsert`, `minirag/operate.py`).
- **Four vector indexes** (`extract_entities`, `minirag/operate.py`): `entity_vdb`
  (name+description), `entity_name_vdb` (**name only** — the query-side workhorse),
  `relationships_vdb` (keywords+src+tgt+description), `chunks_vdb` (chunk text). Embeddings come
  from whatever lightweight sentence model you plug in; graph topology itself is not embedded
  (node2vec config exists but is unused in the query path).

## What the small model does at index time
`extract_entities` (`minirag/operate.py`) — per 1200-token chunk:
1. One LLM call with `PROMPTS["entity_extraction"]` — and here paper and code diverge: the shipped
   prompt is the **full LightRAG/GraphRAG-style one** (entity name/type/**description**, plus
   relationships with description + keywords + strength, plus content keywords). A
   `entity_extraction_noDes` variant sits commented out. So the "no relation semantics needed"
   pitch is aspirational; the code still asks the SLM to name relationships.
2. Up to `entity_extract_max_gleaning=1` "MANY entities were missed" continuation call, gated by a
   yes/no `entiti_if_loop_extraction` call → **~2–3 LLM calls per chunk**.
3. Regex/delimiter parsing (`("entity"<|>NAME<|>type<|>desc)##...`) — tolerant of sloppy SLM
   output because it's pattern-matching, not JSON. Merge duplicates across chunks; descriptions
   above `entity_summary_to_max_tokens=500` get an LLM summarize call.
`enable_llm_cache=True` caches every extraction call, so re-runs are free. Incremental insert
exists (`apipeline_enqueue_documents` / `apipeline_process_enqueue_documents`, content-hash dedup,
doc-status tracking) plus `delete_by_entity`. Paper Fig. 2 shows the honest failure mode: Phi-3.5's
descriptions are vague vs gpt-4o-mini's — the design survives *because* retrieval leans on names,
types, and topology rather than description quality. Verdict on feasibility: yes, 1–4B models
handle this — GLM-Edge-**1.5B** builds an index that scores 52.5% on LiHua (vs Phi-3.5-mini 3.8B's
53.3%), so quality is nearly flat across 1.5–4B.

## How retrieval works
`minirag_query` → `_build_mini_query_context` (`minirag/operate.py`), paper §2.2:
1. **One SLM call** with `PROMPTS["minirag_query2kwd"]`: outputs JSON `answer_type_keywords`
   (≤3, chosen from the **graph's own observed type pool**, `get_types()`) and
   `entities_from_query` (≤5). Parsed with `json_repair` + a fallback re-parse — SLM-tolerant.
2. Each query entity → `entity_name_vdb` top-k → seed nodes `V̂_s`.
3. `get_neighbors_within_k_hops(node, 2)` per seed → candidate paths; seeds with no paths are
   pruned except the top 20% by similarity score.
4. `get_node_from_types(type_keywords)` → candidate **answer nodes** `V̂_a`; each path scored by
   how many answer-type nodes it touches (`cal_path_score_list`, `minirag/utils.py`).
5. `relationships_vdb` queried with the raw query; edges touching seed/answer entities vote for
   paths containing them as a contiguous subsequence (`edge_vote_path`) — the code's approximation
   of paper Eq. 2's k-hop edge relevance `ω_e`.
6. `path2chunk`: paths → chunk ids via `source_id` provenance, weighted by path scores; entity
   descriptions are matched to the query with **Levenshtein** by default (`calculate_similarity`,
   `minirag/utils.py` — not embeddings!) to filter which chunks of a prolific entity count.
7. `kwd2chunk`: Counter vote over chunk ids, ×10 boost if the chunk is also a top `chunks_vdb`
   dense hit — i.e. dense retrieval and graph voting are fused at the end.
8. Final context = entities CSV + chunks CSV → **one** generation call.
Total LLM at query time: 2 calls (keyword extraction + answer). No PPR, no beam search — bounded
2-hop neighborhood + counting. Step 1 is the only query-side step that needs an LM at all.

## Benchmarks and where it loses
Paper Table 1 (acc↑, %). On **LiHua-World** — their own benchmark, and the most personal-KB-like
dataset in any of these papers: one year of a virtual user's chat logs, with single-hop/multi-hop/
summary QA and annotated evidence:

| Model | NaiveRAG | GraphRAG | LightRAG | MiniRAG |
|---|---|---|---|---|
| Phi-3.5-mini (3.8B) | 41.2 | fails | 39.8 | **53.3** |
| GLM-Edge-1.5B | 42.8 | fails | 35.7 | **52.5** |
| Qwen2.5-3B | 43.7 | fails | 39.2 | **48.8** |
| MiniCPM3-4B | 43.4 | fails | 35.4 | **51.3** |
| gpt-4o-mini | 46.6 | 35.3 | **56.9** | 54.1 |

MultiHop-RAG: same pattern with SLMs (MiniRAG 47.8–51.4 vs NaiveRAG 39.2–44.4, LightRAG ≤27 or
fails); with gpt-4o-mini MiniRAG wins outright (68.4 vs LightRAG 64.9). **Where it loses:** (1)
with a competent LLM on LiHua, plain LightRAG beats it — the topology crutch costs precision once
the model can do semantics; (2) error rates are sometimes higher than NaiveRAG's (Qwen2.5-3B:
33.1 vs 31.7 err on MultiHop); (3) GraphRAG-class global/summary questions have no dedicated path.
Ablations (Table 2): swapping in description-driven indexing (`-I`) **halves** accuracy to ~25%
(SLMs genuinely can't do LightRAG-style indexing); removing chunk nodes (`-R_chunk`) costs 4–8 pts;
removing edge voting (`-R_edge`) costs 0.3–4.7 pts. So chunk-nodes-in-the-graph > edge topology.

## Cost profile
- **Storage:** claimed 25% of LightRAG at comparable accuracy (abstract + Fig. 3; no absolute MB
  table in the paper). Plausible: fewer/shorter descriptions and no community reports.
- **Index compute:** ~2–3 SLM calls per 1200-token chunk. Free in dollars with ollama, not free in
  time: a 3k-chunk KB at ~5–15 s/call on CPU is hours; the LLM cache makes rebuilds ~free.
- **Query compute:** 2 SLM calls + 2 small vector lookups + 2-hop graph walk. Cheap.

## What's interesting for Pinakes
LiHua-World is the closest thing in the literature to Pinakes' actual workload (personal,
conversational, entity-dense, temporally scattered), and the headline result on it is directly
relevant: a **1.5B local model** builds a graph that lifts accuracy ~9–13 pts over chunk-only
retrieval *when the answering model is also small*. The caveat cuts the other way for Pinakes: the
free path's consumer is Claude over MCP — a strong reader — and with a strong reader the gap over
NaiveRAG shrinks (54.1 vs 46.6) and LightRAG wins. What survives that caveat: the entity layer's
unique contribution is **cross-document entity edges** (the same person/project mentioned in
unrelated files), which Pinakes' planned structural edges (sibling/heading/co-located/shared-tag/
authored) cannot produce, and which is exactly what multi-constraint personal queries needed in
their case study (§3.4). MiniRAG's retrieval is otherwise a hand-rolled, degree-agnostic PPR-lite —
Pinakes' planned real PPR channel subsumes it.

## What to steal
- **Entity mentions as edges into the existing PPR channel**, not a new retrieval pipeline: a small
  local model (ollama, 1.5–4B) extracting *names + types only* at sync → `entities` table +
  entity–chunk mention edges + entity–entity co-occurrence edges, feeding the same RRF/PPR fusion.
  The `-I` ablation is the license: dumber extraction (no descriptions) is not just cheaper, it's
  *better* with small models. Skip what MiniRAG's own shipped prompt still drags along
  (relationship descriptions/keywords/strength).
- **Extraction cache keyed by chunk hash** (`enable_llm_cache`): makes "rebuilds stay free and
  fast" true even with an LLM in the sync path — only new/changed chunks pay.
- **Name-only embedding index** (`entity_name_vdb`): embedding bare entity names separately from
  descriptions is what makes query→node grounding robust with weak embedders; trivially maps to a
  Pinakes entity-name vec table using the existing bge-small model.
- **Delimiter-tuple output format** over JSON for small-model extraction; `json_repair` where JSON
  is unavoidable.
- **Chunks stay first-class retrieval targets** (their strongest ablation): never replace chunk
  retrieval with entity/summary retrieval — the graph only *re-ranks and expands* chunks. Pinakes'
  architecture already agrees; MiniRAG is evidence for keeping it that way.

## What to avoid / doesn't fit
- **The bespoke path-scoring stack** (`edge_vote_path`/`path2chunk`/`kwd2chunk`): ad-hoc counting
  with magic constants (×2 first-path, ×10 dense-hit boost, 20% short-path save), Levenshtein-based
  description matching, no principled damping. PPR on the same graph is simpler and strictly more
  general.
- **Query-time LLM dependency in the free path**: `minirag_query2kwd` needs an LM call per query.
  For Pinakes, query→entity grounding can be pure embedding match against an
  `entity_name_vdb`-style index; answer-type prediction is a nice-to-have for `--deep`, not the
  free path.
- **Relationship extraction with descriptions/strength** — the code's own LightRAG inheritance,
  contradicted by the paper's thesis and the `-I` ablation. Co-occurrence edges suffice.
- **Adopting the framework itself**: quiet since 2025-10, JSON/NetworkX/nano-vectordb storage
  triplicate vs Pinakes' single SQLite, and its answering-side wins are irrelevant when Claude is
  the reader.
- Mandatory-LLM sync would violate the free path if unconditional — this must stay an **optional
  mode**, off by default, with the structural-edges+PPR baseline as the eval control. Per project
  rules, adopt only if golden-set recall@k/MRR beats that baseline.

## Key sources
- Paper: arXiv 2501.06713 v3 — §2.1 (graph, Eq. 1), §2.2 (retrieval, Eq. 2), Tables 1–3, Fig. 2–3.
- `minirag/operate.py` — `extract_entities`, `minirag_query`, `_build_mini_query_context`,
  `path2chunk`, `kwd2chunk`; `minirag/utils.py` — `cal_path_score_list`, `edge_vote_path`,
  `calculate_similarity`; `minirag/prompt.py` — `entity_extraction`, `minirag_query2kwd`;
  `minirag/minirag.py` — `MiniRAG` dataclass defaults.
- GitHub API metadata fetched 20260726 08:52 (stars/pushed_at/license).
