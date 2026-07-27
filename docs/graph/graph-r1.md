# Graph-R1 — investigation notes
**Repo:** https://github.com/LHRLAB/Graph-R1 · **Stars:** ~584 · **License:** MIT · **Investigated:** 20260725 15:30
**Paper:** arXiv 2507.21892 (ICML 2026, "Graph-R1: Towards Agentic GraphRAG Framework via End-to-end Reinforcement Learning", Luo et al., BUPT/NTU)

## What it is
The first "agentic GraphRAG" framework: instead of one-shot graph retrieval + long-context generation, a
small LLM (Qwen2.5 1.5B/3B/7B) is RL-trained (GRPO) to run a multi-turn think → query → retrieve → rethink →
answer loop against a knowledge **hypergraph** built from the corpus. It is precisely the trained/formalised
version of the loop Pinakes' R6 bet delegates to the caller agent — which is why it is worth studying for loop
structure, not for RL.

## The agentic loop, precisely
- **Action space per step (hierarchical policy):** (i) `a_think` — free-text reflection assessing knowledge
  sufficiency; (ii) intent `α_t ∈ {(query, retrieve), (answer)}`; (iii) content — either a retrieval query or
  the final answer. The *agent* only ever emits natural-language sub-queries; the *environment* executes
  retrieval. No graph-walking primitives (no "expand node", no "follow edge") are exposed to the policy.
- **Wire format:** `<think>…</think>` then either `<query>{"query": "…"}</query>` or `<answer>…</answer>`.
  Retrieved results come back in a `<knowledge>` block as a JSON list of plain-text n-ary facts, each with a
  `<coherence>` score (the RRF fusion score, e.g. 1.833, 0.45) — ranked, scored, sentence-shaped evidence.
- **One retrieval step returns:** top-k (k=5 per turn) n-ary relational facts — natural-language sentences with
  their entity sets — NOT a subgraph object, paths, or node IDs. Knowledge stays in language space.
- **Termination:** the agent itself chooses `answer` instead of `query` when `<think>` concludes knowledge is
  sufficient; hard cap at T steps (trained models converge to ~2.3–2.5 turns). No environment-side stop signal.

## The hypergraph it traverses
- **Construction:** documents → 1200-token chunks (50 overlap) → GPT-4o-mini n-ary relation extraction
  (HyperGraphRAG's prompt, minus confidence-scoring, for cost): each chunk yields facts `(h_i, V_hi)` where
  `h_i` is a *natural-language sentence* ("knowledge segment") that becomes a hyperedge connecting entity set
  `V_hi`. Entities carry name/type/description. Both entities and hyperedges embedded with bge-large-en-v1.5
  into two vector bases.
- Key insight: a "hyperedge" is just a sentence with linked entities — semantic loss is low because the fact
  text is preserved verbatim; the graph structure is an index over sentences, not a replacement for them.
- **Cost (2Wiki):** 5.69 s and $2.81 per 1M tokens of corpus (GPT-4o-mini), 120,499 nodes / 98,073 hyperedges.
  Cheaper than GraphRAG ($3.35) and HyperGraphRAG ($4.14) but still a paid-LLM pass over the whole corpus.

## What RL buys (and what survives without it)
- **RL setup:** GRPO (beats PPO and REINFORCE++ in their comparison), N sampled trajectories, trajectory-level
  reward: `R(τ) = −1.0 + R_format + I{R_format = 1.0} · R_answer`. Format reward = 0.5 per well-formed
  think/intent/content step, capped 1.0; answer reward = token-level F1 vs gold. Answer reward is **gated on
  perfect format** — structure first, correctness second. 4×A100, 1 epoch, batch 128, max len 4096.
- **What RL buys:** protocol compliance and calibrated stopping for a *small* model. Ablation "w/o R.L."
  (same prompt, same graph, untrained Qwen2.5-7B) collapses to 17.8 F1 avg vs 63.9 trained — but that measures
  a 7B model's inability to follow the loop, not the loop's value. Trained models also get *shorter* responses
  (~1200–1500 tokens) with *more* turns (~2.3–2.5) — RL teaches "retrieve again" over "reason longer".
- **What survives without RL:** everything structural — the loop shape, the dual-path retrieval, the ranked
  sentence-shaped results, the agent-decides-termination pattern. Notably, Qwen3-4B (already RL-trained for
  reasoning) gained *less* from Graph-R1 training and over-relied on internal reasoning — evidence that a
  frontier model like Claude already possesses most of what GRPO instills here. For Pinakes' caller-agent
  design, RL is replaceable by a capable model + well-shaped tool returns.

## What the loop teaches tool design
Graph-R1's environment interface is the part that transfers to Pinakes' MCP tools:
1. **Queries in, sentences out.** The agent's only action is a natural-language sub-query; the environment does
   all graph mechanics (entity matching, hyperedge similarity, fusion) internally. Pinakes should keep
   `pinakes_search` exactly this shape — never make the caller assemble graph traversals itself for the common
   path. Graph structure is the *server's* retrieval index, not the caller's burden.
2. **Dual-path retrieval + RRF, server-side.** Entity-based (query entities → similar entity nodes → their
   hyperedges) ∪ direct (query embedding → similar hyperedges), fused by reciprocal rank `1/r_V + 1/r_H`.
   Pinakes' BM25 + embeddings + RRF is already the same pattern; the graph analogue is adding a third RRF leg:
   "docs reachable via links from top lexical/semantic hits". That is a retrieval-channel change (eval-gated).
3. **Return scores the agent can read.** The `<coherence>` value per fact is what lets `<think>` judge
   sufficiency ("top hit 1.8 and on-topic → answer; everything ≤0.5 → re-query"). `pinakes_search` should
   return a per-hit score and the existing corpus-level confidence signal so an untrained caller can implement
   the continue/answer decision Graph-R1 had to *learn*.
4. **Small k per turn, iterate.** k=5 facts/turn × ~2.4 turns beat single-shot top-60 GraphRAG retrieval.
   Default `pinakes_search` limits should stay small and the tool description should *say* "call again with a
   refined query rather than raising limit" — that one sentence encodes Graph-R1's trained policy.
5. **Facts carry their entities.** Each returned fact includes its entity set — the frontier for the next hop
   ("Dziga Vertov" appears in turn 1's result, becomes turn 2's query). Pinakes analogue: `pinakes_search` hits
   should surface their outgoing typed links (or `pinakes_links` should accept a doc from a hit) so results
   advertise where to go next. This is the "frontier suggestion" — Graph-R1 gets it for free from n-ary facts.
6. **Termination belongs to the caller.** The environment never says "stop"; the agent decides from scored
   evidence. Matches R6 exactly — Pinakes should return honest signals (scores, abstain-worthy low confidence),
   never a "you have enough" verdict.

## Cost profile
- **Build:** one paid-LLM pass over the corpus (~$2.81/1M tokens with GPT-4o-mini) + embedding of ~220K
  items (2Wiki). Violates Pinakes' free path if adopted as-is.
- **Query:** $0 marginal (local 7B policy + local vector search), 7.0 s/query — vs $8.76/1K queries for
  HyperGraphRAG on GPT-4o-mini. Their pitch: pay at build time, query free — Pinakes' pitch is stronger
  (free at both ends), at the cost of no LLM-extracted graph.
- **Training:** 4×A100-80GB, per-dataset GRPO runs — entirely out of scope for Pinakes.
- **Results:** avg F1 57.8 (Qwen2.5-7B) vs Search-R1 46.2, R1-Searcher 42.3, HyperGraphRAG 29.4; wins on all
  six datasets (2Wiki 65.0, HotpotQA 62.7, Musique 46.2, NQ 49.9, PopQA 51.2, TriviaQA 71.9). Weakest relative
  edge on NQ/PopQA (single-hop; chunk RAG nearly ties) — the graph pays off on multi-hop. G-E "diversity" is
  its lowest quality dimension (51.7).

## What's interesting for Pinakes
- Independent, quantified validation of the R6 bet: multi-turn agentic retrieval over a modest index beats
  bigger single-shot retrieval, with *fewer* tokens in context (moderate content length, highest F1).
- The hyperedge-as-sentence design shows graph benefits without leaving language space — close in spirit to
  Pinakes' sidecar links over intact documents (docs stay verbatim; structure is an index on top).
- Evidence that one-time "gather everything" retrieval is the thing to avoid — Pinakes' small-k composable
  tools are the right default, not a limitation.
- The w/o-RL collapse is about 7B models; their own Qwen3 result implies strong callers need tool shape, not
  training — supporting "expose good tools, let Claude run the loop".

## What to steal
- **Per-hit relevance score in `pinakes_search`/`pinakes_links` output** (their `<coherence>`) — the single
  input the caller's continue/answer decision needs. Cheap: expose the RRF/rerank score already computed.
- **Hits advertise their frontier:** include each hit's typed outgoing links (or entity-ish anchors) in search
  results so the next hop is visible without a second tool call.
- **Graph leg in RRF fusion:** link-reachable neighbours of top hits as an extra ranked list fused with
  BM25/dense — free (uses the human-authored links table), eval-gated per the retrieval-change rule.
- **Tool-description guidance encoding the learned policy:** "prefer a refined follow-up query over a larger
  k"; document the think→query→check-scores→re-query-or-stop loop in the MCP tool descriptions.
- **Reward-shape lesson repurposed as docs:** structure-before-content (their format gate) becomes: tool
  outputs must be strictly, predictably structured so an untrained caller never has to parse prose.

## What to avoid / doesn't fit
- **LLM-based graph extraction at build time** — paid pass over the whole corpus; breaks the free path. Pinakes
  already has what the extraction buys (typed links) authored by the human, plus planned free structural edges.
- **RL training of any policy** — out of scope by R6; their own Qwen3 result undercuts its value for strong models.
- **Per-corpus policy models** — Graph-R1 trains per dataset; O.O.D. transfer needed extra regimes. Pinakes'
  caller-agnostic tools sidestep this entirely.
- **Their eval setup as a template** — token-F1 vs gold short answers rewards extractive QA, not KB workflows;
  Pinakes' golden-set (recall@k, MRR, false-abstain) is the better fit.
- **Repo as engineering reference** — research code (verl fork, flash-attn, commit messages all "add"), one
  commit in 2026 (20260430); effectively unmaintained. Read the paper, not the code.

## Key sources
- Paper: https://arxiv.org/abs/2507.21892 (v2, 20260602) — §4.1–4.3 loop + retrieval + reward; Alg. 1 (App. C)
  full workflow; App. A prompts/wire format; Table 2 main results; Fig. 6a cost table; Fig. 7 efficiency;
  Fig. 5a ablations; App. J hypergraph construction; App. K O.O.D. regimes.
- Repo: https://github.com/LHRLAB/Graph-R1 — MIT, ~584 stars / 76 forks, dirs `agent/`, `graphr1/`, `verl/`,
  `script_build.py` (hypergraph build), `script_api.py` (retrieval API), `script_process.py`.
- Lineage: HyperGraphRAG (Luo et al., 2025 — same group, same extraction prompt), Search-R1 / R1-Searcher
  (chunk-based RL baselines it beats), GRPO from DeepSeekMath/DeepSeek-R1.
