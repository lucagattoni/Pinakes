# The links release and the graph release — implementation plan

**Status:** draft — revised after adversarial pass 1 (three independent reviewers: 22 HIGH,
30 MEDIUM, 15 LOW). **Not yet implementable**: pass 2 must come back clean first, and v0.2's own
iteration log records that 40–45% of each pass's HIGH findings were *created by the previous pass's
fixes*.

**Date:** written 20260729 02:52, rewritten 20260729 03:31 after pass 1

**Source of truth:** [`docs/DESIGN.md`](../docs/DESIGN.md). Where this plan and DESIGN disagree on
anything *not* in the amendments tables below, DESIGN wins and this plan has a bug.

**Section references are qualified.** `DESIGN §5` and `APPROACH §5` are different documents, and
pass 1 caught this plan using bare `§5` for both, ten lines apart. Every reference below names its
document.

**Written against** [`docs/graph/PINAKES_APPROACH.md`](../docs/graph/PINAKES_APPROACH.md) (five
adversarial passes — this plan's first draft said six), the R1–R7 findings in
[`docs/graph/GRAPH_RAG.md`](../docs/graph/GRAPH_RAG.md), and
[`docs/RETROSPECTIVES.md`](../docs/RETROSPECTIVES.md).

**No version number appears here for unbuilt work** ([CLAUDE.md](../CLAUDE.md)). Increment IDs are
`L1`–`L10` and `G1`–`G4`; they name work inside this plan, not releases.

## Baseline — `main` at `b637be4`, 20260729 03:31

Verified, not assumed. Re-verify before L1 begins: `main` moved eleven commits under this plan's
first draft, the first of them four minutes after it was written.

| Fact | Value |
|---|---|
| `schema_version` | 2 |
| Paid-extraction release | I1–I7c landed on `main`; **I8 and I9 remain**, and cut that release |
| Golden set | 41 questions · recall@5 **0.909** · MRR **0.812** · rerank precision **0.758** · false-abstain 0.03 · false-confidence 0.25 |
| Per class | `lexical` 1.00 · `filter` 1.00 · `no-answer` 1.00 · `multi-hop` **1.00 (at ceiling, n=5)** · `paraphrase` 0.75 |
| `links` table | Exists; populated from sidecars only |
| `kb_refs` table | Exists; **never written** |
| Reverse-scan | **Not implemented.** `store.py` has carried the `reverse-scan` origin value since v0.1, unused |
| Authored links in `tests/demo-kb/` | **Zero.** Thirty documents, no `links:` key in any sidecar |
| `compare()` | Gates the six aggregates, **plus per class and the question count**, since 20260729 |

**The eval harness was repaired before this plan was rewritten** (landed `b637be4`). It had been
scoring a multi-hop question as a single-shot search of its last hop's query — `hops_followed`
reached no metric — and two of the five questions consequently asked about one document while
demanding another. Growing that class, as the first draft proposed, would have multiplied a broken
instrument by five and read the result as increased precision.

**What the repair leaves behind is a constraint, not a clean slate:** `multi-hop` now sits at
**1.00 on five questions**. A class at ceiling can only ever show damage. L9's new questions must be
harder, not merely more numerous, or the expansion channel will have nothing to demonstrate.

---

## Two releases, not one

Pass 1 found that a cut after the links surface would ship under a name that
[STATUS](../docs/STATUS.md#release-roadmap) and [CLAUDE.md](../CLAUDE.md) both define as including
structural edges. The names are split, in the same change as this plan:

| Release | What it is | Rebuild? |
|---|---|---|
| **the links release** | `pnk link`, `pnk links`, `pinakes_links`, reverse-scan, link-coverage reporting | **No** — nothing in L1–L10 bumps `schema_version` |
| **the graph release** | Structural edges, the expansion channel, `schema_version` 3 | Yes, once |

The links release shipping without a rebuild is a real property, checked in L10's cut criteria
rather than asserted: the `links` and `kb_refs` tables already exist, and L5 resolves the one thing
that looked like it needed a column — a cross-KB neighbour's `title` — without adding one.

---

## Goal

A question answered in one KB can reach evidence in another, because a human said the two documents
were related and pinakes remembered — and the structure that makes traversal useful when nobody has
authored anything is derived for free afterwards, if and only if the golden set says it helps.

**Nothing here can spend money.** No paid entry point is added and `.paid-path-allowlist` is
unchanged. But "the four gates stay green without amendment" was wrong in the first draft:
`tests/free_path_run.py` enumerates the free surfaces *by name*, so L5, L6 and L7 each extend it and
`tests/test_paid_path.py`'s surface list. That is amendment of the gate's **coverage**, which is
required; not of its **allowlist**, which is forbidden.

---

## Decisions taken

Settled with the user 20260729 02:30–03:10. Each is load-bearing below.

| # | Decision | Consequence |
|---|---|---|
| 1 | **A second synthetic KB is committed, deliberately sparse.** A hand-adopted ClaudeKB corpus is an optional, human-gated realism check — reported, never committed | L2. CI gates cross-KB behaviour reproducibly, and APPROACH §3's "authored links are sparse, precious signal" is honoured by the corpus rather than contradicted by it |
| 2 | **Two releases, cut after the links surface** (L10), with the names split accordingly | L10. Nothing before G1 bumps `schema_version`, so the first release needs no rebuild |
| 3 | **The golden set grows to ~25 multi-hop questions, most cross-KB**, plus a `simple-lookup` class; the baseline is re-cut **once** | L9, constrained further by the repair: multi-hop is at ceiling, so the new questions must be *harder* |
| 4 | **Minimum of [KB-UPDATES](../docs/KB-UPDATES.md): the `requires_pinakes` pre-pass.** `pnk upgrade` stays template-release work | G2, beside the bump that makes it matter. "Rebuild guidance" is **already shipped** — `IndexSchemaError` prints the remedy — so it is not scope here |
| 5 | **`pnk link` writes forward only, directly, into the source document's sidecar** | L7. The reverse side is computed by reverse-scan (DESIGN §6.2): no inverse-relation vocabulary is invented, and no second file can disagree |
| 6 | **PPR (APPROACH §4B) and the `[ner]` extra (APPROACH §3) are out** | Neither is specified. APPROACH §4B holds the recipe and §9 the gate; if the gate fires, that earns its own plan |
| 7 | **The plan is adversarially reviewed by fresh subagents until a pass is clean** | Pass 1 done — this rewrite *is* its findings. Pass 2 required before L1 |
| 8 | **`pinakes_search`'s `entities`/`concepts` parameters are cut from both releases** | Was G7. RRF here is unweighted by construction — `_fuse` adds `1/(k+rank+1)` per channel with no per-channel weight — so the feature needs an RRF weighting change touching *every* query, plus its own eval. It is orthogonal to links and edges |
| 9 | **The eval harness is repaired before it is grown**, as its own landed work | Done, `b637be4`. See Baseline |
| 10 | **Retrieval ordering is made deterministic before any finer gate depends on it** | L1. Three sources of run-to-run variance are live today, and G1's rebuild reassigns rowids immediately before the measurement G3 depends on |

---

## What this plan deliberately does NOT decide

Each carries a **default** and a **revisit trigger**, so a later increment cannot quietly absorb it.

| Question | Default | Revisit when |
|---|---|---|
| **Does `pnk link` gain a comment-preserving YAML dependency?** DESIGN §2.2 assigns the writer to `pnk link`; `ruamel.yaml` is the obvious vehicle (pure Python, MIT, no runtime deps), but CLAUDE.md says core dependencies stay light | **Ask the user before L7 starts.** No dependency is added on this plan's own authority | L7 is scheduled |
| PPR / the `"ppr"` value of `graph_channel` | Not reserved. The config accepts `"off" \| "expand"` and rejects anything else | APPROACH §9's `ppr` gate becomes measurable — which needs the channel-reachable ceiling metric this plan does not build |
| The `[ner]` extra and `mentions` edges | Out. G1's node model is shaped so entity nodes *can* be added — but adding them is a reshape, not a no-op, because APPROACH §3 gives hub and entity nodes label embeddings and G1 stores none | The gate in APPROACH §9 fires |
| `pnk adopt` | Out — template-release work | Fleet-scale adoption is real work rather than one hand-run script |
| `pnk ask --deep`, `origin: deep` write-back | Out. The sidecar link schema gains no provenance field here | The deep release |
| Federated / fan-out query | Out. DESIGN §6.2's stated limitation stands, and L8 scores exactly the one-hop loop rather than pretending otherwise | Link coverage proves to be the binding ceiling on a real corpus |
| RRF per-channel weighting | Out, with decision 8 | A plan owns RRF weighting and can measure it |
| A graph query language, a graph database, migrations | Never — APPROACH §7 | — |

---

## Ground rules

- **The gate is an artifact.** `./check.sh` passes immediately before every `git commit`.
  **New gates go into `check.sh` *and* into CI as their own job** — pass 1 caught that `ci.yml`
  never invokes `check.sh`, so a gate added only there is local-only while L10's cut criteria
  require CI green. New gates and owners: link-density (L2), traversal-caps (L4), two-KB eval (L8).
- **A gate that cannot run says so and is still a gate**, with a test asserting the printed reason.
- **Worktree + branch per increment**, `YYYYMMDD_HHMM-<id>-<slug>`, timestamp read from `date`,
  never composed. `git fetch` and re-read `origin/main` at the start of every increment.
- **Pure and I/O are separate increments** (v0.1 rule 11), as I3a/I3b and I6a/I6b were: L4 is the
  traversal core, L5 its provider. The first draft collapsed them while citing the rule in the
  increment's own title.
- **The fixture is not the algorithm** (v0.1 rule 5). L2's corpus is authored from an institutional
  scenario, never generated by walking the edge deriver; a traversal test's expected neighbour set
  is written by hand from the corpus.
- **Break the code on purpose before review.** Each increment names its mutation targets. A target
  that *cannot* be mutated — one asserting the absence of behaviour — is not a target; pass 1 caught
  one such in the first draft.
- **Docs land in the same commit as the behaviour**, never batched into a sweep increment. The first
  draft batched them into two, which `docs/README.md`'s landing checklist forbids and which v0.2's
  I9 explicitly refused to do.
- **Every retrieval change reports before/after per-class golden-set numbers in its commit
  message.** The increments that change retrieval are **L1 and G3** — not G3 alone, as the first
  draft claimed while specifying a ranking change inside an increment it had exempted.

---

## DESIGN.md amendments

| § | Amendment | Lands in |
|---|---|---|
| §2.2 Sidecar | The comment-preserving writer it assigns to `pnk link` is delivered, or the deferral is re-recorded; `links[]` entries round-trip unknown per-link keys | L7 |
| §3 Storage | The node model and the `nodes`/`edges` tables; `schema_version` 3 | G1 |
| §4.1 | The free pipeline gains an optional third channel into RRF, default off | G3 |
| §4 (new §4.8) | The graph channel: bounded expansion, logical-hop depth, fan-out caps, visited-edge dedup, membership exclusion | G3 |
| §4.7 Server boundary | A cross-KB neighbour in a KB the server was not pointed at returns id and relation with **no title** and a stated reason — the boundary holds and the contract degrades, rather than reaching outside it | L6 |
| §6.2 Cross-KB links | Reverse-scan becomes built rather than designed; the failure taxonomy gains its reason strings; stale reverse edges are removed on re-scan | L3 |
| §7 Quality | The `simple-lookup` class and the grown multi-hop class | L9 |
| §8 Delivery plan | The links-release row moves to shipped | L10 |
| §8 Delivery plan | The graph-release row moves to shipped | G4 |

## CLAUDE.md amendments

The first draft had no such table; v0.2 carried four rows. Both below land with the increment that
needs them.

| Rule | Amendment | Lands in |
|---|---|---|
| *"`docs/` belongs to the user … the one exception … `provenance.extraction` — **never any other key**"* | `pnk link` additively writes `links[]` into the source document's own sidecar, on explicit user command. The exception list gains a second, narrower entry: **a user-invoked authoring command**, distinct from anything `sync` may do unasked | L7 |
| Naming table | The `the graph release` row splits into the links release and the graph release | this change |

---

## Increments — the links release

### L1 — Deterministic retrieval ordering

**Why first.** Three sources of run-to-run variance are live, and every gate this plan adds is finer
than the one they hide under today:

- `search.py` `_lexical`: `ORDER BY score` with **no secondary key**. SQLite's order among equal
  `bm25()` scores depends on the FTS index's physical layout — and G1's `schema_version` bump forces
  a rebuild that reassigns rowids **immediately before** the before/after measurement G3 depends on.
- `_vector`: `np.argsort(-similarities)` defaults to quicksort, which is **not stable**.
- `_fuse`'s truncation: `sorted(fused, key=-score)[:fusion_top_k]` has **no tiebreak**, so ties
  resolve by dict insertion order — by whatever the two channels happened to emit. The two later
  sorts *do* carry a `p.path` tiebreak; this truncation runs before them.

**What lands.** A secondary sort key at each of the three sites, chosen to be stable across a
rebuild (`chunk_id`, not rowid order).

**Tests.** `tests/test_search.py::test_identical_queries_return_identical_orderings` (twenty runs);
`::test_a_constructed_score_tie_resolves_by_chunk_id`; `::test_ordering_survives_a_rebuild` (sync,
capture, `--rebuild`, compare).

**Exit criteria.** `make eval` three times, byte-identical JSON. Per-class before/after in the
commit message; the change here should be nil or near-nil, and anything larger is a finding to
explain rather than a result to accept.

**Mutation targets.** Each of the three tiebreaks removed independently — three named tests must
fail, one per site.

**Stands alone.** L1 is landable and releasable independently of everything below, as the eval
repair was.

---

### L2 — The partner KB, sparse links in both corpora, the density gate

**What lands.** `tests/partner-kb/` — a synthetic corpus for a partner museum that genuinely
transacts with the archive in `tests/demo-kb/`: outward and inward loans, courier and condition
reporting, a shared emergency plan, a joint digitisation programme. ~18–22 documents, its own
`pinakes.toml` and fresh KB ULID, its own sidecars, and **its own fitted `[retrieval.confidence]`
block** — without one, `search.py` returns `confidence: unknown` for every query against it, which
would make L6's "calibrated with `query`" claim false on exactly the KB the cross-KB tests use.

Why a partner museum: `tests/demo-kb/docs/loans-inward.md` and `loans-outward.md` already exist, so
the cross-institution links are the ones the scenario forces, not ones invented to give the
traversal something to walk.

**Both corpora gain authored links, and stay sparse.** The demo KB has **zero** today. Links are
authored on **≤ 35% of documents in each KB**, of the weakest useful kind (`cites`, `related`,
`supersedes`), forward-only from each side.

**The density gate, stated precisely** — pass 1 showed the first draft's version measured the wrong
quantity in three independent ways:

- It counts **sidecar-authored (forward) links only**, and says so in its own output. Reverse-scan
  materialises the inbound side in L3, so counting both would double every corpus's apparent
  density — and counting forward links while calling the result "density" without qualification is
  what the first draft did.
- It caps **degree as well as count**: no document may carry more than 4 authored links. Ten linked
  documents sharing 25 links between three hubs passes a document-count cap and is maximally easy to
  traverse.
- It reports the cross-KB / intra-KB split and the relation histogram, so a corpus of nothing but
  `related` — the strongest expansion glue, and weighted 2.0 as an authored edge in G1 — is visible
  rather than hidden inside a single percentage.

**`[[links.kb]] path` resolution is defined here**, because L3, L8 and CI all depend on it in a
fresh clone: **relative to the KB root**, `~` expanded, absolute permitted. Non-existence is *not*
an error — resolution is machine-local (DESIGN §6.2) — and L10's doctor check reports it WARN, never
FAIL, or every user whose collaborator's KB sits elsewhere gets a red doctor.

**Tests.** `tests/test_partner_kb.py::test_both_corpora_load_and_validate`;
`::test_every_sidecar_ulid_is_wellformed_and_unique_across_both_kbs`;
`::test_a_corpus_over_the_density_cap_fails_the_gate` — the negative test the first draft omitted;
without it, flipping `>` to `>=` survives — and `::test_a_corpus_with_a_hub_document_fails_the_gate`.

**Exit criteria.** `pnk sync` clean on both corpora; the gate runs in `check.sh` **and** CI; the
corpus carries no PII, credentials or non-synthetic content — a **review step**, recorded as such,
because the first draft listed it as a test and it cannot be one.

**Mutation targets.** The density comparison at its exact boundary; the degree cap; the
forward-only population selector.

---

### L3 — Reverse-scan, `kb_refs`, and stale-edge removal

**What lands.** `pnk sync` scans each linked KB's **committed sidecars** — never its index, which is
gitignored and absent in a fresh clone — and writes inbound edges as `links` rows with
`origin = 'reverse-scan'`, caching the scan in `kb_refs`. No schema change.

**Stale reverse edges are deleted on re-scan.** `_replace_links()` hardcodes `origin='sidecar'` and
is scoped per *local* document; a reverse row's source lives in another KB, so nothing local removes
it today. Without this, KB-B dropping a link leaves KB-A with a phantom inbound edge forever.

**Cost, because this runs on a hook.** `pnk install-hooks` puts `pnk sync` on pre-commit,
post-commit and post-merge, so N linked KBs would mean N filesystem walks per commit. Reverse-scan
is bounded by `kb_refs.last_scan` with a TTL and skipped while fresh; `--scan-links` forces it.

**Concurrency, because the lock is per-KB.** DESIGN §6.5's advisory lock lives in one KB's
`.pinakes/`. Reverse-scan reads another KB's sidecars while that KB may itself be syncing. It never
takes the other KB's lock; a file that vanishes or fails to parse mid-scan is **recorded as a reason
and retried next scan**, never treated as a deletion.

**The failure taxonomy is defined here** and consumed unchanged by L5 and L6: unresolvable KB id,
unreachable path, target document absent, sidecar unparseable.

**Tests.** `tests/test_sync_links.py::test_inbound_rows_carry_the_other_kbs_id_as_source`;
`::test_a_linked_kb_whose_path_is_absent_is_recorded_not_raised`;
`::test_a_removed_link_removes_its_reverse_row`;
`::test_rebuild_reconstructs_reverse_rows_from_sidecars_alone`;
`::test_a_fresh_kb_refs_entry_skips_the_walk`.

**Mutation targets.** The `src_kb_id` assignment — a reverse edge whose source KB is wrong is
indistinguishable from an outbound one; the stale-row delete; and the "sidecars, not index" path
selection, **whose fixture must contain an index that contradicts the sidecars**, or the mutant
survives on any machine where the two agree, which is every machine that has run `make demo`.

---

### L4 — The traversal core, pure

**What lands.** `graph/traverse.py` — bounded neighbour expansion over an edge-provider protocol,
with no SQLite in it. It enforces, all from APPROACH §4A and §5:

- **Depth in logical hops** — chunk-or-doc to chunk-or-doc, with membership and hub pass-throughs
  depth-free. Counted in physical edges, `chunk→doc→doc→chunk` strands the highest-trust authored
  edges beyond depth 2.
- **Per-node fan-out capped** at `adjacent_k`, **ranked before truncation**.
- **Visited-edge dedup**, so a hub expands once globally rather than once per encounter.
- **Responses double-capped: row count *and* token budget**, with `truncated` set when either bites.
  The token budget is what protects a caller's context, and the first draft dropped it.
- **`unresolved` returned, never dropped.**

**`adjacent_k` is introduced here** as a `[retrieval]` key — `manifest.py`, `docs/MANIFEST.md` and
the `notes` template in the same commit. Default 8. A key a user sets makes their KB unreadable to
older pinakes (`_toml.py` hard-errors on unknown keys), which is what G2's `requires_pinakes` exists
for and why the default must be usable without ever setting it.

**Tests.** `tests/test_traverse.py::test_depth_counts_logical_hops_not_physical_edges`;
`::test_fanout_keeps_the_highest_ranked_neighbours_not_the_first_k` — fails under
truncate-then-rank, which the first draft's cap test could not detect; `::test_a_hub_is_expanded_once_globally`;
`::test_a_cycle_terminates`; `::test_unresolved_targets_survive_to_the_caller`;
`::test_the_token_budget_sets_truncated_independently_of_the_row_cap`.

**Mutation targets.** The rank-then-truncate ordering; the visited-edge set insertion; the
`unresolved` accumulation; the depth comparison.

---

### L5 — The SQLite provider and `pnk links`

**What lands.** The provider behind L4's protocol, and **a CLI surface**. DESIGN §8 settled the
precedent for `pnk search`: a vertical slice queryable only over MCP *does not reach end to end*.
The first draft left traversal reachable only through a live MCP client while its own verification
step said "traverse — run, not reasoned about".

```text
pnk links <doc> [--rel R] [--direction in|out|both] [--depth N] [--query Q] [--json]
```

**The cross-KB `title` problem, resolved without a schema change.** APPROACH §5's contract returns
`title` per neighbour; titles live in `documents`, local KB only; DESIGN §6.2 forbids reading the
other KB's index; DESIGN §4.7 confines the server to its configured KBs. So: a neighbour in a KB
that is a configured `[[links.kb]]` whose path resolves takes its title **from that KB's committed
sidecars** — the same source reverse-scan already reads, and the same source a fresh clone has. A
neighbour whose KB is unknown or unreachable returns `title: null` with the reason attached. No
column, no boundary violation, no bump.

**Tests.** `tests/test_cli_links.py::test_a_neighbour_in_an_unreachable_kb_has_no_title_and_a_reason`;
`::test_a_title_comes_from_the_other_kbs_sidecar_not_its_index`;
`::test_depth_beyond_the_cap_is_served_at_the_cap`; `::test_json_output_is_stable`.

**Also lands.** `tests/free_path_run.py` gains `pnk links`, and `tests/test_paid_path.py`'s surface
list gains it — that gate enumerates surfaces by name and would otherwise silently stop covering the
release.

**Exit criteria.** `DESIGN_COMMANDS` in `tests/test_cli.py` is an exact set and must gain `links`,
which means DESIGN's own command list gains it in this same commit.

**Mutation targets.** The title-source selection — point it at the index and a test must fail; the
server-side depth clamp.

---

### L6 — `pinakes_links`

**What lands.** APPROACH §5's contract over the same core, on the MCP surface. `depth` is
server-capped at 3 — deliberately one more than the automatic channel's 2, because an agent spending
its own turn on an explicit probe has judged the hop worth it. No query-language argument, ever.

**Confidence.** With `query`: fan-out and `score` use similarity to it, and `confidence` carries the
same calibrated signal class as `pinakes_search`. Without `query`: edge weight and link distance
rank, and `confidence` is `unknown` — the calibrated signal is fitted on query-relevance scores, and
a query-less listing has nothing to be confident about.

**The §4.7 boundary holds.** `serve.py` resolves only KBs the server was pointed at; a neighbour
outside them is returned as id + relation with a reason and no title, exactly as L5 defines.

**Tool description carries the loop hints**, labelled by origin: "prefer refining the query over
raising k" is Graph-R1's learned behaviour; "take one hop and look before asking for depth 3" is
ours.

**Tests.** `tests/test_serve.py::test_the_tool_set_is_exactly_these_four` — the existing exact-set
assertion, updated; `::test_pinakes_links_reports_unknown_confidence_without_a_query`;
`::test_a_neighbour_outside_the_served_kbs_is_not_reached`; `::test_depth_is_capped_server_side`.

**Mutation targets.** The `confidence = unknown` branch; the served-KB boundary check; the depth
clamp.

---

### L7 — `pnk link`

**Blocked on a decision** (see *does NOT decide*): whether a comment-preserving YAML dependency is
added. DESIGN §2.2 assigns the writer to this command, `sidecar.py`'s module docstring says the same,
and `plans/v0.1.md` says it a third time. **Ask before starting.**

**What lands.** `pnk link <src> <dst> --rel <rel>`, writing one entry into **the source document's
sidecar only**. Aliases and `self` resolve to ULIDs **on write**, so what reaches disk survives being
shared.

**Per-link unknown keys must round-trip.** `Link` is a two-field frozen dataclass and the writer
emits `{"to":…, "rel":…}` only. Top-level unknown keys survive via `extra`; per-link keys are dropped
today. That is a `docs/`-belongs-to-the-user violation waiting for its first user, and it pre-breaks
the deep release's planned per-link `origin: deep`.

**Tests.** `tests/test_cli_link.py::test_an_alias_is_resolved_to_a_ulid_on_write`;
`::test_self_is_expanded_on_write`; `::test_a_link_round_trips_through_sync_into_the_links_table`;
`::test_unknown_keys_inside_a_link_entry_survive_a_rewrite`;
`::test_comments_in_the_sidecar_survive_a_rewrite` — or, if the dependency is declined, an explicit
xfail recording the accepted loss, with DESIGN §2.2 amended to say so;
`::test_the_source_document_is_byte_identical_afterwards`.

**Mutation targets.** The alias→ULID resolution; the per-link `extra` merge — mutate the writer to
reconstruct from known fields, which is the natural implementation and silently eats user data. The
source-document immutability assertion is **not** a mutation target: there is no code to mutate, and
adding a write on purpose proves only that a bug was written on purpose.

---

### L8 — The two-KB eval harness

**What lands.** The harness learns a second KB. Split from L9 because pass 1 was right that "harness
learns two KBs" and "45 new questions plus a re-baseline" are two bisectable landings — and because
`eval.py` is hard single-KB today: one `manifest.load`, one connection, one backend, and `expect` a
tuple of KB-root-relative path strings.

- `expect` accepts a `pnk://` URI or `<kb-alias>:<path>`; an entry resolving to nothing **fails
  loudly** rather than scoring zero and looking like a retrieval miss.
- `Makefile` and `ci.yml` reference `DEMO_KB` in four places; all become two-KB aware.

**How a cross-KB question is scored — and its honest limit.** Pinakes has no fan-out query and this
release adds none. A cross-KB question is scored as **the loop the design tells callers to run**:
search the origin KB, take one traversal hop with L4's core, ask whether the union covers `expect`.

Two consequences pass 1 forced into the open, stated rather than designed away:

1. **"Covers" means *all* of `expect`, for hopped and cross-KB questions only.** Under the existing
   "any" semantics, a cross-KB question scores a hit the moment the origin search returns the origin
   document — no link, no traversal — and deleting the entire `links` table would not move the class.
   Single-KB unhopped questions keep "any" semantics, so the existing 41 are untouched.
2. **The traversal half of a cross-KB question does not respond to `graph_channel`.** The harness
   calls the core directly; G3's channel lives inside `search()` and cannot return another KB's
   chunks in any case. So cross-KB questions measure **the links release**, and G3's gate is decided
   by the **single-KB** multi-hop questions. L9 sizes those accordingly, and G3's gate names the
   subset it reads.

**Tests.** `tests/test_eval_cross_kb.py::test_a_pnk_uri_expectation_resolves`;
`::test_an_unresolvable_expectation_fails_loudly`;
`::test_a_cross_kb_question_misses_when_the_link_is_removed` — the test that makes the class
non-vacuous; `::test_single_kb_questions_keep_any_semantics`.

**Exit criteria.** The committed 41 score **identically** to the L1 baseline — asserted by a test
over the committed baseline file, not pasted into a commit message by the person who wrote the code,
which is what the first draft proposed and what would have made the safeguard unfalsifiable.

**Mutation targets.** The all-vs-any selector; the unresolvable-expectation failure path.

---

### L9 — The golden set grows, and one re-baseline

**What lands.** ~25 multi-hop questions, most cross-KB, and a ~20-question `simple-lookup` class.

**The constraint the repair created.** `multi-hop` is at **1.00 on five questions**. More questions
of the same difficulty leave it at ceiling and G3's gate unmeasurable. The new single-KB multi-hop
questions must be ones today's pipeline **can fail** — and the honest way to author them without
deriving the fixture from the system under test is to write them from the *corpus structure*
(evidence genuinely split across two documents with no shared vocabulary), then report how many the
current pipeline gets, whatever that number turns out to be. If the class lands at ceiling anyway,
that is reported as "this corpus cannot gate a graph channel" — a finding, not a licence to tune.

**`simple-lookup` has the same problem in reverse**, named rather than wished away: `lexical` is
already 1.00, so a class of easy single-document questions is pinned at ceiling and can only show
damage. That is *acceptable for this class* — its job in APPROACH §9's gate is precisely to detect
the ~13% simple-query regression the GraphRAG-Bench line measured. Sized at ~20 so one question is
5 points rather than 8.

**The re-baseline.** Once, in this increment, with per-class before/after in the commit message and
the previous `baseline.json` preserved beside the new one.

**Tests.** `tests/test_eval.py::test_the_committed_golden_set_is_well_formed` gains the new kinds —
its exact-set assertion must be updated, and `test_evaluating_the_demo_kb_produces_every_metric`
hard-codes the same five-kind set. `::test_every_multi_hop_question_has_at_least_one_that_fails` is
**not** written: it would encode today's failures as a requirement.

---

### L10 — `pnk doctor`, and the links release cut

**What lands.** `doctor.py`'s `"{n} cross-KB (unchecked until the links release)"` becomes a real
check: cross-KB targets resolve, or are reported dangling with a reason. Link coverage is reported as
the ceiling on cross-KB answers it is (DESIGN §6.2). A zero-link document count is a nudge — the
proven pressure short of a hard gate (APPROACH §3).

**Severity is decided here, not left to the implementer:** an absent linked-KB path is **WARN**,
since resolution is machine-local; a `pnk://` target absent from a KB that *did* resolve is **WARN**
with the count; a malformed `pnk://` in a committed sidecar is **FAIL**. `cli.py` exits 1 only on
FAIL.

**The cut criteria.** Ship when all hold:

1. L1–L10 merged to `main`, each green, CI green on the merge.
2. The committed 41 questions score identically to the L1 baseline — asserted by test, not by eye.
3. **No `schema_version` bump has occurred** — verified by reading `store.SCHEMA_VERSION`, still 2.
4. `pnk doctor` clean on both corpora.
5. The free-path subprocess gate covers `pnk link`, `pnk links` and the MCP handshake.

**Check `origin/main` for the release number before assigning it.** MINOR under the SemVer table.
The paid-extraction release may well cut first; the number is decided at the cut, never before.

---

## Increments — the graph release

### G1 — The node model and the edge set (`schema_version` 3)

**What lands.** APPROACH §3's heterogeneous node model and its derived edges, computed at sync,
stored in `.pinakes/index.db`. Inert: nothing reads them until G3.

Nodes: **chunk**, **document**, **tag**, **heading-path** (*scoped per document* — a global
"Introduction" hub would weld every document into one noise clique), **directory**.

Every shared-value relation goes **through its hub node**, never as materialised pairwise edges —
what keeps edge counts linear instead of O(members²) and gives G3's visited-edge dedup a single node
to expand once.

**Damping is computed at read, not stored** — the resolution to a problem the first draft did not
see. APPROACH §3's weights (`1/tag-degree`, `1/dir-size`, `1/section-size`) are **global**
quantities, and `pnk sync` is incremental by design: one document gaining a tag changes the correct
weight of every co-tagged document's edge. Storing damped weights would mean either recomputing the
whole edge set on every sync — a wall-clock regression on a hook-driven command — or letting weights
go quietly stale, which no test could catch. So the `edges` table stores **structure only**, the
`nodes` table stores each hub's degree, and traversal applies `1/degree` when it reads. Incremental
sync then updates one degree per affected hub.

| Edge | Connects | Weight (applied at read) |
|---|---|---|
| membership | chunk ↔ doc | 1.0 — transit plumbing, not signal |
| `sibling` | chunk ↔ chunk (adjacent ordinal) | 1.0 |
| `parent` / `child` | chunk ↔ chunk (`heading_path` prefix) | 1.0 |
| `in-section` | chunk ↔ heading node (per-doc) | 1/section-size |
| `co-located` | doc ↔ directory node | 1/dir-size |
| `shared-tag` | doc ↔ tag node | 1/tag-degree |
| authored | doc ↔ doc (sidecar `links`) | 2.0 |

**Weight composition across a hub is the product of both spokes** (APPROACH §3), so 1/degree spokes
damp big hubs superlinearly. L4's core gains that rule here; until G1 the graph is doc↔doc authored
edges only and composition is trivial. Weights are **starting points to be fitted against the golden
set**, not measured constants, and the fitting is reported.

`schema_version` → **3**. Every KB rebuilds; no migration.

**Tests.** `tests/test_edges.py::test_a_shared_tag_produces_linear_not_quadratic_edges`;
`::test_a_heading_hub_never_connects_two_documents`;
`::test_adding_a_document_updates_one_hub_degree_not_every_edge`;
`::test_weight_across_a_hub_is_the_product_of_both_spokes`;
`::test_a_schema_version_2_index_is_refused_with_its_remedy`.

**Mutation targets.** The degree divisor, replaced with 1.0; the per-document scoping of heading
nodes; the incremental degree update; the `schema_version` refusal.

---

### G2 — `requires_pinakes` and the version floor

**What lands.** `[kb]` gains `requires_pinakes`, read in a **pre-pass before strict manifest
validation** — a manifest from a newer pinakes must be able to say so *before* the strict validator
rejects its unknown keys.

**The floor is written at the cut, not now.** KB-UPDATES requires the error to name a version, and
this plan cannot know it: the number is assigned against `origin/main` when G4 cuts. The increment
lands the mechanism with the floor read from `pinakes.__version__`, and G4 verifies the message names
the released number.

Out of scope, explicitly: `pnk upgrade`, `--apply`, template drift, tomlkit. Rebuild *guidance* is
already shipped — `IndexSchemaError` prints the remedy.

**Tests.** `tests/test_manifest_compat.py::test_a_manifest_requiring_a_newer_pinakes_names_the_version`;
`::test_the_pre_pass_runs_before_strict_validation`;
`::test_an_absent_requires_pinakes_is_not_an_error`.

**Mutation target.** The pre-pass ordering — move it after strict validation and the version message
must stop appearing.

---

### G3 — The expansion channel, default off, and its gate

**What lands.** `[retrieval] graph_channel = "off" | "expand"`, default `"off"`, introduced with its
home in `manifest.py`, `docs/MANIFEST.md` and the template. When `"expand"`: the fused top-*k* as
roots, expanded with L4's core to depth ≤ 2, ranked, fed into RRF as a **third** input. An empty edge
set means an empty third channel and RRF fuses two lists exactly as today.

Ranking follows the node model's asymmetry: **chunk** neighbours rank by cosine against the query
embedding; **non-chunk** nodes carry no content embedding, pass through by edge weight, and
contribute their member chunks **minus the root's own document** — APPROACH §3's membership
exclusion, which excludes them from the output **and from the fan-out budget**. Excluding only at
output, after they have consumed fan-out, silently narrows real results; the first draft quoted half
the rule.

In the same eval matrix, both cheaper than everything else here: **in-degree over the `links` table
as a zero-cost salience prior**, and the **link-distance rerank**.

**The gate — defined here, because APPROACH §9 defines none for this channel.** §9's `expand` row
reads *"multi-hop recall@k up, simple-lookup unchanged, false-abstain flat"*, with no threshold; the
"≥ 5 points" figure belongs to its `ppr` row, which decision 6 excludes. The first draft cited that
figure anyway and built its entire sample-size argument on it.

The unit is **questions, not percentages** — at n≈25 one question is 4 points, and a percentage
invites a precision that is not there. On the **single-KB** multi-hop subset (L8 explains why
cross-KB questions cannot respond to this setting), measured three consecutive times with
byte-identical output (L1), `expand` defaults **on** only if all three hold:

1. multi-hop improves by **≥ 5 questions net**;
2. **no class regresses at all** — enforced by `compare()`, not by reading;
3. false-abstain does not rise.

**Why five.** Under an exact one-sided sign test, five discordant questions all in one direction is
the smallest result with p < 0.05 (0.5⁵ = 0.031); four gives p = 0.063. Below five, a corpus this
size cannot distinguish the channel from a coin toss.

**The pre-commitment.** A net improvement of 1–4 questions ships the channel **`off`**, with the
numbers and the p-value recorded, and it is not tuned until it passes. The part that makes this a
commitment rather than a laundering mechanism: **a test asserts the channel actually does
something** — with `"expand"` and a non-empty edge set it must surface at least one document that
two-list fusion does not return. Without that test, a channel broken into returning nothing produces
the identical blessed outcome as a channel that honestly did not help.

**Tests.** `tests/test_graph_channel.py::test_expand_surfaces_a_document_fusion_alone_does_not`;
`::test_an_empty_edge_set_reproduces_two_list_fusion_exactly`;
`::test_off_issues_no_traversal_query`;
`::test_a_same_document_chunk_reachable_only_by_membership_never_appears`;
`::test_membership_neighbours_do_not_consume_the_fanout_budget`.

**Mutation targets.** The membership exclusion at *both* points, output and budget; the default value
of `graph_channel`; the empty-edge degradation path; the third-channel RRF contribution — neuter it,
and `test_expand_surfaces_a_document_fusion_alone_does_not` must fail.

---

### G4 — Edge-hub reporting, docs, release

**What lands.** `pnk doctor` reports the highest-degree edge hubs, so a user can see when a tag has
become meaningless glue. DESIGN §3, §4.1, §4.8 and §8 amendments. `docs/STATUS.md` rows flipped.
CHANGELOG assembled. Release cut, tagged, pushed, GitHub release created from that section.

**Verify, never assume, that the release happened**: `git tag -l`, `gh release list`,
`git merge-base --is-ancestor`. `make release-check` **before** pushing the tag — a tag publishes to
PyPI, and a version cannot be re-uploaded.

---

## Verification — every promise has an owner

v0.1 rule 8: *a promise in a section with no owner is a wish.* Pass 1's most common finding was
"specified in APPROACH, owned by no increment."

| Promise | Source | Owner | Checked by |
|---|---|---|---|
| Reverse links computed by scanning committed sidecars | DESIGN §6.2 | L3 | `test_rebuild_reconstructs_reverse_rows_from_sidecars_alone` |
| Dangling targets reported, never dropped | DESIGN §6.2 | L3, L10 | `test_a_linked_kb_whose_path_is_absent_is_recorded_not_raised` |
| Link coverage reported as the ceiling | DESIGN §6.2 | L10 | doctor output test |
| Aliases never inside a `pnk://` URI | DESIGN §2.2, MANIFEST | L7 | `test_an_alias_is_resolved_to_a_ulid_on_write` |
| Comment-preserving sidecar writer | DESIGN §2.2 | L7 | `test_comments_in_the_sidecar_survive_a_rewrite`, or an amended §2.2 |
| Unknown keys round-trip | DESIGN §2.2 | L7 | `test_unknown_keys_inside_a_link_entry_survive_a_rewrite` |
| Server reaches only its configured KBs | DESIGN §4.7 | L6 | `test_a_neighbour_outside_the_served_kbs_is_not_reached` |
| Typed verbs, hard caps, no query language | APPROACH §5 | L4, L6 | `test_depth_is_capped_server_side` |
| Score + frontier on every return | APPROACH §5 | L6 | contract test |
| Double cap: rows **and** token budget | APPROACH §5 | L4 | `test_the_token_budget_sets_truncated_independently_of_the_row_cap` |
| `confidence` unknown without `query` | APPROACH §5 | L6 | `test_pinakes_links_reports_unknown_confidence_without_a_query` |
| Depth in logical hops | APPROACH §4A | L4 | `test_depth_counts_logical_hops_not_physical_edges` |
| Per-depth Python loop, not a recursive CTE | APPROACH §4A | L5 | provider test: one query per hop |
| Visited-edge dedup | APPROACH §4A | L4 | `test_a_hub_is_expanded_once_globally` |
| Membership excluded from output **and** budget | APPROACH §3 | G3 | two named tests |
| Hub damping on every shared-value hub | APPROACH §3 | G1 | `test_a_shared_tag_produces_linear_not_quadratic_edges` |
| Weight across a hub is the product of spokes | APPROACH §3 | G1 | `test_weight_across_a_hub_is_the_product_of_both_spokes` |
| Heading nodes scoped per document | APPROACH §3 | G1 | `test_a_heading_hub_never_connects_two_documents` |
| Edge-hub reporting in `pnk doctor` | APPROACH §3 | G4 | doctor output test |
| Authored links are sparse | APPROACH §3 | L2 | the density gate, with its negative test |
| Per-class gating | DESIGN §7 | shipped `b637be4` | `test_a_per_class_regression_is_caught_when_the_aggregate_hides_it` |
| Golden set: multi-hop + simple-lookup sections | APPROACH §9 | L9 | `test_the_committed_golden_set_is_well_formed` |
| A channel regressing simple lookup stays off | APPROACH §9 | G3 | `compare()`, plus the gate's clause 2 |
| Free path stays free | CLAUDE.md | L5, L6, L7 | the subprocess gate, extended per increment |
| No `schema_version` bump before the links release | this plan | L10 | cut criterion 3 |

---

## Risks

| Risk | Why it is real | Mitigation |
|---|---|---|
| The synthetic corpus is unrealistically clean | One author writes the corpus, the links, the questions that traverse them, and (in G1) fits seven edge weights against them — closer to a fixture than an instrument | Density **and** degree caps with negative tests; weakest-useful relations only; the optional ClaudeKB realism check; weights stated as starting points, and the fitting reported |
| ~25 multi-hop questions cannot establish significance | Wilson 95% CI at p̂ = 0.8, n = 25 is ±15 points | The gate is stated in questions with an exact sign test, and pre-commits to shipping `off` below five |
| The single-KB multi-hop subset is smaller than 25 | Cross-KB questions cannot respond to `graph_channel` (L8), so the gate reads a subset | L9 sizes that subset explicitly; if it cannot reach 5-question resolution, G3 reports that the corpus cannot gate the channel |
| `multi-hop` is at ceiling after the eval repair | A class at 1.00 can only show damage | L9's new questions are authored to be failable, and the pass rate is reported whatever it is |
| The channel fails its gate | One study in the GraphRAG-Bench line measured graphs *costing* ~13% on simple lookup | The links release ships first and stands alone |
| A concurrent agent lands conflicting work | `main` moved eleven commits under the first draft | `git fetch` and re-read `origin/main` at every increment; release numbers decided at the cut |
| Reverse-scan on a hook is unbounded | `pnk sync` runs on three git hooks; N linked KBs is N tree walks per commit | `kb_refs.last_scan` TTL; `--scan-links` to force |
| Cross-KB reads race the other KB's sync | The advisory lock is per-KB | Never take the other KB's lock; a torn read is a recorded reason, retried, never a deletion |
| A dependency creeps in for the YAML writer | DESIGN §2.2 assigns it; CLAUDE.md says core deps stay light | Explicitly undecided, default "ask first", L7 blocked on it |

---

## Iteration log

| When | What |
|---|---|
| 20260729 02:52 | Written. Seven decisions taken with the user; no adversarial pass |
| 20260729 03:31 | **Pass 1** — three independent reviewers (claims-vs-sources, sequencing, measurement): 22 HIGH, 30 MEDIUM, 15 LOW. Rewritten. Three findings were fixed *outside* this plan first, because they were live defects on `main`: the multi-hop scorer, the missing `by_kind` gate, and the non-deterministic test embedder (`b637be4`). Decisions 8–10 added; the release split in two; `entities`/`concepts` cut; the eval gate given a threshold for the first time |
