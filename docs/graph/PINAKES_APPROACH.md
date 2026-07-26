# The Pinakes graph: lazy, agent-driven, budget-tunable

**Status:** proposed approach · **Date:** 20260726 08:59
**Builds on:** [`../GRAPH_RAG.md`](../GRAPH_RAG.md) (R1–R7) and the twelve investigation docs in
this directory. This doc is the decision layer: what Pinakes should actually build, in what order,
gated how. GRAPH_RAG.md remains the research record and is deliberately untouched.

---

## 1. What twelve investigations changed

GRAPH_RAG.md concluded: no prebuilt LLM graph, free structural edges, PPR as a candidate third
channel, traversal exposed as tools, extraction (if ever) lazy and written back. Every project
investigated since — chosen specifically to stress those conclusions — confirmed the direction and
sharpened it into implementable form:

| Doc | Verdict in one line | What Pinakes takes |
|---|---|---|
| [lightrag.md](lightrag.md) | The cost model R1 exists to avoid; nothing lazy | Caller-supplied dual-level keywords as search params |
| [microsoft-graphrag.md](microsoft-graphrag.md) | LazyGraphRAG still not OSS (verified v3.1.1); OSS has its ingredients | The relevance-test budget as `--deep`'s single cost knob |
| [graphiti.md](graphiti.md) | Converged on BM25+cosine+RRF; its MCP server has no traversal tool | BFS-from-hits as a cheap graph channel; the gap `pinakes_links` fills |
| [hipporag.md](hipporag.md) | PPR works; graph pays only on multi-hop | The exact PPR recipe (§4, stage B) |
| [fast-graphrag.md](fast-graphrag.md) | Query-time PPR stage is entirely LLM-free | Confirmation that R4 has zero free-path cost |
| [graph-r1.md](graph-r1.md) | Trained traversal ≈ 2.3–2.5 turns; the loop survives without RL | What tool *returns* must contain (§5) |
| [linearrag.md](linearrag.md) | Zero-LLM entity graph beats HippoRAG 2 on multi-hop | `mentions` edges — the one free edge class we lacked (§3) |
| [datastax-graph-rag.md](datastax-graph-rag.md) | Metadata-defined edges + bounded traversal, abandoned but right | Query-ranked bounded fan-out, visited-edge dedup (§5) |
| [code-graph-rag.md](code-graph-rag.md) | NL→Cypher needs a validator stack; typed verbs don't | Keep `pinakes_links` typed, hard-capped (§5) |
| [minirag.md](minirag.md) | A 1.5B local model can build a useful entity layer — gain shrinks with a strong reader | The conditional design for the `[ner]` extra's future upgrade |
| [youtu-graphrag.md](youtu-graphrag.md) | Schema-bounded extraction is the budget instrument | Three-list seed schema per template (§6) |
| [logicrag.md](logicrag.md) | Per-query DAG, zero corpus graph, warm-up-first | The `--deep` loop skeleton (§6) |
| [claudekb.md](claudekb.md) | Pinakes is a near-drop-in for its deferred retrieval layer | The `pnk adopt` path (§8); link-authoring realism (§3) |

License gate, stated once: LinearRAG and LogicRAG are GPL-3.0; Youtu-GraphRAG's LICENSE forbids
commercial use despite its README's MIT badge. **Algorithms may inform this design; no code from
those three repos may ever be vendored or translated line-by-line.** Graphiti, fast-graphrag,
HippoRAG, MiniRAG, datastax/graph-rag, nano-graphrag are MIT/Apache-2.0.

---

## 2. The shape of the answer

Three layers, each free until the last, each gated by the golden set before it defaults on:

```
sync time   (free)   edge derivation: structural + authored (+ optional NER mentions)
query time  (free)   graph channel: BFS-from-hits first, PPR if eval demands it
                     tool surface: pinakes_links + enriched pinakes_search returns
--deep only (paid)   lazy agent loop: warm-up → decompose → budgeted rounds → sidecar write-back
```

The caller's agent (Claude over MCP) gets the middle layer for free and runs its own loop — that
is the primary multi-hop path, reaffirming DESIGN §4.3. The paid loop exists only where no caller
agent does (CLI, cron), reusing the same tools.

---

## 3. Sync time: the edge set (€0)

All edges land in the existing derived store (`.pinakes/index.db`), disposable, rebuilt free.
Adding edge storage bumps `schema_version` — one rebuild, no migration, per invariant.

| Edge type | Source | Weight | Notes |
|---|---|---|---|
| `sibling` | adjacent `chunks.ordinal` | 1.0 | already derivable |
| `parent` / `child` | `chunks.heading_path` | 1.0 | hierarchy both directions |
| `co-located` | shared directory in `documents.path` | 1/dir-size | degree-damped |
| `shared-tag` | sidecar `tags` overlap | 1/tag-degree | see vocabulary caution below |
| authored (`cites`, …) | sidecar `links` | 2.0 | highest-trust edge class |
| `mentions` *(optional)* | NER at sync, chunk→entity | occurrence count | `[ner]` extra, default off |

Three findings shape this table:

- **Hub damping is not optional.** ClaudeKB's experience (curated `vocab.yml` exists precisely to
  stop tag sprawl) and datastax's visited-edge dedup both say the same thing: shared-value edges
  over popular values produce noise cliques. Tag and directory edges are weighted down by degree
  from day one, and `pnk doctor` reports the highest-degree edge hubs so a user can see when a tag
  has become meaningless glue.
- **Authored links are sparse, precious signal — plan for scarcity.** ClaudeKB shows that even
  agents author links only when a validator makes linking a precondition of landing a write, and
  then only the weakest useful kind. Pinakes must never assume link density; the structural edges
  are the default fabric, authored links a high-weight overlay. A `pnk doctor` nudge (warn on
  zero-link docs) is the proven pressure short of a hard gate.
- **`mentions` is the one free edge class that bridges unrelated documents.** Every structural
  edge above connects things that are already near each other (same doc, same directory, same
  tag). LinearRAG demonstrates — beating HippoRAG 2 and LightRAG on four multi-hop benchmarks with
  zero index-time LLM tokens — that chunk→entity co-mention edges built by plain NER supply the
  missing cross-silo bridges. Design: an optional `[ner]` extra (spaCy, pinned small model);
  entities are surface-form nodes with embedding-linked near-duplicates; edges are hash-diffed
  incrementally like everything else in sync; **default off** until the golden set shows the BFS
  or PPR channel gaining from it (LinearRAG's own caveat — entity fragmentation — plus MiniRAG's
  finding that the gain shrinks with a strong reader, both say: measure, don't assume). Rebuild
  stays free in euros; the honest cost is sync wall-clock and one more model download, which is
  why it is an extra and not core.

Nothing in this section calls an LLM. R1 stands: **no LLM extraction in `pnk sync`, ever.**

---

## 4. Query time: the graph channel (€0, staged)

Gated behind `[retrieval] graph_channel = "off" | "bfs" | "ppr"`, default `off` until R7's gates
pass. Both stages degrade to today's behaviour when the graph is sparse — an empty edge set means
an empty third channel, and RRF simply fuses two lists as it does now.

**Stage A — BFS-from-hits (ship first).** Graphiti's third channel, on Pinakes' storage: take the
fused top-*k* chunks, expand over the edge set with a recursive CTE (depth ≤ 2), score expanded
chunks by link distance and edge weight, feed the ranked list into the existing RRF as the third
input. Two bounding rules from datastax/graph-rag, adopted verbatim because they are what makes
traversal survive real graphs: per-edge fan-out capped at `adjacent_k` neighbours ranked by
similarity to the query, and visited-**edge** dedup so a hub (popular tag, big directory) expands
once globally, not once per encounter. This is dozens of lines over an index that already exists.

**Stage B — PPR (only if eval demands it).** If the golden set's multi-hop section shows Stage A
leaving recall on the table, implement the R4 channel with HippoRAG 2's measured recipe rather
than folklore defaults: damping **0.5** (not 0.85), undirected, weighted; personalization vector =
at most 5 entity-side seeds weighted by match score and damped by node specificity (1/chunk-count),
**plus every candidate chunk node at `fused_score × 0.05`**. That broad chunk seeding is
HippoRAG 2's stated guard against the simple-query regression GraphRAG-Bench documents — the
specific risk R7 exists to watch. Pure scipy over the adjacency matrix; no igraph dependency
unless profiling says otherwise.

**Why staged and not both at once:** two implementations means two eval matrices and two things to
maintain before the first user-visible win. BFS answers "does graph structure help this KB at all"
with minimal code; PPR is the escalation with a measured recipe waiting if the answer is "yes, and
BFS isn't enough." Each stage crosses its own golden-set gate (§9) before defaulting on.

---

## 5. The tool surface: what the agent's loop needs (€0)

Graph-R1 is the strongest available evidence on what a traversal loop actually consumes: its
trained agent converges to ~2.3–2.5 retrieval turns, deciding continue-vs-answer from exactly two
signals per hit — a relevance score and the visible frontier. code-graph-rag is the counter-example:
an open query language (NL→Cypher) needed a defensive validator stack that a typed signature
encodes for free. Both lessons land directly in the tool contract:

```
pinakes_links(kb, doc_id, rel?, direction?, depth?=1)
  → { neighbours: [{doc_id, title, rel, direction, distance, score}],
      frontier:   [{doc_id, rel}],          # unexpanded next hops
      unresolved: [{target, reason}],        # dangling pnk:// etc., never dropped
      truncated:  bool }                     # caps hit — narrow, don't retry
```

- **Typed args, hard caps.** `depth` is server-capped (≤ 3) regardless of what the caller asks;
  fan-out per node capped at `adjacent_k`; responses double-capped (row count + token budget) with
  `truncated` set so the agent narrows instead of paging. No query-language argument, ever.
- **Score + frontier on every return.** `pinakes_search` already returns confidence and a
  suggested next search (DESIGN §4.2); `pinakes_links` returns per-neighbour scores and the
  unexpanded frontier. That pair is the Graph-R1 loop's full input — an untrained caller can run
  think → probe → decide with no policy on the server side. R6 stands: no traversal policy inside
  Pinakes.
- **Tool descriptions carry the loop hints.** "Prefer refining the query over raising k"; "one
  hop at a time usually beats depth=3" — Graph-R1's learned behaviours, encoded as prose where an
  untrained agent will read them.

---

## 6. The paid path: lazy, agent-driven, written back (`--deep` only)

This is R5 made concrete, assembled from the three projects that each solved one piece:

**The loop (LogicRAG's skeleton, Pinakes' guardrails).**

```
round 0   free pipeline as-is → calibrated confidence signal
          confident → answer, spend €0            (most queries end here)
low conf  decompose: 1–2 LLM calls → subproblem dependency DAG → topo order
rounds    per subproblem: free retrieval → solve → fold into rolling summary
          rolling summary caps context → per-round cost is CONSTANT
          → pre-call reservation (DESIGN §5) prices the whole loop before it runs
stop      confidence gate per round · max_rounds · budget cap — whichever first
```

Two deliberate corrections to LogicRAG: the round-0 sufficiency judge is Pinakes' *calibrated*
confidence signal, not an uncalibrated LLM self-check (fixing LogicRAG's documented
premature-confidence defect on 4-hop questions); and every subproblem's retrieval is the free
hybrid pipeline, so the only paid tokens are decomposition and synthesis. LogicRAG's own numbers
(1,778 tokens/query where LightRAG spends 5,731, with zero index cost) show this shape is not a
compromise — it is the efficient frontier.

**The budget instrument (Youtu-GraphRAG's schema, shipped per template).** Each template carries a
three-list seed schema — entity types, relation types, attribute types (research-papers:
`author/paper/venue/method` × `cites/extends/evaluates_on`). Any `--deep` extraction prompt
includes it verbatim: it caps output combinatorially, keeps extraction on-domain, and makes scope
a declarative, diffable file rather than a prompt-engineering accident. Schema growth is a
user-committed diff, never a silent runtime mutation (Youtu's code writes expansions back with no
threshold — the exact failure mode to design out).

**The write-back (the design's own rule, now with mechanics).** What a `--deep` run discovers —
sub-answers that co-supported an answer, entity pairs that bridged subproblems — is exactly the
structure every investigated system throws away per query. Pinakes persists it as *suggestions*:
`pnk ask --deep` ends by printing proposed sidecar additions (`links:` entries with `rel` and
provenance `origin: deep`), and a `--write-suggestions` flag stages them into the sidecars for
the user to review and commit. Committed suggestions become authored edges: free forever, visible
to every future query, to the BFS/PPR channel, and to every connected KB. Paid inference becomes a
one-time, auditable investment instead of a recurring cost — the property R5 demanded, with the
human in the loop the sidecar invariant requires (`docs/` belongs to the user; nothing writes
there silently).

**The tunability knob.** One number the user reasons about: the per-operation cap already
specified in DESIGN §5, which — because per-round cost is constant — now translates directly into
"how many rounds can this question afford." LazyGraphRAG's single relevance-test budget validated
that one legible knob beats a panel of thresholds.

---

## 7. What Pinakes deliberately does not build

Restated because the investigations added evidence, not because the answers changed:

- **No LLM extraction in `pnk sync`** — R1, now backed by Microsoft's own Standard→Fast→Lazy
  trajectory and by LinearRAG beating extraction-based systems without extraction.
- **No traversal policy or agent framework inside Pinakes** — R6, backed by Graph-R1 (the loop
  belongs to the caller) and by DESIGN §9's "second, worse agent framework" risk.
- **No graph query language on the tool surface** — code-graph-rag's validator stack is the
  cautionary tale; typed verbs with caps.
- **No graph database, no new index file** — edges live in SQLite tables beside everything else;
  the single-portable-directory constraint holds.
- **No migrations** — edge schema changes bump `schema_version` and rebuild, per invariant.

---

## 8. ClaudeKB: the first fleet (`pnk adopt`)

The second-pass investigation ([claudekb.md](claudekb.md)) reached a strategic conclusion: ClaudeKB's
roadmap defers exactly the layer Pinakes is — cross-KB search, MCP, ranking — and Pinakes can serve
it with **zero blueprint changes on ClaudeKB's side**. The mapping is mostly mechanical:

| ClaudeKB has | Pinakes needs | Adapter |
|---|---|---|
| OKF frontmatter (`type`, `title`, `description`) | sidecar metadata | generate `.pnk.yaml` from frontmatter at adopt time |
| curated `vocab.yml` tags | `shared-tag` edges | direct — and already hub-safe by curation |
| gate-enforced link graph (every page reachable) | authored edges | parse Markdown links at sync; `index.md` out-edges become a curated seed prior |
| `kb://name/path.md` cross-KB links | `pnk://` ULID links | resolve path→ULID at index time; report dangling via `pnk doctor` |

Real blockers, all small: ULIDs must be committed back into KB repos (a one-time write-back
ceremony, gated like any sidecar write); sidecars under `docs/` would deploy on public ClaudeKB
sites (relocate or exclude in the SSG config); frontmatter→sidecar sync is one-directional and
needs a rule for conflicts.

Proposed proof, when its version window arrives: `pnk adopt` run against a scaffolded demo KB from
the ClaudeKB template, measured with the golden set. Strategic value beyond the fleet itself: v0.3's
stated prerequisite is "two populated KBs to be worth anything" — a ClaudeKB fleet is that corpus,
already curated, already linked, already access-controlled.

---

## 9. Eval gates before anything defaults on

R7, extended with the specific numbers this research surfaced. The golden set gains two sections
**before** any graph channel lands: multi-hop relational (the ~91%-vs-34% class where graphs pay)
and simple factual lookup (the class where GraphRAG-Bench measures graphs *costing* ~13% accuracy).
Per-class reporting, and one hard rule: **a graph channel that regresses simple-lookup precision
stays `off` by default**, whatever it does for multi-hop. Every stage gates independently:

| Gate | What must be true before |
|---|---|
| `bfs` default-on | multi-hop recall@k up, simple-lookup unchanged, false-abstain flat |
| `ppr` implemented at all | BFS measurably leaves multi-hop recall on the table |
| `[ner]` mentions edges default-on | channel gains from them on the golden set, sync time acceptable |
| `--deep` loop ships | budget machinery in the same release (DESIGN §5 ordering), per-class evals include cost/query |

Per repo rule, every retrieval change lands with before/after numbers in the commit message.

---

## 10. Version mapping

Extends GRAPH_RAG.md's R-table into a build order; v0.1/v0.2 are untouched by all of this.

| Version | Lands | From |
|---|---|---|
| v0.3 | `pnk link` · `pinakes_links` (typed, capped, frontier+scores) · structural edge derivation · BFS channel (`graph_channel`, default off) · golden-set multi-hop + simple-lookup sections · link-coverage + edge-hub reporting in `pnk doctor` | R2 R3 R6 R7 · §3 §4A §5 |
| v0.3.x | PPR stage, only if BFS gate says so (HippoRAG 2 recipe) · `[ner]` extra with `mentions` edges, default off, eval-gated | §4B · §3 |
| v0.4 | `--deep` warm-up loop (LogicRAG skeleton, calibrated round-0 gate) · per-template seed schemas · `--write-suggestions` sidecar write-back · budget machinery (same release, per DESIGN §5) | R5 · §6 |
| v0.5+ | `pnk adopt` (ClaudeKB fleet) · template-schema ecosystem maturation | §8 |
| never | LLM extraction in `pnk sync` · traversal policy in-engine · graph query language · graph DB · migrations | R1 R6 · §7 |

---

## 11. Summary

The research question was how to get a smart, budget-friendly, tunable, agent-driven, lazy graph.
The answer that survived twelve investigations is that each adjective already had a best-in-class
mechanism — they just lived in different projects:

- **smart** — entity co-mention bridges (LinearRAG) over structural fabric (datastax), ranked by
  BFS then PPR with measured parameters (Graphiti, HippoRAG 2);
- **budget-friendly** — €0 until `--deep`; then constant per-round cost (LogicRAG) under the
  existing reservation cap;
- **tunable** — one config gate per channel, one budget number per operation, one seed schema per
  template (Youtu-GraphRAG), every default set by the golden set, not intuition;
- **agent-driven** — score + frontier on every tool return so the caller runs the loop
  (Graph-R1), typed and capped so it can't run away (code-graph-rag);
- **lazy** — nothing is precomputed that isn't free, nothing paid is spent twice: discoveries are
  written back to sidecars and become free structure (R5, ClaudeKB's scheduled-pass precedent).

Pinakes doesn't adopt any of these systems. It occupies the position they are all converging on
from different directions — and it starts from the one asset none of them have: a human-curated,
typed, committed link graph that costs nothing and is never wrong about intent.
