# The links release and the graph release — implementation plan

**Status:** draft — revised after adversarial passes 1 (22 HIGH), 2 (26 HIGH), 3 (24 HIGH),
4 (13 HIGH) and 5 (3 HIGH). **Not yet implementable.** The count is falling and the findings are
localising, but pass 5 still found a decision resting on a false premise — so assume this revision
has defects too, and run pass 6 before building.

**Date:** written 20260729 02:52 · rewritten 03:31, 04:05, 04:27, 04:46, 05:06

**Source of truth:** [`docs/DESIGN.md`](../docs/DESIGN.md). Where this plan and DESIGN disagree on
anything *not* in the amendments tables, DESIGN wins and this plan has a bug.

**Section references are qualified** — `DESIGN §5` and `APPROACH §5` are different documents.

**Written against** [`docs/graph/PINAKES_APPROACH.md`](../docs/graph/PINAKES_APPROACH.md) (five
adversarial passes) and `docs/RETROSPECTIVES.md` **together with any unspliced fragments in
[`retro.d/`](../retro.d/)** — the newest findings live there until a release splices them, so
reading only the document systematically misses them.

## Baseline — `main` at `5ff5897`, 20260729 04:27

Re-verify before L1. `main` moved fifteen commits and cut a release under the first three drafts.

| Fact | Value |
|---|---|
| Latest release | **0.3.0**, the paid-extraction release, tagged and published |
| `schema_version` | 2 |
| I8, I9 | **Still planned.** 0.3.0 was cut at I7c, so these belong to a later release and are not this plan's concern |
| Golden set | 41 questions · recall@5 0.909 · MRR 0.812 · rerank precision 0.758 · false-abstain 0.03 · false-confidence 0.25 |
| Per class | `lexical` 1.00 · `filter` 1.00 · `no-answer` 1.00 · `multi-hop` **1.00 (n=5, at ceiling)** · `paraphrase` 0.75 |
| `links` | PK is `(src_kb_id, src_doc_id, dst_kb_id, dst_doc_id, rel)` — **`origin` is not in it** |
| `kb_refs` | Four columns, never written |
| `chunks.id` | The rowid. `store.py`: *"a chunk has no identity across rebuilds"* |
| Authored links in `tests/demo-kb/` | **Zero**, across 30 documents |
| `eval.py` | Structurally **single-KB**: one connection, one manifest, one backend; `retrieved` is local `passage.path` strings; per-question outcomes are computed and discarded |
| Conventions | `changelog.d/` and `retro.d/` fragments — **editing `CHANGELOG.md` or `RETROSPECTIVES.md` directly is forbidden**; `tools/fragments.py --check` and `tools/shared_file_overlap.py` are `check.sh` gates |

---

## Two releases

| Release | What it is | Rebuild? | Needs the golden set? |
|---|---|---|---|
| **the links release** | `pnk link`, `pnk links`, `pinakes_links`, reverse-scan, link coverage | **No** | **No** |
| **the graph release** | Structural edges, the expansion channel, `schema_version` 3 | Yes, once | Yes — it is the whole gate |

**A third outcome exists and is planned for**, not discovered: if G2's precondition fails, G3 and G5
do not run, and G1 + G2 + G4 ship as their own release — a reproducibility measurement, a larger and
better-instrumented golden set, and a manifest forward-compatibility pre-pass. Its verification is
G6's minus the edge-dependent steps, its deliverable is not edge-hub reporting, and it is named at
the cut like any other.

**The links release changes no retrieval**, so no golden-set work is on its critical path. Pass 3
made this unavoidable: `eval.py` is structurally single-KB, and every attempt to score a cross-KB
question through it produced a class pinned at 0.00 or 1.00 by construction. Traversal correctness
is directly testable — does the traversal return the neighbour the corpus says it should — and that
is what the links release ships with. All eval work moves to the graph release, where it is the gate.

---

## Goal

A question answered in one KB can reach evidence in another **one hop out**, because a human said the
two documents were related and pinakes remembered — and the structure that makes retrieval better
when nobody has authored anything is derived for free afterwards, if and only if the golden set says
it helps.

**One hop, stated plainly** (decision 16): a cross-KB neighbour is terminal — **by policy, enforced
by an explicit suppression**, not because the query comes back empty. It does not: K's index holds
each partner document's links *that target K*, so a depth-2 hop through one would return K
documents. It is suppressed because that view is **partial** — the partner's internal links are not
in K's index and never will be — and a silently incomplete result is the failure mode this project
refuses. Multi-hop *within* a KB is unbounded to the cap; multi-hop *across* KBs is one step. This
is a **new** DESIGN §6.2 amendment (L4): §6.2's existing "honest limitation" is about link
*coverage*, not traversal depth, and the plan should not claim DESIGN already says this.

**Nothing here can spend money.** `.paid-path-allowlist` is unchanged; the free-path gate's
*coverage* is extended per increment, which is required.

---

## Decisions taken

Dated by when each was settled, because a decision produced by a review is not one the user made
earlier.

| # | Decision | When | Consequence |
|---|---|---|---|
| 1 | A second synthetic KB is committed, deliberately sparse; the ClaudeKB realism check is optional and human-gated | 02:30–03:10 | L1, L8 |
| 2 | Two releases, cut after the links surface; names split | 02:30–03:10 | L8 |
| 3 | The golden set grows and gains a `simple-lookup` class; one re-baseline | 02:30–03:10 | G2 — **amended by 12 and 14** |
| 4 | Minimum of [KB-UPDATES](../docs/KB-UPDATES.md): the `requires_pinakes` pre-pass only | 02:30–03:10 | G4 |
| 5 | `pnk link` writes forward only, into the source document's sidecar | 02:30–03:10 | L6 |
| 6 | PPR and the `[ner]` extra are out | 02:30–03:10 | — |
| 7 | Adversarial subagent passes until one comes back clean | 02:30–03:10 | Passes 1–5 done; **pass 6 required** |
| 8 | `pinakes_search`'s `entities`/`concepts` are cut | 03:20–03:35 | RRF here is unweighted by construction |
| 9 | The eval harness is repaired before it is grown | 03:20–03:35 | Landed `b637be4`, released in 0.3.0 |
| 10 | Retrieval reproducibility is established before a finer gate depends on it | 03:20–03:35 | G1 — **reframed by 15**: measured first, fixed only if measurement says so |
| 11 | Cross-KB neighbours carry no `title` | 04:00–04:05 | L4, L5 |
| 12 | The multi-hop class is majority single-KB | 04:00–04:05 | G2 — **superseded by 14** |
| 13 | **The edge weights** are frozen at APPROACH §3's priors, committed before G2's questions are authored | 04:00–04:05 | G3, G5 |
| 14 | **The golden set gains no cross-KB questions at all.** The multi-hop class stays single-KB, and cross-KB behaviour is verified by direct traversal tests instead | 04:27 (pass 3) | L1–L7, G2. `eval.py` is single-KB in its bones — one connection, one backend, `retrieved` as local paths. A cross-KB question scored through it is 0.00 by construction (the hop can never be followed) or 1.00 by construction (it merely confirms a link L1 hand-authored). Neither can decide anything, and pass 2 already established such questions cannot respond to `graph_channel` |
| 15 | **Ordering reproducibility is measured before anything is changed.** No tiebreak is specified in advance | 04:27 (pass 3) | G1. The previous revision's three tiebreaks would have changed nothing observable: cross-document ties are already totalised by `documents.path`, and within a document rowid order *is* ordinal order in every write path that exists. **That is a fact about writes, and it reaches the output only through `_hydrate`'s unordered `WHERE c.id IN (…)` — an undocumented SQLite behaviour the tiebreak would have removed the dependency on.** So: measure first, and let the measurement scope the fix |
| 16 | **The traversal surface serves document-level neighbours only, and a cross-KB neighbour is terminal at any depth** | 04:46 (pass 4) | L3–L5, G3, G5. Two findings collapse into this. First, terminality is **a policy, and needs an explicit suppression in the core** — an earlier draft of this row claimed K's index has "nothing to walk" past a cross-KB neighbour, which is false: `store.py` states that *"a reverse link's source lives in another KB"*, so a reverse-scanned row is keyed on the **foreign** document and a depth-2 query from one returns K documents. The reason to stop is not emptiness but **partiality**: K only ever holds the partner's links that point *back at* K, never the partner's internal links, so expanding through a foreign document would show a systematically incomplete slice of its graph that no caller could distinguish from the whole. Second, structural nodes (tag, directory, heading, chunk) have **no `doc_id`**, so serving them would break the neighbour shape L4 pins with a test. Keeping the tool document-level means **G3 changes no released surface at all** and G5 flips no filter: the structural graph is internal to the expansion channel, permanently, and the authored graph is what `pnk links` shows |
| 17 | **Traversal `confidence` is always `unknown`** in both releases | 04:46 (pass 4) | L5, amending APPROACH §5. The calibrated thresholds are fitted per KB on the reranker score of the *top retrieved passage* for a golden-set query (`calibrate.py`). A traversal neighbour is not a retrieved passage, a cross-KB neighbour list has no single manifest whose thresholds apply, and no fitted data for a traversal signal exists. DESIGN §4.2's rule is that an absent signal is `unknown`, never invented |

---

## What this plan deliberately does NOT decide

| Question | Default | Revisit when |
|---|---|---|
| Does `pnk link` gain a comment-preserving YAML dependency? | **Ask before L6.** If unavailable: ship without it, xfail the comment test, amend DESIGN §2.2 to record the deferral. Nothing else depends on L6 except L8's verification step 2 | L6 is scheduled |
| Does that writer become *the* sidecar writer? | Only `pnk link`'s, and DESIGN §2.2 records that a later paid-extraction sync destroys the comments it preserved | The churn is observed |
| PPR, the `[ner]` extra, `pnk adopt`, `--deep`, federated query, a graph query language, migrations | Out | — |
| `pnk unlink` | Out; fix a mistyped link by editing the sidecar | A user hits it |
| Held-out eval splits | Out at this corpus size | The set is large enough that a holdout can still gate |

---

## Ground rules

- **The gate is an artifact.** `./check.sh` before every commit — **and every new gate also gets its
  own CI job**, because `ci.yml` never invokes `check.sh`. New gates and owners: link-density (L1),
  traversal-caps (L3), eval reproducibility (G1).
- **A gate that cannot run says so and is still a gate**, with a test asserting the printed reason.
- **Worktree + branch per increment**, `YYYYMMDD_HHMM-<id>-<slug>`, timestamp from `date`.
- **Before merging, run `python3 tools/shared_file_overlap.py --fetch --strict`** and read the merged
  state of anything it names. A clean auto-merge is not a correct merge. Thirteen of these fourteen
  increments touch `docs/DESIGN.md` or `docs/STATUS.md` by their own Docs lines.
- **The changelog entry is a [`changelog.d/`](../changelog.d/README.md) fragment**, in the same
  commit as the code. **Never edit `CHANGELOG.md`.** Retrospective findings are a
  [`retro.d/`](../retro.d/README.md) fragment; **never edit `docs/RETROSPECTIVES.md`.** No gate
  catches a direct edit, so this is on the author.
- **Retrospectives are an input** — read `docs/RETROSPECTIVES.md` **and** `retro.d/` at the start of
  each increment.
- **Pure and I/O are separate increments** (v0.1 rule 11): L3 core, L4 provider.
- **The fixture is not the algorithm** (v0.1 rule 5).
- **No inline type suppressions** (v0.1 rule 7) — the node model (G3) is a discriminated union under
  `pyright` strict and is where the temptation will be.
- **Durability** (v0.1 rule 12): every sidecar write is rename-atomic. L6 introduces a new writer,
  and a sidecar's ULID is the one thing no later command can recompute.
- **Break the code on purpose before review.** A target that cannot be mutated is not a target.
- **Docs land in the same commit as the behaviour**, and every increment names its homes.
- **Every retrieval change reports before/after per-class numbers.** The only such increment is
  **G5**. G3 is genuinely inert under decision 16: the provider serves authored document edges, the
  structural graph is read only by the channel, and G3's exit criterion checks that `pnk links`
  output is unchanged rather than assuming it.

---

## DESIGN.md amendments

| § | Amendment | Lands in |
|---|---|---|
| §2.1 | `[retrieval] adjacent_k` | L3 |
| §2.1 | `[retrieval] graph_channel` | G5 |
| §2.1 | `[kb] requires_pinakes` | G4 |
| §2.2 | The comment-preserving writer delivered or its deferral re-recorded; `links[]` round-trips unknown per-link keys | L6 |
| §3 | The node model, `nodes`/`edges`, `schema_version` 3 | G3 |
| §4.1, new §4.8 | The graph channel | G5 |
| §4.7 | Publishing a KB publishes the ULIDs and relations of every KB it links to | L1 |
| §6.2 | Reverse-scan built; failure taxonomy; stale reverse edges removed | L2 |
| §6.3 | `pnk sync --scan-links` | L2 |
| §7 | The `simple-lookup` class; per-question outcomes are an artifact; a template ships no golden set | G2 |
| §6.2 | Cross-KB traversal is one hop: a neighbour in another KB is terminal | L4 |
| §8 | Command list gains `link` and `links`; every tool takes an explicit `kb` | L4, L5, L6 |
| §8 | The links-release row moves to shipped | L8 |
| §8 | **Both** graph-release rows reconciled | G6 |

## APPROACH amendments

| § | Departure | Lands in |
|---|---|---|
| §5 | The neighbour shape gains `kb_id` and loses `title` for cross-KB neighbours | L4 |
| §3 | Weights are frozen, not fitted | G3 |
| §10 | Cross-KB golden-set questions are not built (decision 14) | G2 |
| §5 | `confidence` on a traversal response is always `unknown` (decision 17) | L5 |
| §5 | Neighbours are documents only; a cross-KB neighbour is terminal (decision 16) | L4 |
| §5 | `frontier` entries gain `kb_id` and a five-valued `reason`, and include fan-out-dropped candidates, not only next hops | L3 |
| §5, §10 | `pinakes_search`'s `entities`/`concepts` parameters are not built (decision 8) | — |

## CLAUDE.md amendments

| Rule | Amendment | Lands in |
|---|---|---|
| *"`docs/` belongs to the user … never any other key"* | A second, narrower exception: **a user-invoked authoring command** writing `links[]` to the source document's own sidecar | L6 |
| The "🚫 Unbuilt work is named" table (**not** the "Naming (fixed…)" table) in `CLAUDE.md` **and** `docs/STATUS.md` | Both files' links-release rows gain `pnk links` | L4 |

---

## Increments — the links release

### L1 — The partner KB, sparse links, the density gate

**What lands.** `tests/partner-kb/` — a partner museum that transacts with the archive in
`tests/demo-kb/`: loans in and out, courier and condition reporting, a shared emergency plan, a joint
digitisation programme. ~18–22 documents, own `pinakes.toml` and KB ULID, own sidecars.

**No golden set is needed for it** (decision 14). It exists to be linked to and traversed, and both
are tested directly.

**Both corpora gain authored links, and stay sparse.** The demo KB has zero today. ≤ 35% of
documents in each KB, weakest useful relations, forward-only from each side.

**The density gate reads the committed sidecars, not the index** — it must run in `check.sh`, which
never builds one. It counts forward-authored links, caps **degree** at 4 per document as well as
count, and reports the cross-KB/intra-KB split and the relation histogram. (The previous revision
described an `origin='sidecar'` filter and a test that reverse-scan rows are ignored; a sidecar
cannot contain a reverse-scan row, and L1 lands before L2 creates one anywhere.)

**`[[links.kb]] path` resolution:** relative to the KB root, `~` expanded, absolute permitted but
**warned** by `pnk doctor` (L7) — this repo is public by rule and an absolute path in a committed
manifest publishes a filesystem layout. Non-existence is not an error.

**Tests.** `tests/test_partner_kb.py::test_both_corpora_load_and_validate`;
`::test_every_sidecar_ulid_is_wellformed_and_unique_across_both_kbs`;
`::test_a_corpus_over_the_density_cap_fails_the_gate`;
`::test_a_corpus_with_a_hub_document_fails_the_gate`;
`::test_the_gate_runs_without_an_index`.

**Exit criteria.** `pnk sync` and `pnk doctor` clean on both; the gate in `check.sh` **and** its own
CI job. **Review step** (not a test): no PII, credentials or non-synthetic content.
**Docs:** `docs/MANIFEST.md`, `docs/DESIGN.md` §4.7, `docs/STATUS.md`, a `changelog.d/` fragment.

**Mutation targets.** The density comparison at its boundary; the degree cap; the per-document
grouping that makes degree distinguishable from count.

---

### L2 — Reverse-scan, `kb_refs`, and stale-edge removal

**What lands.** `pnk sync` scans each linked KB's **committed sidecars** — never its index — and
writes inbound rows with `origin='reverse-scan'`, recording alias, resolved path and scan time in
`kb_refs` (DESIGN §3 defines all four columns; nothing writes any of them today). No schema change.

**A reverse row never overwrites an authored one.** `origin` is not in the `links` PK, so a plain
`INSERT OR REPLACE` could downgrade a weight-2.0 authored edge whenever the tuples collide — which
happens when a manifest lists itself as a `[[links.kb]]`, or two aliases resolve to one KB. Insert
with `ON CONFLICT DO NOTHING`.

**Stale reverse edges are deleted on re-scan**, scoped **per scanned `src_kb_id`**.

**Cost, because this runs on a hook.** Bounded by `kb_refs.last_scan` with a TTL — **a code constant,
not a manifest key**, stated here because "how stale may a cross-KB link be" is user-visible and the
previous revision left it to the implementer — forced by `--scan-links`. `--sidecars-only` (the pre-commit hook) does **not** scan; reverse rows are index
rows.

**Concurrency.** Never take the other KB's lock; a file that vanishes or fails to parse mid-scan is
a recorded reason, retried, never a deletion.

**The failure taxonomy** — unresolvable KB id, unreachable path, target document absent, sidecar
unparseable — lands as typed errors in `errors.py`, each with a remedy, and is consumed unchanged by
L4, L5 and L7.

**Tests.** `tests/test_sync_links.py::test_inbound_rows_carry_the_other_kbs_id_as_source`;
`::test_a_reverse_row_never_overwrites_an_authored_row` (fixture: a manifest listing itself);
`::test_kb_refs_records_alias_path_and_scan_time`;
`::test_each_failure_mode_is_recorded_with_its_reason` (four cases);
`::test_a_removed_link_removes_its_reverse_row`; `::test_the_delete_is_scoped_to_the_scanned_kb`;
`::test_a_fresh_kb_refs_entry_skips_the_walk`; `::test_an_expired_ttl_forces_a_rescan`;
`::test_scan_links_forces_a_rescan`; `::test_sidecars_only_does_not_scan`;
`::test_rebuild_reconstructs_reverse_rows_from_sidecars_alone`.

**Exit criteria.** All green; `pnk doctor` clean. **Docs:** `docs/CLI.md` (`--scan-links`),
`docs/DESIGN.md` §6.2 and §6.3, `docs/STATUS.md`, a `changelog.d/` fragment.

**Mutation targets.** The `src_kb_id` assignment; `DO NOTHING` → `OR REPLACE`; the delete's scoping;
the TTL check; the "sidecars, not index" selection — **whose fixture must hold an index that
contradicts the sidecars**, since a rebuild has no index to read.

---

### L3 — The traversal core, pure

**What lands.** `graph/traverse.py` over an edge-provider protocol, no SQLite. **Depth in logical
hops**; **fan-out capped at `adjacent_k`, ranked before truncation**; **visited-edge dedup**;
**responses double-capped on row count *and* token budget**; **`unresolved` returned, never dropped**.

**Both ranking modes are specified here**, because APPROACH §5 defines two and no previous revision
owned either: **with `query`**, neighbours rank by similarity to it; **without**, by edge weight then
link distance, deterministically tie-broken on `(kb_id, doc_id)`. The core stays pure by taking
similarity as a **provider-supplied score per candidate** — the provider embeds and scores, the core
only ranks, caps and dedups.

**The core is generic over node identity**, so one implementation serves both the document provider
(L4) and G5's structural expansion. A candidate carries an opaque `node_key` the provider defines
and totally orders — `(kb_id, doc_id)` for documents, `(kind, key)` for structural nodes — and the
core's dedup and tie-break use only that. Without this, G5 would need a second expander outside
L3's traversal-cap gate.

**`frontier` is defined here and produced here**, not in the MCP layer — it is core work, and the
previous revision left APPROACH §5's other half unowned. A frontier entry is
`{kb_id, doc_id, rel, reason}` — a neighbour *discovered and not expanded* — and `reason` is one of
**five**, because five distinct mechanisms stop an expansion and they mean different things to a
caller: `terminal` (a cross-KB neighbour, never expandable at any depth — decision 16), `depth` (the
hop limit), `fanout` (the `adjacent_k` cap), `rows` and `tokens` (the two response caps, which L3
already requires to be independently observable on `truncated`, so they cannot share one reason).
**Precedence when several apply is that order**, stated because it is otherwise the implementer's
choice: a cross-KB neighbour dropped by the fan-out cap reports `terminal`, since retrying with a
larger cap cannot help. A caller that cannot tell `fanout` from `terminal` retries a hop that can
never succeed.

This departs from APPROACH §5's `[{doc_id, rel}]` and from its "unexpanded **next hops**" wording — a
fan-out-dropped candidate is not a next hop — and carries an amendment row.

**`adjacent_k`** is a `[retrieval]` key, code default 8, documented — and **not stamped into the
`notes` template**, in this release or the next. `_toml.py` hard-errors on unknown keys, and
`requires_pinakes` (G4) **cannot help retroactively**: a pinakes built before G4 has no pre-pass and
fails on `requires_pinakes` itself. Deferring the stamp to G4 buys nothing, so the key stays
settable-but-unstamped until a release deliberately accepts the break.

**Tests.** `tests/test_traverse.py::test_depth_counts_logical_hops_not_physical_edges`;
`::test_fanout_keeps_the_highest_ranked_neighbours_not_the_first_k`;
`::test_ranking_without_a_query_uses_edge_weight_then_distance`;
`::test_ranking_with_a_query_uses_provider_supplied_similarity`;
`::test_a_frontier_entry_carries_the_reason_it_was_not_expanded` (five cases);
`::test_terminal_outranks_fanout_when_both_apply`;
`::test_a_cross_kb_neighbour_is_frontier_terminal_at_every_depth` — **its fixture must contain the
back-link rows that make the hop walkable** (a partner document with links targeting the local KB,
in both directions), or the test passes against an implementation with no suppression at all;
`::test_a_hub_is_expanded_once_globally`;
`::test_a_cycle_terminates`; `::test_unresolved_targets_survive_to_the_caller`;
`::test_the_token_budget_sets_truncated_independently_of_the_row_cap`.

**Exit criteria.** The traversal-cap gate in `check.sh` **and** its own CI job. Its predicate,
stated rather than left as a name: it drives the core with a caller asking for `depth=99` and
`adjacent_k=10_000` against a fixture graph, and fails if either exceeds the server cap or if
`truncated` is unset when a cap bit.
**Docs:** `docs/MANIFEST.md`, `docs/DESIGN.md` §2.1, `docs/STATUS.md`, a `changelog.d/` fragment.

**Mutation targets.** Rank-then-truncate ordering; the visited-edge set; the `unresolved`
accumulation; the depth comparison; the token-budget check; **the cross-KB suppression** — delete it
and the terminality test must fail, which it can only do against the back-link fixture above.

---

### L4 — The SQLite provider and `pnk links`

**What lands.** The provider — **a per-depth Python loop, one query per hop, never a recursive CTE**
— and a CLI surface, because DESIGN §8 settled that a slice queryable only over MCP does not reach
end to end.

```text
pnk links <doc> [--kb K] [--rel R] [--direction in|out|both] [--depth N] [--query Q] [--json]
```

`--depth` defaults to 1, server-capped at 3. `--kb` is DESIGN §8's required explicit KB argument,
defaulting to the configured KB.

**The neighbour shape**, amending APPROACH §5:

```text
{kb_id, doc_id, rel, direction, distance, score, terminal, title?}
```

**Every neighbour is a document** (decision 16). Tag, directory, heading and chunk nodes have no
`doc_id` and never appear here — they are internal to the expansion channel, in this release and
after it. That is what lets G3 add a whole structural graph without touching this contract, and it
is why there is no filter to flip later. `terminal` is true for a cross-KB neighbour, which is never
expandable at any depth.

**`kb_id` is the KB ULID, never a name or alias.** Three namespaces exist — `[kb] name` (documented
as free to rename), `[[links.kb]] name` (machine-local), and the ULID (canonical) — and only the
ULID is dereferenceable and portable, which is the same reason a `pnk://` URI carries no alias.
`title` is present for same-KB neighbours and **absent** for cross-KB ones, with a reason.

**Tests.** `tests/test_cli_links.py::test_every_neighbour_is_a_document`;
`::test_a_cross_kb_neighbour_is_marked_terminal`;
`::test_a_cross_kb_neighbour_carries_its_kb_ulid_and_no_title`;
`::test_kb_id_is_a_ulid_not_a_name`; `::test_a_same_kb_neighbour_carries_its_title`;
`::test_depth_beyond_the_cap_is_served_at_the_cap`; `::test_json_output_shape_is_pinned`;
`tests/test_traverse_provider.py::test_one_query_per_hop_not_a_recursive_cte`.

**Also lands.** `tests/free_path_run.py` gains `pnk links`; `tests/test_paid_path.py`'s **module**
list gains `pinakes.graph.traverse` and the provider — it enumerates modules, not commands.
`DESIGN_COMMANDS` and `IMPLEMENTED` in `tests/test_cli.py` gain `links`, and `docs/CLI.md:233`'s
Planned row is split so `pnk link` and `pinakes_links` stay listed.

**Docs:** `docs/CLI.md`, `docs/GUIDE.md` (a cross-KB walkthrough, every command run),
`docs/DESIGN.md` §8, `docs/STATUS.md`, the "🚫 Unbuilt work is named" table in **both** `CLAUDE.md` and `docs/STATUS.md` (the links-release
row in each gains `pnk links`; not the "Naming (fixed…)" table), a `changelog.d/` fragment.

**Mutation targets.** The `kb_id` field; the ULID-not-name selection; the depth clamp; the per-hop
loop replaced by one unbounded query.

---

### L5 — `pinakes_links`

**What lands.** APPROACH §5's contract on the MCP surface:
`pinakes_links(kb, doc_id, rel?, direction?, depth?=1, query?)`, `depth` server-capped at 3, no
query-language argument ever, **score and frontier on every return**, and the loop hints in the tool
description, labelled by origin.

**One boundary rule.** A neighbour is *reachable* iff its KB is one the **server was pointed at**
(`serve.py`'s roots) — a server-invocation property, not a manifest one. Unreachable neighbours
still return `kb_id`, `doc_id`, `rel` and a reason.

**Confidence is always `unknown`** (decision 17), amending APPROACH §5. Thresholds are fitted **per
KB** on the reranker score of the top *retrieved passage* for a golden-set query; a traversal
neighbour is not a retrieved passage, a cross-KB list has no single manifest whose thresholds apply,
and no fitted data for a traversal signal exists. Reporting `low`/`medium`/`high` here would be the
invented signal DESIGN §4.2 exists to forbid. Calibrating traversal needs its own fitted set and is
not in either release.

**Tests.** `tests/test_serve.py::test_the_tools_are_namespaced` (existing; its exact-set assertion
gains `pinakes_links`);
`::test_pinakes_links_reports_unknown_confidence_with_and_without_a_query`;
`::test_pinakes_links_returns_score_and_frontier_on_every_return`;
`::test_a_neighbour_outside_the_served_kbs_returns_its_kb_id_and_a_reason`;
`::test_pinakes_get_resolves_a_neighbour_returned_by_pinakes_links` (the test that makes "fetchable"
mean something); `::test_depth_is_capped_server_side`;
`::test_pinakes_search_and_get_payloads_are_unchanged`.

**Exit criteria.** `free_path_run.py`'s MCP handshake **invokes** `pinakes_links`; today it asserts
`if not tools` and never calls one.
**Docs:** `docs/CLI.md` (MCP tool table), `docs/GUIDE.md`, `docs/STATUS.md`, a `changelog.d/`
fragment.

**Mutation targets.** The unconditional `unknown`; the served-KB boundary check; the depth clamp.

---

### L6 — `pnk link`

**Blocked on a decision** with a stated default. Only L8's verification depends on it.

**What lands.** `pnk link <src> <dst> --rel <rel>`, writing one entry into the **source document's
sidecar only**, rename-atomically.

**`<dst>` grammar:** a path relative to the local KB root; `pnk://<kb-ulid>/<doc-ulid>`; or
`<alias>:<path>` where the alias is a `[[links.kb]]` name. Aliases and `self` resolve to ULIDs **on
write**. An unresolvable `<dst>` is refused with a typed error and a remedy.

**Per-link unknown keys round-trip.** `Link` is a two-field frozen dataclass; top-level unknown keys
survive via `extra`, per-link keys do not.

**Tests.** `tests/test_cli_link.py::test_an_alias_is_resolved_to_a_ulid_on_write`;
`::test_self_is_expanded_on_write`; `::test_each_dst_grammar_resolves`;
`::test_an_unresolvable_dst_is_refused_with_its_remedy`;
`::test_a_link_round_trips_through_sync_into_the_links_table`;
`::test_unknown_keys_inside_a_link_entry_survive_a_rewrite`;
`::test_the_write_is_atomic_under_an_interrupted_rename`;
`::test_the_source_document_is_byte_identical_afterwards`;
`::test_comments_in_the_sidecar_survive_a_rewrite` (xfail if the dependency is declined).

**Exit criteria.** `DESIGN_COMMANDS`, `IMPLEMENTED`, DESIGN §8's command list and CLAUDE.md's
`docs/`-ownership amendment all land here.
**Docs:** `docs/CLI.md`, `docs/GUIDE.md`, `docs/MANIFEST.md`, `docs/DESIGN.md` §2.2,
`docs/STATUS.md`, a `changelog.d/` fragment.

**Mutation targets.** The alias→ULID resolution; the per-link `extra` merge; the atomic rename.

---

### L7 — `pnk doctor`: link coverage and cross-KB resolution

**What lands.** `doctor.py`'s `"cross-KB (unchecked until the links release)"` becomes a real check.
Link coverage counts **authored links only** — the same population as L1's gate, so the number a
user reads and the number the gate enforces cannot differ. Highest-degree authored targets reported.
**Zero authored links KB-wide** is a WARN nudge — not a per-document count, which L1's ≤ 35% cap
guarantees would fire on both committed corpora by construction.

**Severity:** absent linked-KB path → WARN; a `pnk://` target absent from a KB that did resolve →
WARN with the count; a malformed `pnk://` in a committed sidecar → FAIL; an absolute
`[[links.kb]] path` → WARN.

**Tests.** `tests/test_doctor.py::test_link_coverage_counts_authored_links_only`;
`::test_a_dangling_cross_kb_target_warns_with_a_reason`; `::test_a_malformed_pnk_uri_fails`;
`::test_an_absolute_linked_kb_path_warns`; `::test_a_kb_with_no_authored_links_nudges`.

**Docs:** `docs/CLI.md` (doctor's checks), `docs/STATUS.md`, a `changelog.d/` fragment.

---

### L8 — Verification of the whole, and the links release cut

**Verification** — run, not reasoned about:

1. `./check.sh` green on all three CI legs; CI green on the merge.
2. A fresh KB works: `pnk init`, add a document, `pnk link` to a second KB, `pnk sync`, `pnk search`,
   `pnk links` — executed. (If L6 was deferred, the link is hand-authored and that is recorded.)
3. Every command in `docs/GUIDE.md` runs as written, install line included.
4. `.paid-path-allowlist` byte-identical; the free-path gate covers `pnk link`, `pnk links` and an
   MCP handshake that **invokes** `pinakes_links`.
5. `make eval` unchanged — this release touches no retrieval, so any movement is a defect.
6. **`store.SCHEMA_VERSION` is still 2.**
7. `pnk doctor` exits 0 on both corpora — "clean" means no FAIL; WARNs are expected, since the
   density cap guarantees most documents carry no authored link.
8. The ClaudeKB realism check is **run, or declined in writing**.

**The cut.** `python3 tools/fragments.py --apply` (splices `changelog.d/` and `retro.d/`, deleting
what it consumes — a release that skips it and runs it later splices into the wrong version), bump
`__version__`, move `[Unreleased]` into a dated section **and add its link definition at the foot,
repointing `[Unreleased]`'s compare** (`fragments.py --apply` splices entries and does not touch the
footer), commit, **merge from the primary checkout**,
push, `make release-check`, tag, push the tag, create the GitHub release. Then `git tag -l`,
`gh release list` and `git merge-base --is-ancestor` to verify it happened.
**Check `origin/main` for the number first** — 0.3.0 shipped mid-plan, and I8/I9 may cut another.

---

## Increments — the graph release

### G1 — Is the eval reproducible? (measure, then decide)

**Measure before fixing** — decision 15. The previous revision specified tiebreaks at three sites
and pass 3 showed they were a provable no-op: cross-document ties are already totalised by
`documents.path` (`UNIQUE`), and within a document rowid order *is* ordinal order in every write
path that exists (`replace_chunks` enumerates; the rebuild carry-over selects `ORDER BY ordinal`).
The instability a rebuild *could* introduce is upstream — in `_lexical`'s `ORDER BY score` and
`_vector`'s unstable `argsort`, which set the RRF ranks that determine the fused scores. A final
tiebreak cannot reach it.

**What lands.** A test that runs the golden set, edits a document, re-syncs, `--rebuild`s, and
compares **per-question outcomes** (not just aggregates), plus the same across two machines' CI legs.
If it is already reproducible, that is the finding and nothing else changes. If it is not, the fix
is scoped by what the measurement shows and lands here with per-class numbers.

**Tests.** `tests/test_search_reproducibility.py::test_outcomes_survive_an_incremental_sync_and_rebuild`;
`::test_outcomes_are_identical_across_repeated_runs`.

**Exit criteria.** The reproducibility gate in `check.sh` **and** its own CI job. A written statement
of what was measured, in `docs/STATUS.md`.
**Docs:** `docs/STATUS.md`, a `changelog.d/` fragment, and a `retro.d/` fragment if the measurement
contradicts the previous revision's assumptions.

---

### G2 — Per-question outcomes, the grown golden set, one re-baseline

**What lands, and why it is one increment.** G5's gate is an exact sign test, which needs
**per-question before/after pairs**. Nothing can produce them today: `run()` discards outcomes
(`metrics, _ = evaluate(...)`), `write_baseline` stores aggregates, and `compare()` reads only those.
So the artifact and the questions that populate it land together.

- **Per-question outcomes become a committed artifact** beside `baseline.json`: one row per question
  — id, kind, hit, hit_rank, confidence. **Questions have no id today**, so `questions.yaml` gains a
  stable `id` per entry in this increment; pairing before/after needs one and nothing else supplies
  it. This is what a sign test reads, and what makes "which
  questions flipped" answerable at all.
- **~18 single-KB multi-hop questions** (13 new), and **~20 `simple-lookup`**. **No cross-KB
  questions** (decision 14).
- `eval.py` **validates `kind`** against the known set instead of defaulting silently.
- The template's `eval/questions.yaml` is `questions: []`, which `eval.run` rejects outright, so a
  freshly `pnk init`ed KB fails `make eval` by construction. Fixed by making an empty set a
  **skip with a printed reason**, not an error — the template scaffolds an empty `docs/`, so it
  cannot ship questions naming documents that do not exist.

**The new questions must be failable**, authored from **corpus structure** — evidence genuinely split
across two documents with no shared vocabulary — not by probing what today's pipeline gets wrong.

**The headroom precondition, derived rather than asserted.** G5's gate needs, with *r* regressions,
*i* improvements: (0,5), (1,7), (2,9), (3,10). Improvements can only come from questions that
currently fail. So the corpus must supply at least **7** currently-failing single-KB multi-hop
questions to tolerate one regression, and 9 to tolerate two. The precondition is:

> **At least 7 of the ~18 single-KB multi-hop questions currently fail, AND at least 7 of those are
> channel-reachable** — both measured by running them.

**Failing is necessary and nowhere near sufficient**, which the previous revision missed. A question
can only be *lifted* if its evidence documents are connected in the derived edge set within ≤ 2
logical hops of the fused seeds. With `mentions`/`[ner]` cut (decision 6), every surviving
structural edge connects things already near each other — same document, directory or tag — and
APPROACH §3 names `mentions` as *"the one free edge class that bridges unrelated documents"*. So
this increment's own authoring rule ("no shared vocabulary") actively selects for pairs the
remaining edge set **cannot** bridge. You could pass a failure-count check with 18 questions of
which zero are reachable, bump `schema_version`, force every KB in existence to rebuild, and only
then discover the gate was unreachable.

APPROACH §9 already names the right instrument — the **channel-reachable ceiling** — and the
previous revision dropped it because it appeared in the `ppr` row. It comes back here, as an
**in-memory probe**: derive the edge set in memory from the committed corpora, with no schema change
and no rebuild, and report the share of multi-hop questions whose evidence lies within 2 logical
hops of the fused seeds, minus what the membership exclusion forbids — **computed twice, with and
without authored edges**, because a corpus reachable only through links its own author wrote cannot
tell you whether derived structure helps. That probe is throwaway
measurement code, not the G3 deriver, and it is what makes the stop/go sound.

All five committed multi-hop questions score 1.00, so every failure must come from the 13 new ones —
a 54% authored-failure rate, and **7 is the point at which the gate becomes conceivable, not the
point at which it has slack**: with exactly 7 failing, the one-regression branch requires all 7 to
flip.

**If the precondition does not hold, G3 does not start** — bumping `schema_version` and forcing every
KB in existence to rebuild, for an edge table whose channel could never be licensed, is the wrong
order.

**And then G1, G2 and G4 ship as a release on their own**, named at the cut. They stand alone: a
reproducibility measurement, a larger and better-instrumented golden set, and a manifest
forward-compatibility pre-pass. The project's rule is that complete self-contained work never
lingers in `[Unreleased]`, and "the graph release did not happen" is not a reason to strand three
finished increments. G6's verification then drops the *edge-dependent clauses* of steps 2, 3, 6 and 7 — the fresh-KB
end-to-end run in step 2 still happens, without the channel — and the release does not carry G6's
edge-hub reporting, which has nothing to report.

**The re-baseline.** Once, here, per-class before/after in the commit message, the previous
`baseline.json` preserved.

**Tests.** `tests/test_eval.py::test_the_committed_golden_set_is_well_formed` and
`::test_evaluating_the_demo_kb_produces_every_metric` gain `simple-lookup`;
`::test_per_question_outcomes_round_trip`; `::test_an_unknown_kind_is_refused`;
`::test_the_reachable_ceiling_probe_needs_no_index_schema_change`;
`::test_an_empty_question_set_skips_with_a_reason`;
`::test_the_committed_41_score_exactly_their_pre_growth_values` (over the preserved baseline).

**Docs:** `docs/DESIGN.md` §7 (including the "and with each template" clause, which the template's
committed `questions: []` has always falsified — the amendment records that a template ships no
golden set and says why), `src/pinakes/templates/notes/eval/questions.yaml` (its header enumerates
the kinds and goes stale the moment `kind` is validated), `docs/STATUS.md`, a `changelog.d/`
fragment.

---

### G3 — The node model and the edge set (`schema_version` 3)

**Precondition:** G2's headroom measurement passed.

**What lands.** APPROACH §3's node model — **chunk**, **document**, **tag**, **heading-path**
(scoped per document), **directory** — with every shared-value relation through its hub node.

**Node identity, specified because five node kinds span incompatible id spaces** and the previous
revision named a `nodes` table it never described. A node is `(kind, key)`:

| kind | key |
|---|---|
| `doc` | the document ULID |
| `chunk` | `<doc-ulid>:<ordinal>` — **not** `chunks.id`, which `store.py` says has no identity across rebuilds |
| `tag` | the tag string |
| `heading` | `<doc-ulid>:<heading_path>` — scoped per document, so no global "Introduction" hub exists |
| `dir` | the directory path relative to the KB root |

`nodes(id INTEGER PRIMARY KEY, kind TEXT, key TEXT, UNIQUE(kind, key))` mints surrogate ids;
`edges(src INTEGER, dst INTEGER, kind TEXT)` references them, indexed on **both** `src` and `dst`.

**Orientation, stated because the divisor depends on it.** A hub spoke is **one row** with the hub
always as `src`, so the damping divisor is well defined. The non-hub kinds are symmetric or
bidirectional and are also stored once, with an explicit rule: `sibling` as lower→higher ordinal,
`parent`/`child` as parent→child, `membership` as doc→chunk, **`authored` as the direction the
sidecar wrote it** (a reverse-scanned row keeps the foreign document as `src`, exactly as `links`
stores it). The provider therefore queries
`src = ? OR dst = ?` for those kinds and `src = ?` for hub kinds — the distinction is part of the
edge-kind table, not left to the implementer, because a `src`-only query silently drops half of
every symmetric relation.

**Damping at read.** The divisor is `SELECT count(*) FROM edges WHERE src = ? AND kind = ?` on an
indexed column, and it is well defined precisely because hub spokes always carry the hub as `src`.
No stored `degree` — that would be derived state inside derived state.

**Weights are frozen** (decision 13), committed before G2's questions were authored.

| Edge | Connects | Weight at read |
|---|---|---|
| membership | chunk ↔ doc | 1.0 — transit plumbing, not signal |
| `sibling` | chunk ↔ chunk (adjacent ordinal) | 1.0 |
| `parent` / `child` | chunk ↔ chunk (`heading_path` prefix) | 1.0 |
| `in-section` | chunk ↔ heading node (per-doc) | 1/section-size |
| `co-located` | doc ↔ directory node | 1/dir-size |
| `shared-tag` | doc ↔ tag node | 1/tag-degree |
| authored | doc ↔ doc | 2.0 — **read from `links`, not copied into `edges`**, so there is one home for an authored link and `pnk doctor`'s coverage number and the channel cannot disagree |

Composition across a hub is the **product of both spokes**.

**Authored edges are in the channel** — APPROACH §4A's whole argument for counting depth in logical
hops is that physical counting "would strand the highest-trust authored edges beyond depth 2", so
the channel traverses them. The previous revision left this unstated while three things depended on
it, and stating it exposes a circularity the plan has already refused once elsewhere: **G5's gate
could be satisfied by L1's hand-authored links bridging G2's hand-authored questions** — the same
"1.00 by construction" shape decision 14 used to cut cross-KB questions. The guard is in G2 and G5:
reachability and the gate are both reported **twice, with and without authored edges**, and a gate
that passes only *with* them is recorded as such rather than counted as evidence that structure
helps.

**Edge removal.** `documents.state='deleted'` is a soft delete: a soft-deleted document's edges are
removed and hub nodes reaching degree zero are reaped, so the channel can never surface deleted
content.

**The released traversal surface never sees these edges — not in G5, not later** (decision 16). Every
neighbour `pnk links` and `pinakes_links` return is a document; a tag, directory, heading or chunk
node has no `doc_id` and cannot be expressed in the shape L4 pins with a test. The structural graph
is read only by G5's channel. There is no filter to flip, no released payload to amend, and no
`--rel` flag spanning two vocabularies. This is what makes "inert" true rather than aspirational.

`schema_version` → **3**. Every KB rebuilds; no migration.

**Tests.** `tests/test_edges.py::test_a_shared_tag_produces_linear_not_quadratic_edges`;
`::test_a_hub_spoke_is_stored_once_not_twice`; `::test_a_heading_hub_never_connects_two_documents`;
`::test_sibling_edges_join_adjacent_ordinals`;
`::test_parent_and_child_follow_heading_path_prefixes`;
`::test_weight_across_a_hub_is_the_product_of_both_spokes`;
`::test_a_soft_deleted_document_leaves_no_edges`; `::test_a_dropped_tag_lowers_the_divisor`;
`::test_the_traversal_surface_returns_no_structural_nodes`;
`::test_a_symmetric_edge_is_reachable_from_both_ends`;
`::test_a_chunk_node_key_survives_a_rebuild`;
`::test_a_schema_version_2_index_is_refused_with_its_remedy`.

**Exit criteria.** `pnk links --json` on both corpora is byte-identical to a fixture **captured at
G2's HEAD and committed in this increment** — after the bump there is no pre-G3 index and no binary
that can read the new one, so the comparison is only executable against a stored artifact. Sync
wall-clock and edge counts reported for both corpora, and whether derivation is incremental or full
is decided here (`--sidecars-only`, the pre-commit hook, does **not** derive edges).
**Docs:** `docs/DESIGN.md` §3, `docs/STATUS.md`, a `changelog.d/` fragment.

**Mutation targets.** The divisor replaced by 1.0; the per-document scoping of heading nodes; the
one-row-per-spoke convention; the `src = ? OR dst = ?` orientation for symmetric kinds; the
soft-delete removal; the `schema_version` refusal.

---

### G4 — `requires_pinakes`

**What lands.** `[kb] requires_pinakes`, read in a **pre-pass before strict manifest validation**, so
a manifest from a newer pinakes can say so before the strict validator rejects its unknown keys.

**What it does not do.** It cannot explain a key retroactively: a pinakes built before this
increment has no pre-pass and fails on `requires_pinakes` itself. It only ever helps for keys added
*after* it ships — which is why `adjacent_k` and `graph_channel` stay out of the template in both
releases (L3), rather than being deferred to this increment as if it licensed them.

**Tests.** `tests/test_manifest_compat.py::test_a_manifest_requiring_a_newer_pinakes_names_the_version`;
`::test_the_pre_pass_runs_before_strict_validation`;
`::test_an_absent_requires_pinakes_is_not_an_error`.

**Exit criteria.** The floor is read from `pinakes.__version__`; G6 verifies the shipped message
names the released number.
**Docs:** `docs/MANIFEST.md`, `docs/DESIGN.md` §2.1, `docs/KB-UPDATES.md`, `docs/STATUS.md`, a
`changelog.d/` fragment.

**Mutation target.** The pre-pass ordering.

---

### G5 — The expansion channel, default off, and its gate

**What lands.** `[retrieval] graph_channel = "off" | "expand"`, default `"off"`. When `"expand"`: the
fused top-*k* as roots, expanded to depth ≤ 2, ranked, fed into RRF as a third input; an empty edge
set degrades to today's two-list fusion exactly. **No traversal surface changes** (decision 16): the
structural graph feeds the channel and nothing else, so `pnk links` and `pinakes_links` return
exactly what they returned in the links release.

Chunk neighbours rank by cosine; non-chunk nodes pass through by edge weight and contribute their
member chunks, **excluding same-document chunks reachable *only* through their own document's
membership edges** — excluded from the output **and from the fan-out budget**. A same-document chunk
also reachable by `sibling` or `in-section` is not excluded.

**One configuration is gated.** In-degree salience and the link-distance rerank are measured in the
same matrix and **reported**, not gated — three variables against one threshold is not a decision
procedure. The matrix runner, what it varies and where its results are recorded land here.

**The gate.** On the single-KB `multi-hop` class, at frozen weights, using G2's per-question
outcomes, `expand` defaults **on** only if all three hold:

1. The **exact one-sided sign test on discordant questions** gives p < 0.05:

   | regressed | improvements needed | net |
   |---|---|---|
   | 0 | 5 | 5 |
   | 1 | 7 | 6 |
   | 2 | 9 | 7 |
   | 3 | 10 | 7 |

2. No class regresses beyond `compare()`'s `tolerance=0.02` — which at these class sizes means "no
   class loses a question".
3. `false_abstain` does not rise **among questions that were already hits**. Its numerator requires a
   hit, so converting misses into low-confidence hits raises it — an unqualified clause would veto
   the win clause 1 demands.

   **`compare()` has no such carve-out, and it is a hard CI gate.** Five misses becoming hits, two
   of them at LOW confidence, is 2/66 = 0.030 against `tolerance=0.02` — CI red on a channel this
   gate just blessed. So **turning the channel on re-baselines in the same commit**, with the rise
   decomposed into "newly-found questions reported at low confidence" and "previously-found
   questions that lost confidence", and only the second treated as a regression. A second
   re-baseline is legitimate here precisely because a default was deliberately changed; G2's "once"
   applies to growing the set, not to shipping a new default.

4. **No other `compare()` metric may be absorbed silently by that re-baseline.** Rewriting
   `baseline.json` disarms every guard in it, and `false_confidence` is sensitive to the channel by
   the same mechanism as `false_abstain` — a third RRF input changes the top passage, which changes
   the calibrated confidence. It is **not** covered by clause 2, because `by_kind["no-answer"]` is
   hit-based: a no-answer question can stay a clean non-hit while flipping to HIGH. One flip is
   0.125 against a 0.02 tolerance. So `false_confidence` and `confidence_coverage` before/after go
   in `docs/STATUS.md` and the commit message, and a rise in either is a **stop**, not a
   re-baseline. This clause exists because the clause-3 remedy opened the hole it closes.

**Why the sign test, and why not "net".** Paired binary before/after on the same questions is
McNemar, whose exact form is the sign test on discordant pairs. "≥ 5 net" is a different quantity:
8 improved / 3 regressed is also net +5 and gives p = 0.113.

**The pre-commitment.** A result short of the table ships the channel **`off`**, with counts and
p-value recorded, untuned. Fitting afterwards is exploratory and cannot flip the gate without a newly
authored question set. And **a test asserts the channel does something**: with `"expand"` and a
non-empty edge set it must surface a document two-list fusion does not return — otherwise a channel
broken into returning nothing produces the same blessed outcome as one that honestly did not help.

**Tests.** `tests/test_graph_channel.py::test_expand_surfaces_a_document_fusion_alone_does_not`;
`::test_an_empty_edge_set_reproduces_two_list_fusion_exactly`;
`::test_off_issues_no_traversal_query`;
`::test_a_chunk_reachable_only_by_membership_never_appears`;
`::test_a_same_document_chunk_reachable_by_sibling_is_not_excluded`;
`::test_membership_neighbours_do_not_consume_the_fanout_budget`;
`::test_pnk_links_output_is_unchanged_with_the_channel_on`.

**Exit criteria.** Per-class before/after numbers and the gate's counts and p-value in the commit
message and `docs/STATUS.md`. Query-time latency reported with the channel on and off — the double
cap bounds response size, not time, and this runs on every query.
**Docs:** `docs/DESIGN.md` §4.1 and new §4.8, `docs/CLI.md`, `docs/MANIFEST.md`, `docs/STATUS.md`, a
`changelog.d/` fragment.

**Mutation targets.** The membership exclusion at both points; `graph_channel`'s default; the
empty-edge degradation path; the third-channel RRF contribution; the false-abstain decomposition.

---

### G6 — Edge-hub reporting, verification, and the graph release cut

**What lands.** `pnk doctor` reports the highest-degree structural edge hubs.

**Tests.** `tests/test_doctor.py::test_edge_hubs_are_reported_highest_degree_first`;
`::test_a_kb_with_no_edges_reports_none`.

**Verification** — run, not reasoned about:

1. `./check.sh` green on all three legs; CI green on the merge.
2. A fresh KB works end to end, including `pnk links` with the channel on and off.
3. **A `schema_version` 2 KB is refused with a remedy that works** — executed.
4. Every command in `docs/GUIDE.md` runs as written.
5. `.paid-path-allowlist` byte-identical; the free-path gate green on the full two-KB surface.
6. The gate's decision, counts and p-value recorded in `docs/STATUS.md`, whichever way it went.
7. Sync wall-clock, edge counts and query latency reported for both corpora.
8. `pnk doctor` clean on both.

**The cut.** As L8, beginning with `python3 tools/fragments.py --apply`.

**Docs:** `docs/CLI.md`, `docs/DESIGN.md` §8 (**both** graph-release rows reconciled),
`docs/STATUS.md`, a `changelog.d/` fragment.

---

## Verification — every promise has an owner

| Promise | Source | Owner | Checked by |
|---|---|---|---|
| Reverse links computed by scanning committed sidecars | DESIGN §6.2 | L2 | `test_rebuild_reconstructs_reverse_rows_from_sidecars_alone` |
| `kb_refs` records alias, path and scan time | DESIGN §3 | L2 | `test_kb_refs_records_alias_path_and_scan_time` |
| Stale reverse edges are removed on re-scan | DESIGN §6.2, amended | L2 | `test_a_removed_link_removes_its_reverse_row`, `test_the_delete_is_scoped_to_the_scanned_kb` |
| Each failure mode reported with a reason | DESIGN §6.2 | L2 | `test_each_failure_mode_is_recorded_with_its_reason` |
| Dangling cross-KB targets surfaced | DESIGN §6.2 | L7 | `test_a_dangling_cross_kb_target_warns_with_a_reason` |
| Link coverage reported as the ceiling | DESIGN §6.2 | L7 | `test_link_coverage_counts_authored_links_only` |
| The zero-link nudge | APPROACH §3 | L7 | `test_a_kb_with_no_authored_links_nudges` |
| Absolute linked-KB paths are a publication hazard | DESIGN §4.7 | L7 | `test_an_absolute_linked_kb_path_warns` |
| Aliases never inside a `pnk://` URI | DESIGN §2.2 | L6 | `test_an_alias_is_resolved_to_a_ulid_on_write` |
| Comment-preserving sidecar writer | DESIGN §2.2 | L6 | `test_comments_in_the_sidecar_survive_a_rewrite`, or an amended §2.2 |
| Unknown per-link keys round-trip | DESIGN §2.2 | L6 | `test_unknown_keys_inside_a_link_entry_survive_a_rewrite` |
| Sidecar writes are rename-atomic | v0.1 rule 12 | L6 | `test_the_write_is_atomic_under_an_interrupted_rename` |
| Server reaches only its configured KBs | DESIGN §4.7 | L5 | `test_a_neighbour_outside_the_served_kbs_returns_its_kb_id_and_a_reason` |
| Every tool takes an explicit `kb` | DESIGN §8 | L4, L5 | the CLI grammar and the tool signature |
| A neighbour is identifiable **and fetchable** | decision 11 | L5 | `test_pinakes_get_resolves_a_neighbour_returned_by_pinakes_links` |
| Typed verbs, hard caps, no query language | APPROACH §5 | L3, L5 | `test_depth_is_capped_server_side` |
| Score + frontier on every return | APPROACH §5 | L3 core, L5 surface | `test_pinakes_links_returns_score_and_frontier_on_every_return` |
| Double cap: rows **and** token budget | APPROACH §5 | L3 | `test_the_token_budget_sets_truncated_independently_of_the_row_cap` |
| Both ranking modes, with and without `query` | APPROACH §5 | L3 | two named tests |
| `confidence` is `unknown`, always | decision 17, amending APPROACH §5 | L5 | `test_pinakes_links_reports_unknown_confidence_with_and_without_a_query` |
| `unresolved` returned, never dropped | APPROACH §5, DESIGN §6.2 | L3 | `test_unresolved_targets_survive_to_the_caller` |
| Depth in logical hops | APPROACH §4A | L3 | `test_depth_counts_logical_hops_not_physical_edges` |
| Per-depth Python loop, not a recursive CTE | APPROACH §4A | L4 | `test_one_query_per_hop_not_a_recursive_cte` |
| Visited-edge dedup | APPROACH §4A | L3 | `test_a_hub_is_expanded_once_globally` |
| Membership excluded from output **and** budget | APPROACH §3 | G5 | three named tests |
| Hub damping on every shared-value hub | APPROACH §3 | G3 | `test_a_shared_tag_produces_linear_not_quadratic_edges` |
| One row per spoke | this plan | G3 | `test_a_hub_spoke_is_stored_once_not_twice` |
| Weight across a hub is the product of spokes | APPROACH §3 | G3 | `test_weight_across_a_hub_is_the_product_of_both_spokes` |
| Heading nodes scoped per document | APPROACH §3 | G3 | `test_a_heading_hub_never_connects_two_documents` |
| Hierarchy edges derived by prefix | APPROACH §3 | G3 | `test_parent_and_child_follow_heading_path_prefixes` |
| Edge-hub reporting | APPROACH §3 | G6 | `test_edge_hubs_are_reported_highest_degree_first` |
| Authored links are sparse | APPROACH §3 | L1 | the density gate and its negative tests |
| The eval is reproducible enough to gate on | decision 15 | G1 | `test_outcomes_survive_an_incremental_sync_and_rebuild` |
| Per-question outcomes exist as an artifact | this plan | G2 | `test_per_question_outcomes_round_trip` |
| The gate is reachable before the schema bumps | this plan | G2 | the headroom measurement |
| A template ships no golden set, and DESIGN §7 says so | DESIGN §7, amended | G2 | `test_an_empty_question_set_skips_with_a_reason` |
| `frontier` carries why a neighbour was not expanded | APPROACH §5 | L3 | `test_a_frontier_entry_carries_the_reason_it_was_not_expanded` |
| A cross-KB neighbour is terminal at any depth | decision 16 | L3, L4 | `test_a_cross_kb_neighbour_is_frontier_terminal_at_every_depth` |
| The traversal surface returns documents only | decision 16 | L4, G3 | `test_the_traversal_surface_returns_no_structural_nodes` |
| The channel-reachable ceiling is measured before the schema bumps | APPROACH §9 | G2 | the in-memory probe |
| In-degree salience and link-distance rerank evaluated | APPROACH §4A, §10 | G5 | the matrix runner and its recorded results |
| A channel regressing simple lookup stays off | APPROACH §9 | G5 | `compare()` plus gate clause 2 |
| Free path stays free | CLAUDE.md | L4, L5, L6 | the subprocess gate, extended per increment |
| No `schema_version` bump before the links release | this plan | L8 | verification step 6 |
| The ClaudeKB realism check happens or is declined | decision 1 | L8 | verification step 8 |

---

## Risks

| Risk | Why it is real | Mitigation |
|---|---|---|
| The synthetic corpus is unrealistically clean | One author writes the corpus, the links and the questions | Density and degree caps with negative tests; **frozen weights**; the ClaudeKB check, owned by L8 |
| The gate cannot be reached | Improvements come only from questions that both currently fail **and** are channel-reachable — and the authoring rule ("no shared vocabulary") selects against reachability once `mentions` is cut | G2 measures **both**, in memory, before G3 bumps the schema; if either fails, G3 does not start and G1/G2/G4 ship on their own |
| The gate is reached by chance | ~18 questions is a small sample | An exact test, one gated configuration, no post-hoc tuning |
| Frozen weights understate the channel | Unfitted priors may fail a gate tuned weights would pass | Pre-committed: fitting is exploratory and needs a new question set |
| A concurrent agent lands conflicting work | `main` moved fifteen commits and cut a release under three drafts | `shared_file_overlap.py --fetch --strict` before every merge, and read what it names |
| Reverse-scan on a hook is unbounded | `pnk sync` runs on three git hooks | TTL, `--scan-links`, and `--sidecars-only` does not scan |
| A reverse row overwrites an authored one | `origin` is not in the `links` PK | `ON CONFLICT DO NOTHING`, with a self-referencing fixture |
| Cross-KB reads race the other KB's sync | The advisory lock is per-KB | Never take the other lock; a torn read is a recorded reason |
| Edge derivation is slow at scale | It runs on every sync, on a hook path | Wall-clock and edge counts reported, as a G3 exit criterion |
| The channel is slow at query time | It runs on every query when on | Latency reported on and off, as a G5 exit criterion |
| A YAML dependency creeps in | DESIGN §2.2 assigns the writer; core deps stay light | Undecided, with a default that unblocks the chain |

---

## Iteration log

| When | What |
|---|---|
| 20260729 02:52 | Written. Seven decisions with the user; no adversarial pass |
| 20260729 03:31 | **Pass 1** — 22 HIGH. Three findings were live defects on `main`, fixed there first (`b637be4`, released in 0.3.0). Release split in two; `entities`/`concepts` cut |
| 20260729 04:05 | **Pass 2** — 26 HIGH. Six of pass 1's fixes were wrong, two self-refuting. Decisions 11–13 |
| 20260729 04:27 | **Pass 3** — 24 HIGH across two reviewers. Three collapsed into one root cause: **the links release never needed the golden set**, and forcing cross-KB questions through a structurally single-KB harness produced a class pinned at 0.00 or 1.00 by construction. Cross-KB eval cut entirely (decision 14); all eval work moved to the graph release; the determinism increment became a *measurement* after its proposed fix was shown to be a provable no-op (decision 15); the per-question artifact the sign test needs was found to exist nowhere and given an owner; twelve increments were still instructing a future agent to edit `CHANGELOG.md`, forbidden by a convention that landed while this plan was being written. **Pass 4 required** |
| 20260729 04:46 | **Pass 4** — two reviewers, **13 HIGH, down from 24**, and no self-refuting fixes for the first time. Five findings collapsed into decision 16: the traversal surface serves **documents only**, so structural nodes (which have no `doc_id`) never reach the pinned neighbour shape, G3 becomes genuinely inert, and G5 flips no filter. Cross-KB neighbours are terminal, and the Goal was a one-hop claim all along (the *reason* this pass gave was wrong — see 05:06). Also: `frontier` was contract text with no owner and no definition, now L3's with stated reasons; G5's clause 3 conflicted with `compare()`, a hard CI gate, so turning the channel on re-baselines in the same commit; the headroom precondition measured failure without reachability, and APPROACH §9's channel-reachable ceiling comes back as an in-memory probe; the node identity scheme spanned five incompatible id spaces and is now specified; and G1/G2/G4 have a stated fallback if the precondition fails. **Pass 5 required**, scoped to these seams |
| 20260729 05:06 | **Pass 5** — **3 HIGH, down from 13.** All three on the pass-4 seams. Decision 16's *conclusion* survived but its *premise* did not: the plan claimed K's index has nothing to walk past a cross-KB neighbour, and `store.py` says a reverse link's source lives in another KB — so the hop is walkable and terminality is a policy needing an explicit suppression, which no test or mutation target had. The real reason to stop is partiality, not emptiness, and the user reconfirmed on the corrected basis. Whether authored `doc ↔ doc` edges are in the channel was never stated while three things depended on it — they are, and stating it exposed a circularity (the gate satisfiable by hand-authored links bridging hand-authored questions) now guarded by reporting reachability and the gate with and without them. And the clause-3 remedy had disarmed `compare()`'s guard on `false_confidence`, which clause 4 restores. **Pass 6 required** |
