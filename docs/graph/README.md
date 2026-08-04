# Graph retrieval — research

Thirteen investigations — twelve external projects plus the in-house precedent — and the synthesis
that turns them into a gated build order for **the links release** and **the graph release**.
Research, not specification: where these disagree with [`../DESIGN.md`](../DESIGN.md), DESIGN wins;
where they disagree with [`../../plans/20260729_0256-links-and-graph.md`](https://github.com/lucagattoni/pinakes/blob/main/plans/20260729_0256-links-and-graph.md) about
what is built when, the plan wins.

**Partly built.** The links release this research shaped shipped in 0.5.0 and 0.6.0, and G1, G2
and G4 of the graph release followed; the graph release's remaining increments are blocked on a
corpus, not on code. [`../STATUS.md`](../STATUS.md) is the authority on what exists.

## Start here

| Doc | What it is |
|---|---|
| [**PINAKES_APPROACH.md**](PINAKES_APPROACH.md) | **The synthesis.** The Pinakes graph: lazy, agent-driven, budget-tunable. §9 is the eval gate each channel must pass; §10 is its build order, sequenced into increments by [`plans/20260729_0256-links-and-graph.md`](https://github.com/lucagattoni/pinakes/blob/main/plans/20260729_0256-links-and-graph.md). Five adversarial passes |
| [**GRAPH_RAG.md**](GRAPH_RAG.md) | The research record — what the literature actually says about graphs, RAG and agents, and what Pinakes should take from it |

## Investigations

Licences are recorded because they decide whether an idea may become code here — see the gate below.

| Project | Licence | Why it was read |
|---|---|---|
| [ClaudeKB](claudekb.md) | in-house | What was already tried here, and what it cost |
| [LightRAG](lightrag.md) | MIT | Dual-level retrieval — the most-copied simple design |
| [Microsoft GraphRAG](microsoft-graphrag.md) | MIT | The reference implementation, and its own retreat from eager indexing into LazyGraphRAG |
| [Graphiti](graphiti.md) | Apache-2.0 | Temporal knowledge graphs, bitemporal edges |
| [HippoRAG 2](hipporag.md) | MIT | Personalised PageRank over a passage graph — the PPR channel's origin |
| [fast-graphrag](fast-graphrag.md) | MIT | The cost profile of doing PPR cheaply |
| [Graph-R1](graph-r1.md) | MIT | Agentic multi-turn traversal — closest to the agent-driven posture |
| [datastax/graph-rag](datastax-graph-rag.md) | Apache-2.0 | Retrofitting edges onto an existing vector store |
| [code-graph-rag](code-graph-rag.md) | MIT | Structural edges that need no LLM |
| [MiniRAG](minirag.md) | MIT | Whether a small local model suffices for heterogeneous graph indexing |
| [LinearRAG](linearrag.md) | ⛔ **GPL-3.0** | Linear-cost construction — whether the build step can stay free |
| [LogicRAG](logicrag.md) | ⛔ **GPL-3.0** | Reasoning over logical structure — the upper bound on query complexity |
| [Youtu-GraphRAG](youtu-graphrag.md) | ⛔ **academic only** | Schema-guided hierarchical construction — schema as a cost control |

## The licence gate

These are read-only references. **Never copy code from the three marked ⛔.**

- **LinearRAG** and **LogicRAG** are GPL-3.0.
- **Youtu-GraphRAG** ships a custom licence forbidding commercial and production use. Its README
  badge says MIT and is **wrong** — the `LICENSE` file is the truth.

Pinakes is Apache-2.0 and `pnk serve` is a network service, so a copyleft obligation would reach
anyone embedding it. The same reasoning ruled out PyMuPDF in favour of `pypdfium2`
(`plans/20260727_1543-v0.2.md`, decision 1). **Ideas and measured results are free to reuse; source is not** —
read them, then write it yourself. Stated once in
[PINAKES_APPROACH.md §"License gate"](PINAKES_APPROACH.md) and repeated here because the index is
where someone starts.
