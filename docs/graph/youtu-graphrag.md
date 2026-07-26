# Youtu-GraphRAG — investigation notes

**Repo:** https://github.com/TencentCloudADP/youtu-graphrag · **Stars:** ~1.2k (1223, 183 forks) ·
**License:** custom "Youtu-GraphRAG License" — **academic use only, commercial/production use forbidden**
(the README's MIT badge is wrong; `LICENSE` is the truth) · **Investigated:** 20260726 08:52
**Paper:** arXiv 2508.19855 (v3), "Youtu-GraphRAG: Vertically Unified Agents for Graph
Retrieval-Augmented Complex Reasoning", Tencent Youtu Lab, accepted ICLR 2026

## What it is

A "vertically unified" GraphRAG framework: the same declared graph schema drives both construction
(bounds the LLM extraction agent) and retrieval (guides query decomposition). Pipeline: schema-bounded
triple/attribute extraction per chunk → dually-perceived community detection (topology + embeddings,
no LLM in the clustering itself) → a four-level "knowledge tree" → an agentic retriever that
decomposes queries against the schema and runs an IRCoT-style retrieve-reflect loop. Ships as a
FastAPI web app + CLI (`main.py`), Docker or conda. An "Enterprise Edition" launched Feb 2026;
the OSS repo was last pushed 2026-02-26 (active, 57 open issues).

## The seed schema as a cost boundary

- **Format:** one JSON file per dataset, `schemas/<dataset>.json`, three flat lists — the demo schema
  (`schemas/demo.json`) has 10 entity types (`person`, `location`, `organization`, `event`, ...),
  12 relations (`is_a`, `part_of`, `located_in`, `created_by`, ...), 11 attribute types (`name`,
  `date`, `size`, ...). Paper §3.1: S = ⟨S_e, S_r, S_attr⟩.
- **How it enters extraction:** `models/constructor/kt_gen.py`, `KTBuilder._get_construction_prompt()`
  does `json.dumps(self.schema)` and injects it plus the chunk into the construction prompt template.
  Extraction is "constrained generation": the LLM may only emit triples whose types appear in S,
  formally reducing the search space to S_e × S_r × S_attr (paper Eq. 2).
- **Cost/scope bound:** the schema is the noise filter — open-ended OpenIE-style extraction produces
  "noise and irrelevant trivia"; bounding by declared types keeps the graph small, which is the main
  lever behind their token-cost claims (see Cost profile).
- **Auto-expansion:** yes, in agent mode. The extraction response may carry a `new_schema_types` key;
  `KTBuilder._update_schema_with_new_types()` parses suggested nodes/relations/attributes, dedupes
  against the current schema, updates `self.schema`, and **writes the merged schema back to the JSON
  file** (`json.dump`). The paper (Eq. 3) describes a confidence threshold μ; the code applies no
  threshold — every non-duplicate suggestion is accepted. Ablation (Table 3): removing schema
  guidance costs up to −7.27 pts on AnonyRAG-CHS, i.e. schema matters most on unseen domains.
- **Pinakes mapping:** this is exactly a template-shippable artifact. A Pinakes template
  (research-papers, contacts, recipes...) could ship a seed schema of entity types/relations/attribute
  types that a future `--deep` lazy extraction passes into its prompt — same three-list JSON shape,
  small enough to sit in `pinakes.toml` or a template file.

## The four-layer knowledge tree

Paper Eq. 8 (§3.2.1), built in `KTBuilder.build_knowledge_graph()`:

| Level | Content | Built by | LLM? |
|---|---|---|---|
| L1 | Attribute nodes `(e, has_attr, {type: value})` | `_process_attributes()` from the extraction call | yes (same single call as L2) |
| L2 | Entity-relation triples `(h, r, t)` | `_process_triples()` | yes (same call) |
| L3 | Keywords: top entities per community by degree + cosine-to-centroid | `utils/tree_comm.py`, `extract_keywords_from_community()` | no |
| L4 | Communities + LLM-generated name/summary nodes (`member_of` edges) | `FastTreeComm.detect_communities()` + `create_super_nodes()` | batched naming calls |

Community detection is "dually perceived": `_compute_sim_matrix()` mixes Jaccard structural
similarity with embedding cosine as `struct_weight * structural + (1-struct_weight) * semantic`
(`tree_comm.struct_weight` = 0.3 in `config/base_config.yaml`), then `_refine_cluster()` iteratively
merges clusters above a 0.5 threshold, capped at 100 communities. The tree supports top-down
filtering (start at community summaries) and bottom-up reasoning (entity/triple granularity).

## The agentic retriever

- **Decomposition:** `models/retriever/agentic_decomposer.py`, class `GraphQ`. `decompose(question,
  schema_path)` embeds the schema JSON in the prompt and asks for 2–3 sub-questions plus
  `involved_types` (nodes/relations/attributes touched) — **one LLM call**. `involved_types` is then
  used to filter candidates during retrieval (schema-aware pruning).
- **Retrieval per sub-question:** `models/retriever/enhanced_kt_retriever.py`, class `KTRetriever`,
  `process_retrieval_results()` — pure embedding/FAISS work, **no LLM**. Paper Eq. 10 lists four
  parallel routes: entity matching, triple matching, community filtering, bounded DFS path traversal.
- **IRCoT loop** (`main.py` / `app.py`): initial answer from merged sub-question context (1 LLM
  call), then up to `retrieval.agent.max_steps` iterations (config: 5; code fallback default 3).
  Each iteration: one LLM call over triples+chunks+previous thoughts that must end with either
  `So the answer is: <answer>` (stop) or `The new query is: <query>` (another embedding retrieval,
  loop). Also stops if no new query or query repeats.
- **LLM calls per query:** 1 (decompose) + 1 (initial answer) + ≤ max_steps reflections ⇒ typically
  2–7 calls. Retrieval itself is free once the index is built.

## Cost profile

- **Construction:** exactly **one LLM call per chunk** (`extract_with_llm()`), returning attributes +
  triples + optional schema expansions in one response; plus batched community-naming calls
  (`_call_llm_api_batch()`, many communities per prompt). Chunks are large — `construction.chunk_size:
  5000` tokens (overlap 200) — so calls per document are few. Parallelised via `ThreadPoolExecutor`
  (`max_workers: 32`).
- **Claims:** "up to 90.71% saving of token costs" vs SOTA baselines (paper abstract; the README's
  headline number is 33.6% lower token cost, 16.62% higher accuracy). Mechanism verified in code:
  (a) schema-bounded output keeps extraction terse; (b) single combined call per big chunk vs
  GraphRAG/LightRAG's multiple passes (entity descriptions, relation summaries, per-community
  reports); (c) no per-element LLM summarisation — communities get one short batched naming call,
  keywords are computed without LLM. Not magic: fewer, tighter LLM calls.

## Benchmarks (incl. AnonyRAG)

- Six benchmarks: HotpotQA, 2Wiki, MuSiQue, GraphRAG-Bench, AnonyRAG-CHS/ENG. Top-10 accuracy
  (DeepSeek, Table 2): 83.4 HotpotQA, 82.3 2Wiki, 52.1 MuSiQue, 83.5 G-Bench, 38.08/42.57 AnonyRAG —
  best on all, biggest gains in "reject" (abstention) mode (+8–12 pts).
- **AnonyRAG** (HuggingFace `Youtu-Graph/AnonyRAG`): entities anonymised so pretrained-LLM knowledge
  leakage can't answer for free; includes an "Anonymity Reversion" task. Relevant to Pinakes eval
  thinking: a personal KB is naturally "anonymous" to the model, so AnonyRAG-style numbers are the
  honest ones — and there everyone is weak (Youtu leads with only 38–43%, vs HippoRAG-IRCoT 36.19 on
  CHS, a ~2-pt margin; ablations show w/o-Agent drops below HippoRAG variants).
- Losses/caveats: absolute accuracy on anonymised and MuSiQue-style compositional data stays ~40–52%;
  gains over HippoRAG2 on plain HotpotQA open mode are modest (83.4 vs 79.4).

## What's interesting for Pinakes

- Independent confirmation of the Pinakes thesis: unbounded LLM graph construction is the cost sink,
  and the fix is declared structure up front. Their schema is the construction-side analogue of
  Pinakes' typed sidecar links vocabulary.
- Retrieval is cheap once built: embeddings + FAISS + graph walks, LLM only for decompose/reflect —
  mirrors Pinakes free-path/paid-path split, with their IRCoT loop ≈ a bounded `--deep` loop
  (max_steps is their cap; Pinakes v0.4 adds what they lack: cost reservation + spend ledger).
- Community summaries as L4 nodes retrieved like any other node is a lightweight alternative to
  Microsoft-GraphRAG's expensive community reports.

## What to steal (esp. schema-bounded lazy extraction for R5)

1. **Seed schema as the R5 budget instrument.** If `--deep` extraction ever lands, bound it with a
   template-shipped three-list schema (entity types / relations / attribute types) injected verbatim
   into the extraction prompt. It caps both output size (fewer tokens) and semantic drift, and it is
   declarative — auditable in the repo like any Pinakes template. A `research-papers` template would
   ship e.g. `{author, paper, venue, method, dataset}` × `{cites, extends, evaluates_on, authored_by}`.
2. **One combined extraction call per (large) chunk** returning entities+relations+attributes in a
   single JSON — never separate description/summary passes.
3. **Schema expansion as explicit, reviewable writes:** their agent writes proposed new types back to
   the schema file. Pinakes version: `--deep` proposes new link types / entity types into a sidecar or
   schema file as a *diff the user commits* — matching R5's "write results back into committed
   sidecars" — but add the confidence gate the paper describes and the code skips.
4. **`involved_types` decomposition output:** having the decompose step name the schema types a query
   touches, then filtering retrieval candidates by type, is a cheap precision win for a future
   PPR/structural channel.
5. **AnonyRAG's framing** for the golden-set eval: measure on content the model cannot already know;
   report reject/abstain accuracy separately (maps to Pinakes' false-abstain-rate metric).

## What to avoid / doesn't fit

- **License:** academic-only, no commercial use — read for ideas, never vendor code.
- **Dependency weight:** torch + transformers + sentence-transformers + faiss + spacy + magic-pdf +
  Apache Tika (Java) + FastAPI; Neo4j for visualisation; Docker-first. Antithetical to Pinakes'
  light-core rule.
- **Eager whole-corpus extraction:** every chunk hits the LLM at build time — violates the free path.
  Pinakes takes the schema idea but applies it lazily (query-scoped, R5), not corpus-wide.
- **Ungated schema auto-expansion:** code accepts every LLM-suggested type with no threshold —
  schema drift with no human in the loop. Pinakes must keep the user as the commit gate.
- **Their four-level tree as storage:** communities/keywords are derived state; if ever wanted, they
  belong in disposable `.pinakes/`, not in the document model.

## Key sources

- Paper arXiv 2508.19855v3: §3.1 schema-bounded extraction (Eqs. 1–3), §3.2 dual-perception
  communities + Eq. 8 four-level tree, §3.3 agentic retriever (Eqs. 9–10), Table 2 results, Table 3
  ablations, Figure 6 Pareto/token plot.
- `schemas/demo.json` — seed schema shape.
- `models/constructor/kt_gen.py` — `KTBuilder`, `_get_construction_prompt()`, `extract_with_llm()`,
  `_update_schema_with_new_types()`, `process_level4()`.
- `utils/tree_comm.py` — `FastTreeComm`, `_compute_sim_matrix()`, `_refine_cluster()`,
  `extract_keywords_from_community()`, `create_super_nodes()`.
- `models/retriever/agentic_decomposer.py` (`GraphQ.decompose()`),
  `models/retriever/enhanced_kt_retriever.py` (`KTRetriever.process_retrieval_results()`),
  `main.py`/`app.py` IRCoT loop; `config/base_config.yaml` (chunk_size 5000, struct_weight 0.3,
  max_steps 5, top_k_filter 20); `LICENSE`, `requirements.txt`.
