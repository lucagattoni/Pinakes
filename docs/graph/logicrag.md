# LogicRAG — investigation notes

**Repo:** https://github.com/chensyCN/LogicRAG · **Stars:** ~234 (36 forks) · **License:** GPL-3.0 · **Investigated:** 20260726 08:53
**Paper:** arXiv 2508.06105 (AAAI 2026)

## What it is

"You Don't Need Pre-built Graphs for RAG" — a query-time-only alternative to GraphRAG. No corpus
graph is ever built. At inference, the LLM decomposes the question into subproblems, models their
logical dependencies as a per-query DAG, topologically sorts it, and retrieve-and-solves the
subproblems in order, with earlier answers conditioning later retrievals. Small research code
(~43 commits, `run.py` + `src/`, setup.py still named "agentic-rag" from a repo rename). All LLM
calls go to `gpt-4o-mini` at temperature 0 with `max_tokens=250` (`config/config.py`); the
retriever is dense-only cosine over `sentence-transformers/all-MiniLM-L6-v2` embeddings
(`BaseRAG.retrieve` in `src/models/base_rag.py`). Maintained-but-frozen research artifact; PRs
badge, no visible issue triage.

## The query-time pipeline, precisely

All of it lives in `LogicRAG.answer_question` (`src/models/logic_rag.py`):

1. **Warm-up retrieval** — dense top-k retrieve on the raw question; `refine_summary_with_context`
   (LLM call 1) compresses chunks into a summary; `warm_up_analysis` (LLM call 2) returns JSON
   `{can_answer, missing_info, subquery, current_understanding, dependencies, missing_reason}`.
2. **Easy exit** — if `can_answer`, `generate_answer` (LLM call 3) and return with `rounds=0`.
3. **DAG construction** — otherwise the `dependencies` list (flat strings from the warm-up call)
   goes to `_sort_dependencies`: one LLM call emits `dependency_pairs` as index tuples
   `(dependent, dependency)`; `_topological_sort` (plain DFS, no LLM) linearizes. Note: the code
   has **no cycle detection** — the paper claims acyclicity is "verified via topological sorting",
   but the DFS just won't revisit nodes; a cyclic answer silently produces an arbitrary order.
4. **Sequential solve loop** — `while round_count < max_rounds and idx < len(sorted_dependencies)`:
   retrieve on `sorted_dependencies[idx]` (dense, same retriever), fold chunks into the rolling
   summary (`refine_summary_with_context`, 1 LLM call), then `dependency_aware_rag` (1 LLM call)
   judges `can_answer` against the full question. Yes → synthesize and return; no → `idx += 1`
   (move to the next dependency, never retry the same one).
5. **Synthesis** — `generate_answer` formats a terse final answer from the summary alone.

LLM calls: easy path = 3; hard path = 3 + 1 (pairs) + 2 per round + 1 (final). Retrievals: 1 + one
per round. There is no reranker, no BM25, no per-subproblem answer object — the rolling summary is
the only state that flows forward.

**Paper-vs-code gaps (important):** the paper's *graph pruning via unified subquery generation*
(merge all same-topological-rank subproblems into one `Merge(S_r)` query, Eq. 4) and *dynamic DAG
augmentation* (adding new subproblems mid-flight, Algorithm 1 lines 16–18) are **not in the
released code** — the code does one dependency per round and never grows the DAG. Treat those as
paper-only mechanisms.

## The budget mechanisms

- **Graph pruning** (paper): merge same-rank (parallelizable sibling/leaf) subproblems into one
  unified retrieval query, collapsing rounds. Figure 7 shows it cuts average retrieval rounds
  across all query types (e.g. compositional/multi-hop benefit most). In code, the analogue is
  weaker: "sampling without replacement" — `idx += 1` guarantees forward progress, no re-asking a
  stalled subproblem. Figure 4: without-replacement cuts per-question tokens (MuSiQue 3873 → 2501)
  at equal accuracy, by killing the "hesitation" loop of near-duplicate subqueries (Figure 3 shows
  subquery Jaccard similarity rising toward 0.8–0.9 across rounds when re-sampling is allowed).
- **Rolling memory** (context pruning): a single text string, re-summarized *every* round
  (unconditionally — no size trigger): `Mem_i = Summarize(Mem_{i-1} ∪ retrieved(p_i))`, question-
  oriented. `max_tokens=250` caps each summary, so context to the LLM stays O(1) per round instead
  of accumulating all retrieved chunks. Fallback on LLM failure is raw concatenation.
- **`--max-rounds`** (default 3): hard cap on solve-loop iterations; on exhaustion it still
  synthesizes a best-effort answer from the current summary. **`--top-k`** (default 5; paper uses
  3): chunks per retrieval. Paper Figure 6: accuracy saturates at k=3–5; k=20 exceeds 6000
  tokens/question on MuSiQue for marginal gain.

## Does it degrade gracefully on easy queries?

Yes, by explicit design. The warm-up stage *is* plain RAG: one dense retrieval + summarize +
sufficiency check. If the LLM says `can_answer`, the DAG machinery never runs — total cost is one
retrieval and 3 small LLM calls, `rounds=0`. The decider is a single un-calibrated LLM judgment
(`warm_up_analysis`'s `can_answer` boolean). The paper itself documents the failure mode of that
judge: 4-hop questions average *fewer* rounds than 3-hop because the LLM gets prematurely
confident on long queries and answers from partial information ("Impact of Graph Pruning"
section) — a trust-calibration gap they name but don't fix.

## Cost and accuracy vs baselines

- **Indexing:** zero, by construction. Graph baselines on 2WikiMQA burn 10^7-scale tokens and tens
  to hundreds of minutes building the graph (Figure 1: HippoRAG, RAPTOR, LightRAG, GraphRAG).
- **Query time** (Table 4, 2WikiMQA, avg per question): LogicRAG 9.83 s / 1778 tokens vs
  VanillaRAG 4.28 s / 490, HippoRAG2 5.89 s / 2809, GraphRAG 13.05 s / 4700, LightRAG 35.14 s /
  5731, KGP 70.72 s / 11098. So ~3.6x the tokens of plain RAG, but cheaper than every graph method
  even *ignoring* their indexing cost.
- **Accuracy** (Table 1, Str-Acc / LLM-Acc, gpt-4o-mini, same embedder for all): 2WikiMQA
  64.7/62.5 (best; HippoRAG2 50.0/47.1), MuSiQue 30.4/37.5 (best; HippoRAG2 27.0/32.6), HotpotQA
  54.8/62.6 — best LLM-Acc but **loses on string accuracy to HippoRAG2 (56.7)**. Pattern: biggest
  wins where questions are structurally compositional (2WikiMQA); narrowest where single-corpus
  bridge questions favor a good one-shot graph retriever (HotpotQA).

## What's interesting for Pinakes

The core claim aligns exactly with Pinakes' R5/R6 stance: reasoning structure is a property of the
*query*, not the corpus — so build it lazily at ask-time instead of paying an indexing-time graph.
LogicRAG is essentially a published, benchmarked validation of the `pnk ask --deep` shape: bounded
loop, plain-RAG warm-up with an escape hatch, sequential dependency-ordered retrieval, constant-
size carried context, hard round cap, forced progress. Its weakest components (dense-only
retriever, un-calibrated LLM sufficiency judge) are precisely where Pinakes is already stronger
(hybrid BM25+embeddings+RRF+rerank; calibrated confidence signal).

## What to steal (esp. as blueprint for pnk ask --deep)

- **Warm-up-first adaptivity:** round 0 is ordinary retrieval + a sufficiency gate; only escalate
  to decomposition when it fails. In Pinakes the gate can be the *free* calibrated confidence
  signal instead of an LLM call — better calibrated and zero cost, fixing their known
  premature-confidence defect.
- **Flat-list DAG, one call:** decomposition returns flat subproblem strings; a second call emits
  index pairs; local code does the topo sort. Two cheap calls buys the whole "graph" — no graph
  library, no schema. Add the cycle check they skipped (reject/repair on back-edge).
- **Rolling memory as the budget backbone:** a single bounded summary re-folded each round keeps
  per-round token cost constant — which makes *pre-call cost reservation* against the `--deep` cap
  actually predictable (2 LLM calls of known max size per round).
- **Sampling without replacement:** never re-ask a stalled subproblem; advance the cursor. Their
  measured ~35% token cut at equal accuracy is the cheapest anti-loop guarantee available.
- **Round-cap-with-best-effort-answer:** on `max_rounds` exhaustion, synthesize from what's in
  memory rather than failing — right behavior for a budgeted CLI/cron path.
- **Write-back opportunities they leave on the floor:** LogicRAG persists nothing per query
  (only the corpus embedding cache, `cache/embeddings_N.pt`; `retrieval_cache` is per-process).
  A Pinakes adaptation could durably keep, per R5: (a) the decomposition + sub-answers as a
  committed ask-transcript file, (b) doc-pairs that co-supported one dependency chain as
  *suggested* typed links surfaced for sidecar adoption — turning each paid `--deep` run into
  permanent free structure.

## What to avoid / doesn't fit

- **GPL-3.0** — algorithm-level lessons only; never port code into MIT/Apache-style Pinakes.
- **LLM-judged sufficiency without calibration** — their own Figure 7 analysis shows it
  under-rounds hard questions. Pinakes' confidence signal should gate rounds, not the LLM's
  self-report alone.
- **Dense-only, whole-matrix retrieval** with no rerank — strictly weaker than Pinakes' pipeline;
  nothing to adopt from `BaseRAG`.
- **JSON fragility as architecture:** `max_tokens=250` routinely truncates responses, patched by
  `fix_json_response` regex surgery (`src/utils/utils.py`). Use structured outputs / tool calls.
- **Per-subproblem answers are discarded into the summary** — no auditable intermediate record;
  Pinakes' ledger/transcript needs each round's query, cost, and result kept.
- **Paper features absent from code** (rank-merged unified queries, dynamic DAG growth): unproven
  in the artifact — don't cite them as validated.
- Per R6, this whole loop belongs *only* in `pnk ask --deep`; MCP callers compose
  `pinakes_search`/`pinakes_get` themselves and must not trigger an internal LLM loop.

## Key sources

- Paper: arXiv 2508.06105v2 — pipeline (Framework section, Eq. 1–4), Algorithm 1 (suppl. A),
  Tables 1/4, Figures 1, 3, 4, 6, 7.
- Code: `src/models/logic_rag.py` (`answer_question`, `warm_up_analysis`, `_sort_dependencies`,
  `_topological_sort`, `refine_summary_with_context`, `dependency_aware_rag`, `generate_answer`),
  `src/models/base_rag.py` (`retrieve`, `load_corpus`), `config/config.py`,
  `src/utils/utils.py` (`get_response_with_retry`, `fix_json_response`), `README.md`.
