# The Pinakes graph: lazy, agent-driven, budget-tunable

**Status:** proposed approach · **Date:** 20260726 08:59 · review-revised 20260726 09:11, 09:17, 09:23, 09:28, 09:34 (five adversarial passes; commit times)
**Builds on:** [`GRAPH_RAG.md`](GRAPH_RAG.md) (R1–R7) and the investigation docs in this
directory — twelve external projects plus the in-house precedent (ClaudeKB). This doc is the
decision layer: what Pinakes should actually build, in what order, gated how. GRAPH_RAG.md remains
the research record and is deliberately untouched.

---

## 1. What the investigations changed

GRAPH_RAG.md concluded: no prebuilt LLM graph, free structural edges, PPR as a candidate third
channel, traversal exposed as tools, extraction (if ever) lazy and written back. Every project
investigated since — chosen specifically to stress those conclusions — confirmed the direction and
sharpened it into implementable form:

| Doc | Verdict in one line | What Pinakes takes |
|---|---|---|
| [lightrag.md](lightrag.md) | The cost model R1 exists to avoid; nothing lazy | Caller-supplied dual-level keywords on `pinakes_search` (§5) |
| [microsoft-graphrag.md](microsoft-graphrag.md) | LazyGraphRAG still not OSS (verified v3.1.1); OSS has its ingredients | The relevance-test budget as `--deep`'s single cost knob |
| [graphiti.md](graphiti.md) | Converged on BM25+cosine+RRF; its MCP server has no traversal tool | Expansion-from-hits as a cheap graph channel; link-distance rerank; the gap `pinakes_links` fills |
| [hipporag.md](hipporag.md) | PPR works; graph pays only on multi-hop | The exact PPR recipe (§4, stage B) |
| [fast-graphrag.md](fast-graphrag.md) | Query-time PPR stage is entirely LLM-free | Confirmation that R4 has zero free-path cost |
| [graph-r1.md](graph-r1.md) | Trained traversal ≈ 2.3–2.5 turns; the loop survives without RL | What tool *returns* must contain (§5) |
| [linearrag.md](linearrag.md) | Zero-LLM entity graph beats HippoRAG 2 on its benchmarks | `mentions` edges — the one free edge class we lacked (§3) |
| [datastax-graph-rag.md](datastax-graph-rag.md) | Metadata-defined edges + bounded traversal, abandoned but right | Query-ranked bounded fan-out, visited-edge dedup (§4, §5) |
| [code-graph-rag.md](code-graph-rag.md) | NL→Cypher needs a validator stack; typed verbs don't | Keep `pinakes_links` typed, hard-capped (§5) |
| [minirag.md](minirag.md) | A 1.5B local model can build a useful entity layer — gain shrinks with a strong reader | Evidence on file if the `[ner]` extra ever needs an SLM upgrade — an R1 amendment, not a plan (§3) |
| [youtu-graphrag.md](youtu-graphrag.md) | Schema-bounded extraction is the budget instrument | Three-list seed schema per template (§6) |
| [logicrag.md](logicrag.md) | Per-query DAG, zero corpus graph, warm-up-first | The `--deep` loop skeleton (§6) |
| [claudekb.md](claudekb.md) | Pinakes is a near-drop-in for its deferred retrieval layer | The `pnk adopt` path (§8); link-authoring realism (§3) |

License gate, stated once: LinearRAG and LogicRAG are GPL-3.0; Youtu-GraphRAG's LICENSE forbids
commercial use despite its README's MIT badge. **Algorithms may inform this design; no code from
those three repos may ever be vendored or translated line-by-line.** The permissively licensed
sources — Graphiti, fast-graphrag, HippoRAG, MiniRAG, datastax/graph-rag, LightRAG,
microsoft/graphrag, Graph-R1, code-graph-rag (all MIT or Apache-2.0 per their docs here) — are
safe to study at code level.

---

## 2. The shape of the answer

Three layers, each free until the last, each gated by the golden set before it defaults on:

```
sync time   (free)   edge derivation: structural + authored (+ optional NER mentions)
query time  (free)   graph channel: bounded expansion first, PPR if eval demands it
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

**The node model, stated before the edges that connect it.** The graph is heterogeneous, per
hipporag.md's chunk↔tag/chunk↔heading mapping: **chunk** nodes (the retrieval unit), **document**
nodes (one per doc; a membership edge links each chunk to its doc), **tag** nodes (one per
distinct tag KB-wide), **heading-path** nodes (**scoped per document** — a global "Introduction"
hub would weld every document into one noise clique worse than any tag), **directory** nodes (one
per directory), and **entity** nodes when the `[ner]` extra is on. Every shared-value relation
goes *through* its hub node — `doc ↔ tag`, `doc ↔ directory`, `chunk ↔ heading` — never as
materialized pairwise edges: hubs are what let §4B seed tags and headings with specificity
1/connected-chunk-count, what keep edge counts linear instead of O(members²) per shared value,
and what give §4A's visited-edge dedup a single node to expand once globally. Spoke weights are
per-spoke; flow between two members through their hub is the product of both spokes, so
1/degree spokes damp big hubs superlinearly — deliberate, and like every weight here a starting
point to fit. Hierarchy is the one relation that stays direct: `parent`/`child` edges are
chunk ↔ chunk, derived by `heading_path` prefix comparison (DESIGN §3 stores the path per chunk;
heading nodes exist for seeding and same-section grouping, not to carry hierarchy). On
embeddings: only chunk nodes carry stored *content* embeddings; hub and entity nodes get cheap
label embeddings (used for entity near-duplicate linking and §4B seed matching) that §4A
deliberately does not use for traversal ranking.

| Edge | Connects | Weight | Notes |
|---|---|---|---|
| membership | chunk ↔ doc | 1.0 | transit plumbing, not signal — see below |
| `sibling` | chunk ↔ chunk (adjacent `ordinal`) | 1.0 | already derivable |
| `parent` / `child` | chunk ↔ chunk (`heading_path` prefix) | 1.0 | hierarchy both directions |
| `in-section` | chunk ↔ heading node (per-doc) | 1/section-size | same-section grouping; §4B seeds |
| `co-located` | doc ↔ directory node | 1/dir-size | hub form; degree-damped |
| `shared-tag` | doc ↔ tag node | 1/tag-degree | see vocabulary caution below |
| authored (`cites`, …) | doc ↔ doc (sidecar `links`) | 2.0 | highest-trust edge class |
| `mentions` *(optional)* | chunk ↔ entity node | normalized occurrence (count / entities-in-chunk) | `[ner]` extra, default off |

Weights are starting points to be fitted against the golden set, not measured constants. The
damping principle applies to *every* shared-value hub — tag, directory, and `in-section` alike
(1/section-size; a 50-chunk section must not be a full-strength clique). The two exemptions are
explicit, not accidental: `sibling` and `parent`/`child` stay at 1.0 because adjacency and
hierarchy are not shared-value relations, and **membership is transit plumbing, not signal** —
same-doc chunks reached only through their own document's membership edges are excluded from the
expansion channel's output and never consume its fan-out budget (intra-doc structure is already
sibling/parent-child/in-section's job; the channel exists to surface *cross-doc* connections).
HippoRAG 2's own passage↔phrase edges sit undamped at 1.0 and rely on seed-side specificity
instead (hipporag.md) — that precedent is noted, and the choice here is the stricter one.

Three findings shape this table:

- **Hub damping is not optional.** ClaudeKB's experience (curated `vocab.yml` exists precisely to
  stop tag sprawl) and datastax's visited-edge dedup both say the same thing: shared-value edges
  over popular values produce noise cliques. Tag, directory and section spokes are weighted down
  by degree from day one (the complete damping statement follows the table); `mentions` weights
  are normalized per chunk for the same reason. `pnk doctor`
  reports the highest-degree edge hubs so a user can see when a tag has become meaningless glue.
- **Authored links are sparse, precious signal — plan for scarcity.** ClaudeKB shows that even
  agents author links only when a validator makes linking a precondition of landing a write, and
  then only the weakest useful kind. Pinakes must never assume link density; the structural edges
  are the default fabric, authored links a high-weight overlay. A `pnk doctor` nudge (warn on
  zero-link docs) is the proven pressure short of a hard gate.
- **`mentions` is the one free edge class that bridges unrelated documents.** Every structural
  edge above connects things that are already near each other (same doc, same directory, same
  tag). LinearRAG's results — beating HippoRAG 2 and LightRAG on its four benchmarks with zero
  index-time LLM tokens — *suggest* that chunk→entity co-mention edges supply the missing
  cross-silo bridges. Suggest, not demonstrate: LinearRAG's wins come from a whole system —
  transformer-scale NER (a 440 MB spaCy model), sentence-level embeddings of the entire corpus,
  and query-gated spreading activation before its PPR — and no published ablation isolates the
  edges alone. That is exactly why the `[ner]` extra ships **default off** behind its own eval
  gate (§9). Design: spaCy with a pinned model; entities are surface-form nodes with
  embedding-linked near-duplicates; edges hash-diffed incrementally like everything else in sync.
  Rebuild stays free in euros; the honest cost is sync wall-clock and one more model download,
  which is why it is an extra and not core.

Nothing in this section calls an LLM, and R1 stands: **no LLM extraction in `pnk sync`.** One
boundary case is named rather than blurred: MiniRAG proves a 1.5–4B *local* model can build a
useful entity layer at sync — free in euros but LLM extraction all the same, which R1 as written
forbids at any version. This doc does **not** propose it. If the spaCy `[ner]` extra ever proves
insufficient where an SLM layer would not be, that is a conscious amendment of R1's wording (from
"no LLM extraction" to "no paid extraction; opt-in local-model extraction behind an extra,
eval-gated") to be argued then — not a silent reinterpretation now.

---

## 4. Query time: the graph channel (€0, staged)

Gated behind `[retrieval] graph_channel = "off" | "expand" | "ppr"`, default `off` until R7's
gates pass. Both stages degrade to today's behaviour when the graph is sparse — an empty edge set
means an empty third channel, and RRF simply fuses two lists as it does now.

**Stage A — bounded expansion from hits (ship first).** Graphiti's third-channel shape on
Pinakes' storage: take the fused top-*k* chunks as roots, expand over the edge set breadth-first
to depth ≤ 2, score expanded chunks by edge weight and link distance, and feed the ranked list
into the existing RRF as the third input. **Depth counts logical hops** — chunk-or-doc to
chunk-or-doc transitions — with membership edges and hub- and entity-node pass-throughs
depth-free; counted
in physical edges, the model's plumbing (chunk→doc→doc→chunk) would strand the highest-trust
authored edges beyond depth 2, which cannot be the intent. §5's tool cap and §9's reachability
ceiling use the same metric. The mechanism is a **per-depth loop in Python, not a
recursive CTE**: one SQL query per hop fetches the frontier's neighbours, then the ranking rule
follows the node model's asymmetry — **chunk** neighbours are ranked by cosine against the query
embedding (in-process on the NumPy tier — DESIGN §3.1; the v0.5 `sqlite-vec` tier instead fetches
the bounded frontier's vectors from SQLite per hop, cheap because the frontier is capped);
**non-chunk** nodes (doc, tag, heading, directory) carry no content embedding, pass through by
edge weight, and contribute their member chunks (minus the root's own document — §3's membership
exclusion), which are then query-ranked like any others. A
Python-side visited-edge set enforces the two datastax bounding rules that make traversal survive
real graphs: per-node fan-out capped at
`adjacent_k` neighbours ranked as above, and visited-**edge** dedup so a hub (popular tag, big
directory) expands once globally, not once per encounter. Neither rule is expressible inside a
plain SQLite CTE — ranking needs the vector array and global dedup needs shared state — and
pruning *after* an unbounded CTE would let the hub explosion happen before the prune. A driver
loop it is; still small, still free.

Also evaluated in Stage A, per graphiti.md's explicit recommendation: **in-degree over the `links`
table as a zero-cost salience signal** — a static citation-count prior on documents, inherited by
their chunks through the membership edge — and the `center_node_uuid`-style link-distance rerank.
Both are cheaper than everything else on this page and belong in the first eval matrix.

**Stage B — PPR (only if eval demands it).** If the golden set shows Stage A leaving multi-hop
recall on the table (the gate is quantified in §9), implement the R4 channel with HippoRAG 2's
measured recipe rather than folklore defaults: damping **0.5** (not 0.85), undirected, weighted.
The personalization vector has two parts, and the second is the one that matters:

- *Non-chunk seeds:* at most 5 nodes from the metadata side of the graph, weighted by match score
  and damped by node specificity (1/chunk-count). Without the `[ner]` extra there are no entity
  nodes — **tag and heading nodes play the phrase-node role**, matched against the query by the
  same embedding/BM25 machinery (hipporag.md's own mapping). With `[ner]`, entity nodes join them.
- *Chunk seeds:* **every chunk node in the graph**, weighted by its raw dense (cosine) score
  × 0.05, clamped at zero (DESIGN §4.1 already treats non-positive cosine as no evidence; a reset
  vector must not carry negative mass) — not only the RRF candidates. Seeding all chunks, not
  top-k, is HippoRAG 2's stated key to multi-hop signal flow and its guard against the
  simple-query regression that one study in the GraphRAG-Bench line measured at ~13%
  (GRAPH_RAG §2.3). On the NumPy tier the full score vector is a free by-product of the vector
  search already run. Under the future `sqlite-vec` tier (v0.5) only the vector scan's top-N
  (~50; BM25 candidates carry no cosine) would have scores — which is precisely the top-k-only
  seeding HippoRAG 2 warns against. That degraded mode is acceptable only because the vec tier
  is a v0.5 concern; when it lands, all-chunk seeding must be re-evaluated on that tier, not
  assumed.

Implementation is power iteration over the edge list in plain NumPy — a gather/scatter
(`np.add.at`) sparse matvec, never a dense adjacency matrix (50k² floats would be ~10 GB against a
design that budgets 77 MB for all embeddings at that scale). Whether `scipy.sparse` replaces the
hand-rolled matvec is decided by profiling against the core-deps-stay-light rule, not assumed
here; hipporag.md and fast-graphrag.md both confirm no igraph is needed at Pinakes' scale.

**Why staged and not both at once:** two implementations means two eval matrices and two things to
maintain before the first user-visible win. Bounded expansion answers "does graph structure help
this KB at all" with minimal code; PPR is the escalation with a measured recipe waiting if the
answer is "yes, and expansion isn't enough." Each stage crosses its own golden-set gate (§9)
before defaulting on.

---

## 5. The tool surface: what the agent's loop needs (€0)

Graph-R1 is the strongest available evidence on what a traversal loop actually consumes: its
trained agent converges to ~2.3–2.5 retrieval turns, deciding continue-vs-answer from exactly two
signals per hit — a relevance score and the visible frontier. code-graph-rag is the counter-example:
an open query language (NL→Cypher) needed a defensive validator stack that a typed signature
encodes for free. Both lessons land directly in the tool contract:

```
pinakes_links(kb, doc_id, rel?, direction?, depth?=1, query?)
  → { neighbours: [{doc_id, title, rel, direction, distance, score}],
      frontier:   [{doc_id, rel}],          # unexpanded next hops
      unresolved: [{target, reason}],        # dangling pnk:// etc., never dropped
      confidence, truncated }                # same signal class as pinakes_search;
                                             # truncated ⇒ narrow, don't retry
```

- **Typed args, hard caps.** `depth` is server-capped (≤ 3) regardless of what the caller asks;
  fan-out per node capped at `adjacent_k`; responses double-capped (row count + token budget) with
  `truncated` set so the agent narrows instead of paging. No query-language argument, ever. The
  tool's cap (3) is deliberately one more than the automatic channel's depth (2): an agent
  spending its own turn on an explicit probe has judged the hop worth it; the automatic channel
  runs on every query and must stay cheap.
- **Ranking with and without `query`.** When the optional `query` is supplied, fan-out and
  `score` use similarity to it (the datastax rule), and `confidence` carries the same calibrated
  signal class as `pinakes_search` — completing R6's stated contract ("neighbours plus the same
  confidence signal"). Without `query`, edge weight and link distance rank — deterministic
  neighbourhood inspection is a legitimate use — and `confidence` is reported `unknown`: the
  calibrated signal is fitted on query-relevance scores, and a query-less listing has nothing to
  be confident about (DESIGN §4.2's "absent ⇒ unknown, never invented" ethos).
- **Score + frontier on every return.** That pair is the Graph-R1 loop's full input — an
  untrained caller can run think → probe → decide with no policy on the server side. R6 stands:
  no traversal policy inside Pinakes.
- **Tool descriptions carry the loop hints.** "Prefer refining the query over raising k" is
  Graph-R1's learned behaviour, encoded as prose where an untrained agent will read it. "Take one
  hop and look before asking for depth 3" is Pinakes' own guidance following from the caps above —
  labelled as ours, not the paper's.
- **Dual-level keywords on search (from LightRAG).** `pinakes_search` gains optional
  `entities=[]` / `concepts=[]` parameters: entity-ish terms boost the FTS5/link side, concept-ish
  terms the embedding side. The caller's agent does the keyword split in its own reasoning — the
  one genuinely useful piece of LightRAG's query side, obtained without its LLM call.

---

## 6. The paid path: lazy, agent-driven, written back (`--deep` only)

This is R5 made concrete, assembled from the three projects that each solved one piece:

**The loop (LogicRAG's skeleton, Pinakes' guardrails).**

```
round 0   free pipeline as-is → calibrated confidence signal
          confident → ONE synthesis call over retrieved passages, done
          (cheapest paid exit; decomposition never runs)
low conf  decompose: 1–2 LLM calls → subproblem dependency DAG
          → cycle check (reject or repair on back-edge — LogicRAG skipped this; we don't)
          → topo order
rounds    per subproblem: free retrieval → solve → fold into rolling summary
          rolling summary caps context → per-round cost is CONSTANT
          every round's query, cost and result → the ask transcript (auditable, not discarded)
stop      confidence gate per round · max_rounds · budget cap — whichever first
```

Two deliberate corrections to LogicRAG: the round-0 sufficiency judge is Pinakes' *calibrated*
confidence signal, not an uncalibrated LLM self-check (fixing LogicRAG's documented
premature-confidence defect on 4-hop questions); and every subproblem's retrieval is the free
hybrid pipeline, so the only paid tokens are decomposition, per-round solving, and synthesis.
LogicRAG's own numbers (1,778 tokens/query where LightRAG spends 5,731, with zero index cost) show
this shape is not a compromise — it is the efficient frontier.

Budget mechanics, precisely: the constant per-round cost gives the **dry-run estimate** a sound
upper bound (`decompose + max_rounds × round-cost + synthesis`) to print and confirm against
`confirm_above_eur`; during the run, DESIGN §5's **per-call reservation** halts the loop the
moment the next round would breach the cap. Estimate up front, reserve per call — two existing
mechanisms, used as designed.

**Honest scope note (amending, not reinterpreting).** DESIGN §9 bounds `--deep` with "no
orchestration the free path doesn't have," and §4.3 calls it "a bounded version of the same
loop." A decompose→DAG→topo-order loop *is* orchestration the free path doesn't have. This
proposal therefore amends that line rather than claiming compliance with it: the bound that
actually contains the agent-framework risk is the conjunction of *same retrieval tools as MCP*
(nothing retrieves that the free path can't), *hard caps* (rounds, budget, context), and *no
persistent agent state beyond the transcript and the explicitly staged, user-committed suggestions
below*. The DAG is prompt-side structure within one operation, not a framework. DESIGN §9's
wording should be updated in the increment that ships this, so the risk table stays true.

**The budget instrument (Youtu-GraphRAG's schema, shipped per template).** Each template carries a
three-list seed schema — entity types, relation types, attribute types. For research-papers:
entities `author/paper/venue/method/dataset`, relations `cites/extends/evaluates_on/authored_by`,
attributes `year/task/metric`. Any `--deep` extraction prompt includes it verbatim: it caps output
combinatorially, keeps extraction on-domain, and makes scope a declarative, diffable file rather
than a prompt-engineering accident. Schema growth is a user-committed diff, never a silent runtime
mutation (Youtu's code writes expansions back with no threshold — the exact failure mode to design
out).

**The write-back (the design's own rule, now with mechanics).** What a `--deep` run discovers —
sub-answers that co-supported an answer, entity pairs that bridged subproblems — is exactly the
structure every investigated system throws away per query. Pinakes persists it as *suggestions*:
`pnk ask --deep` ends by printing proposed sidecar additions (`links:` entries with `rel` and
provenance `origin: deep`), and a `--write-suggestions` flag stages them into the sidecars for the
user to review and commit. Sidecars are Pinakes-authored files by design (sync generates their
skeletons), so this writes where Pinakes already writes — the flag exists because *semantic*
additions deserve explicit opt-in, a stricter bar than the invariant demands. One schema note,
recorded because sidecar-schema evolution is the design's acknowledged blind spot (claudekb.md,
D18 discussion): the per-link sidecar shape gains an optional provenance field (`origin: deep`) —
strictly additive, stated in DESIGN in the increment that ships this. The `links` *table's*
`origin` enum (`sidecar` / `reverse-scan`, DESIGN §3) does **not** change: an accepted suggestion
is read from the sidecar like any other link, so its row is `origin: sidecar` at authored weight —
acceptance-by-commit is exactly what promotes a machine suggestion to authored trust, and the
`deep` provenance survives in the truth layer where it belongs. Committed suggestions are then
free forever, visible to every future query, to the graph channel, and to every connected KB.
Paid inference becomes a one-time, auditable investment instead of a recurring cost — with the
human in the loop.

**The tunability knob.** One number the user reasons about: the per-operation cap already
specified in DESIGN §5, which — because per-round cost is constant — translates directly into "how
many rounds can this question afford." LazyGraphRAG's single relevance-test budget (100/500/1500,
with published quality curves) is the working precedent for a single legible cost knob.

---

## 7. What Pinakes deliberately does not build

Restated because the investigations added evidence, not because the answers changed:

- **No LLM extraction in `pnk sync`** — R1, now backed by Microsoft's own Standard→Fast→Lazy
  trajectory and by LinearRAG beating extraction-based systems without extraction. (The SLM
  boundary case and the amendment it would require are stated in §3, not hidden here.)
- **No traversal policy or agent framework inside Pinakes** — R6, backed by Graph-R1 (the loop
  belongs to the caller). The `--deep` loop's relationship to DESIGN §9's risk line is handled
  honestly in §6.
- **No graph query language on the tool surface** — code-graph-rag's validator stack is the
  cautionary tale; typed verbs with caps.
- **No graph database, no new index file** — edges live in SQLite tables beside everything else;
  the single-portable-directory constraint holds.
- **No migrations** — edge and enum schema changes bump `schema_version` and rebuild, per
  invariant; sidecar-schema additions stay strictly additive (§6).

---

## 8. ClaudeKB: the first fleet (`pnk adopt`)

The second-pass investigation ([claudekb.md](claudekb.md)) reached a strategic conclusion:
ClaudeKB's roadmap defers exactly the layer Pinakes is — cross-KB search, MCP, ranking — and
Pinakes can serve it with only small, mostly KB-side adaptations. The mapping is largely
mechanical:

| ClaudeKB has | Pinakes needs | Adapter |
|---|---|---|
| OKF frontmatter (`type`, `title`, `description`) | sidecar metadata | generate `.pnk.yaml` from frontmatter at adopt time |
| curated `vocab.yml` tags | `shared-tag` edges | direct — and already hub-safe by curation |
| gate-enforced link graph (every page reachable) | authored edges | parse Markdown links at sync; `index.md` out-edges become a curated seed prior |
| `kb://name/path.md` cross-KB links | `pnk://` ULID links | resolve path→ULID at index time; report dangling via `pnk doctor` |

Real blockers, all small but not zero: ULIDs must be committed back into KB repos (a one-time
write-back ceremony, gated like any sidecar write); sidecars under `docs/` would deploy on public
ClaudeKB sites (exclude via SSG config — which may touch a blueprint-owned, checksummed file, so
it lands as a blueprint version bump on the ClaudeKB side, not a hand-edit); frontmatter→sidecar
sync is one-directional and needs a conflict rule; and each KB needs a `pinakes.toml` plus a
minimal fleet registry.

Sequencing, honestly: the automated `pnk adopt` command is v0.5+ work (§10). What v0.3 needs is
just **two populated KBs** — and a single ClaudeKB-templated KB adopted *by hand* (a
frontmatter→sidecar script run once, ULIDs committed) is a realistic v0.3-window corpus without
any adopt machinery. The fleet-scale value arrives with the command; the prerequisite-unblocking
value doesn't have to wait for it.

Proposed proof, when the version window arrives: `pnk adopt` run against a scaffolded demo KB from
the ClaudeKB template, measured with the golden set.

---

## 9. Eval gates before anything defaults on

R7, extended with the specific numbers this research surfaced. The golden set gains two sections
**before** any graph channel lands: multi-hop relational (the ~91%-vs-34% class where graphs pay)
and simple factual lookup (the class where one study in the GraphRAG-Bench line measured graphs
*costing* ~13% accuracy). Per-class reporting, and one hard rule: **a graph channel that regresses
simple-lookup precision stays `off` by default**, whatever it does for multi-hop. Every stage
gates independently:

| Gate | What must be true before |
|---|---|
| `expand` default-on | multi-hop recall@k up, simple-lookup unchanged, false-abstain flat |
| `ppr` implemented at all | expansion's multi-hop recall@k sits ≥ 5 points below the golden set's *channel-reachable ceiling* — the share of multi-hop questions whose evidence lies within 2 logical hops (§4A's metric) of the fused seeds, **minus what §3's membership exclusion forbids the channel to return**. Below-ceiling-but-close means expansion suffices; a wide gap is PPR's mandate. The eval also reports two excluded shares: the **beyond-2-hop share** — if it dominates, the gate is blind to exactly what PPR's diffusion could reach — and the **membership-only-reachable share** — if *it* dominates the gap, revisit the §3 exclusion before implementing PPR, because that is the cheaper remedy. The decision weighs all three numbers, not the gate alone |
| `[ner]` mentions edges default-on | the active channel gains from them on the golden set, sync time acceptable |
| `--deep` loop ships | budget machinery in the same release (DESIGN §5 ordering), per-class evals include cost/query |

Per repo rule, every retrieval change lands with before/after numbers in the commit message.

---

## 10. Version mapping

Extends GRAPH_RAG.md's R-table into a build order; v0.1/v0.2 are untouched by all of this.

| Version | Lands | From |
|---|---|---|
| v0.3 | `pnk link` · `pinakes_links` (typed, capped, score+frontier+confidence) · `pinakes_search` `entities`/`concepts` params · structural edge derivation · expansion channel (`graph_channel`, default off) · in-degree salience + link-distance rerank in the eval matrix · golden-set multi-hop + simple-lookup sections · link-coverage + edge-hub reporting in `pnk doctor` · hand-adopted ClaudeKB corpus as second KB | R2 R3 R6 R7 · §3 §4A §5 §8 |
| v0.3.x | PPR stage, only if the §9 gate says so (HippoRAG 2 recipe) · `[ner]` extra with `mentions` edges, default off, eval-gated | §4B · §3 |
| v0.4 | `--deep` warm-up loop (LogicRAG skeleton + cycle check, calibrated round-0 gate) · ask transcript · per-template seed schemas · `--write-suggestions` sidecar write-back (`origin: deep`) · budget machinery (same release, per DESIGN §5) · DESIGN §9 wording update (§6) | R5 · §6 |
| v0.5+ | `pnk adopt` (automated ClaudeKB fleet onboarding) · template-schema ecosystem maturation | §8 |
| never | LLM extraction in `pnk sync` (SLM boundary case requires an explicit R1 amendment, §3) · traversal policy in-engine · graph query language · graph DB · migrations | R1 R6 · §7 |

---

## 11. Summary

The research question was how to get a smart, budget-friendly, tunable, agent-driven, lazy graph.
The answer that survived twelve external investigations plus the in-house precedent is that each
adjective already had a best-in-class mechanism — they just lived in different projects:

- **smart** — entity co-mention bridges (LinearRAG) over structural fabric (datastax), ranked by
  bounded expansion (Graphiti's channel shape) then, if the eval demands it, PPR with HippoRAG 2's
  measured parameters;
- **budget-friendly** — €0 until `--deep`; then constant per-round cost (LogicRAG) under the
  existing estimate-then-reserve machinery;
- **tunable** — one config gate per channel, one budget number per operation, one seed schema per
  template (Youtu-GraphRAG), every default set by the golden set, not intuition;
- **agent-driven** — score + frontier on every tool return so the caller runs the loop
  (Graph-R1), typed and capped so it can't run away (code-graph-rag);
- **lazy** — nothing is precomputed that isn't free, nothing paid is spent twice: discoveries are
  written back to sidecars and become free structure (R5, ClaudeKB's scheduled-pass precedent).

Pinakes doesn't adopt any of these systems. It occupies the position they are all converging on
from different directions — and it starts from the one asset none of them have: a human-curated,
typed, committed link graph that costs nothing and is never wrong about intent.
