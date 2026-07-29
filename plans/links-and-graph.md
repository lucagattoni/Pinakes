# The links release and the graph release — implementation plan

**Status:** draft — revised after adversarial passes 1 (22 HIGH), 2 (26 HIGH) and 3 (24 HIGH, two
reviewers). **Not yet implementable.** Each pass has found real defects in the previous pass's
fixes; assume this revision has them too.

**Date:** written 20260729 02:52 · rewritten 03:31, 04:05, 04:27

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

**The links release changes no retrieval**, so no golden-set work is on its critical path. Pass 3
made this unavoidable: `eval.py` is structurally single-KB, and every attempt to score a cross-KB
question through it produced a class pinned at 0.00 or 1.00 by construction. Traversal correctness
is directly testable — does the traversal return the neighbour the corpus says it should — and that
is what the links release ships with. All eval work moves to the graph release, where it is the gate.

---

## Goal

A question answered in one KB can reach evidence in another, because a human said the two documents
were related and pinakes remembered — and the structure that makes traversal useful when nobody has
authored anything is derived for free afterwards, if and only if the golden set says it helps.

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
| 7 | Adversarial subagent passes until one comes back clean | 02:30–03:10 | Passes 1–3 done; **pass 4 required** |
| 8 | `pinakes_search`'s `entities`/`concepts` are cut | 03:20–03:35 | RRF here is unweighted by construction |
| 9 | The eval harness is repaired before it is grown | 03:20–03:35 | Landed `b637be4`, released in 0.3.0 |
| 10 | Retrieval reproducibility is established before a finer gate depends on it | 03:20–03:35 | G1 — **reframed by 15**: measured first, fixed only if measurement says so |
| 11 | Cross-KB neighbours carry no `title` | 04:00–04:05 | L4, L5 |
| 12 | The multi-hop class is majority single-KB | 04:00–04:05 | G2 — **superseded by 14** |
| 13 | G1's edge weights are frozen at APPROACH §3's priors | 04:00–04:05 | G3, G5 |
| 14 | **The golden set gains no cross-KB questions at all.** The multi-hop class stays single-KB, and cross-KB behaviour is verified by direct traversal tests instead | 04:27 (pass 3) | L1–L7, G2. `eval.py` is single-KB in its bones — one connection, one backend, `retrieved` as local paths. A cross-KB question scored through it is 0.00 by construction (the hop can never be followed) or 1.00 by construction (it merely confirms a link L1 hand-authored). Neither can decide anything, and pass 2 already established such questions cannot respond to `graph_channel` |
| 15 | **Ordering reproducibility is measured before anything is changed.** No tiebreak is specified in advance | 04:27 (pass 3) | G1. The three sites the previous revision proposed to fix are provably a no-op: cross-document ties are already totalised by `path`, and within a document rowid order *is* ordinal order in every write path that exists. The instability that a rebuild can introduce is upstream, in the candidate lists that set the RRF ranks, where no final tiebreak can reach it |

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
  state of anything it names. A clean auto-merge is not a correct merge. Nine of these increments
  touch `docs/DESIGN.md` or `docs/STATUS.md`.
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
- **Every retrieval change reports before/after per-class numbers.** Those increments are **G3 and
  G5** — G3 because the moment `edges` carries rows the L4 provider would serve them.

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
| §7 | The `simple-lookup` class; per-question outcomes are an artifact | G2 |
| §8 | Command list gains `link` and `links`; every tool takes an explicit `kb` | L4, L5, L6 |
| §8 | The links-release row moves to shipped | L8 |
| §8 | **Both** graph-release rows reconciled | G6 |

## APPROACH amendments

| § | Departure | Lands in |
|---|---|---|
| §5 | The neighbour shape gains `kb_id` and loses `title` for cross-KB neighbours | L4 |
| §3 | Weights are frozen, not fitted | G3 |
| §10 | Cross-KB golden-set questions are not built (decision 14) | G2 |

## CLAUDE.md amendments

| Rule | Amendment | Lands in |
|---|---|---|
| *"`docs/` belongs to the user … never any other key"* | A second, narrower exception: **a user-invoked authoring command** writing `links[]` to the source document's own sidecar | L6 |
| Naming table | Both release rows gain `pnk links` | L4 |

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

**The density gate** counts **sidecar-authored (forward) links only** and prints that it does; caps
**degree** at 4 per document as well as count; reports the cross-KB/intra-KB split and the relation
histogram.

**`[[links.kb]] path` resolution:** relative to the KB root, `~` expanded, absolute permitted but
**warned** by `pnk doctor` (L7) — this repo is public by rule and an absolute path in a committed
manifest publishes a filesystem layout. Non-existence is not an error.

**Tests.** `tests/test_partner_kb.py::test_both_corpora_load_and_validate`;
`::test_every_sidecar_ulid_is_wellformed_and_unique_across_both_kbs`;
`::test_a_corpus_over_the_density_cap_fails_the_gate`;
`::test_a_corpus_with_a_hub_document_fails_the_gate`;
`::test_the_gate_ignores_reverse_scan_rows`.

**Exit criteria.** `pnk sync` and `pnk doctor` clean on both; the gate in `check.sh` **and** its own
CI job. **Review step** (not a test): no PII, credentials or non-synthetic content.
**Docs:** `docs/MANIFEST.md`, `docs/DESIGN.md` §4.7, `docs/STATUS.md`, a `changelog.d/` fragment.

**Mutation targets.** The density comparison at its boundary; the degree cap; the `origin='sidecar'`
filter.

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

**Cost, because this runs on a hook.** Bounded by `kb_refs.last_scan` with a TTL, forced by
`--scan-links`. `--sidecars-only` (the pre-commit hook) does **not** scan; reverse rows are index
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
link distance, deterministically tie-broken on `(kb_id, doc_id)`.

**`adjacent_k`** is a `[retrieval]` key, code default 8, documented — and **not stamped into the
`notes` template**, in this release or the next. `_toml.py` hard-errors on unknown keys, and
`requires_pinakes` (G4) **cannot help retroactively**: a pinakes built before G4 has no pre-pass and
fails on `requires_pinakes` itself. Deferring the stamp to G4 buys nothing, so the key stays
settable-but-unstamped until a release deliberately accepts the break.

**Tests.** `tests/test_traverse.py::test_depth_counts_logical_hops_not_physical_edges`;
`::test_fanout_keeps_the_highest_ranked_neighbours_not_the_first_k`;
`::test_ranking_without_a_query_uses_edge_weight_then_distance`;
`::test_ranking_with_a_query_uses_similarity`; `::test_a_hub_is_expanded_once_globally`;
`::test_a_cycle_terminates`; `::test_unresolved_targets_survive_to_the_caller`;
`::test_the_token_budget_sets_truncated_independently_of_the_row_cap`.

**Exit criteria.** The traversal-cap gate in `check.sh` **and** its own CI job.
**Docs:** `docs/MANIFEST.md`, `docs/DESIGN.md` §2.1, `docs/STATUS.md`, a `changelog.d/` fragment.

**Mutation targets.** Rank-then-truncate ordering; the visited-edge set; the `unresolved`
accumulation; the depth comparison; the token-budget check.

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
{kb_id, doc_id, rel, direction, distance, score, title?}
```

**`kb_id` is the KB ULID, never a name or alias.** Three namespaces exist — `[kb] name` (documented
as free to rename), `[[links.kb]] name` (machine-local), and the ULID (canonical) — and only the
ULID is dereferenceable and portable, which is the same reason a `pnk://` URI carries no alias.
`title` is present for same-KB neighbours and **absent** for cross-KB ones, with a reason.

**Tests.** `tests/test_cli_links.py::test_a_cross_kb_neighbour_carries_its_kb_ulid_and_no_title`;
`::test_kb_id_is_a_ulid_not_a_name`; `::test_a_same_kb_neighbour_carries_its_title`;
`::test_depth_beyond_the_cap_is_served_at_the_cap`; `::test_json_output_shape_is_pinned`;
`tests/test_traverse_provider.py::test_one_query_per_hop_not_a_recursive_cte`.

**Also lands.** `tests/free_path_run.py` gains `pnk links`; `tests/test_paid_path.py`'s **module**
list gains `pinakes.graph.traverse` and the provider — it enumerates modules, not commands.
`DESIGN_COMMANDS` and `IMPLEMENTED` in `tests/test_cli.py` gain `links`, and `docs/CLI.md:233`'s
Planned row is split so `pnk link` and `pinakes_links` stay listed.

**Docs:** `docs/CLI.md`, `docs/GUIDE.md` (a cross-KB walkthrough, every command run),
`docs/DESIGN.md` §8, `docs/STATUS.md`, `CLAUDE.md` and `docs/STATUS.md`'s naming tables (both gain
`pnk links`), a `changelog.d/` fragment.

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

**Confidence.** `unknown` without `query`. **With `query`, `unknown` for any neighbour the server
cannot rerank** — the calibrated thresholds are fitted on reranker scores of retrieved passages, and
a neighbour whose text the server does not hold has no such score. The previous revision claimed the
same calibrated class unconditionally.

**Tests.** `tests/test_serve.py::test_the_tools_are_namespaced` (existing; its exact-set assertion
gains `pinakes_links`);
`::test_pinakes_links_reports_unknown_confidence_without_a_query`;
`::test_confidence_is_unknown_for_a_neighbour_that_cannot_be_reranked`;
`::test_pinakes_links_returns_score_and_frontier_on_every_return`;
`::test_a_neighbour_outside_the_served_kbs_returns_its_kb_id_and_a_reason`;
`::test_pinakes_get_resolves_a_neighbour_returned_by_pinakes_links` (the test that makes "fetchable"
mean something); `::test_depth_is_capped_server_side`;
`::test_pinakes_search_and_get_payloads_are_unchanged`.

**Exit criteria.** `free_path_run.py`'s MCP handshake **invokes** `pinakes_links`; today it asserts
`if not tools` and never calls one.
**Docs:** `docs/CLI.md` (MCP tool table), `docs/GUIDE.md`, `docs/STATUS.md`, a `changelog.d/`
fragment.

**Mutation targets.** The confidence branches; the served-KB boundary check; the depth clamp.

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
A zero-link document count is a **WARN** nudge with its own test.

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
7. `pnk doctor` clean on both corpora.
8. The ClaudeKB realism check is **run, or declined in writing**.

**The cut.** `python3 tools/fragments.py --apply` (splices `changelog.d/` and `retro.d/`, deleting
what it consumes — a release that skips it and runs it later splices into the wrong version), bump
`__version__`, move `[Unreleased]` into a dated section, commit, **merge from the primary checkout**,
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
  — id, kind, hit, hit_rank, confidence. This is what a sign test reads, and what makes "which
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

> **At least 7 of the ~18 single-KB multi-hop questions currently fail**, measured by running them.

The previous revision asserted 8 with no derivation and proposed to check it against a
number the author had committed — a test that cannot fail. This one runs the questions and counts.
All five committed multi-hop questions score 1.00, so every failure must come from the 13 new ones.

**If the precondition does not hold, G3 does not start.** Bumping `schema_version` and forcing every
KB in existence to rebuild, for an edge table whose channel could never be licensed, is the wrong
order.

**The re-baseline.** Once, here, per-class before/after in the commit message, the previous
`baseline.json` preserved.

**Tests.** `tests/test_eval.py::test_the_committed_golden_set_is_well_formed` and
`::test_evaluating_the_demo_kb_produces_every_metric` gain `simple-lookup`;
`::test_per_question_outcomes_round_trip`; `::test_an_unknown_kind_is_refused`;
`::test_an_empty_question_set_skips_with_a_reason`;
`::test_the_committed_41_score_exactly_their_pre_growth_values` (over the preserved baseline).

**Docs:** `docs/DESIGN.md` §7, `docs/STATUS.md`, a `changelog.d/` fragment.

---

### G3 — The node model and the edge set (`schema_version` 3)

**Precondition:** G2's headroom measurement passed.

**What lands.** APPROACH §3's node model — **chunk**, **document**, **tag**, **heading-path**
(scoped per document), **directory** — with every shared-value relation through its hub node.

**Storage convention, stated because it silently doubles every divisor if left implicit:** a hub
spoke is **one row**, not two directed rows. `edges(src, dst, kind)` with `kind` naming the relation;
hub membership is `(hub_node, member, kind)` exactly once.

**Damping at read.** The divisor is `SELECT count(*) FROM edges WHERE src = ? AND kind = ?` on an
indexed column — no stored `degree`, which would be derived state inside derived state.

**Weights are frozen** (decision 13), committed before G2's questions were authored.

| Edge | Connects | Weight at read |
|---|---|---|
| membership | chunk ↔ doc | 1.0 — transit plumbing, not signal |
| `sibling` | chunk ↔ chunk (adjacent ordinal) | 1.0 |
| `parent` / `child` | chunk ↔ chunk (`heading_path` prefix) | 1.0 |
| `in-section` | chunk ↔ heading node (per-doc) | 1/section-size |
| `co-located` | doc ↔ directory node | 1/dir-size |
| `shared-tag` | doc ↔ tag node | 1/tag-degree |
| authored | doc ↔ doc | 2.0 |

Composition across a hub is the **product of both spokes**.

**Edge removal.** `documents.state='deleted'` is a soft delete: a soft-deleted document's edges are
removed and hub nodes reaching degree zero are reaped, so the channel can never surface deleted
content.

**The provider stays authored-only until G5.** L4's provider and L5's tool read the same core, so
the moment `edges` carries structural rows they would start returning tag and directory neighbours
in a **released** surface. The filter is a provider argument, **and G5 is the increment that flips
it** — named there, tested there, and documented in `docs/CLI.md` there, because it changes the
output of a released command.

`schema_version` → **3**. Every KB rebuilds; no migration.

**Tests.** `tests/test_edges.py::test_a_shared_tag_produces_linear_not_quadratic_edges`;
`::test_a_hub_spoke_is_stored_once_not_twice`; `::test_a_heading_hub_never_connects_two_documents`;
`::test_sibling_edges_join_adjacent_ordinals`;
`::test_parent_and_child_follow_heading_path_prefixes`;
`::test_weight_across_a_hub_is_the_product_of_both_spokes`;
`::test_a_soft_deleted_document_leaves_no_edges`; `::test_a_dropped_tag_lowers_the_divisor`;
`::test_the_provider_serves_only_authored_edges_by_default`;
`::test_a_schema_version_2_index_is_refused_with_its_remedy`.

**Exit criteria.** `pnk links` output on both corpora is byte-identical to its pre-G3 output (this,
not the golden set, is what detects a leaking filter — the golden set never touches the provider).
Sync wall-clock and edge counts reported for both corpora.
**Docs:** `docs/DESIGN.md` §3, `docs/STATUS.md`, a `changelog.d/` fragment.

**Mutation targets.** The divisor replaced by 1.0; the per-document scoping of heading nodes; the
one-row-per-spoke convention; the authored-only filter; the soft-delete removal; the
`schema_version` refusal.

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
set degrades to today's two-list fusion exactly. **G3's provider filter is flipped here**, so
`pnk links` and `pinakes_links` begin serving structural neighbours — a change to released surfaces,
documented in `docs/CLI.md` in this commit.

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
   hit, so converting misses into low-confidence hits raises it — clause 3 would otherwise veto the
   win clause 1 demands.

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
`::test_pnk_links_serves_structural_neighbours_once_the_channel_is_on`.

**Exit criteria.** Per-class before/after numbers and the gate's counts and p-value in the commit
message and `docs/STATUS.md`. Query-time latency reported with the channel on and off — the double
cap bounds response size, not time, and this runs on every query.
**Docs:** `docs/DESIGN.md` §4.1 and new §4.8, `docs/CLI.md`, `docs/MANIFEST.md`, `docs/STATUS.md`, a
`changelog.d/` fragment.

**Mutation targets.** The membership exclusion at both points; `graph_channel`'s default; the
empty-edge degradation path; the third-channel RRF contribution; the provider filter flip.

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
| Score + frontier on every return | APPROACH §5 | L5 | `test_pinakes_links_returns_score_and_frontier_on_every_return` |
| Double cap: rows **and** token budget | APPROACH §5 | L3 | `test_the_token_budget_sets_truncated_independently_of_the_row_cap` |
| Both ranking modes, with and without `query` | APPROACH §5 | L3 | two named tests |
| `confidence` unknown without `query`, and when unrerankable | APPROACH §5 | L5 | two named tests |
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
| The golden set lives with each template too | DESIGN §7 | G2 | `test_an_empty_question_set_skips_with_a_reason` |
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
| The gate cannot be reached | Improvements can only come from currently-failing questions | G2's headroom measurement, **before** G3 bumps the schema |
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
